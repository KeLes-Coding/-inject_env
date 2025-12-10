#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import os
import time
import sys
import logging
import shlex

# ==============================================================================
# 配置区域
# ==============================================================================

ADB_PATH = "/home/zzh/Android/Sdk/platform-tools/adb"
TARGET_DEVICE = "emulator-5556"

# 关键包名
PKG_TELEPHONY_PROVIDER = "com.android.providers.telephony"
PKG_PHONE = "com.android.phone"
PKG_MSG_APP = "com.google.android.apps.messaging"

# 路径
DB_DIR = f"/data/data/{PKG_TELEPHONY_PROVIDER}/databases"
DB_PATH = f"{DB_DIR}/mmssms.db"

# 日志
LOG_FILE = "inspect_sms.log"

# ==============================================================================
# 0. 日志系统
# ==============================================================================

def setup_logger():
    logger = logging.getLogger("SMS_Inspector")
    logger.setLevel(logging.DEBUG)
    if logger.hasHandlers(): logger.handlers.clear()
    
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
    
    fh = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger

logger = setup_logger()

# ==============================================================================
# 1. ADB 基础层
# ==============================================================================

def run_adb(cmd_list, timeout=20, ignore_error=False):
    cmd_str = " ".join(cmd_list)
    logger.debug(f"EXEC: {cmd_str}")
    try:
        result = subprocess.run(
            [ADB_PATH, "-s", TARGET_DEVICE] + cmd_list,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            encoding='utf-8'
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        
        if stdout: 
            log_out = stdout[:300] + "..." if len(stdout) > 300 else stdout
            logger.debug(f"  -> STDOUT: {log_out}")
        if stderr and not ignore_error: 
            # 过滤掉一些无关紧要的警告
            if "pulled" not in stderr and "pushed" not in stderr:
                logger.warning(f"  -> STDERR: {stderr}")
            
        return stdout, stderr
    except Exception as e:
        logger.error(f"  -> EXCEPTION: {e}")
        return "", str(e)

def run_shell(cmd, **kwargs):
    return run_adb(["shell", cmd], **kwargs)

# ==============================================================================
# 2. 远程 SQL 执行工具 (核心修改)
# ==============================================================================

def db_exec(sql):
    """直接在设备上执行 SQL (Write)"""
    # 转义双引号以免 shell 混淆
    safe_sql = sql.replace('"', '\\"')
    cmd = f"sqlite3 {DB_PATH} \"{safe_sql}\""
    out, err = run_shell(cmd)
    if "Error" in (out or "") or "Error" in (err or ""):
        logger.error(f"SQL Error: {err or out} | SQL: {sql}")
        return False
    return True

def db_query(sql):
    """直接在设备上查询 SQL (Read)"""
    safe_sql = sql.replace('"', '\\"')
    cmd = f"sqlite3 {DB_PATH} \"{safe_sql}\""
    out, _ = run_shell(cmd)
    return out.strip() if out else None

# ==============================================================================
# 3. 环境健康度检查与修复
# ==============================================================================

def get_pid(package_name):
    out, _ = run_shell(f"pidof {package_name}", ignore_error=True)
    if out:
        pids = out.split()
        if pids and pids[0].isdigit():
            return pids[0]
    return None

def kill_process_softly(package_name):
    pid = get_pid(package_name)
    if pid:
        logger.info(f"Killing {package_name} (PID: {pid})...")
        run_shell(f"kill {pid}")
        return True
    return False

def check_db_integrity():
    """检查数据库是否存在且包含必要的系统表"""
    # 直接在设备上查，避开本地 python 兼容性问题
    out = db_query("SELECT name FROM sqlite_master WHERE type='table';")
    if not out: return False
    
    tables = out.splitlines()
    required = ['sms', 'threads', 'canonical_addresses']
    missing = [t for t in required if t not in tables]
    
    if missing:
        logger.warning(f"Database Integrity Check: FAILED. Missing: {missing}")
        return False
    
    logger.info("✅ Database Integrity Check: PASS.")
    return True

def ensure_healthy_env():
    """环境自愈核心逻辑"""
    logger.info(">>> Step 1: 环境健康度检查 <<<")
    
    if get_pid(PKG_TELEPHONY_PROVIDER) and check_db_integrity():
        logger.info("Environment is healthy. Skipping rebuild.")
        return

    logger.warning("🚨 环境异常. 开始执行重建流程 (Fix Logic)...")
    
    # 1. 停止进程
    run_shell(f"am force-stop {PKG_TELEPHONY_PROVIDER}")
    run_shell(f"killall {PKG_PHONE}", ignore_error=True)
    
    # 2. 清理
    logger.info("Cleaning old database files...")
    run_shell(f"rm -f {DB_PATH} {DB_PATH}-wal {DB_PATH}-shm")
    
    # 3. 修复权限
    logger.info("Fixing permissions (1001:1001)...")
    run_shell(f"mkdir -p {DB_DIR}")
    run_shell(f"chown -R 1001:1001 {DB_DIR}")
    run_shell(f"chmod 771 {DB_DIR}")
    run_shell(f"restorecon -R {DB_DIR}")
    
    # 4. 踢醒系统 (启动 App + 发短信)
    logger.info(">>> Kicking Telephony Stack <<<")
    logger.info("Launching Messaging App...")
    run_shell(f"monkey -p {PKG_MSG_APP} -c android.intent.category.LAUNCHER 1")
    time.sleep(2)
    
    logger.info("Sending Trigger SMS...")
    run_adb(["emu", "sms", "send", "10086", "System_Init_Trigger"])
    
    # 5. 等待生成
    logger.info("Waiting for system to generate DB...")
    for i in range(15):
        time.sleep(1)
        if check_db_integrity():
            logger.info(f"✅ System DB generated (Attempt {i+1}).")
            return
            
    logger.error("❌ Failed to generate system DB after trigger.")

# ==============================================================================
# 4. 远程注入逻辑 (V12: On-Device Injection)
# ==============================================================================

def get_or_create_canonical_address_remote(address):
    # 1. Check
    sql_check = f"SELECT _id FROM canonical_addresses WHERE address = '{address}'"
    res = db_query(sql_check)
    if res and res.isdigit():
        return int(res)
    
    # 2. Insert
    db_exec(f"INSERT INTO canonical_addresses (address) VALUES ('{address}')")
    
    # 3. Fetch ID
    res = db_query(sql_check)
    return int(res) if res and res.isdigit() else None

def get_or_create_thread_remote(recipient_id):
    recip_str = str(recipient_id)
    # 1. Check
    sql_check = f"SELECT _id FROM threads WHERE recipient_ids = '{recip_str}'"
    res = db_query(sql_check)
    if res and res.isdigit():
        return int(res)
        
    # 2. Insert (Need timestamp)
    now = int(time.time() * 1000)
    # 这里的 snippet 只是占位，后面会更新
    sql_insert = (
        f"INSERT INTO threads (date, message_count, recipient_ids, read, type, error, has_attachment) "
        f"VALUES ({now}, 0, '{recip_str}', 1, 0, 0, 0)"
    )
    db_exec(sql_insert)
    
    # 3. Fetch ID
    res = db_query(sql_check)
    return int(res) if res and res.isdigit() else None

def perform_injection_remote():
    logger.info(">>> Step 2: 执行数据注入 (On-Device Mode) <<<")
    
    # 1. 清理旧数据 (保留表结构)
    logger.info("Clearing old data via ADB...")
    db_exec("DELETE FROM sms;")
    db_exec("DELETE FROM threads;")
    # canonical_addresses 不删，避免 ID 碎片化
    
    messages = [
        ("10086", "Welcome to Android service.", 0, 1),
        ("13800138000", "Hey, are we still on for dinner?", -3600000, 1),
        ("95588", "Your verification code is 8848.", -10000, 1),
        ("Mike", "I will be there in 5 mins.", 0, 1),
        ("13800138000", "Yes, see you at 7.", 0, 2) # Sent message
    ]
    
    now_ms = int(time.time() * 1000)
    count = 0
    
    for addr, body, offset, type_ in messages:
        # A. 获取关联 ID
        recip_id = get_or_create_canonical_address_remote(addr)
        if not recip_id:
            logger.error(f"Failed to get canonical ID for {addr}")
            continue
            
        tid = get_or_create_thread_remote(recip_id)
        if not tid:
            logger.error(f"Failed to get Thread ID for {addr}")
            continue
            
        # B. 插入 SMS
        # 转义单引号
        safe_body = body.replace("'", "''")
        ts = now_ms + offset
        
        sql_sms = (
            f"INSERT INTO sms (address, body, date, read, type, thread_id) "
            f"VALUES ('{addr}', '{safe_body}', {ts}, 1, {type_}, {tid})"
        )
        if db_exec(sql_sms):
            count += 1
            
            # C. 更新 Thread 摘要
            # 简化版：直接把最新这条作为摘要更新进去
            sql_update_thread = (
                f"UPDATE threads SET snippet = '{safe_body}', date = {ts}, message_count = message_count + 1 "
                f"WHERE _id = {tid}"
            )
            db_exec(sql_update_thread)
    
    logger.info(f"✅ Injected {count} messages directly on device.")
    
    # 2. 刷新缓存
    logger.info("Flushing WAL and refreshing...")
    # 清理 WAL 强迫写入主文件
    run_shell(f"rm -f {DB_PATH}-wal {DB_PATH}-shm")
    
    # 3. 软重启服务 (保活)
    # kill_process_softly(PKG_TELEPHONY)
    kill_process_softly(PKG_PHONE)
    
    # 4. 刷新 UI
    logger.info("Restarting Messaging App...")
    run_shell(f"am force-stop {PKG_MSG_APP}")
    time.sleep(1)
    run_shell(f"monkey -p {PKG_MSG_APP} -c android.intent.category.LAUNCHER 1")

# ==============================================================================
# 5. 结果验证
# ==============================================================================

def verify():
    logger.info(">>> Step 3: Verification <<<")
    
    # 检查进程
    if get_pid(PKG_TELEPHONY_PROVIDER):
        logger.info("✅ Telephony Process is ALIVE.")
    else:
        logger.warning("⚠️ Telephony Process NOT detected (Might be restarting).")
        
    # 检查数据
    sms_count = db_query("SELECT count(*) FROM sms;")
    thread_count = db_query("SELECT count(*) FROM threads;")
    
    logger.info(f"✅ Final SMS Count: {sms_count}")
    logger.info(f"✅ Final Threads Count: {thread_count}")
    
    if sms_count and sms_count.isdigit() and int(sms_count) > 0:
        logger.info("🎉 SUCCESS! Injection Verified.")
    else:
        logger.error("❌ FAILURE: DB is empty.")

# ==============================================================================
# Main
# ==============================================================================

if __name__ == "__main__":
    if not os.path.exists(ADB_PATH):
        print("ADB Path Error")
    else:
        logger.info(f"Starting V12 On-Device Injection Test on {TARGET_DEVICE}...")
        run_adb(["root"])
        time.sleep(1)
        
        ensure_healthy_env()
        perform_injection_remote()
        verify()