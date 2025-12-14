# modules/inject_system.py
# -*- coding: utf-8 -*-
import time
import re
from utils import run_adb
from config import PKG_TELEPHONY
from utils import run_adb, load_json_data # 导入 load_json_data

# ==============================================================================
# 配置与常量
# ==============================================================================

# 注意：部分设备可能使用 /data/user_de/0/，但 /data/data/ 通常是兼容的软链接
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
    required = ['sms', 'threads', 'canonical_addresses']
    return all(t in tables for t in required)

def ensure_sms_environment(device_id, logger):
    logger.info(">>> [SMS] 检查环境健康度...")
    
    if check_db_schema(device_id, logger):
        logger.info("  环境结构正常 (Schema OK)。")
        return

    logger.warning("  🚨 环境异常，执行强制重建...")
    
    # 1. 清理目录
    run_adb(device_id, ["shell", f"rm -rf {REMOTE_DB_DIR}"], logger=logger)
    run_adb(device_id, ["shell", f"mkdir -p {REMOTE_DB_DIR}"], logger=logger)
    # 2. 初始权限
    run_adb(device_id, ["shell", f"chown -R 1001:1001 {REMOTE_DB_DIR}"], logger=logger)
    run_adb(device_id, ["shell", f"chmod 771 {REMOTE_DB_DIR}"], logger=logger)
    run_adb(device_id, ["shell", f"restorecon -R {REMOTE_DB_DIR}"], logger=logger)
    
    # 3. 杀进程释放锁
    run_adb(device_id, ["shell", f"killall {PKG_PHONE}"], logger=logger)
    
    # 4. 触发建库
    logger.info("  激活系统建库...")
    run_adb(device_id, ["shell", f"monkey -p {PKG_MSG} -c android.intent.category.LAUNCHER 1"], logger=logger)
    time.sleep(2)
    run_adb(device_id, ["emu", "sms", "send", "10086", "System_Init_Trigger"], logger=logger)
    
    # 5. 等待
    for i in range(15):
        time.sleep(1)
        if check_db_schema(device_id, logger):
            logger.info(f"  ✅ 数据库重建成功 (耗时 {i+1}s)")
            return
            
    logger.error("  ❌ 重建超时。")

def fix_sms_permissions_recursive(device_id, logger):
    """
    [关键] 递归修复权限。
    必须使用 -R，否则可能漏掉 -journal 文件，导致 radio 用户无法写入/读取，
    从而导致 APP 看起来是空的。
    """
    logger.info("  [Permission] 递归修复数据库权限 (Owner: 1001:1001)...")
    # 1001 是 radio 用户，TelephonyProvider 运行在此用户下
    run_adb(device_id, ["shell", f"chown -R 1001:1001 {REMOTE_DB_DIR}"], logger=logger)
    run_adb(device_id, ["shell", f"chmod 771 {REMOTE_DB_DIR}"], logger=logger)
    # 数据库文件通常是 660
    run_adb(device_id, ["shell", f"chmod 660 {REMOTE_DB_PATH}"], logger=logger) 
    run_adb(device_id, ["shell", f"restorecon -R {REMOTE_DB_DIR}"], logger=logger)

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
        # 完整字段插入，防止 NULL 错误
        db_exec(device_id, f"INSERT INTO threads (date, message_count, recipient_ids, read, type, error, has_attachment) VALUES ({now}, 0, '{recipient_id}', 1, 0, 0, 0)", logger)
        res = db_query(device_id, f"SELECT _id FROM threads WHERE recipient_ids = '{recipient_id}'", logger)
        
    return res

def verify_data(device_id, logger):
    """验证数据是否真的写入了数据库"""
    sms_count = db_query(device_id, "SELECT count(*) FROM sms;", logger)
    thread_count = db_query(device_id, "SELECT count(*) FROM threads;", logger)
    
    logger.info(f"  [Verify] DB Rows -> SMS: {sms_count}, Threads: {thread_count}")
    
    if sms_count and sms_count.isdigit() and int(sms_count) > 0:
        return True
    return False

def inject_sms_msg(device_id, temp_dir, logger):
    logger.info(">>> 注入 SMS (V12.4) <<<")
    ensure_sms_environment(device_id, logger)
    
    sms_data = load_json_data("sms.json")
    if not sms_data:
        logger.error("无 SMS 数据配置。")
        return

    logger.info("  [Inject] 清空短信与会话表...")
    db_exec(device_id, "DELETE FROM sms;", logger)
    db_exec(device_id, "DELETE FROM threads;", logger)
    
    now_ms = int(time.time() * 1000)
    count = 0
    
    logger.info("  [Inject] 正在插入数据...")
    for item in sms_data:
        addr = item.get("address")
        body = item.get("body")
        offset = item.get("date_offset", 0)
        type_ = item.get("type", 1)
        
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
            sql_update = (
                f"UPDATE threads SET snippet = '{safe_body}', date = {ts}, message_count = message_count + 1 "
                f"WHERE _id = {tid}"
            )
            db_exec(device_id, sql_update, logger)
            
    logger.info(f"  SQL 执行完成，插入 {count} 条。")
    
    # 3. 验证数据 (防止假注入)
    if not verify_data(device_id, logger):
        logger.error("  ❌ 数据验证失败：数据库为空！")
        return

    # 4. 刷新缓存与修复权限
    logger.info("  [Inject] 刷新 WAL 并递归修复权限...")
    # 清理 WAL
    run_adb(device_id, ["shell", f"rm -f {REMOTE_DB_PATH}-wal {REMOTE_DB_PATH}-shm"], logger=logger)
    
    # [核心修复] 使用递归修复，确保 -journal 等文件也被归属给 radio
    fix_sms_permissions_recursive(device_id, logger)
    
    # 5. 重启服务与清除 UI 缓存
    logger.info("  [Restart] 重启服务与 UI...")
    
    # 软杀 TelephonyProvider 宿主
    kill_softly(device_id, PKG_PHONE, logger)
    
    # [关键新增] 清除短信 APP 的缓存 (不是数据)，强制其重新加载
    # 这一步可以解决"数据库有数据但APP显示为空"的问题
    run_adb(device_id, ["shell", f"pm clear {PKG_MSG}"], logger=logger)
    # 注意：pm clear com.google.android.apps.messaging 不会删除 mmssms.db，只会删除 APP 自己的设置和视图缓存
    
    # 启动 APP
    time.sleep(1)
    run_adb(device_id, ["shell", f"monkey -p {PKG_MSG} -c android.intent.category.LAUNCHER 1"], logger=logger)
    
    logger.info("✅ SMS 注入全部完成 (已执行 verify 与 pm clear)。")

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
    
    run_adb(device_id, ["shell", "content query --uri content://com.android.contacts/raw_contacts --projection _id"], logger=logger)
    
    # [修改] 改为从 JSON 文件读取
    contacts_data = load_json_data("contacts.json")
    if not contacts_data:
        logger.warning("未读取到 contacts.json，使用硬编码默认值")
        contacts_data = [
            {"name": "Emergency", "phone": "110"}, 
            {"name": "Zheng Zihan", "phone": "13912345678"}, 
            {"name": "Bob", "phone": "987654321"}
        ]
        
    for item in contacts_data:
        name = item.get("name")
        phone = item.get("phone")
        
        if not name or not phone:
            continue
            
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
    
    kill_softly(device_id, "android.process.acore", logger)
    run_adb(device_id, ["shell", "am force-stop com.android.contacts"], logger=logger)