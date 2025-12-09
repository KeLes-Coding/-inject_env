# -*- coding: utf-8 -*-
import time
import re
from utils import run_adb

def get_last_insert_id(device_id, uri, logger):
    """
    强制查询最后一条记录的 ID
    [修复] 移除 --limit 和 --sort，改为获取所有 ID 后在 Python 取最大值
    """
    cmd = f'content query --uri {uri} --projection _id'
    out, _ = run_adb(device_id, ["shell", cmd], logger=logger)
    
    if not out:
        return None
        
    ids = []
    # 输出格式通常是 "Row: 0 _id=1", "Row: 1 _id=2" ...
    # 或者直接 "_id=1" 取决于版本
    for line in out.splitlines():
        match = re.search(r"_id=(\d+)", line)
        if match:
            ids.append(int(match.group(1)))
            
    if ids:
        return str(max(ids))
    return None

def inject_contacts(device_id, logger):
    logger.info(">>> 注入系统联系人 <<<")
    
    contacts = [
        ("Emergency", "110"),
        ("Zheng Zihan", "13912345678"),
        ("Bob", "987654321")
    ]
    
    for name, phone in contacts:
        # 1. 插入 RawContact
        cmd_raw = 'content insert --uri content://com.android.contacts/raw_contacts --bind account_name:s:google --bind account_type:s:com.google'
        out, _ = run_adb(device_id, ["shell", cmd_raw], logger=logger)
        
        raw_id = None
        # 优先尝试直接解析 stdout (部分模拟器支持)
        if out:
            match = re.search(r'(\d+)$', out.strip())
            if match:
                raw_id = match.group(1)
        
        # 兜底查询
        if not raw_id:
            # logger.debug("RawContact ID 解析失败，尝试反向查询...")
            raw_id = get_last_insert_id(device_id, "content://com.android.contacts/raw_contacts", logger)

        if not raw_id:
            logger.error(f"无法获取 RawContact ID, 跳过 {name}")
            continue
            
        try:
            # 2. 插入 Name
            cmd_name = f'content insert --uri content://com.android.contacts/data --bind raw_contact_id:i:{raw_id} --bind mimetype:s:vnd.android.cursor.item/name --bind data1:s:"{name}"'
            run_adb(device_id, ["shell", cmd_name], logger=logger)
            
            # 3. 插入 Phone
            cmd_phone = f'content insert --uri content://com.android.contacts/data --bind raw_contact_id:i:{raw_id} --bind mimetype:s:vnd.android.cursor.item/phone_v2 --bind data1:s:"{phone}"'
            run_adb(device_id, ["shell", cmd_phone], logger=logger)
            
            logger.info(f"联系人 {name} 注入成功 (ID: {raw_id})")
        except Exception as e:
            logger.error(f"联系人数据插入异常: {e}")

def init_messaging_app(device_id, logger):
    """启动短信应用"""
    logger.info("预热短信应用...")
    pkgs = ["com.google.android.apps.messaging", "com.android.messaging", "com.android.mms"]
    for pkg in pkgs:
        out, _ = run_adb(device_id, ["shell", "pm", "list", "packages", pkg], logger=logger)
        if pkg in out:
            run_adb(device_id, ["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"], logger=logger)
            time.sleep(3)
            return pkg
    return None

def inject_sms_msg(device_id, logger):
    logger.info(">>> 注入 SMS (仅模拟器生效) <<<")
    
    if "emulator" not in device_id:
        return

    msg_pkg = init_messaging_app(device_id, logger)

    messages = [
        ("459123", "Your Google code is 459123"),
        ("13900000001", "Can we meet at 18:30?"), 
        ("10086", "Your package has arrived"), 
        ("987654321", "Let's go to Gym on Tuesday"), 
        ("13900000001", "The passcode is 1234"), 
    ]
    
    for phone, body in messages:
        run_adb(device_id, ["emu", "sms", "send", phone, body], logger=logger)
        time.sleep(1)

    if msg_pkg:
        logger.info("刷新短信应用视图...")
        run_adb(device_id, ["shell", "am", "force-stop", msg_pkg], logger=logger)
        time.sleep(1)
        run_adb(device_id, ["shell", "monkey", "-p", msg_pkg, "-c", "android.intent.category.LAUNCHER", "1"], logger=logger)