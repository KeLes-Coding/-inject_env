#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import os
import sys

# ==============================================================================
# 配置区域
# ==============================================================================

ADB_PATH = "/home/zzh/Android/Sdk/platform-tools/adb" # 请确保此路径正确
TARGET_DEVICE = "emulator-5556" # 指定检测设备

# 基于 Android World 源码优化的侦测目标
TARGETS = [
    {
        "name": "Calendar (Simple Calendar)",
        "pkg": "com.simplemobiletools.calendar.pro",
        "type": "db",
        "known_db": "events.db" # 源码指明
    },
    {
        "name": "Tasks (Org.Tasks)",
        "pkg": "org.tasks",
        "type": "db",
        "known_db": "database" # 常见默认名
    },
    {
        "name": "Expense (Pro Expense)",
        "pkg": "com.arduia.expense",
        "type": "db",
        "known_db": "accounting.db" # 源码指明
    },
    {
        "name": "Markor",
        "pkg": "net.gsantner.markor",
        "type": "file",
        "possible_paths": [
            "/sdcard/Documents/Markor", 
            "/sdcard/markor", 
            "/storage/emulated/0/Documents/Markor",
            "/data/user/0/net.gsantner.markor/files" # 内部存储备选
        ]
    }
]

# ==============================================================================
# 工具函数
# ==============================================================================

def run_command(command, timeout=30):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            encoding='utf-8'
        )
        return result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return "", str(e)

def inspect_db_structure(device_id, target):
    pkg_name = target["pkg"]
    print(f"\n🔍 [{target['name']}] 正在扫描数据库...")
    
    base_dir = f"/data/data/{pkg_name}/databases"
    
    # 1. 优先检查已知数据库名
    db_files = []
    if "known_db" in target:
        known_path = f"{base_dir}/{target['known_db']}"
        check_out, _ = run_command([ADB_PATH, "-s", device_id, "shell", f"ls {known_path}"])
        if check_out and "No such file" not in check_out:
            db_files.append(target['known_db'])
    
    # 2. 如果没找到或想看更多，扫描目录
    if not db_files:
        cmd_ls = [ADB_PATH, "-s", device_id, "shell", f"ls {base_dir}"]
        files_out, _ = run_command(cmd_ls)
        
        if "No such file" in files_out or not files_out:
            print(f"  ❌ 找不到目录: {base_dir} (应用可能未安装或从未启动)")
            return

        # 过滤掉日志文件
        candidates = [f for f in files_out.split() if not any(x in f for x in ['-journal', '-shm', '-wal'])]
        db_files.extend(candidates)

    if not db_files:
        print(f"  ⚠️  在 {base_dir} 下未发现数据库文件。")
        return

    print(f"  📂 发现数据库文件: {db_files}")

    # 3. 分析 Schema
    for db_file in db_files:
        full_path = f"{base_dir}/{db_file}"
        print(f"  👉 分析文件: {db_file}")
        
        # 获取所有表名
        sql_tables = "SELECT name FROM sqlite_master WHERE type='table';"
        cmd_schema = [ADB_PATH, "-s", device_id, "shell", f"sqlite3 {full_path} \"{sql_tables}\""]
        tables_out, err = run_command(cmd_schema)
        
        if "inaccessible" in err or "Permission denied" in err:
            print("  ❌ 权限不足，请确保 adb root 成功")
            continue

        tables = tables_out.splitlines()
        if not tables:
            print("     (空数据库或读取失败)")
        
        for table in tables:
            if table in ['android_metadata', 'sqlite_sequence', 'room_master_table']: continue
            
            print(f"    📋 表名: [{table}]")
            
            # 获取字段详情
            sql_cols = f"PRAGMA table_info({table});"
            cmd_cols = [ADB_PATH, "-s", device_id, "shell", f"sqlite3 {full_path} \"{sql_cols}\""]
            cols_out, _ = run_command(cmd_cols)
            
            if cols_out:
                print(f"       字段结构 (cid|name|type|notnull|dflt_value|pk):")
                for line in cols_out.splitlines():
                    print(f"       - {line}")
            else:
                print("       (无法读取列信息)")

def inspect_file_structure(device_id, target_config):
    print(f"\n🔍 [{target_config['name']}] 正在扫描存储路径...")
    found = False
    for path in target_config['possible_paths']:
        out, _ = run_command([ADB_PATH, "-s", device_id, "shell", f"ls -d {path}"])
        if out and "No such file" not in out:
            print(f"  ✅ 确认路径存在: {path}")
            ls_out, _ = run_command([ADB_PATH, "-s", device_id, "shell", f"ls -l {path} | head -n 5"])
            if ls_out:
                print("  📂 目录内容示例:")
                print(ls_out)
            found = True
            break
    
    if not found:
        print(f"  ❌ 未找到常见存储路径。")

def main():
    if not os.path.exists(ADB_PATH):
        print(f"ADB 路径错误: {ADB_PATH}")
        return

    # 检查设备连接
    out, _ = run_command([ADB_PATH, "devices"])
    if TARGET_DEVICE not in out:
        print(f"错误: 设备 {TARGET_DEVICE} 未连接或不在线。")
        print("当前设备列表:\n" + out)
        return

    print(f">>> 开始侦测设备: {TARGET_DEVICE} <<<")
    run_command([ADB_PATH, "-s", TARGET_DEVICE, "root"])
    
    for target in TARGETS:
        if target["type"] == "db":
            inspect_db_structure(TARGET_DEVICE, target)
        elif target["type"] == "file":
            inspect_file_structure(TARGET_DEVICE, target)
            
    print("\n<<< 侦测完成 <<<")

if __name__ == "__main__":
    main()