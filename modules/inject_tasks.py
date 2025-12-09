# -*- coding: utf-8 -*-
import os
import sqlite3
import time
from utils import run_adb
from config import PKG_TASKS, DB_TASKS_PATH
from modules.wizards import init_tasks # 引用修复逻辑

def verify_table_exists(db_path, table_name, logger):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        exists = cursor.fetchone()[0] > 0
        conn.close()
        return exists
    except Exception as e:
        logger.error(f"DB Check Error: {e}")
        return False

def inject_tasks_db(device_id, temp_dir, logger):
    logger.info(">>> 注入 Tasks (Org.Tasks) 数据 <<<")
    
    local_db_path = os.path.join(temp_dir, f"tasks_{device_id}.db")
    run_adb(device_id, ["shell", "am", "force-stop", PKG_TASKS], logger=logger)
    
    # 1. 拉取
    run_adb(device_id, ["pull", DB_TASKS_PATH, local_db_path], logger=logger)
    
    # 2. 检查 DB 是否有效 (表是否存在)
    if not os.path.exists(local_db_path) or not verify_table_exists(local_db_path, "tasks", logger):
        logger.warning("Tasks 数据库表不存在，尝试重新执行初始化向导...")
        init_tasks(device_id, logger)
        # 再次拉取
        run_adb(device_id, ["shell", "am", "force-stop", PKG_TASKS], logger=logger)
        run_adb(device_id, ["pull", DB_TASKS_PATH, local_db_path], logger=logger)
        
        if not verify_table_exists(local_db_path, "tasks", logger):
            logger.error("Tasks 初始化依然失败，跳过注入。")
            return False

    try:
        conn = sqlite3.connect(local_db_path)
        cursor = conn.cursor()
        
        # 清理旧数据
        cursor.execute("DELETE FROM tasks")
        
        now_ms = int(time.time() * 1000)
        
        tasks_data = [
            ("Buy Groceries", 2, 0, "", 0), 
            ("Send Christmas Cards", 0, 1766620800000, "", 0),
            ("Car Service", 0, 0, "Mileage: 50000km", 0),
            ("Submit Final Report", 0, 1761782400000, "", 0),
            ("Old Task 1", 0, 0, "", now_ms - 86400000),
            ("Old Task 2", 0, 0, "", now_ms - 172800000),
            ("Old Task 3", 0, 0, "", now_ms - 259200000),
        ]

        sql = """
        INSERT INTO tasks (
            title, importance, dueDate, notes, completed, 
            created, modified, hideUntil, estimatedSeconds, elapsedSeconds, 
            timerStart, notificationFlags, lastNotified, recurrence, repeat_from, 
            collapsed, parent, order, read_only
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, '', 0, 0, 0, 0, 0)
        """
        
        for item in tasks_data:
            title, imp, due, note, completed = item
            cursor.execute(sql, (title, imp, due, note, completed, now_ms, now_ms))

        conn.commit()
        conn.close()
        
        # 3. 推送
        run_adb(device_id, ["shell", f"rm {DB_TASKS_PATH}-wal {DB_TASKS_PATH}-shm"], logger=logger)
        temp_remote = "/data/local/tmp/tasks_inject.db"
        run_adb(device_id, ["push", local_db_path, temp_remote], logger=logger)
        run_adb(device_id, ["shell", f"cat {temp_remote} > {DB_TASKS_PATH}"], logger=logger)
        run_adb(device_id, ["shell", f"rm {temp_remote}"], logger=logger)
        
        logger.info("Tasks 数据注入完成。")
        return True

    except Exception as e:
        logger.error(f"Tasks 注入失败: {e}")
        return False