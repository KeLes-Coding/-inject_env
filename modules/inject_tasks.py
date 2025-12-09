# -*- coding: utf-8 -*-
import os
import sqlite3
import time
import shutil
from utils import run_adb
from config import PKG_TASKS, DB_TASKS_PATH
from modules.wizards import init_tasks

def verify_table_exists(db_path, table_name, logger):
    if not os.path.exists(db_path): return False
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        cnt = cursor.fetchone()[0]
        conn.close()
        return cnt > 0
    except Exception:
        return False

def inject_tasks_db(device_id, temp_dir, logger):
    logger.info(">>> 注入 Tasks (Org.Tasks) 数据 <<<")
    
    local_db_dir = os.path.join(temp_dir, f"tasks_dir_{device_id}")
    if os.path.exists(local_db_dir): shutil.rmtree(local_db_dir)
    os.makedirs(local_db_dir, exist_ok=True)
    
    remote_db_dir = os.path.dirname(DB_TASKS_PATH)
    
    run_adb(device_id, ["shell", "am", "force-stop", PKG_TASKS], logger=logger)
    run_adb(device_id, ["pull", remote_db_dir, local_db_dir], logger=logger)
    
    local_db_file = None
    for root, dirs, files in os.walk(local_db_dir):
        if "database" in files:
            local_db_file = os.path.join(root, "database")
            break
    
    if not local_db_file or not verify_table_exists(local_db_file, "tasks", logger):
        logger.warning("Tasks DB 无效，执行 Wizard...")
        init_tasks(device_id, logger)
        run_adb(device_id, ["shell", "am", "force-stop", PKG_TASKS], logger=logger)
        if os.path.exists(local_db_dir): shutil.rmtree(local_db_dir)
        os.makedirs(local_db_dir, exist_ok=True)
        run_adb(device_id, ["pull", remote_db_dir, local_db_dir], logger=logger)
        
        local_db_file = None
        for root, dirs, files in os.walk(local_db_dir):
            if "database" in files:
                local_db_file = os.path.join(root, "database")
                break

        if not local_db_file:
            logger.error("Tasks 初始化失败")
            return False

    try:
        conn = sqlite3.connect(local_db_file)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=DELETE;")
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
        
        # [修复] 添加了 deleted 字段 (在 completed 后面)
        sql = """INSERT INTO tasks (title, importance, dueDate, notes, completed, deleted, created, modified, hideUntil, estimatedSeconds, elapsedSeconds, timerStart, notificationFlags, lastNotified, recurrence, repeat_from, collapsed, parent, "order", read_only) VALUES (?, ?, ?, ?, ?, 0, ?, ?, 0, 0, 0, 0, 0, 0, '', 0, 0, 0, 0, 0)"""
        
        for item in tasks_data:
            # item 结构: title, importance, dueDate, notes, completed
            # 参数顺序: title, imp, due, note, completed, created, modified
            cursor.execute(sql, (item[0], item[1], item[2], item[3], item[4], now_ms, now_ms))
            
        conn.commit()
        conn.close()
        
        run_adb(device_id, ["shell", f"rm -f {DB_TASKS_PATH}-wal {DB_TASKS_PATH}-shm"], logger=logger)
        temp_remote = "/data/local/tmp/tasks_inject.db"
        run_adb(device_id, ["push", local_db_file, temp_remote], logger=logger)
        run_adb(device_id, ["shell", f"cat {temp_remote} > {DB_TASKS_PATH}"], logger=logger)
        run_adb(device_id, ["shell", f"rm {temp_remote}"], logger=logger)
        
        uid_out, _ = run_adb(device_id, ["shell", f"dumpsys package {PKG_TASKS} | grep userId"], logger=logger)
        if uid_out:
            import re
            m = re.search(r"userId=(\d+)", uid_out)
            if m:
                uid = m.group(1)
                run_adb(device_id, ["shell", f"chown {uid}:{uid} {DB_TASKS_PATH}"], logger=logger)

        logger.info("Tasks 数据注入完成。")
        return True

    except Exception as e:
        logger.error(f"Tasks 注入异常: {e}", exc_info=True)
        return False