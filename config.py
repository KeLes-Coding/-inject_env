# -*- coding: utf-8 -*-
import os

# ADB 路径
ADB_PATH = "/home/zzh/Android/Sdk/platform-tools/adb"

# 目标应用包名
CALENDAR_PKG = "com.simplemobiletools.calendar.pro"

# 数据库远程路径
REMOTE_DB_DIR = f"/data/data/{CALENDAR_PKG}/databases"
REMOTE_DB_PATH = f"{REMOTE_DB_DIR}/events.db"

# 那些必须保留的系统应用正则 (清理后台时的白名单)
SAFE_PACKAGES_REGEX = [
    r"^com\.android\.adbkeyboard$",
    r"^com\.android\.systemui$",
    r"^com\.android\.settings$",
    r".*launcher.*",
    r"^com\.google\.android\.gms$",
    r"^com\.android\.vending$",
    r"^android$",
    r"^com\.android\.shell$",
    r"^com\.android\.inputmethod",
    r"^com\.android\.providers", # 关键：内容提供者不能杀
]

# 日志目录
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)