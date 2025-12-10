#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import subprocess
import time
import os
import sys

ADB_PATH = "/home/zzh/Android/Sdk/platform-tools/adb"
DEVICE_ID = "emulator-5556"
PKG_TELEPHONY = "com.android.providers.telephony"
DB_DIR = f"/data/data/{PKG_TELEPHONY}/databases"

def run_cmd(cmd):
    print(f"EXEC: {cmd}")
    subprocess.run([ADB_PATH, "-s", DEVICE_ID, "shell", cmd])

def fix_telephony_env():
    print(f">>> 开始修复 {DEVICE_ID} 的短信环境 <<<")
    
    # 1. 获得 Root
    subprocess.run([ADB_PATH, "-s", DEVICE_ID, "root"])
    time.sleep(1)

    # 2. 暴力清理：删除那个被 root 锁死的文件
    print("\n[Step 1] 清理损坏的数据库文件...")
    run_cmd(f"rm -f {DB_DIR}/mmssms.db")
    run_cmd(f"rm -f {DB_DIR}/mmssms.db-wal")
    run_cmd(f"rm -f {DB_DIR}/mmssms.db-shm")

    # 3. 权限修复：将目录还给 radio (UID 1001)
    print("\n[Step 2] 修复目录权限 (Owner: radio:radio)...")
    # 确保目录存在
    run_cmd(f"mkdir -p {DB_DIR}")
    # 关键：Telephony Provider 的 UID 是 1001 (radio)
    run_cmd(f"chown -R 1001:1001 {DB_DIR}") 
    run_cmd(f"chmod 771 {DB_DIR}")
    # 修复 SELinux 上下文 (非常重要)
    run_cmd(f"restorecon -R {DB_DIR}")

    # 4. 重启进程：杀掉 Telephony 相关进程让其自动重启
    print("\n[Step 3] 重启 Telephony 服务...")
    run_cmd("am force-stop com.android.providers.telephony")
    run_cmd("killall com.android.phone") # 杀掉电话进程以强制刷新
    
    print("    等待 5 秒让服务重生...")
    time.sleep(5)

    # 5. 检查进程是否活过来了
    print("\n[Step 4] 检查进程状态...")
    res = subprocess.run([ADB_PATH, "-s", DEVICE_ID, "shell", "ps -A | grep telephony"], capture_output=True, text=True)
    if "telephony" in res.stdout:
        print("✅ Telephony 进程已复活！")
    else:
        print("⚠️  警告：Telephony 进程似乎仍未启动，尝试手动发送短信激活...")

    # 6. 激活：发送一条短信
    print("\n[Step 5] 发送激活短信...")
    subprocess.run([ADB_PATH, "-s", DEVICE_ID, "emu", "sms", "send", "10086", "Hello_World_Fix"])
    
    print("    等待 5 秒数据库生成...")
    time.sleep(5)

    # 7. 最终验收
    print("\n[Step 6] 验收结果...")
    run_cmd(f"ls -l {DB_DIR}/mmssms.db")
    run_cmd(f"sqlite3 {DB_DIR}/mmssms.db 'SELECT count(*) FROM sms;'")

if __name__ == "__main__":
    fix_telephony_env()