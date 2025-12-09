# -*- coding: utf-8 -*-
import subprocess
import logging
import os
import sys
import time
from config import ADB_PATH, LOG_DIR

def setup_logger(device_id):
    """为每个设备创建一个独立的 Logger"""
    logger = logging.getLogger(device_id)
    logger.setLevel(logging.DEBUG)
    if logger.hasHandlers(): logger.handlers.clear()

    log_file = os.path.join(LOG_DIR, f"{device_id}.log")
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(f'[{device_id}] %(message)s')
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
            # 只有在 check=True 或者 logger 存在且明确不是忽略错误时才警告
            if logger and not check and "No such file" not in err: 
                logger.debug(f"CMD RET {result.returncode}: {err}")
            return None, err
        
        return result.stdout.strip() if result.stdout else "Success", None
    except Exception as e:
        if logger: logger.error(f"EXCEPTION: {e}")
        return None, str(e)

def capture_crash_log(device_id, logger):
    """
    抓取该设备最近的 Logcat 错误堆栈，用于分析闪退原因
    """
    log_name = f"crash_{device_id}_{int(time.time())}.txt"
    log_path = os.path.join(LOG_DIR, log_name)
    
    logger.warning(f"检测到潜在的闪退/崩溃，正在抓取系统日志到 {log_name} ...")
    
    # 抓取最近 500 行日志，重点关注 AndroidRuntime 和 target app
    # -d: dump and exit, -t: tail lines
    cmd = [ADB_PATH, "-s", device_id, "logcat", "-d", "-t", "800"]
    
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=10)
        logger.info(f"崩溃日志已保存: {log_path}")
    except Exception as e:
        logger.error(f"抓取 Logcat 失败: {e}")