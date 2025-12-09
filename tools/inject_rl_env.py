#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import os
import re
import time
import concurrent.futures
import tempfile
import sqlite3
import shutil

# ==============================================================================
# 配置区域
# ==============================================================================

ADB_PATH = "/home/zzh/Android/Sdk/platform-tools/adb"
CALENDAR_PKG = "com.simplemobiletools.calendar.pro"

# ==============================================================================
# 工具函数
# ==============================================================================

def run_command(command, timeout=60):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            encoding='utf-8'
        )
        if result.returncode != 0:
            return None, result.stderr.strip()
        return result.stdout.strip() if result.stdout else "Success", None
    except Exception as e:
        return None, str(e)

def log(device_id, message):
    print(f"[{device_id}] {message}")

def find_devices():
    output, _ = run_command([ADB_PATH, "devices"])
    devices = []
    if output:
        for line in output.splitlines()[1:]:
            if line.strip() and "device" in line:
                match = re.match(r"(\S+)\s+device", line)
                if match:
                    devices.append(match.group(1))
    return devices

# ==============================================================================
# 核心逻辑
# ==============================================================================

def trigger_app_db_creation(device_id):
    """模拟点击右下角，强制应用初始化 DB"""
    out, _ = run_command([ADB_PATH, "-s", device_id, "shell", "wm size"])
    width, height = 1080, 1920
    if out and "Physical size" in out:
        match = re.search(r"(\d+)x(\d+)", out)
        if match:
            width = int(match.group(1))
            height = int(match.group(2))
    
    # 点击右下角 FAB (Floating Action Button)
    x = int(width * 0.85)
    y = int(height * 0.90)
    run_command([ADB_PATH, "-s", device_id, "shell", f"input tap {x} {y}"])
    time.sleep(2)
    run_command([ADB_PATH, "-s", device_id, "shell", "input keyevent BACK"])

def wait_for_app_to_generate_db(device_id, remote_db_path, max_retries=5):
    for i in range(max_retries):
        ls_cmd = [ADB_PATH, "-s", device_id, "shell", f"ls -l {remote_db_path}"]
        out, err = run_command(ls_cmd)
        if out and "No such file" not in out:
            return True
        
        log(device_id, f"等待数据库生成 ({i+1}/{max_retries})...")
        trigger_app_db_creation(device_id)
        time.sleep(3)
    return False

def inject_data_and_merge_wal(local_db_path):
    """
    连接本地数据库，合并 WAL，并插入数据 (包含必填字段修复)。
    """
    try:
        conn = sqlite3.connect(local_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. 强制合并 WAL 文件
        cursor.execute("PRAGMA journal_mode=DELETE;")
        conn.commit()

        # 2. 检查表结构
        cursor.execute("PRAGMA table_info(events)")
        columns_info = cursor.fetchall()
        column_names = [info['name'] for info in columns_info]
        
        if not column_names:
            print("错误: 依然找不到 events 表")
            conn.close()
            return False

        # 3. 准备数据
        events_data = [
            (1760508000, "Project Review", "Review Phase 1", "Office"),      # 2025-10-15
            (1762828800, "Dentist Appointment", "Checkup", "Clinic"),        # 2025-11-11
            (1764561600, "Team Lunch", "Monthly Gathering", "Pizza Hut"),    # 2025-12-01
            (1747708800, "Dad's Birthday", "Buy gift", "Home"),              # 2025-05-20
            (1749264000, "Exam", "Room 303", "School"),                      # 2025-06-07
        ]

        current_time = int(time.time())

        # 4. [关键修复] 扩展目标列，包含所有可能的 NOT NULL 字段
        # 我们列出所有可能需要的字段，脚本会自动检查数据库里是否存在这些列
        target_cols_map = {
            'start_ts': None,
            'end_ts': None,
            'title': None,
            'description': None,
            'location': None,
            'event_type': 1,
            'display_event_type': 1, # 如果是新版APP可能需要，旧版可能不需要
            'last_updated': current_time,
            'source': 'imported-ics',
            'repeat_interval': 0,
            'repeat_rule': 0,
            'reminder_1_minutes': -1,
            'reminder_2_minutes': -1,
            'reminder_3_minutes': -1,
            # === 新增补充字段 ===
            'reminder_1_type': 0,      # 补充
            'reminder_2_type': 0,      # 补充
            'reminder_3_type': 0,      # 补充
            'repeat_limit': 0,         # 补充
            'repetition_exceptions': '[]', # 补充：空JSON数组字符串
            'attendees': '',           # 补充：空字符串
            'time_zone': 'Asia/Shanghai', # 补充：非常重要！或者使用 'UTC'，根据设备设置
            'availability': 0,         # 补充
            'color': 0,                # 补充
            # ===================
            'import_id': '0',
            'flags': 0,
            'type': 0,
            'parent_id': 0
        }

        # 过滤出当前数据库实际存在的列
        valid_cols = [c for c in target_cols_map.keys() if c in column_names]
        
        placeholders = ",".join(["?"] * len(valid_cols))
        sql = f"INSERT INTO events ({','.join(valid_cols)}) VALUES ({placeholders})"

        # 清理旧数据
        cursor.execute("DELETE FROM events")
        
        for start_ts, title, desc, loc in events_data:
            # 更新动态数据
            row_data = target_cols_map.copy()
            row_data['start_ts'] = start_ts
            row_data['end_ts'] = start_ts + 3600
            row_data['title'] = title
            row_data['description'] = desc
            row_data['location'] = loc
            
            # 按 valid_cols 的顺序提取参数值
            params = [row_data[c] for c in valid_cols]
            
            cursor.execute(sql, params)
            
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"数据库操作异常: {e}")
        return False

