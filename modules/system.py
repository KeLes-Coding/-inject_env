# -*- coding: utf-8 -*-
import re
import time
from utils import run_adb
from config import SAFE_PACKAGES_REGEX

def go_home(device_id, logger):
    logger.info("回到桌面...")
    run_adb(device_id, ["shell", "input", "keyevent", "KEYCODE_HOME"], logger=logger)
    time.sleep(1)

def clean_background_apps(device_id, logger, exclude_pkgs=None):
    """
    清理后台应用 (环境重置)
    :param exclude_pkgs: 本次任务需要保留的应用列表 (例如刚注入数据的应用)
    """
    if exclude_pkgs is None:
        exclude_pkgs = []
        
    logger.info(f"=== 开始环境重置 (保留: {exclude_pkgs}) ===")
    
    # 1. 获取所有包名
    out, _ = run_adb(device_id, ["shell", "pm", "list", "packages"], logger=logger)
    if not out:
        logger.warning("无法获取应用列表，跳过清理")
        return

    all_packages = [line.split(":")[-1].strip() for line in out.splitlines() if line.startswith("package:")]
    
    cleared_count = 0
    skipped_count = 0
    
    # 预编译正则
    safe_patterns = [re.compile(p) for p in SAFE_PACKAGES_REGEX]

    for pkg in all_packages:
        if not pkg: continue
        
        # 1. 白名单检查
        is_safe = any(p.search(pkg) for p in safe_patterns)
        if is_safe:
            skipped_count += 1
            continue
        
        # 2. 任务保留项检查
        if pkg in exclude_pkgs:
            logger.debug(f"保留任务应用: {pkg}")
            continue
        
        # 3. 执行清理 (Force Stop + Clear Data)
        # 忽略 stop 失败
        run_adb(device_id, ["shell", "am", "force-stop", pkg]) 
        
        # 清除数据
        out, err = run_adb(device_id, ["shell", "pm", "clear", pkg])
        if not err and "Success" in out:
            cleared_count += 1
        else:
            logger.debug(f"清理 {pkg} 失败/无权限: {err or out}")
            
    logger.info(f"环境重置完成: 清理 {cleared_count} 个, 跳过 {skipped_count} 个系统应用。")