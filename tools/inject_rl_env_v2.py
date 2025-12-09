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

# 定义不应被清理的核心/安全包名正则表达式
SAFE_PACKAGES_REGEX = [
    r"^com\.android\.adbkeyboard$",      # ADB Keyboard
    r"^com\.android\.systemui$",         # 系统 UI
    r"^com\.android\.settings$",         # 设置
    r".*launcher.*",                     # 任何包含 "launcher" 的包名 (桌面)
    r"^com\.google\.android\.gms$",      # Google Play 服务
    r"^com\.android\.vending$",          # Google Play 商店
    r"^android$",                        # 核心操作系统包
    r"^com\.android\.inputmethod\.latin$", #以此类推，输入法等
    r"^com\.android\.shell$",
    r"^com\.android\.providers\.media$",
    r"^com\.android\.providers\.calendar$" # 避免清理系统日历存储服务，否则Calendar Pro可能读不到数据
]

# ==============================================================================
# 工具函数
# ==============================================================================

def run_command(command, timeout=60, check=False):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
            encoding='utf-8'
        )
        if result.returncode != 0 and not check:
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
# 清理与重置逻辑 (新增功能)
# ==============================================================================

def clean_background_apps(device_id, exclude_pkgs=None):
    """
    清理设备应用数据。
    :param exclude_pkgs: list, 需要跳过清理的包名列表（例如刚注入数据的应用）
    """
    if exclude_pkgs is None:
        exclude_pkgs = []
        
    log(device_id, f"开始清理应用数据 (跳过列表: {exclude_pkgs})...")
    
    # 1. 获取所有包名
    out, err = run_command([ADB_PATH, "-s", device_id, "shell", "pm", "list", "packages"])
    if not out:
        log(device_id, "未获取到包列表或发生错误")
        return

    all_packages = [line.split(":")[-1].strip() for line in out.splitlines() if line.startswith("package:")]
    
    cleared_count = 0
    skipped_count = 0

    for package_name in all_packages:
        if not package_name: 
            continue

        # 检查是否是系统/安全白名单
        is_system_safe = any(re.search(pattern, package_name) for pattern in SAFE_PACKAGES_REGEX)
        # 检查是否是本次任务指定的保留应用
        is_task_excluded = package_name in exclude_pkgs

        if is_system_safe or is_task_excluded:
            skipped_count += 1
            continue

        # 执行清理：先停止，再清除数据
        run_command([ADB_PATH, "-s", device_id, "shell", "am", "force-stop", package_name], timeout=10)
        
        # pm clear 会清除数据和权限，相当于重置应用
        # 注意：如果有特定应用只想杀后台不想清数据，逻辑需调整。这里按你的要求是"重置"。
        _, err = run_command([ADB_PATH, "-s", device_id, "shell", "pm", "clear", package_name], timeout=20)
        
        if not err:
            cleared_count += 1
        else:
            # 某些系统应用无法 clear，忽略错误
            pass

    log(device_id, f"清理完成。重置: {cleared_count}, 跳过: {skipped_count}")

def go_home(device_id):
    """回到桌面"""
    run_command([ADB_PATH, "-s", device_id, "shell", "input keyevent KEYCODE_HOME"])
    time.sleep(1)

