# -*- coding: utf-8 -*-
import subprocess
import logging
import os
import sys
import time
from config import ADB_PATH, LOG_ROOT_DIR

def setup_logger(device_id, app_context="main"):
    """
    为设备和特定 APP 上下文创建独立的 Logger
    日志路径: logs/{device_id}/{app_context}.log
    """
    logger_name = f"{device_id}_{app_context}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    
    # 清除旧的 handlers 防止重复打印
    if logger.hasHandlers(): logger.handlers.clear()

    # 创建目录: logs/device_id/
    device_log_dir = os.path.join(LOG_ROOT_DIR, device_id)
    os.makedirs(device_log_dir, exist_ok=True)

    log_file = os.path.join(device_log_dir, f"{app_context}.log")
    
    # 文件 Handler
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)

    # 控制台 Handler (仅在 main 上下文或错误时显示，避免刷屏，可根据需要调整)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(f'[{device_id}][{app_context}] %(message)s')
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def run_adb(device_id, command_list, timeout=60, check=False, logger=None):
    full_cmd = [ADB_PATH, "-s", device_id] + command_list
    try:
        if logger: logger.debug(f"EXEC: {' '.join(full_cmd)}")
        result = subprocess.run(full_cmd, capture_output=True, text=True, check=check, timeout=timeout, encoding='utf-8')
        
        if result.returncode != 0:
            err = result.stderr.strip()
            if logger and not check and "No such file" not in err: 
                logger.debug(f"CMD RET {result.returncode}: {err}")
            return None, err
        
        return result.stdout.strip() if result.stdout else "Success", None
    except Exception as e:
        if logger: logger.error(f"EXCEPTION: {e}")
        return None, str(e)