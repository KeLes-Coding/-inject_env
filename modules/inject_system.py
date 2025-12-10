# modules/inject_system.py
# -*- coding: utf-8 -*-
import time
import re
from utils import run_adb
from config import PKG_TELEPHONY

# ==============================================================================
# 配置与常量
# ==============================================================================

REMOTE_DB_DIR = f"/data/data/{PKG_TELEPHONY}/databases"
REMOTE_DB_PATH = f"{REMOTE_DB_DIR}/mmssms.db"
PKG_PHONE = "com.android.phone"
PKG_MSG = "com.google.android.apps.messaging"

# ==============================================================================
# 基础工具
# ==============================================================================

def db_exec(device_id, sql, logger):
    """通过 ADB 在设备上直接执行 SQL"""
    safe_sql = sql.replace('"', '\\"')
    cmd = f"sqlite3 {REMOTE_DB_PATH} \"{safe_sql}\""
    out, err = run_adb(device_id, ["shell", cmd], logger=logger)
    if "Error" in (out or "") or "Error" in (err or ""):
        logger.error(f"SQL Error: {err or out} | SQL: {sql}")
        return False
    return True

def db_query(device_id, sql, logger):
    safe_sql = sql.replace('"', '\\"')
    cmd = f"sqlite3 {REMOTE_DB_PATH} \"{safe_sql}\""
    out, _ = run_adb(device_id, ["shell", cmd], logger=logger)
    return out.strip() if out else None

def get_pid(device_id, pkg_name, logger):
    out, _ = run_adb(device_id, ["shell", f"pidof {pkg_name}"], logger=logger)
    if out:
        return out.split()[0]
    return None

def kill_softly(device_id, pkg_name, logger):
    """软杀进程，触发自动重启"""
    pid = get_pid(device_id, pkg_name, logger)
    if pid:
        logger.info(f"  重启进程 {pkg_name} (PID: {pid})...")
        run_adb(device_id, ["shell", f"kill {pid}"], logger=logger)

# ==============================================================================
# 环境健康检查与自愈
# ==============================================================================

def check_db_schema(device_id, logger):
    out = db_query(device_id, "SELECT name FROM sqlite_master WHERE type='table';", logger)
    if not out: return False
    tables = out.splitlines()
    # 只要有这几个核心表就算系统已初始化
    required = ['sms', 'threads', 'canonical_addresses']
    return all(t in tables for t in required)

def ensure_sms_environment(device_id, logger):
    logger.info(">>> [SMS] 检查环境健康度...")
    
    # 检查表结构，如果完整则直接通过
    if check_db_schema(device_id, logger):
        logger.info("  环境正常，准备注入。")
        return

    logger.warning("  🚨 环境异常，执行强制激活流程...")
    
    # 1. 再次清理 (防止坏文件)
    run_adb(device_id, ["shell", f"rm -rf {REMOTE_DB_DIR}"], logger=logger)
    run_adb(device_id, ["shell", f"mkdir -p {REMOTE_DB_DIR}"], logger=logger)
    run_adb(device_id, ["shell", f"chown -R 1001:1001 {REMOTE_DB_DIR}"], logger=logger)
    run_adb(device_id, ["shell", f"chmod 771 {REMOTE_DB_DIR}"], logger=logger)
    run_adb(device_id, ["shell", f"restorecon -R {REMOTE_DB_DIR}"], logger=logger)
    
    # 2. 杀进程确保释放锁
    run_adb(device_id, ["shell", f"killall {PKG_PHONE}"], logger=logger)
    
    # 3. 启动 UI + 发送指令
    logger.info("  激活系统建库...")
    run_adb(device_id, ["shell", f"monkey -p {PKG_MSG} -c android.intent.category.LAUNCHER 1"], logger=logger)
    time.sleep(2)
    run_adb(device_id, ["emu", "sms", "send", "10086", "System_Init_Trigger"], logger=logger)
    
    # 4. 等待
    for i in range(15):
        time.sleep(1)
        if check_db_schema(device_id, logger):
            logger.info(f"  ✅ 数据库重建成功 (耗时 {i+1}s)")
            return
            
    logger.error("  ❌ 重建超时，注入可能失败。")

# ==============================================================================
# 数据注入
# ==============================================================================

def get_or_create_thread(device_id, addr, logger):
    # 1. Canonical Address
    res = db_query(device_id, f"SELECT _id FROM canonical_addresses WHERE address = '{addr}'", logger)
    if not (res and res.isdigit()):
        db_exec(device_id, f"INSERT INTO canonical_addresses (address) VALUES ('{addr}')", logger)
        res = db_query(device_id, f"SELECT _id FROM canonical_addresses WHERE address = '{addr}'", logger)
    
    recipient_id = res
    if not recipient_id: return None
    
    # 2. Thread
    res = db_query(device_id, f"SELECT _id FROM threads WHERE recipient_ids = '{recipient_id}'", logger)
    if not (res and res.isdigit()):
        now = int(time.time() * 1000)
        # 插入新会话，初始化 message_count=0
        db_exec(device_id, f"INSERT INTO threads (date, message_count, recipient_ids, read, type, snippet) VALUES ({now}, 0, '{recipient_id}', 1, 0, 'init')", logger)
        res = db_query(device_id, f"SELECT _id FROM threads WHERE recipient_ids = '{recipient_id}'", logger)
        
    return res

