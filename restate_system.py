import os
import shutil
from tkinter import messagebox

def restate_system_to_previous(action_log):
    """
    Restores all sorted files back to their exact previous state.
    `action_log` is a dictionary: { "new_path": "original_path" }
    """
    if not action_log:
        messagebox.showinfo("Restate System", "No recent changes detected to restore.")
        return

    restored_count = 0
    failed_count = 0

    for current_path, original_path in action_log.items():
        if os.path.exists(current_path):
            try:
                # 1. Ensure original directory exists
                original_dir = os.path.dirname(original_path)
                os.makedirs(original_dir, exist_ok=True)

                # 2. Move file back to exact previous state
                shutil.move(current_path, original_path)
                restored_count += 1
            except Exception as e:
                failed_count += 1
                print(f"Error restoring {current_path}: {e}")

    # 3. Clean up empty sorted directories left behind
    _cleanup_empty_folders(action_log)

    messagebox.showinfo(
        "Restate Complete", 
        f"System Restated Successfully!\n\n"
        f" Files Restored: {restored_count}\n"
        f" Failures: {failed_count}"
    )

def _cleanup_empty_folders(action_log):
    """Removes created category folders (e.g., Images/, Docs/) if left empty."""
    for current_path in action_log.keys():
        folder = os.path.dirname(current_path)
        if os.path.exists(folder) and not os.listdir(folder):
            try:
                os.rmdir(folder)
            except OSError:
                pass