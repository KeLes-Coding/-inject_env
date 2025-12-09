# -*- coding: utf-8 -*-
import os
import sqlite3
import time
from utils import run_adb
from config import PKG_EXPENSE, DB_EXPENSE_PATH
from modules.wizards import init_expense # 引用修复逻辑

def verify_table_exists(db_path, table_name, logger):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        exists = cursor.fetchone()[0] > 0
        conn.close()
        return exists
    except Exception as e:
        return False

def inject_expense_db(device_id, temp_dir, logger):
    logger.info(">>> 注入 Expense (Pro Expense) 数据 <<<")
    
    local_db_path = os.path.join(temp_dir, f"expense_{device_id}.db")
    run_adb(device_id, ["shell", "am", "force-stop", PKG_EXPENSE], logger=logger)
    
    run_adb(device_id, ["pull", DB_EXPENSE_PATH, local_db_path], logger=logger)
    
    # 检查 DB 有效性
    if not os.path.exists(local_db_path) or not verify_table_exists(local_db_path, "expense", logger):
        logger.warning("Expense 数据库表不存在，尝试重新执行初始化向导...")
        init_expense(device_id, logger)
        run_adb(device_id, ["shell", "am", "force-stop", PKG_EXPENSE], logger=logger)
        run_adb(device_id, ["pull", DB_EXPENSE_PATH, local_db_path], logger=logger)
        
        if not verify_table_exists(local_db_path, "expense", logger):
            logger.error("Expense 初始化依然失败，跳过注入。")
            return False
        
    try:
        conn = sqlite3.connect(local_db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM expense")
        
        ts_oct = 1759276800000 
        ts_nov = 1761955200000 
        
        expenses = [
            ("Coffee", 550, 1, "Nice coffee", ts_oct),
            ("Uber Ride", 5000, 2, "To Office", ts_oct + 86400000), 
            ("Fancy Dinner", 12000, 1, "Treat", ts_nov),
        ]
        
        sql = "INSERT INTO expense (name, amount, category, note, created_date, modified_date) VALUES (?, ?, ?, ?, ?, ?)"
        
        for name, amt, cat, note, date in expenses:
            cursor.execute(sql, (name, amt, cat, note, date, date))
            
        conn.commit()
        conn.close()
        
        run_adb(device_id, ["shell", f"rm {DB_EXPENSE_PATH}-wal {DB_EXPENSE_PATH}-shm"], logger=logger)
        temp_remote = "/data/local/tmp/expense_inject.db"
        run_adb(device_id, ["push", local_db_path, temp_remote], logger=logger)
        run_adb(device_id, ["shell", f"cat {temp_remote} > {DB_EXPENSE_PATH}"], logger=logger)
        run_adb(device_id, ["shell", f"rm {temp_remote}"], logger=logger)
        
        logger.info("Expense 数据注入完成。")
        return True
        
    except Exception as e:
        logger.error(f"Expense 注入失败: {e}")
        return False