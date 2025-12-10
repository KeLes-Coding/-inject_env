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
    r"^com\.android\.adbkeyboard$",      # ADB Keyboard
    r"^com\.android\.systemui$",         # 系统 UI
    r"^com\.android\.settings$",         # 设置
    r".*launcher.*",                     # 桌面 Launcher
    r"^com\.google\.android\.gms$",      # Google Play 服务
    r"^com\.android\.vending$",          # Google Play Store
    r"^android$",                        # Android 核心
    r"^com\.android\.shell$",            # Shell
    r"^com\.android\.inputmethod",       # 输入法
    r"^com\.google\.android\.inputmethod", # Gboard
    
    # --- 关键修改开始 ---
    # 原来的 r"^com\.android\.providers" 范围太广，导致短信和联系人无法被重置。
    # 改为仅保护系统运行必须的 Provider：
    r"^com\.android\.providers\.settings$",  # 系统设置存储 (必须保留)
    r"^com\.android\.providers\.media$",     # 媒体存储 (通常保留，避免铃声丢失，除非你想清空相册)
    r"^com\.android\.providers\.downloads$", # 下载管理 (建议保留)
    r"^com\.android\.providers\.ui$",        # 文档 UI
    # --- 关键修改结束 ---

    # 注意：不要把 PKG_CALENDAR 等目标应用放在这里，除非你想在清理阶段特意保留它们
    # 如果 PKG_CALENDAR 等在 Main 流程中通过 exclude_pkgs 传入，这里不需要列出
]

LOG_ROOT_DIR = "logs"
PKG_CALENDAR = "com.simplemobiletools.calendar.pro"
DB_CALENDAR_PATH = f"/data/data/{PKG_CALENDAR}/databases/events.db"
PKG_TASKS = "org.tasks"
DB_TASKS_PATH = f"/data/data/{PKG_TASKS}/databases/database"
PKG_EXPENSE = "com.arduia.expense"
DB_EXPENSE_PATH = f"/data/data/{PKG_EXPENSE}/databases/accounting.db"
PKG_MARKOR = "net.gsantner.markor"
PATH_MARKOR_ROOT = "/sdcard/Documents/Markor"
PKG_CONTACTS = "com.android.contacts" 
PKG_TELEPHONY = "com.android.providers.telephony"
DB_SMS_PATH = f"/data/data/{PKG_TELEPHONY}/databases/mmssms.db"
PKG_CONTACTS_STORAGE = "com.android.providers.contacts"