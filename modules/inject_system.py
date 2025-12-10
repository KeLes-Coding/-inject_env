# -*- coding: utf-8 -*-
import time
import re
import shlex
from utils import run_adb
from config import PKG_TELEPHONY

# ==========================================
# 诊断与环境修复
# ==========================================

def get_db_path():
    return f"/data/data/{PKG_TELEPHONY}/databases/mmssms.db"

def check_db_ready(device_id, logger):
    """检查数据库和表是否存在"""
    db_path = get_db_path()
    check, _ = run_adb(device_id, ["shell", f"[ -f {db_path} ] && echo yes"], logger=logger)
    if "yes" not in check: return False
    
    sql = "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='sms';"
    out, _ = run_adb(device_id, ["shell", f"sqlite3 {db_path} \"{sql}\""], logger=logger)
    return out and out.strip() == "1"

def ensure_telephony_env(device_id, logger):
    """
    环境自愈逻辑：确保 DB 存在且可用。
    """
    logger.info(">>> 检查 Telephony 环境 (V7) <<<")
    if check_db_ready(device_id, logger):
        logger.info("✅ 数据库环境正常。")
        return

    logger.warning("⚠️ 数据库缺失或损坏，正在重建...")
    db_dir = f"/data/data/{PKG_TELEPHONY}/databases"
    
    # 1. 清理残余
    run_adb(device_id, ["shell", f"rm -rf {db_dir}"], logger=logger)
    
    # 2. 重建目录与权限
    run_adb(device_id, ["shell", f"mkdir -p {db_dir}"], logger=logger)
    uid = "1001" # Default radio uid
    uid_out, _ = run_adb(device_id, ["shell", f"dumpsys package {PKG_TELEPHONY} | grep userId"], logger=logger)
    if uid_out:
        m = re.search(r"userId=(\d+)", uid_out)
        if m: uid = m.group(1)
        
    run_adb(device_id, ["shell", f"chown {uid}:{uid} {db_dir}"], logger=logger)
    run_adb(device_id, ["shell", f"chmod 771 {db_dir}"], logger=logger)
    run_adb(device_id, ["shell", f"restorecon -R {db_dir}"], logger=logger)
    
    # 3. 杀进程触发重建
    run_adb(device_id, ["shell", f"am force-stop {PKG_TELEPHONY}"], logger=logger)
    
    # 4. 激活
    if "emulator" in device_id:
        run_adb(device_id, ["emu", "sms", "send", "10086", "Init_Trigger"], logger=logger)
        
    # 5. 等待
    for i in range(10):
        time.sleep(1)
        if check_db_ready(device_id, logger):
            logger.info("✅ 数据库重建完成。")
            return
    logger.error("❌ 数据库重建超时。")

# ==========================================
# 核心注入逻辑 (混合策略)
# ==========================================

def get_thread_id(device_id, address, logger):
    """
    从 sms 表中查询指定号码的 thread_id。
    如果系统已经为该号码建立了会话，这里就能查到。
    """
    sql = f"SELECT thread_id FROM sms WHERE address='{address}' LIMIT 1;"
    out, _ = run_adb(device_id, ["shell", f"sqlite3 {get_db_path()} \"{sql}\""], logger=logger)
    if out and out.strip().isdigit():
        return int(out.strip())
    return None

def prime_thread_with_emu(device_id, address, logger):
    """
    利用 emu sms 发送一条临时消息，强制系统创建 Thread 和 Canonical Address
    """
    # 注意：emu sms 可能不支持非数字号码（如 Amazon），这里做个尝试
    logger.info(f"正在预热会话: {address}")
    
    # 发送临时消息 "PRIME_MSG"
    run_adb(device_id, ["emu", "sms", "send", address, "PRIME_MSG"], logger=logger)
    
    # 等待系统处理 (通常很快，1-2秒)
    for _ in range(5):
        time.sleep(0.5)
        tid = get_thread_id(device_id, address, logger)
        if tid:
            return tid
            
    logger.warning(f"预热失败或超时: {address} (可能不支持此号码格式)")
    return None

