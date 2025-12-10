# -*- coding: utf-8 -*-
import os
import time
import re
from config import PKG_CALENDAR, DB_CALENDAR_PATH
from utils import run_adb, load_json_data
from db_helper import CalendarDBHelper

REMOTE_DB_PATH = DB_CALENDAR_PATH
REMOTE_DB_DIR = os.path.dirname(REMOTE_DB_PATH)

def trigger_db_creation(device_id, logger):
    """通过 Monkey 启动并模拟点击以触发建库"""
    logger.info("触发应用建库流程...")
    run_adb(device_id, ["shell", "monkey", "-p", PKG_CALENDAR, "-c", "android.intent.category.LAUNCHER", "1"], logger=logger)
    time.sleep(3) 
    
    out, _ = run_adb(device_id, ["shell", "wm", "size"], logger=logger)
    width, height = 1080, 1920
    if out and "Physical size" in out:
        match = re.search(r"(\d+)x(\d+)", out)
        if match:
            width = int(match.group(1))
            height = int(match.group(2))
            
    x = int(width * 0.85)
    y = int(height * 0.90)
    
    logger.debug(f"点击坐标: {x},{y}")
    run_adb(device_id, ["shell", f"input tap {x} {y}"], logger=logger)
    time.sleep(2)
    run_adb(device_id, ["shell", "input keyevent BACK"], logger=logger)
    time.sleep(1)

def inject_calendar(device_id, temp_dir, logger):
    logger.info(">>> 开始 Simple Calendar Pro 注入流程 <<<")
    
    events_data = load_json_data("calendar.json")
    if not events_data:
        logger.error("无 Calendar 数据，跳过。")
        return False
    
    local_db_dir = os.path.join(temp_dir, f"db_{device_id}")
    if os.path.exists(local_db_dir):
        import shutil
        shutil.rmtree(local_db_dir)
    os.makedirs(local_db_dir, exist_ok=True)

    run_adb(device_id, ["shell", "am", "force-stop", PKG_CALENDAR], logger=logger)
    perms = ["READ_CALENDAR", "WRITE_CALENDAR", "POST_NOTIFICATIONS"]
    for p in perms:
        run_adb(device_id, ["shell", "pm", "grant", PKG_CALENDAR, f"android.permission.{p}"], logger=logger)

    ls_out, _ = run_adb(device_id, ["shell", f"ls {REMOTE_DB_PATH}"], logger=logger)
    if not ls_out or "No such file" in ls_out:
        logger.warning("未检测到数据库，正在初始化以获取正确的 SELinux 上下文...")
        trigger_db_creation(device_id, logger)
        run_adb(device_id, ["shell", "am", "force-stop", PKG_CALENDAR], logger=logger)
        
        time.sleep(1)
        ls_out, _ = run_adb(device_id, ["shell", f"ls {REMOTE_DB_PATH}"], logger=logger)
        if not ls_out or "No such file" in ls_out:
            logger.error("初始化失败：无法生成基准数据库。")
            return False

    logger.info("拉取基准数据库...")
    run_adb(device_id, ["pull", REMOTE_DB_DIR, local_db_dir], logger=logger, check=True)
    
    target_db = None
    for root, dirs, files in os.walk(local_db_dir):
        if "events.db" in files:
            target_db = os.path.join(root, "events.db")
            break
            
    if not target_db:
        logger.error(f"拉取失败，未找到 events.db")
        return False

    # 传递数据给 Helper
    helper = CalendarDBHelper(target_db, logger)
    if not helper.inject_data(events_data):
        logger.error("本地数据库修改失败")
        return False

    logger.info("正在注入数据 (采用流式覆盖)...")
    temp_remote_path = "/data/local/tmp/events_inject.db"
    run_adb(device_id, ["push", target_db, temp_remote_path], logger=logger)
    run_adb(device_id, ["shell", f"rm -f {REMOTE_DB_PATH}-wal {REMOTE_DB_PATH}-shm"], logger=logger)
    
    overwrite_cmd = f"cat {temp_remote_path} > {REMOTE_DB_PATH}"
    out, err = run_adb(device_id, ["shell", overwrite_cmd], logger=logger)
    run_adb(device_id, ["shell", f"rm {temp_remote_path}"], logger=logger)
    
    if err and "Permission denied" in err:
        logger.error(f"写入失败: {err}")
        return False

    uid_out, _ = run_adb(device_id, ["shell", f"dumpsys package {PKG_CALENDAR} | grep userId"], logger=logger)
    if uid_out:
        match = re.search(r"userId=(\d+)", uid_out)
        if match:
            uid = match.group(1)
            run_adb(device_id, ["shell", f"chown {uid}:{uid} {REMOTE_DB_PATH}"], logger=logger)
            run_adb(device_id, ["shell", f"chown -R {uid}:{uid} {REMOTE_DB_DIR}"], logger=logger)
            
    logger.info("Calendar 注入完成。")
    return True