# -*- coding: utf-8 -*-
import time
import re
from utils import run_adb
from config import PKG_MARKOR, PKG_EXPENSE, PKG_TASKS

def get_screen_size(device_id, logger):
    out, _ = run_adb(device_id, ["shell", "wm", "size"], logger=logger)
    width, height = 1080, 1920
    if out and "Physical size" in out:
        match = re.search(r"(\d+)x(\d+)", out)
        if match:
            width = int(match.group(1))
            height = int(match.group(2))
    return width, height

def tap_percent(device_id, x_pct, y_pct, width, height, logger):
    """按屏幕百分比点击"""
    x = int(width * x_pct)
    y = int(height * y_pct)
    run_adb(device_id, ["shell", f"input tap {x} {y}"], logger=logger)
    time.sleep(0.5)

def tap_bottom_area(device_id, width, height, logger, clicks=1):
    """疯狂点击底部区域 (Next/Done/Skip 通常在这里)"""
    for _ in range(clicks):
        # 尝试点击底部中间、右侧、右下角
        tap_percent(device_id, 0.5, 0.9, width, height, logger) # 中下
        tap_percent(device_id, 0.85, 0.9, width, height, logger) # 右下
        tap_percent(device_id, 0.85, 0.94, width, height, logger) # 更靠下
        # 尝试发送 Enter 键 (物理键盘支持)
        run_adb(device_id, ["shell", "input keyevent KEYCODE_ENTER"], logger=logger)
        time.sleep(0.5)

def init_markor(device_id, logger):
    logger.info(f"正在初始化 {PKG_MARKOR}...")
    run_adb(device_id, ["shell", "monkey", "-p", PKG_MARKOR, "-c", "android.intent.category.LAUNCHER", "1"], logger=logger)
    time.sleep(3)
    width, height = get_screen_size(device_id, logger)
    
    # Markor 引导页通常有 5 页左右
    logger.debug("处理 Markor 引导页...")
    tap_bottom_area(device_id, width, height, logger, clicks=6)
    
    time.sleep(2)
    run_adb(device_id, ["shell", "am", "force-stop", PKG_MARKOR], logger=logger)

def init_expense(device_id, logger):
    logger.info(f"正在初始化 {PKG_EXPENSE}...")
    run_adb(device_id, ["shell", "monkey", "-p", PKG_EXPENSE, "-c", "android.intent.category.LAUNCHER", "1"], logger=logger)
    time.sleep(4) # 给更多启动时间
    width, height = get_screen_size(device_id, logger)
    
    # Expense 引导页: Next -> Continue
    logger.debug("处理 Expense 引导页...")
    tap_bottom_area(device_id, width, height, logger, clicks=4)
    
    # 额外等待一下让 DB 写入
    time.sleep(3)
    run_adb(device_id, ["shell", "am", "force-stop", PKG_EXPENSE], logger=logger)

def init_tasks(device_id, logger):
    logger.info(f"正在初始化 {PKG_TASKS}...")
    run_adb(device_id, ["shell", "monkey", "-p", PKG_TASKS, "-c", "android.intent.category.LAUNCHER", "1"], logger=logger)
    time.sleep(4)
    width, height = get_screen_size(device_id, logger)
    
    # Org.Tasks 引导页: 也是类似 Welcome -> Get Started
    logger.debug("处理 Tasks 引导页...")
    tap_bottom_area(device_id, width, height, logger, clicks=4)
    
    time.sleep(3)
    run_adb(device_id, ["shell", "am", "force-stop", PKG_TASKS], logger=logger)