def inject_sms_msg(device_id, temp_dir, logger):
    logger.info(">>> 注入 SMS (V12.1: Full Clean) <<<")
    ensure_sms_environment(device_id, logger)
    
    # 1. 彻底清空数据 (包括地址表，防止ID错位)
    logger.info("  [Inject] 清空所有旧数据...")
    db_exec(device_id, "DELETE FROM sms;", logger)
    db_exec(device_id, "DELETE FROM threads;", logger)
    db_exec(device_id, "DELETE FROM canonical_addresses;", logger) # 关键新增！
    # 重置自增 ID (可选，让数据看起来更整洁)
    db_exec(device_id, "DELETE FROM sqlite_sequence WHERE name='sms' OR name='threads' OR name='canonical_addresses';", logger)
    
    # 2. 插入数据
    messages = [
        ("10086", "Welcome to Android service.", 0, 1),
        ("13800138000", "Hey, are we still on for dinner?", -3600000, 1),
        ("95588", "Your verification code is 8848.", -10000, 1),
        ("Mike", "I will be there in 5 mins.", 0, 1),
        ("13800138000", "Yes, see you at 7.", 0, 2)
    ]
    
    now_ms = int(time.time() * 1000)
    count = 0
    
    logger.info("  [Inject] 正在插入数据...")
    for addr, body, offset, type_ in messages:
        tid = get_or_create_thread(device_id, addr, logger)
        if not tid: continue
        
        ts = now_ms + offset
        safe_body = body.replace("'", "''")
        
        sql_sms = (
            f"INSERT INTO sms (address, body, date, read, type, thread_id) "
            f"VALUES ('{addr}', '{safe_body}', {ts}, 1, {type_}, {tid})"
        )
        
        if db_exec(device_id, sql_sms, logger):
            count += 1
            # 实时更新会话摘要，确保 UI 显示最新消息
            sql_update = (
                f"UPDATE threads SET snippet = '{safe_body}', date = {ts}, message_count = message_count + 1 "
                f"WHERE _id = {tid}"
            )
            db_exec(device_id, sql_update, logger)
            
    logger.info(f"  成功插入 {count} 条短信。")
    
    # 3. 刷新与重启
    logger.info("  [Inject] 刷新缓存并重启服务...")
    run_adb(device_id, ["shell", f"rm -f {REMOTE_DB_PATH}-wal {REMOTE_DB_PATH}-shm"], logger=logger)
    
    # 软重启 com.android.phone (他是大哥，重启他会带动 Telephony Provider)
    kill_softly(device_id, PKG_PHONE, logger)
    
    # 重启短信 App UI
    run_adb(device_id, ["shell", f"am force-stop {PKG_MSG}"], logger=logger)
    time.sleep(1)
    run_adb(device_id, ["shell", f"monkey -p {PKG_MSG} -c android.intent.category.LAUNCHER 1"], logger=logger)
    
    logger.info("✅ SMS 注入全部完成。")

# ==========================================
# 联系人注入 (保持不变)
# ==========================================
def get_last_insert_id(device_id, uri, logger):
    cmd = f'content query --uri {uri} --projection _id'
    out, _ = run_adb(device_id, ["shell", cmd], logger=logger)
    if not out: return None
    ids = []
    for line in out.splitlines():
        m = re.search(r"_id=(\d+)", line)
        if m: ids.append(int(m.group(1)))
    if ids: return str(max(ids))
    return None

def inject_contacts(device_id, logger):
    logger.info(">>> 注入系统联系人 (Fixed) <<<")
    # 清理旧数据，确保纯净 (可选，如果 Step 1 已经重置了这里其实是空的)
    # run_adb(device_id, ["shell", "pm clear com.android.providers.contacts"], logger=logger) # 注意：这会杀进程，慎用
    
    run_adb(device_id, ["shell", "content query --uri content://com.android.contacts/raw_contacts --projection _id"], logger=logger)
    contacts = [("Emergency", "110"), ("Zheng Zihan", "13912345678"), ("Bob", "987654321")]
    for name, phone in contacts:
        cmd_raw = 'content insert --uri content://com.android.contacts/raw_contacts --bind account_name:n: --bind account_type:n:'
        out, _ = run_adb(device_id, ["shell", cmd_raw], logger=logger)
        raw_id = None
        if out:
            match = re.search(r"_id=(\d+)", out)
            if match: raw_id = match.group(1)
        if not raw_id:
            raw_id = get_last_insert_id(device_id, "content://com.android.contacts/raw_contacts", logger)
        if not raw_id: continue
        
        cmd_name = (f'content insert --uri content://com.android.contacts/data --bind raw_contact_id:i:{raw_id} --bind mimetype:s:vnd.android.cursor.item/name --bind data1:s:"{name}"')
        run_adb(device_id, ["shell", cmd_name], logger=logger)
        
        cmd_phone = (f'content insert --uri content://com.android.contacts/data --bind raw_contact_id:i:{raw_id} --bind mimetype:s:vnd.android.cursor.item/phone_v2 --bind data1:s:"{phone}"')
        run_adb(device_id, ["shell", cmd_phone], logger=logger)
        logger.info(f"  已注入: {name} (ID: {raw_id})")
    
    # 重启联系人存储进程以刷新
    kill_softly(device_id, "android.process.acore", logger)
    run_adb(device_id, ["shell", "am force-stop com.android.contacts"], logger=logger)