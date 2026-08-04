import os
import string
import sys
from pathlib import Path

# Folders to COMPLETELY IGNORE (System junk, app assets, icons, caches)
IGNORE_SYSTEM_PATHS = {
    "windows", "program files", "program files (x86)", 
    "appdata", "programdata", "system volume information", 
    "$recycle.bin", "temp", "cache", ".cache", "node_modules",
    "vendor", "assets", "site-packages", "package"
}

# Image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico"}

def get_user_personal_directories():
    """Finds user personal directories (Desktop, Downloads, Pictures, Documents, etc.)"""
    user_home = Path.home()
    personal_folders = [
        user_home / "Downloads",
        user_home / "Desktop",
        user_home / "Pictures",
        user_home / "Documents",
        user_home / "Videos"
    ]
    # Add connected non-C drives (D:\, E:\) if available
    if sys.platform.startswith("win"):
        for letter in string.ascii_uppercase:
            if letter != "C":
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    personal_folders.append(Path(drive))
    
    return [p for p in personal_folders if p.exists()]

def scan_system_with_analytics(max_depth=4, min_file_size_kb=50):
    """
    Scans personal user directories, filters out tiny system icons (<50KB),
    and gives 100% accurate personal file records.
    """
    scan_result = {
        "tree": {"name": "User Space (Personal Files)", "type": "root", "children": []},
        "stats": {},
        "extension_map": {}
    }

    target_dirs = get_user_personal_directories()

    for target in target_dirs:
        dir_node = {
            "name": target.name if target.name else str(target),
            "path": str(target),
            "type": "folder",
            "is_dangerous": False,
            "children": []
        }

        def build_tree(current_path, current_dict, current_depth):
            if current_depth >= max_depth:
                return

            try:
                entries = sorted(os.listdir(current_path))
            except (PermissionError, FileNotFoundError):
                return

            for entry in entries:
                folder_lower = entry.lower()
                
                # SKIP SYSTEM JUNK & APP CACHES
                if folder_lower in IGNORE_SYSTEM_PATHS or folder_lower.startswith("."):
                    continue

                full_path = os.path.join(current_path, entry)
                is_dir = os.path.isdir(full_path)

                if is_dir:
                    child_item = {
                        "name": entry,
                        "path": full_path,
                        "type": "folder",
                        "is_dangerous": False,
                        "children": []
                    }
                    current_dict["children"].append(child_item)
                    if current_depth + 1 < max_depth:
                        build_tree(full_path, child_item, current_depth + 1)
                else:
                    ext = os.path.splitext(entry)[1].lower() or "No Extension"
                    
                    try:
                        file_size_kb = os.path.getsize(full_path) / 1024
                    except (PermissionError, FileNotFoundError):
                        continue

                    # FILTER OUT TINY SYSTEM ICONS (Anything smaller than 50 KB is usually an icon/button)
                    if ext in IMAGE_EXTENSIONS and file_size_kb < min_file_size_kb:
                        continue

                    # Update Analytics Memory
                    scan_result["stats"][ext] = scan_result["stats"].get(ext, 0) + 1
                    if ext not in scan_result["extension_map"]:
                        scan_result["extension_map"][ext] = []
                    scan_result["extension_map"][ext].append(full_path)

                    child_item = {
                        "name": entry,
                        "path": full_path,
                        "type": "file",
                        "ext": ext,
                        "is_dangerous": False
                    }
                    current_dict["children"].append(child_item)

        build_tree(str(target), dir_node, current_depth=0)
        scan_result["tree"]["children"].append(dir_node)

    return scan_result