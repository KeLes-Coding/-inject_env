# -*- coding: utf-8 -*-
import os
import time
import re
from config import CALENDAR_PKG, REMOTE_DB_DIR, REMOTE_DB_PATH
from utils import run_adb
from db_helper import CalendarDBHelper

def trigger_db_creation(device_id, logger):
    """通过 Monkey 启动并模拟点击以触发建库"""
    logger.info("触发应用建库流程...")
    
    # 1. 启动
    run_adb(device_id, ["shell", "monkey", "-p", CALENDAR_PKG, "-c", "android.intent.category.LAUNCHER", "1"], logger=logger)
    time.sleep(3) 
    
    # 2. 点击右下角 FAB (根据分辨率计算坐标)
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
    
    # 3. 返回以保存状态
    run_adb(device_id, ["shell", "input keyevent BACK"], logger=logger)
    time.sleep(1)

def inject_calendar(device_id, temp_dir, logger):
    logger.info(">>> 开始 Simple Calendar Pro 注入流程 <<<")
    
    local_db_dir = os.path.join(temp_dir, f"db_{device_id}")
    if os.path.exists(local_db_dir):
        import shutil
        shutil.rmtree(local_db_dir)
    os.makedirs(local_db_dir, exist_ok=True)

    # 1. 停止应用并授权
    run_adb(device_id, ["shell", "am", "force-stop", CALENDAR_PKG], logger=logger)
    perms = ["READ_CALENDAR", "WRITE_CALENDAR", "POST_NOTIFICATIONS"]
    for p in perms:
        run_adb(device_id, ["shell", "pm", "grant", CALENDAR_PKG, f"android.permission.{p}"], logger=logger)

    # 2. 检查并触发建库 (确保目标文件存在且拥有正确的 SELinux 标签)
    ls_out, _ = run_adb(device_id, ["shell", f"ls {REMOTE_DB_PATH}"], logger=logger)
    if not ls_out or "No such file" in ls_out:
        logger.warning("未检测到数据库，正在初始化以获取正确的 SELinux 上下文...")
        trigger_db_creation(device_id, logger)
        run_adb(device_id, ["shell", "am", "force-stop", CALENDAR_PKG], logger=logger)
        
        # 二次检查
        time.sleep(1)
        ls_out, _ = run_adb(device_id, ["shell", f"ls {REMOTE_DB_PATH}"], logger=logger)
        if not ls_out or "No such file" in ls_out:
            logger.error("初始化失败：无法生成基准数据库。")
            return False

    # 3. 拉取数据库 (用于获取 schema)
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

    # 4. 修改本地数据库
    helper = CalendarDBHelper(target_db, logger)
    if not helper.inject_data():
        logger.error("本地数据库修改失败")
        return False

    # ======================================================================
    # 5. [核心修复] 使用 "覆盖写入" 而非 "删除替换"
    # ======================================================================
    logger.info("正在注入数据 (采用流式覆盖以保留 SELinux 上下文)...")
    
    # 5.1 推送到临时目录
    temp_remote_path = "/data/local/tmp/events_inject.db"
    run_adb(device_id, ["push", target_db, temp_remote_path], logger=logger)
    
    # 5.2 确保目标目录的 WAL/SHM 被清理 (防止 SQLite 版本冲突)
    # 注意：我们不删除 events.db 本身
    run_adb(device_id, ["shell", f"rm -f {REMOTE_DB_PATH}-wal {REMOTE_DB_PATH}-shm"], logger=logger)
    
    # 5.3 使用 cat 命令覆盖内容
    # 这会保留 events.db 原有的所有者(UID)和安全上下文(SELinux Context)
    overwrite_cmd = f"cat {temp_remote_path} > {REMOTE_DB_PATH}"
    out, err = run_adb(device_id, ["shell", overwrite_cmd], logger=logger)
    
    # 5.4 清理临时文件
    run_adb(device_id, ["shell", f"rm {temp_remote_path}"], logger=logger)
    
    if err and "Permission denied" in err:
        logger.error(f"写入失败: {err}")
        return False

    # 6. 权限兜底修复 (虽然 cat 应该保留了权限，但为了防止意外，再次修正 UID)
    # 注意：不再依赖 restorecon 来修复文件，因为文件本身就是系统创建的合法文件
    uid_out, _ = run_adb(device_id, ["shell", f"dumpsys package {CALENDAR_PKG} | grep userId"], logger=logger)
    if uid_out:
        match = re.search(r"userId=(\d+)", uid_out)
        if match:
            uid = match.group(1)
            # 只需要确保 Owner 正确，不需要 chmod 600，因为 cat 不会改变原文件的 chmod
            run_adb(device_id, ["shell", f"chown {uid}:{uid} {REMOTE_DB_PATH}"], logger=logger)
            
            # 为了保险，目录权限还是要维护一下
            run_adb(device_id, ["shell", f"chown -R {uid}:{uid} {REMOTE_DB_DIR}"], logger=logger)
            
    logger.info("Calendar 注入完成 (SELinux Safe Mode)。")
    return True

def inject_media_files(device_id, temp_dir, logger):
    logger.info("注入媒体文件 (占位)...")
    # 此处放置原本的 inject_files 和 inject_photos 逻辑
    # 仅作示例
    p = os.path.join(temp_dir, "test.txt")
    with open(p, "w") as f: f.write("test")
    run_adb(device_id, ["push", p, "/sdcard/Download/"], logger=logger)