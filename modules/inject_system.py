# -*- coding: utf-8 -*-
import time
import re
from utils import run_adb
from config import PKG_CONTACTS

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
        out, err = run_adb(device_id, ["shell", cmd_raw], logger=logger)
        
        # 解析 ID，例如 "Result: content://com.android.contacts/raw_contacts/1"
        # 或者仅仅是 "Created row 1" 取决于系统版本
        # 我们寻找行尾的数字
        raw_id = None
        if out:
            # 匹配行尾的数字
            match = re.search(r'(\d+)$', out.strip())
            if match:
                raw_id = match.group(1)
            else:
                # 尝试匹配 "row id X"
                match2 = re.search(r'id\s*=?\s*(\d+)', out)
                if match2: raw_id = match2.group(1)

        if not raw_id:
            logger.error(f"无法解析 Contact ID, 输出: {out}, 错误: {err}")
            continue
            
        try:
            # 2. 插入 Name
            # 注意: mimetype 必须完全匹配
            cmd_name = f'content insert --uri content://com.android.contacts/data --bind raw_contact_id:i:{raw_id} --bind mimetype:s:vnd.android.cursor.item/name --bind data1:s:"{name}"'
            run_adb(device_id, ["shell", cmd_name], logger=logger)
            
            # 3. 插入 Phone
            cmd_phone = f'content insert --uri content://com.android.contacts/data --bind raw_contact_id:i:{raw_id} --bind mimetype:s:vnd.android.cursor.item/phone_v2 --bind data1:s:"{phone}"'
            run_adb(device_id, ["shell", cmd_phone], logger=logger)
            
            logger.info(f"成功注入联系人: {name} (ID: {raw_id})")
        except Exception as e:
            logger.error(f"联系人数据插入异常: {e}")

def init_messaging_app(device_id, logger):
    """启动短信应用以确保 DB 已创建"""
    # 尝试启动常见的 Messaging 包名
    pkgs = ["com.google.android.apps.messaging", "com.android.messaging", "com.android.mms"]
    for pkg in pkgs:
        out, _ = run_adb(device_id, ["shell", "pm", "list", "packages", pkg], logger=logger)
        if pkg in out:
            run_adb(device_id, ["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"], logger=logger)
            time.sleep(2)
            # 回到桌面
            run_adb(device_id, ["shell", "input", "keyevent", "KEYCODE_HOME"], logger=logger)
            return
    logger.warning("未找到常见的短信应用，跳过预热。")

def inject_sms_msg(device_id, logger):
    logger.info(">>> 注入 SMS (仅模拟器生效) <<<")
    
    if "emulator" not in device_id:
        return

    # 1. 预热 App
    init_messaging_app(device_id, logger)

    messages = [
        ("459123", "Your Google code is 459123"),
        ("13900000001", "Can we meet at 18:30?"), 
        ("Amazon", "Your package has arrived"),
        ("987654321", "Let's go to Gym on Tuesday"), 
        ("13900000001", "The passcode is 1234"), 
    ]
    
    for phone, body in messages:
        sender = phone if phone.isdigit() else "10086"
        # 处理空格
        body_safe = body.replace(" ", "_")
        # 发送
        run_adb(device_id, ["emu", "sms", "send", sender, body], logger=logger)
        time.sleep(1) # 增加间隔，防止系统丢包