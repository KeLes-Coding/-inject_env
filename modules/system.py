# modules/system.py
# -*- coding: utf-8 -*-
import re
import time
from utils import run_adb
from config import SAFE_PACKAGES_REGEX, PKG_TELEPHONY, PKG_CONTACTS_STORAGE

# 定义关键系统服务的宿主进程
SYSTEM_PROCESS_MAP = {
    PKG_TELEPHONY: ["com.android.phone"],
    PKG_CONTACTS_STORAGE: ["android.process.acore"],
    "com.android.providers.media": ["android.process.media"]
}

def go_home(device_id, logger):
    logger.info("回到桌面...")
    run_adb(device_id, ["shell", "input", "keyevent", "KEYCODE_HOME"], logger=logger)
    time.sleep(1)

def kill_process_by_name(device_id, proc_name, logger):
    """查找并杀死指定名称的进程"""
    out, _ = run_adb(device_id, ["shell", f"pidof {proc_name}"], logger=logger)
    if out:
        pids = out.split()
        for pid in pids:
            if pid.isdigit():
                logger.debug(f"  Killing system process {proc_name} (PID: {pid}) to force reload...")
                run_adb(device_id, ["shell", f"kill {pid}"], logger=logger)

def clean_background_apps(device_id, logger, exclude_pkgs=None):
    if exclude_pkgs is None:
        exclude_pkgs = []
        
    logger.info(f"=== 开始环境重置 (保留: {len(exclude_pkgs)} 个应用) ===")
    
    out, _ = run_adb(device_id, ["shell", "pm", "list", "packages"], logger=logger)
    if not out: return

    all_packages = [line.split(":")[-1].strip() for line in out.splitlines() if line.startswith("package:")]
    safe_patterns = [re.compile(p) for p in SAFE_PACKAGES_REGEX]

    cleared = 0
    skipped = 0
    
    for pkg in all_packages:
        if not pkg: continue
        
        # 1. 检查白名单
        is_safe = any(p.search(pkg) for p in safe_patterns)
        if is_safe:
            skipped += 1
            continue
            
        # 2. 检查任务保留
        if pkg in exclude_pkgs:
            continue
        
        # 3. 执行清理
        try:
            # 常规应用：停止 + 清除
            run_adb(device_id, ["shell", "am", "force-stop", pkg])
            
            # 特殊处理：如果是系统核心存储服务，执行物理删除 + 进程重启
            if pkg in SYSTEM_PROCESS_MAP:
                logger.info(f"  [Deep Clean] 深度清理系统服务: {pkg}")
                # 物理删除数据库目录 (确保数据彻底消失)
                run_adb(device_id, ["shell", f"rm -rf /data/data/{pkg}/databases/*"])
                run_adb(device_id, ["shell", f"rm -rf /data/data/{pkg}/cache/*"])
                
                # 重启宿主进程 (关键步骤！否则进程会持有无效句柄)
                for proc in SYSTEM_PROCESS_MAP[pkg]:
                    kill_process_by_name(device_id, proc, logger)
            else:
                # 普通应用直接 pm clear
                run_adb(device_id, ["shell", "pm", "clear", pkg])
                
            cleared += 1
        except Exception as e:
            logger.warning(f"  清理 {pkg} 失败: {e}")
            
    # 等待系统进程重生
    time.sleep(3)
    logger.info(f"环境重置完成: 清理 {cleared}, 跳过 {skipped}。")