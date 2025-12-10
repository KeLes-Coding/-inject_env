# -*- coding: utf-8 -*-
import os
import sqlite3
import time
import shutil
from utils import run_adb, load_json_data
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
    
    # 加载配置
    expenses_data = load_json_data("expense.json")
    if not expenses_data:
        logger.error("无 Expense 数据，跳过注入。")
        return False

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
        
        sql = "INSERT INTO expense (name, amount, category, note, created_date, modified_date) VALUES (?, ?, ?, ?, ?, ?)"
        
        for item in expenses_data:
            name = item.get("name")
            amt = item.get("amount")
            cat = item.get("category")
            note = item.get("note", "")
            date = item.get("date")
            
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
                
        logger.info(f"Expense 数据注入完成 ({len(expenses_data)} 条)。")
        return True
        
    except Exception as e:
        logger.error(f"Expense 注入异常: {e}", exc_info=True)
        return False