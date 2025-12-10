# -*- coding: utf-8 -*-
import os
import re
import tempfile
import concurrent.futures
import time
from config import ADB_PATH, PKG_CALENDAR, PKG_TASKS, PKG_EXPENSE, PKG_MARKOR, PKG_CONTACTS, PKG_TELEPHONY, PKG_CONTACTS_STORAGE
from utils import setup_logger, run_adb
from modules.system import clean_background_apps, go_home
from modules.wizards import init_markor, init_expense, init_tasks

# 引入各注入模块
from modules.injector import inject_calendar, inject_media_files
from modules.inject_tasks import inject_tasks_db
from modules.inject_expense import inject_expense_db
from modules.inject_markor import inject_markor_files
from modules.inject_system import inject_contacts, inject_sms_msg # 确保使用 V10 版本

def find_devices():
    import subprocess
    res = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True)
    devices = []
    if res.stdout:
        for line in res.stdout.splitlines()[1:]:
            if "device" in line: # 移除 emulator 限制，允许真机
                match = re.match(r"(\S+)\s+device", line)
                if match: devices.append(match.group(1))
    return devices

def process_device_pipeline(device_id):
    # 1. 设置主 Logger
    logger = setup_logger(device_id, "system")
    logger.info(f"========== 开始处理设备 {device_id} ==========")
    
    run_adb(device_id, ["root"], logger=logger)
    
    # 2. 环境清理
    logger.info("--- 步骤 1: 清理环境 ---")
    clean_background_apps(device_id, logger, exclude_pkgs=[])

    time.sleep(2)
    
    # 3. 初始化应用 (生成基础文件/DB)
    logger.info("--- 步骤 2: 初始化应用 (Wizard Skipping) ---")
    
    # 实例化 Logger 用于各 App
    log_cal = setup_logger(device_id, "calendar")
    log_task = setup_logger(device_id, "tasks")
    log_exp = setup_logger(device_id, "expense")
    log_markor = setup_logger(device_id, "markor")
    log_sys = setup_logger(device_id, "system_data")
    
    # 执行初始化点击逻辑 (Warm-up)
    init_markor(device_id, log_markor)
    init_expense(device_id, log_exp)
    init_tasks(device_id, log_task)
    
    # 4. 注入数据
    with tempfile.TemporaryDirectory() as temp_dir:
        logger.info("--- 步骤 3: 注入数据 ---")
        
        # Calendar
        inject_calendar(device_id, temp_dir, log_cal)
        
        # Tasks
        inject_tasks_db(device_id, temp_dir, log_task)
        
        # Expense
        inject_expense_db(device_id, temp_dir, log_exp)
        
        # Markor
        inject_markor_files(device_id, temp_dir, log_markor)
        
        # System (Files, SMS, Contacts)
        inject_media_files(device_id, temp_dir, log_sys)
        inject_contacts(device_id, log_sys)
        
        # [关键修复] 补全参数：需要传入 temp_dir 以便处理 SQLite 文件
        inject_sms_msg(device_id, temp_dir, log_sys)
        
    # 5. 收尾
    logger.info("--- 步骤 4: 收尾 ---")
    go_home(device_id, logger)
    
    # [关键配置] 保护系统数据不被清理
    exclude_list = [
        PKG_CALENDAR, 
        PKG_TASKS, 
        PKG_EXPENSE, 
        PKG_MARKOR, 
        PKG_CONTACTS,         # 联系人 UI
        PKG_TELEPHONY,        # 短信数据库 (必须保留)
        PKG_CONTACTS_STORAGE, # 联系人数据库 (必须保留)
        "com.google.android.apps.messaging",
        "com.android.phone"   # 电话服务 (建议保留)
    ]
    
    clean_background_apps(device_id, logger, exclude_pkgs=exclude_list)
    
    logger.info("========== 设备处理完成 ==========")

def main():
    if not os.path.exists(ADB_PATH): 
        print("ADB Path Error")
        return
    devices = find_devices()
    print(f"Detected Devices: {devices}")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(devices)) as executor:
        # 使用 map 会导致异常在迭代时才抛出，如果您希望看到报错，可以考虑 wrap 一下
        try:
            results = executor.map(process_device_pipeline, devices)
            for _ in results: pass # 触发迭代以抛出潜在异常
        except Exception as e:
            print(f"Pipeline Execution Error: {e}")

if __name__ == "__main__":
    main()