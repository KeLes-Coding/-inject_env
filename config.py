# -*- coding: utf-8 -*-
import os

# ADB 路径
ADB_PATH = "/home/zzh/Android/Sdk/platform-tools/adb"

# ==================== 应用配置 ====================
PKG_CALENDAR = "com.simplemobiletools.calendar.pro"
DB_CALENDAR_PATH = f"/data/data/{PKG_CALENDAR}/databases/events.db"

PKG_TASKS = "org.tasks"
DB_TASKS_PATH = f"/data/data/{PKG_TASKS}/databases/database"

PKG_EXPENSE = "com.arduia.expense"
DB_EXPENSE_PATH = f"/data/data/{PKG_EXPENSE}/databases/accounting.db"

PKG_MARKOR = "net.gsantner.markor"
PATH_MARKOR_ROOT = "/sdcard/Documents/Markor"

PKG_CONTACTS = "com.android.contacts" 

# [新增] 系统短信数据库路径
# 注意：在部分 Android 版本可能是 /data/user_de/0/... 但通常 /data/data/ 是通用的软链接
PKG_TELEPHONY = "com.android.providers.telephony"
DB_SMS_PATH = f"/data/data/{PKG_TELEPHONY}/databases/mmssms.db"

# ==================== 系统配置 ====================
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
    r"^com\.google\.android\.apps\.messaging", # 保护短信应用不被彻底清空数据
    PKG_CALENDAR, PKG_TASKS, PKG_EXPENSE, PKG_MARKOR
]

LOG_ROOT_DIR = "logs"