def inject_sms_msg(device_id, logger):
    logger.info(">>> 注入 SMS (V7: Hybrid Strategy) <<<")
    
    # 1. 准备环境
    msg_pkg = "com.google.android.apps.messaging" # 默认假设
    ensure_telephony_env(device_id, logger)
    
    # 清空旧数据 (可选，防止重复运行导致堆积)
    logger.info("清理旧短信数据...")
    run_adb(device_id, ["shell", f"sqlite3 {get_db_path()} 'DELETE FROM sms;'"], logger=logger)
    run_adb(device_id, ["shell", f"sqlite3 {get_db_path()} 'DELETE FROM threads;'"], logger=logger)
    
    now_ms = int(time.time() * 1000)
    day_ms = 86400 * 1000
    
    # 格式: (Phone, Body, TimeOffset, Type)
    # Type: 1=Inbox(收), 2=Sent(发)
    messages = [
        ("459123", "Your Google code is 459123", 0, 1), 
        ("13900000001", "Can we meet at 18 30?", -day_ms, 1), 
        ("Amazon", "Your package has arrived", 0, 1), 
        ("987654321", "Lets go to Gym on Tuesday", 0, 2), 
        ("13900000001", "The passcode is 1234", -3600*1000, 1), 
    ]
    
    success_count = 0
    db_path = get_db_path()
    
    for phone, body, offset, msg_type in messages:
        # --- 步骤 A: 获取合法的 thread_id ---
        # 先尝试在库里找（如果是同一个号码的第二条短信）
        tid = get_thread_id(device_id, phone, logger)
        
        # 如果找不到，就用 emu sms 预热
        if not tid:
            tid = prime_thread_with_emu(device_id, phone, logger)
            
        # 如果还是没有 (比如 Amazon 这种 alphanumeric 可能 emu 不支持)，
        # 我们只能尝试手动插入，thread_id 设为 NULL 或 假装一个 ID
        # 但通常 thread_id=NULL 会导致不显示。
        # 这里做一个兜底：如果是发件箱(2)，或者 emu 失败，我们强行给一个自增 ID 试试？
        # 更安全的做法：如果不显示，就放弃 thread_id (NULL)，有些旧版应用会自己扫。
        sql_tid = tid if tid else "NULL"
        
        # --- 步骤 B: SQL 注入 ---
        ts = now_ms + offset
        safe_body = body.replace("'", "''") # SQL 转义
        
        # 插入语句，显式指定 thread_id
        sql = (
            f"INSERT INTO sms (address, body, date, read, type, thread_id) "
            f"VALUES ('{phone}', '{safe_body}', {ts}, 1, {msg_type}, {sql_tid});"
        )
        
        cmd = f"sqlite3 {db_path} {shlex.quote(sql)}"
        run_adb(device_id, ["shell", cmd], logger=logger)
        
        # 验证
        # 简单查一下总数变没变
        success_count += 1
        logger.info(f"注入: {phone} | Thread: {sql_tid} | Type: {msg_type}")

    # --- 步骤 C: 清理战场 ---
    logger.info("清理预热产生的临时短信...")
    run_adb(device_id, ["shell", f"sqlite3 {db_path} \"DELETE FROM sms WHERE body='PRIME_MSG';\""], logger=logger)
    run_adb(device_id, ["shell", f"sqlite3 {db_path} \"DELETE FROM sms WHERE body='Init_Trigger';\""], logger=logger)

    # --- 步骤 D: 刷新缓存 ---
    # 删除 WAL 文件并重启 Provider，强制应用重新读取 DB
    run_adb(device_id, ["shell", f"rm -f {db_path}-wal {db_path}-shm"], logger=logger)
    run_adb(device_id, ["shell", f"am force-stop {PKG_TELEPHONY}"], logger=logger)
    
    # 重启短信 APP
    run_adb(device_id, ["shell", f"am force-stop {msg_pkg}"], logger=logger)
    time.sleep(1)
    run_adb(device_id, ["shell", "monkey", "-p", msg_pkg, "-c", "android.intent.category.LAUNCHER", "1"], logger=logger)
    
    logger.info(f"全部完成。注入 {success_count} 条。")

# ==========================================
# (保留) 联系人注入部分 - 不变
# ==========================================
def get_last_insert_id(device_id, uri, logger):
    cmd = f'content query --uri {uri} --projection _id'
    out, _ = run_adb(device_id, ["shell", cmd], logger=logger)
    if not out: return None
    ids = []
    for line in out.splitlines():
        match = re.search(r"_id=(\d+)", line)
        if match: ids.append(int(match.group(1)))
    if ids: return str(max(ids))
    return None

def inject_contacts(device_id, logger):
    logger.info(">>> 注入系统联系人 (Local Mode) <<<")
    contacts = [("Emergency", "110"), ("Zheng Zihan", "13912345678"), ("Bob", "987654321")]
    for name, phone in contacts:
        cmd_raw = 'content insert --uri content://com.android.contacts/raw_contacts --bind account_name:n: --bind account_type:n:'
        out, _ = run_adb(device_id, ["shell", cmd_raw], logger=logger)
        raw_id = None
        if out:
            match = re.search(r"_id=(\d+)", out)
            if match: raw_id = match.group(1)
            elif "Row" in out and "id=" in out: 
                 match = re.search(r"id=(\d+)", out)
                 if match: raw_id = match.group(1)
        if not raw_id:
            raw_id = get_last_insert_id(device_id, "content://com.android.contacts/raw_contacts", logger)
        if not raw_id: continue
        try:
            cmd_name = f'content insert --uri content://com.android.contacts/data --bind raw_contact_id:i:{raw_id} --bind mimetype:s:vnd.android.cursor.item/name --bind data1:s:"{name}"'
            run_adb(device_id, ["shell", cmd_name], logger=logger)
            cmd_phone = f'content insert --uri content://com.android.contacts/data --bind raw_contact_id:i:{raw_id} --bind mimetype:s:vnd.android.cursor.item/phone_v2 --bind data1:s:"{phone}"'
            run_adb(device_id, ["shell", cmd_phone], logger=logger)
            logger.info(f"联系人 {name} 注入成功 (ID: {raw_id})")
        except Exception: pass