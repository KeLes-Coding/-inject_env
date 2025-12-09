# -*- coding: utf-8 -*-
import os

# ADB 路径 (请确认你的环境路径)
ADB_PATH = "/home/zzh/Android/Sdk/platform-tools/adb"

# ==================== 应用配置 ====================

# 1. Simple Calendar Pro
PKG_CALENDAR = "com.simplemobiletools.calendar.pro"
DB_CALENDAR_PATH = f"/data/data/{PKG_CALENDAR}/databases/events.db"

# 2. Tasks (Org.Tasks)
PKG_TASKS = "org.tasks"
DB_TASKS_PATH = f"/data/data/{PKG_TASKS}/databases/database"

# 3. Pro Expense
PKG_EXPENSE = "com.arduia.expense"
DB_EXPENSE_PATH = f"/data/data/{PKG_EXPENSE}/databases/accounting.db"

# 4. Markor
PKG_MARKOR = "net.gsantner.markor"
# Markor 默认存储位置，可能因设备而异，通常在 SD 卡
PATH_MARKOR_ROOT = "/sdcard/Documents/Markor"

# 5. Contacts (System)
PKG_CONTACTS = "com.google.android.contacts" # Google Contacts 或 com.android.contacts

# ==================== 系统配置 ====================

# 清理后台时的白名单 (正则)
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
    r"^com\.android\.providers", 
    r"^com\.google\.android\.inputmethod",
    # 避免杀掉正在测试的应用 (虽然逻辑中会单独处理，这里加一层保险)
    PKG_CALENDAR, PKG_TASKS, PKG_EXPENSE, PKG_MARKOR
]

# 日志根目录
LOG_ROOT_DIR = "logs"