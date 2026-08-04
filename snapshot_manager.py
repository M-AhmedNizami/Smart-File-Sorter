import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from tkinter import messagebox


class SnapshotManager:

    def __init__(self, storage_dir="app_snapshots"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        self.master_snapshot_file = self.storage_dir / "master_snapshot.json"
        self.current_state_file = self.storage_dir / "latest_state.json"

    def is_first_run(self):
        return not self.master_snapshot_file.exists()

    def prompt_first_time_setup(self, target_drives):
        response = messagebox.askyesno(
            "Master Safety Capture Initializer",
            "Welcome! Would you like to create a Master System Safety Snapshot now?",
        )
        if response:
            self.capture_system_state(
                target_drives, is_master=True, max_depth=3
            )
            messagebox.showinfo(
                "Success", "Master Snapshot Created successfully!"
            )
            return True
        return False

    def capture_system_state(self, target_paths, is_master=False, max_depth=3):
        manifest = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "files": {},
        }
        for path_str in target_paths:
            base_path = Path(path_str)
            if not base_path.exists():
                continue
            base_depth = str(base_path).rstrip(os.sep).count(os.sep)
            for root, dirs, files in os.walk(base_path):
                cur_depth = root.count(os.sep) - base_depth
                if cur_depth >= max_depth:
                    dirs.clear()
                    continue
                for f in files:
                    full_p = Path(root) / f
                    manifest["files"][str(full_p)] = {
                        "name": f,
                        "dir": str(root),
                        "size": full_p.stat().st_size
                        if full_p.exists()
                        else 0,
                    }

        target_file = (
            self.master_snapshot_file if is_master else self.current_state_file
        )
        with open(target_file, "w") as f:
            json.dump(manifest, f, indent=4)

    # THIS IS THE CONNECTED RESTATE FUNCTION
    def revert_last_sort(self, action_log):
        if not action_log:
            messagebox.showinfo(
                "Restate System", "No recent file movements to undo."
            )
            return

        restored_count = 0
        failed_count = 0

        for current_path, original_path in action_log.items():
            if os.path.exists(current_path):
                try:
                    os.makedirs(os.path.dirname(original_path), exist_ok=True)
                    shutil.move(current_path, original_path)
                    restored_count += 1
                except Exception as e:
                    failed_count += 1

        # Cleanup empty sorted folders
        for current_path in action_log.keys():
            folder = os.path.dirname(current_path)
            if os.path.exists(folder) and not os.listdir(folder):
                try:
                    os.rmdir(folder)
                except OSError:
                    pass

        messagebox.showinfo(
            "System Restated",
            f"Restoration Complete!\n\nFiles Restored: {restored_count}\nErrors: {failed_count}",
        )