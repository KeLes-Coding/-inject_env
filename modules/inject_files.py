# -*- coding: utf-8 -*-
import os
from utils import run_adb, load_json_data

def inject_files_from_manifest(device_id, temp_dir, logger):
    logger.info(">>> 注入通用文件 (Source -> Device) <<<")
    
    # 读取 data/files_manifest.json
    manifest = load_json_data("files_manifest.json")
    if not manifest:
        logger.warning("未找到文件清单 files_manifest.json，跳过文件注入。")
        return

    for item in manifest:
        src_rel = item.get("source")
        remote_path = item.get("remote_path")
        metadata = item.get("metadata", {})
        
        if not src_rel or not remote_path:
            continue
            
        # 本地 source 目录
        src_path = os.path.join("source", src_rel)
        
        # 特殊处理：如果是 installer.zip 且需要生成大小
        if "installer.zip" in src_rel and metadata.get("size_mb") and not os.path.exists(src_path):
            logger.info(f"生成虚拟文件: {src_path}")
            os.makedirs(os.path.dirname(src_path), exist_ok=True)
            size = metadata["size_mb"] * 1024 * 1024
            with open(src_path, "wb") as f: f.write(os.urandom(size))

        if not os.path.exists(src_path):
            logger.warning(f"源文件缺失: {src_path} -> {remote_path}")
            continue
            
        # 创建远程目录
        remote_dir = os.path.dirname(remote_path)
        run_adb(device_id, ["shell", f"mkdir -p {remote_dir}"], logger=logger)
        
        # 推送文件
        run_adb(device_id, ["push", src_path, remote_path], logger=logger)
        
        # 处理元数据 (修改时间戳)
        if "touch_time" in metadata:
            # touch -t [[CC]YY]MMDDhhmm[.ss]
            ts = metadata["touch_time"]
            run_adb(device_id, ["shell", f"touch -t {ts} {remote_path}"], logger=logger)
            
    # 刷新媒体库
    logger.info("刷新媒体扫描...")
    run_adb(device_id, ["shell", "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/"], logger=logger)
    logger.info("文件注入完成。")