# ==============================================================================
# 日历注入核心逻辑 (保持不变)
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
    连接本地数据库，合并 WAL，并插入数据。
    [健壮性修复]: 强制修复 event_types 表和 android_metadata，防止新设备空引用闪退。
    """
    try:
        conn = sqlite3.connect(local_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. 强制合并 WAL 文件 (防止模式冲突)
        cursor.execute("PRAGMA journal_mode=DELETE;")
        conn.commit()

        # ======================================================================
        # 🛡️ 修复 1: 确保 android_metadata 存在 (区域设置)
        # ======================================================================
        try:
            cursor.execute("CREATE TABLE IF NOT EXISTS android_metadata (locale TEXT)")
            cursor.execute("SELECT count(*) FROM android_metadata")
            if cursor.fetchone()[0] == 0:
                print("   [修复] 注入默认 locale: en_US")
                cursor.execute("INSERT INTO android_metadata (locale) VALUES ('en_US')")
        except Exception as e:
            print(f"   [警告] metadata 检查失败: {e}")

        # ======================================================================
        # 🛡️ 修复 2: 强制注入默认的 Event Type (防止外键引用闪退)
        # ======================================================================
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='event_types'")
        if cursor.fetchone():
            # 检查是否有 ID=1 的类型
            cursor.execute("SELECT count(*) FROM event_types WHERE id=1")
            if cursor.fetchone()[0] == 0:
                print("   [修复] event_types 表缺失 ID=1，正在补全...")
                # 根据你提供的表结构构造插入语句
                # 结构: id, title, color, caldav_calendar_id, caldav_display_name, caldav_email, type
                # 补充默认值: ID=1, Title=Regular, Color=-11226442 (Teal), Type=0
                
                # 动态获取列名以防止版本差异
                cursor.execute("PRAGMA table_info(event_types)")
                et_cols = [c['name'] for c in cursor.fetchall()]
                
                et_data = {
                    'id': 1,
                    'title': 'Regular',
                    'color': -11226442, # 一个默认颜色值
                    'caldav_calendar_id': 0,
                    'caldav_display_name': '',
                    'caldav_email': '',
                    'type': 0 # 0 usually means regular local category
                }
                
                valid_et_cols = [c for c in et_data.keys() if c in et_cols]
                et_placeholders = ",".join(["?"] * len(valid_et_cols))
                et_values = [et_data[c] for c in valid_et_cols]
                
                et_sql = f"INSERT INTO event_types ({','.join(valid_et_cols)}) VALUES ({et_placeholders})"
                cursor.execute(et_sql, et_values)
                conn.commit()
            else:
                print("   [检查] event_types ID=1 已存在，跳过。")
        else:
            print("   [严重警告] event_types 表不存在！数据库可能已损坏。")

        # ======================================================================
        # 3. 注入 Events 数据 (原逻辑优化)
        # ======================================================================
        
        # 检查 events 表结构
        cursor.execute("PRAGMA table_info(events)")
        columns_info = cursor.fetchall()
        column_names = [info['name'] for info in columns_info]
        
        if not column_names:
            print("错误: 找不到 events 表")
            conn.close()
            return False

        # 准备数据 (时间戳)
        events_data = [
            (1760508000, "Project Review", "Review Phase 1", "Office"),       # 2025-10-15
            (1762828800, "Dentist Appointment", "Checkup", "Clinic"),         # 2025-11-11
            (1764561600, "Team Lunch", "Monthly Gathering", "Pizza Hut"),     # 2025-12-01
            (1747708800, "Dad's Birthday", "Buy gift", "Home"),               # 2025-05-20
            (1749264000, "Exam", "Room 303", "School"),                       # 2025-06-07
        ]
        current_time = int(time.time())

        # 映射表: 确保 event_type=1 与上面的修复对应
        target_cols_map = {
            'start_ts': None, 'end_ts': None, 'title': None, 'description': None, 'location': None,
            'event_type': 1,  # <--- 关键：必须对应 event_types 表里的 ID
            'last_updated': current_time,
            'source': 'imported-ics',
            'repeat_interval': 0, 'repeat_rule': 0,
            'reminder_1_minutes': -1, 'reminder_2_minutes': -1, 'reminder_3_minutes': -1,
            'reminder_1_type': 0, 'reminder_2_type': 0, 'reminder_3_type': 0,
            'repeat_limit': 0, 'repetition_exceptions': '[]', 'attendees': '',
            'time_zone': 'Asia/Shanghai', 'availability': 0, 'color': 0,
            'import_id': '0', 'flags': 0, 'type': 0, 'parent_id': 0
        }

        # 动态过滤列
        valid_cols = [c for c in target_cols_map.keys() if c in column_names]
        placeholders = ",".join(["?"] * len(valid_cols))
        sql = f"INSERT INTO events ({','.join(valid_cols)}) VALUES ({placeholders})"

        # 清空旧数据
        cursor.execute("DELETE FROM events")
        
        # 批量插入
        for start_ts, title, desc, loc in events_data:
            row_data = target_cols_map.copy()
            row_data['start_ts'] = start_ts
            row_data['end_ts'] = start_ts + 3600
            row_data['title'] = title
            row_data['description'] = desc
            row_data['location'] = loc
            
            params = [row_data[c] for c in valid_cols]
            cursor.execute(sql, params)
            
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"数据库操作异常: {e}")
        import traceback
        traceback.print_exc() # 打印详细报错方便调试
        return False

def setup_calendar(device_id, temp_dir):
    log(device_id, ">>> 开始配置 Simple Calendar Pro (v6 修复版) <<<")
    
    # 远程路径
    remote_db_dir = f"/data/data/{CALENDAR_PKG}/databases"
    remote_db_path = f"{remote_db_dir}/events.db"
    
    # 本地路径
    local_db_dir = os.path.join(temp_dir, f"db_{device_id}")
    os.makedirs(local_db_dir, exist_ok=True)
    
    # 1. 重置并授权 (注意：虽然最开始清理过，但这里需要确保App干净并授予权限)
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
        
        # 1. 初始全量清理 (重置环境)
        # 不保留任何第三方应用，确保环境纯净
        log(device_id, "--- 步骤1: 环境初始化 (全量重置) ---")
        clean_background_apps(device_id, exclude_pkgs=[])
        
        # 2. 数据注入
        log(device_id, "--- 步骤2: 数据注入 ---")
        setup_calendar(device_id, temp_dir)
        inject_files(device_id, temp_dir)
        inject_sms(device_id)
        inject_photos(device_id, temp_dir)
        
        # 3. 启动应用查看效果 (可选，按照原逻辑保留)
        run_command([ADB_PATH, "-s", device_id, "shell", "monkey", "-p", CALENDAR_PKG, "-c", "android.intent.category.LAUNCHER", "1"])
        time.sleep(3) # 让应用跑一会

        # 4. 回到首页
        log(device_id, "--- 步骤3: 回到桌面并清理后台 ---")
        go_home(device_id)
        
        # 5. 最终后台清理 (白名单机制)
        # 这里我们将 CALENDAR_PKG 加入排除列表。
        # 意味着我们杀掉并重置所有其他应用，但保留我们刚刚辛苦注入的日历数据。
        # 如果你想连日历的后台进程也杀掉(但不清数据)，需要在 clean 函数里做更细致区分(kill vs clear)。
        # 当前 clean_background_apps 的逻辑是 pm clear (会清空数据)。
        # 因此必须将 CALENDAR_PKG 放入 exclude_pkgs 以保护数据。
        clean_background_apps(device_id, exclude_pkgs=[CALENDAR_PKG])
        
        # 额外：强制停止日历应用以释放内存（但不清除数据）
        run_command([ADB_PATH, "-s", device_id, "shell", "am", "force-stop", CALENDAR_PKG])

    log(device_id, "<<< 全部完成 <<<")

def main():
    if not os.path.exists(ADB_PATH): 
        print(f"Error: ADB not found at {ADB_PATH}")
        return
    devices = find_devices()
    if not devices: 
        print("未发现设备")
        return
    print(f"处理 {len(devices)} 台设备")
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(devices)) as executor:
        executor.map(process_device, devices)

if __name__ == "__main__":
    main()