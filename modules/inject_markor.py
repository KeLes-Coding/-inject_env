# -*- coding: utf-8 -*-
import os
from utils import run_adb
from config import PKG_MARKOR, PATH_MARKOR_ROOT

def inject_markor_files(device_id, temp_dir, logger):
    logger.info(">>> 注入 Markor 文件 <<<")
    
    # 确保目录存在
    run_adb(device_id, ["shell", f"mkdir -p {PATH_MARKOR_ROOT}"], logger=logger)
    
    # 定义文件内容
    # T2-4: shopping_list.md (List: ..., Milk)
    # T2-5: meeting_minutes.txt ("Minute Taker: David")
    # T5-4: Budget.md ("Transport: 100")
    
    files = {
        "shopping_list.md": "## Shopping List\n- [ ] Eggs\n- [ ] Bread\n- [ ] Milk",
        "meeting_minutes.txt": "Meeting Date: 2025-10-10\nMinute Taker: David\n\nTopics:...",
        "Budget.md": "# Monthly Budget\n\n- Transport: 100\n- Food: 200"
    }
    
    for filename, content in files.items():
        local_path = os.path.join(temp_dir, filename)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        remote_path = f"{PATH_MARKOR_ROOT}/{filename}"
        run_adb(device_id, ["push", local_path, remote_path], logger=logger)
        
    # 刷新媒体扫描 (可选，对于 Markor 这种文件浏览型应用，通常重开即可看到)
    logger.info("Markor 文件注入完成。")