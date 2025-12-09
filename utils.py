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
    
    if logger.hasHandlers(): logger.handlers.clear()

    device_log_dir = os.path.join(LOG_ROOT_DIR, device_id)
    os.makedirs(device_log_dir, exist_ok=True)

    log_file = os.path.join(device_log_dir, f"{app_context}.log")
    
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    # 增加 %(funcName)s 和 %(lineno)d 方便定位代码位置
    file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s')
    file_handler.setFormatter(file_formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(f'[{device_id}][{app_context}] %(message)s')
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def run_adb(device_id, command_list, timeout=60, check=False, logger=None):
    """
    执行 ADB 命令并提供详细的日志记录
    """
    full_cmd = [ADB_PATH, "-s", device_id] + command_list
    cmd_str = ' '.join(full_cmd)
    
    try:
        if logger: logger.debug(f"EXEC: {cmd_str}")
        
        start_time = time.time()
        result = subprocess.run(full_cmd, capture_output=True, text=True, check=check, timeout=timeout, encoding='utf-8')
        duration = time.time() - start_time
        
        stdout = result.stdout.strip() if result.stdout else ""
        stderr = result.stderr.strip() if result.stderr else ""
        
        # 记录输出结果，方便调试 (限制长度防止日志爆炸)
        if logger:
            if stdout: 
                log_content = stdout[:500] + "..." if len(stdout) > 500 else stdout
                logger.debug(f"STDOUT ({duration:.2f}s): {log_content}")
            if stderr:
                logger.debug(f"STDERR ({duration:.2f}s): {stderr}")
            if result.returncode != 0 and not check:
                logger.warning(f"CMD FAIL (Ret: {result.returncode}): {stderr}")

        if result.returncode != 0 and check:
            # 如果 check=True，subprocess 已经抛出异常，这里通常走不到
            pass
            
        return stdout, stderr
        
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() if e.stderr else str(e)
        if logger: logger.error(f"ADB CHECK ERROR: {err_msg}")
        raise e
    except Exception as e:
        if logger: logger.error(f"EXCEPTION: {e}")
        return None, str(e)