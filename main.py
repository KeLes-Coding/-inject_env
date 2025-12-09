# -*- coding: utf-8 -*-
import os
import re
import tempfile
import concurrent.futures
import time
from config import ADB_PATH, CALENDAR_PKG
from utils import setup_logger, run_adb, capture_crash_log
from modules.injector import inject_calendar, inject_media_files
from modules.system import clean_background_apps, go_home

def find_devices():
    # ... (保持原样)
    import subprocess
    res = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True)
    devices = []
    if res.stdout:
        for line in res.stdout.splitlines()[1:]:
            if "device" in line and "emulator" in line:
                match = re.match(r"(\S+)\s+device", line)
                if match: devices.append(match.group(1))
    return devices

def process_pipeline(device_id):
    logger = setup_logger(device_id)
    logger.info(">>> 任务开始 <<<")
    
    try:
        run_adb(device_id, ["root"], logger=logger)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # --- Phase 1: 环境全量重置 ---
            logger.info("--- Phase 1: 环境全量重置 ---")
            clean_background_apps(device_id, logger, exclude_pkgs=[])
            
            # --- Phase 2: 数据注入 ---
            logger.info("--- Phase 2: 数据注入 ---")
            
            if not inject_calendar(device_id, temp_dir, logger):
                logger.error("严重错误：日历注入失败，跳过后续步骤")
                return

            inject_media_files(device_id, temp_dir, logger)
            
            # --- Phase 3: 验证启动与崩溃诊断 ---
            logger.info("--- Phase 3: 验证启动 (带崩溃捕捉) ---")
            
            # 1. 先清空 logcat 缓冲区，确保抓到的是最新的报错
            run_adb(device_id, ["logcat", "-c"], logger=logger)
            
            # 2. 启动应用
            run_adb(device_id, ["shell", "monkey", "-p", CALENDAR_PKG, "-c", "android.intent.category.LAUNCHER", "1"], logger=logger)
            time.sleep(3) # 给它几秒钟让它崩溃
            
            # 3. 检查进程是否还活着
            pid_out, _ = run_adb(device_id, ["shell", f"pidof {CALENDAR_PKG}"], logger=logger)
            
            if not pid_out:
                logger.error("❌ 检测到应用启动后进程消失 (闪退)！")
                # 抓取日志！
                capture_crash_log(device_id, logger)
            else:
                logger.info(f"✅ 应用启动正常 (PID: {pid_out})")

            # --- Phase 4: 收尾清理 ---
            logger.info("--- Phase 4: 收尾清理 ---")
            go_home(device_id, logger)
            
            # 1. 清理其他所有应用 (清除数据 + 停止)
            # 这里的 exclude 仅仅是不执行 `pm clear`，防止删掉我们刚注入的数据
            clean_background_apps(device_id, logger, exclude_pkgs=[CALENDAR_PKG])
            
            # 2. 针对 Calendar Pro，执行 Force Stop (不保留在后台，但保留数据)
            logger.info(f"停止 {CALENDAR_PKG} (保留数据)...")
            run_adb(device_id, ["shell", "am", "force-stop", CALENDAR_PKG], logger=logger)
            
        logger.info(">>> 任务成功完成 <<<")
        
    except Exception as e:
        logger.exception("任务执行中发生未捕获异常")

def main():
    if not os.path.exists(ADB_PATH): return
    devices = find_devices()
    print(f"检测到设备: {devices}")
    if not devices: return
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(devices)) as executor:
        executor.map(process_pipeline, devices)

if __name__ == "__main__":
    main()