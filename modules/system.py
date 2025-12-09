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
    清理后台应用
    :param exclude_pkgs: 不清理的包名列表
    """
    if exclude_pkgs is None:
        exclude_pkgs = []
        
    logger.info(f"开始清理后台 (保留: {exclude_pkgs})...")
    
    out, _ = run_adb(device_id, ["shell", "pm", "list", "packages"], logger=logger)
    if not out:
        return

    all_packages = [line.split(":")[-1].strip() for line in out.splitlines() if line.startswith("package:")]
    
    count = 0
    for pkg in all_packages:
        if not pkg: continue
        
        # 1. 白名单检查
        is_safe = any(re.search(pattern, pkg) for pattern in SAFE_PACKAGES_REGEX)
        if is_safe: continue
        
        # 2. 排除项检查
        if pkg in exclude_pkgs: continue
        
        # 3. 执行清理 (Force Stop + Clear Data)
        # 注意：Clear Data 会重置应用，符合你的"重置"需求
        run_adb(device_id, ["shell", "am", "force-stop", pkg]) # 不检查结果，加快速度
        _, err = run_adb(device_id, ["shell", "pm", "clear", pkg])
        
        if not err:
            count += 1
            
    logger.info(f"清理完成，重置了 {count} 个应用。")