# -*- coding: utf-8 -*-
import os
import sqlite3
import time
import shutil
from utils import run_adb
from config import PKG_EXPENSE, DB_EXPENSE_PATH
from modules.wizards import init_expense

def verify_table_exists(db_path, table_name, logger):
    if not os.path.exists(db_path):
        return False
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        cnt = cursor.fetchone()[0]
        conn.close()
        return cnt > 0
    except Exception as e:
        logger.error(f"Check DB Error: {e}")
        return False

def inject_expense_db(device_id, temp_dir, logger):
    logger.info(">>> 注入 Expense (Pro Expense) 数据 <<<")
    
    local_db_dir = os.path.join(temp_dir, f"expense_dir_{device_id}")
    if os.path.exists(local_db_dir): shutil.rmtree(local_db_dir)
    os.makedirs(local_db_dir, exist_ok=True)
    
    remote_db_dir = os.path.dirname(DB_EXPENSE_PATH)

    run_adb(device_id, ["shell", "am", "force-stop", PKG_EXPENSE], logger=logger)
    run_adb(device_id, ["pull", remote_db_dir, local_db_dir], logger=logger)
    
    local_db_file = None
    for root, dirs, files in os.walk(local_db_dir):
        if "accounting.db" in files:
            local_db_file = os.path.join(root, "accounting.db")
            break
            
    if not local_db_file or not verify_table_exists(local_db_file, "expense", logger):
        logger.warning("Expense DB 不完整，重试 Wizard...")
        init_expense(device_id, logger)
        run_adb(device_id, ["shell", "am", "force-stop", PKG_EXPENSE], logger=logger)
        if os.path.exists(local_db_dir): shutil.rmtree(local_db_dir)
        os.makedirs(local_db_dir, exist_ok=True)
        run_adb(device_id, ["pull", remote_db_dir, local_db_dir], logger=logger)
        
        local_db_file = None
        for root, dirs, files in os.walk(local_db_dir):
            if "accounting.db" in files:
                local_db_file = os.path.join(root, "accounting.db")
                break
        
        if not local_db_file or not verify_table_exists(local_db_file, "expense", logger):
            logger.error("Expense 初始化失败，跳过。")
            return False
        
    try:
        conn = sqlite3.connect(local_db_file)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=DELETE;")
        cursor.execute("DELETE FROM expense")
        
        ts_oct = 1759276800000 
        ts_nov = 1761955200000 
        
        # 定义数据 (5个元素)
        expenses_data = [
            ("Coffee", 550, 1, "Nice coffee", ts_oct),
            ("Uber Ride", 5000, 2, "To Office", ts_oct + 86400000), 
            ("Fancy Dinner", 12000, 1, "Treat", ts_nov),
        ]
        
        # SQL 需要 6 个参数 (created_date, modified_date)
        sql = "INSERT INTO expense (name, amount, category, note, created_date, modified_date) VALUES (?, ?, ?, ?, ?, ?)"
        
        for name, amt, cat, note, date in expenses_data:
            # 修正：手动构造 6 元素元组，将 date 重复一次作为 modified_date
            cursor.execute(sql, (name, amt, cat, note, date, date))
            
        conn.commit()
        conn.close()
        
        run_adb(device_id, ["shell", f"rm -f {DB_EXPENSE_PATH}-wal {DB_EXPENSE_PATH}-shm"], logger=logger)
        temp_remote = "/data/local/tmp/expense_inject.db"
        run_adb(device_id, ["push", local_db_file, temp_remote], logger=logger)
        run_adb(device_id, ["shell", f"cat {temp_remote} > {DB_EXPENSE_PATH}"], logger=logger)
        run_adb(device_id, ["shell", f"rm {temp_remote}"], logger=logger)
        
        uid_out, _ = run_adb(device_id, ["shell", f"dumpsys package {PKG_EXPENSE} | grep userId"], logger=logger)
        if uid_out:
            import re
            m = re.search(r"userId=(\d+)", uid_out)
            if m:
                uid = m.group(1)
                run_adb(device_id, ["shell", f"chown {uid}:{uid} {DB_EXPENSE_PATH}"], logger=logger)
                
        logger.info("Expense 数据注入完成。")
        return True
        
    except Exception as e:
        logger.error(f"Expense 注入异常: {e}", exc_info=True)
        return False