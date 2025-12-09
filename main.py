# -*- coding: utf-8 -*-
import os
import re
import tempfile
import concurrent.futures
import time
from config import ADB_PATH, PKG_CALENDAR, PKG_TASKS, PKG_EXPENSE, PKG_MARKOR
from utils import setup_logger, run_adb
from modules.system import clean_background_apps, go_home
from modules.wizards import init_markor, init_expense

# 引入各注入模块
from modules.injector import inject_calendar, inject_media_files # 假设你把旧的 calendar 逻辑留在这里或独立文件
from modules.inject_tasks import inject_tasks_db
from modules.inject_expense import inject_expense_db
from modules.inject_markor import inject_markor_files
from modules.inject_system import inject_contacts, inject_sms_msg
from modules.wizards import init_tasks

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
    
    # 3. 初始化应用 (生成基础文件/DB)
    logger.info("--- 步骤 2: 初始化应用 (Wizard Skipping) ---")
    
    # 实例化 Logger 用于各 App
    log_cal = setup_logger(device_id, "calendar")
    log_task = setup_logger(device_id, "tasks")
    log_exp = setup_logger(device_id, "expense")
    log_markor = setup_logger(device_id, "markor")
    log_sys = setup_logger(device_id, "system_data")
    
    # 执行初始化点击逻辑 (Warm-up)
    # Calendar 已有 trigger_db_creation，这里处理新的
    init_markor(device_id, log_markor)
    init_expense(device_id, log_exp)
    init_tasks(device_id, log_task) # <--- 必须加上这行
    # Tasks 通常启动即建库，或者我们可以像 Calendar 一样加一个 init_tasks
    
    # 4. 注入数据
    with tempfile.TemporaryDirectory() as temp_dir:
        logger.info("--- 步骤 3: 注入数据 ---")
        
        # Calendar
        inject_calendar(device_id, temp_dir, log_cal) # 使用旧有逻辑
        
        # Tasks
        inject_tasks_db(device_id, temp_dir, log_task)
        
        # Expense
        inject_expense_db(device_id, temp_dir, log_exp)
        
        # Markor
        inject_markor_files(device_id, temp_dir, log_markor)
        
        # System (Files, SMS, Contacts)
        inject_media_files(device_id, temp_dir, log_sys) # PDF, txt etc.
        inject_contacts(device_id, log_sys)
        inject_sms_msg(device_id, log_sys)
        
    # 5. 收尾
    logger.info("--- 步骤 4: 收尾 ---")
    go_home(device_id, logger)
    clean_background_apps(device_id, logger, exclude_pkgs=[PKG_CALENDAR, PKG_TASKS, PKG_EXPENSE, PKG_MARKOR])
    
    logger.info("========== 设备处理完成 ==========")

def main():
    if not os.path.exists(ADB_PATH): 
        print("ADB Path Error")
        return
    devices = find_devices()
    print(f"Detected Devices: {devices}")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(devices)) as executor:
        executor.map(process_device_pipeline, devices)

if __name__ == "__main__":
    main()