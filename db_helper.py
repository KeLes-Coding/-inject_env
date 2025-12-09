# -*- coding: utf-8 -*-
import sqlite3
import time

class CalendarDBHelper:
    def __init__(self, db_path, logger):
        self.db_path = db_path
        self.logger = logger

    def inject_data(self):
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            self.logger.info("正在处理本地数据库...")

            # 1. 强制合并 WAL (防止推送后数据回滚或损坏)
            cursor.execute("PRAGMA journal_mode=DELETE;")
            conn.commit()

            # 2. 补全 event_types (防止新安装设备打开详情闪退)
            # 检查 event_types 表是否为空
            cursor.execute("SELECT count(*) FROM event_types")
            if cursor.fetchone()[0] == 0:
                self.logger.info("补全 event_types 表 (插入默认分类)...")
                # 插入默认分类 ID=1
                try:
                    cursor.execute("""
                        INSERT INTO event_types (id, title, color, type, caldav_calendar_id, caldav_display_name, caldav_email)
                        VALUES (1, 'Regular', -11823966, 0, 0, '', '')
                    """)
                except Exception as e:
                    self.logger.warning(f"插入 event_types 警告: {e}")

            # 3. 获取 events 表的实际列结构 (动态修复的核心)
            cursor.execute("PRAGMA table_info(events)")
            columns_info = cursor.fetchall()
            # 提取数据库中真实存在的列名列表
            valid_columns_in_db = [info['name'] for info in columns_info]
            
            self.logger.debug(f"数据库实际列结构: {valid_columns_in_db}")
            
            if not valid_columns_in_db:
                self.logger.error("无法读取 events 表结构，数据库可能损坏")
                return False

            # 4. 准备全量数据字典 (包含所有我们想填的字段，不管数据库有没有)
            current_time = int(time.time())
            
            # 定义基础数据
            base_data_map = {
                'event_type': 1,              # 必须对应 event_types 表中的 id
                'last_updated': current_time,
                'source': 'imported-ics',
                'repeat_interval': 0,
                'repeat_rule': 0,
                'reminder_1_minutes': -1,
                'reminder_2_minutes': -1,
                'reminder_3_minutes': -1,
                'reminder_1_type': 0,
                'reminder_2_type': 0,
                'reminder_3_type': 0,
                'repeat_limit': 0,
                'repetition_exceptions': '[]',
                'attendees': '',
                'time_zone': 'Asia/Shanghai',
                'availability': 0,
                'color': 0,
                'import_id': '0',
                'flags': 0,
                'type': 0,
                'parent_id': 0,
                # 'display_event_type': 1 # 已移除，因为你的表结构里没有
            }

            # 待插入的具体事件
            events_list = [
                (1760508000, "Project Review", "Review Phase 1", "Office"),
                (1762828800, "Dentist Appointment", "Checkup", "Clinic"),
                (1764561600, "Team Lunch", "Monthly Gathering", "Pizza Hut"),
                (1747708800, "Dad's Birthday", "Buy gift", "Home"),
                (1749264000, "Exam", "Room 303", "School"),
            ]

            # 5. 构建动态 SQL 语句
            # 找出 (我们想插的数据) 和 (数据库实际有的列) 的交集
            # 假设 base_data_map 的 key 加上 start_ts, end_ts, title... 是全集
            
            # 先清空旧数据
            cursor.execute("DELETE FROM events")

            for start_ts, title, desc, loc in events_list:
                # 构建这一行的完整数据字典
                row_data = base_data_map.copy()
                row_data['start_ts'] = start_ts
                row_data['end_ts'] = start_ts + 3600
                row_data['title'] = title
                row_data['description'] = desc
                row_data['location'] = loc
                
                # 筛选：只保留数据库中存在的 key
                final_keys = [k for k in row_data.keys() if k in valid_columns_in_db]
                final_values = [row_data[k] for k in final_keys]
                
                placeholders = ",".join(["?"] * len(final_keys))
                sql = f"INSERT INTO events ({','.join(final_keys)}) VALUES ({placeholders})"
                
                cursor.execute(sql, final_values)

            conn.commit()
            self.logger.info(f"成功注入 {len(events_list)} 条事件 (动态匹配列)")
            return True

        except Exception as e:
            self.logger.error(f"SQL执行致命错误: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return False
        finally:
            if conn: conn.close()