def setup_calendar(device_id, temp_dir):
    log(device_id, ">>> 开始配置 Simple Calendar Pro (v6 修复版) <<<")
    
    # 远程路径
    remote_db_dir = f"/data/data/{CALENDAR_PKG}/databases"
    remote_db_path = f"{remote_db_dir}/events.db"
    
    # 本地路径
    local_db_dir = os.path.join(temp_dir, f"db_{device_id}")
    os.makedirs(local_db_dir, exist_ok=True)
    
    # 注意：pull 目录时，adb 会在 local_db_dir 下创建一个名为 databases 的子目录（或者是 events.db 文件本身，取决于远程结构）
    # 为了稳妥，我们后续使用 find/walk 来定位文件
    
    # 1. 重置并授权
    run_command([ADB_PATH, "-s", device_id, "shell", "pm", "clear", CALENDAR_PKG])
    perms = [
        "android.permission.READ_CALENDAR",
        "android.permission.WRITE_CALENDAR",
        "android.permission.POST_NOTIFICATIONS"
    ]
    for p in perms:
        run_command([ADB_PATH, "-s", device_id, "shell", "pm", "grant", CALENDAR_PKG, p])

    # 2. 启动 App 并触发建库
    run_command([ADB_PATH, "-s", device_id, "shell", "monkey", "-p", CALENDAR_PKG, "-c", "android.intent.category.LAUNCHER", "1"])
    time.sleep(5)
    
    if not wait_for_app_to_generate_db(device_id, remote_db_path):
        log(device_id, "[!] DB生成失败")
        return

    # 3. 停止 App
    run_command([ADB_PATH, "-s", device_id, "shell", "am", "force-stop", CALENDAR_PKG])

    # 4. 拉取整个 databases 目录
    run_command([ADB_PATH, "-s", device_id, "pull", remote_db_dir, local_db_dir])
    
    # 查找 events.db
    actual_db_file = None
    for root, dirs, files in os.walk(local_db_dir):
        if "events.db" in files:
            actual_db_file = os.path.join(root, "events.db")
            break
            
    if not actual_db_file:
        log(device_id, f"[!] 拉取失败，未在 {local_db_dir} 找到 events.db")
        return

    log(device_id, f"本地数据库路径: {actual_db_file}")

    # 5. 注入数据 (含字段修复)
    if inject_data_and_merge_wal(actual_db_file):
        # 6. 删除远程所有旧文件
        run_command([ADB_PATH, "-s", device_id, "shell", f"rm -rf {remote_db_dir}/*"])
        
        # 7. 推送单文件
        run_command([ADB_PATH, "-s", device_id, "push", actual_db_file, remote_db_path])
        
        # 8. 修复权限
        uid_out, _ = run_command([ADB_PATH, "-s", device_id, "shell", f"dumpsys package {CALENDAR_PKG} | grep userId"])
        if uid_out:
            match = re.search(r"userId=(\d+)", uid_out)
            if match:
                uid = match.group(1)
                cmds = [
                    f"chown {uid}:{uid} {remote_db_dir}",
                    f"chown {uid}:{uid} {remote_db_path}",
                    f"chmod 770 {remote_db_dir}",
                    f"chmod 660 {remote_db_path}",
                    f"restorecon -R {remote_db_dir}"
                ]
                for cmd in cmds:
                    run_command([ADB_PATH, "-s", device_id, "shell", cmd])
        
        log(device_id, "✅ 日历注入成功 (WAL已合并)")
    else:
        log(device_id, "[!] 数据注入逻辑失败")

# ==============================================================================
# 其他辅助注入
# ==============================================================================

def inject_files(device_id, temp_dir):
    log(device_id, "注入文件...")
    f_map = {"budget.pdf": "Content", "notes.txt": "Notes", "todo.txt": "List"}
    run_command([ADB_PATH, "-s", device_id, "shell", "mkdir -p /sdcard/Documents"])
    for n, c in f_map.items():
        p = os.path.join(temp_dir, n)
        with open(p, "w") as f: f.write(c)
        run_command([ADB_PATH, "-s", device_id, "push", p, "/sdcard/Documents/"])

def inject_sms(device_id):
    if "emulator" in device_id:
        log(device_id, "注入 SMS...")
        run_command([ADB_PATH, "-s", device_id, "emu", "sms", "send", "123456", "Code_1234"])

def inject_photos(device_id, temp_dir):
    log(device_id, "注入照片...")
    p = os.path.join(temp_dir, "img.jpg")
    with open(p, "wb") as f: f.write(os.urandom(1024))
    run_command([ADB_PATH, "-s", device_id, "push", p, "/sdcard/Pictures/"])
    run_command([ADB_PATH, "-s", device_id, "shell", "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Pictures/img.jpg"])

# ==============================================================================
# 主入口
# ==============================================================================

def process_device(device_id):
    log(device_id, ">>> 开始处理 <<<")
    with tempfile.TemporaryDirectory() as temp_dir:
        run_command([ADB_PATH, "-s", device_id, "root"])
        
        setup_calendar(device_id, temp_dir)
        inject_files(device_id, temp_dir)
        inject_sms(device_id)
        inject_photos(device_id, temp_dir)
        
        run_command([ADB_PATH, "-s", device_id, "shell", "monkey", "-p", CALENDAR_PKG, "-c", "android.intent.category.LAUNCHER", "1"])
    log(device_id, "<<< 完成 <<<")

def main():
    if not os.path.exists(ADB_PATH): return
    devices = find_devices()
    if not devices: return
    print(f"处理 {len(devices)} 台设备")
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(devices)) as executor:
        executor.map(process_device, devices)

if __name__ == "__main__":
    main()