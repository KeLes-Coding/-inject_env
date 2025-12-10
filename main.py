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
from modules.injector import inject_calendar
from modules.inject_tasks import inject_tasks_db
from modules.inject_expense import inject_expense_db
# [修改] 引入新的通用文件注入模块 (替代旧的 Markor 和 Media 注入)
from modules.inject_files import inject_files_from_manifest
from modules.inject_system import inject_contacts, inject_sms_msg 

def find_devices():
    import subprocess
    # 获取连接的设备列表
    res = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True)
    devices = []
    if res.stdout:
        for line in res.stdout.splitlines()[1:]:
            if "device" in line: 
                match = re.match(r"(\S+)\s+device", line)
                if match: devices.append(match.group(1))
    return devices

def is_injected(device_id, logger):
    """
    [修正版] 检测是否已经注入过环境 (幂等性检测)。
    """
    # 同时接收 stdout 和 stderr
    out, err = run_adb(device_id, ["shell", "ls /data/local/tmp/env_injected_flag"], logger=logger)
    
    # 只要任意一个输出包含 "No such file"，就说明没注入过
    if "No such file" in out or "No such file" in err:
        return False
        
    # 如果 stderr 为空且 stdout 输出了文件名，或者没有报错信息，则认为已注入
    # 注意：某些 Android ls 成功时只会输出路径，失败时才有内容
    # 简单粗暴的判断：如果刚才没返回 False，且看起来也没报错，那就是 True
    return True

def mark_injected(device_id, logger):
    """
    [新增] 注入完成后在设备上创建标记文件。
    """
    run_adb(device_id, ["shell", "touch /data/local/tmp/env_injected_flag"], logger=logger)

def process_device_pipeline(device_id):
    # 1. 设置主 Logger
    logger = setup_logger(device_id, "system")
    logger.info(f"========== 开始处理设备 {device_id} ==========")
    
    run_adb(device_id, ["root"], logger=logger)

    # [新增] 幂等性检测：如果已经注入过，直接跳过
    # if is_injected(device_id, logger):
    #     logger.info("检测到设备已存在注入标记 (env_injected_flag)，跳过注入流程。")
    #     logger.info("========== 设备处理结束 (Skipped) ==========")
    #     return

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
        logger.info("--- 步骤 3: 注入数据 (From JSON) ---")
        
        # Calendar (读取 calendar.json)
        inject_calendar(device_id, temp_dir, log_cal)
        
        # Tasks (读取 tasks.json)
        inject_tasks_db(device_id, temp_dir, log_task)
        
        # Expense (读取 expense.json)
        inject_expense_db(device_id, temp_dir, log_exp)
        
        # Files (Documents, Markor, Photos, etc.) - [修改] 使用新模块读取 files_manifest.json
        inject_files_from_manifest(device_id, temp_dir, log_sys)
        
        # System (SMS, Contacts) - 读取 sms.json, contacts.json
        inject_contacts(device_id, log_sys)
        inject_sms_msg(device_id, temp_dir, log_sys)
        
    # 5. 收尾
    logger.info("--- 步骤 4: 收尾 ---")
    
    # [新增] 标记注入完成
    mark_injected(device_id, logger)
    
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
        print(f"Error: ADB Path not found at {ADB_PATH}")
        return
    
    devices = find_devices()
    print(f"Detected Devices: {devices}")
    
    if not devices:
        print("未发现在线设备。")
        return
    
    # 使用线程池并发处理所有连接的设备
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(devices)) as executor:
        try:
            results = executor.map(process_device_pipeline, devices)
            # 迭代结果以触发任何潜在的异常
            for _ in results: pass 
        except Exception as e:
            print(f"Pipeline Execution Error: {e}")

if __name__ == "__main__":
    main()