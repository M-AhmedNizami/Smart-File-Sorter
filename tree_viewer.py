import os
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from scanner_engine import scan_system_with_analytics
from snapshot_manager import SnapshotManager


class AdvancedSorterApp(ttk.Frame):

    def __init__(self, parent):
        super().__init__(parent, padding="10")

        self.snapshot_mgr = SnapshotManager()
        self.scan_data = None
        self.last_action_log = {}  # { new_path: original_path }

        self._build_top_controls()
        self._build_main_layout()

        # Initial setup check
        self.after(500, self._check_first_run)

    def _build_top_controls(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(top, text="Scan Depth:").pack(side=tk.LEFT, padx=(0, 5))
        self.depth_var = tk.IntVar(value=3)
        ttk.Spinbox(
            top,
            from_=1,
            to=5,
            textvariable=self.depth_var,
            width=3,
            state="readonly",
        ).pack(side=tk.LEFT, padx=(0, 10))

        self.scan_btn = ttk.Button(
            top, text="🔍 Scan & Analyze PC", command=self.start_scan
        )
        self.scan_btn.pack(side=tk.LEFT, padx=2)

        self.undo_btn = ttk.Button(
            top, text="⏪ Undo Last Gather", command=self.undo_gather
        )
        self.undo_btn.pack(side=tk.LEFT, padx=2)

        self.status_lbl = ttk.Label(
            top, text=" Status: Ready", font=("Arial", 9, "bold")
        )
        self.status_lbl.pack(side=tk.RIGHT, padx=5)

    def _build_main_layout(self):
        # Split view: Left = Extension Analytics, Right = Red-Flagged System Tree
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # 1. Left Panel: Analytics & Extension Gatherer
        left_frame = ttk.LabelFrame(
            paned, text=" File Type Analytics & Gather ", padding="10"
        )
        paned.add(left_frame, weight=1)

        self.stats_tree = ttk.Treeview(
            left_frame, columns=("count",), show="tree headings"
        )
        self.stats_tree.heading("#0", text="Extension")
        self.stats_tree.heading("count", text="Total Files")
        self.stats_tree.column("#0", width=110)
        self.stats_tree.column("count", width=80, anchor=tk.E)
        self.stats_tree.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        gather_btn = ttk.Button(
            left_frame,
            text="📦 Gather Selected Extension...",
            command=self.prompt_gather_extension,
        )
        gather_btn.pack(fill=tk.X)

        # 2. Right Panel: Tree View with Safety Colors
        right_frame = ttk.LabelFrame(
            paned, text=" Directory Tree Explorer ", padding="10"
        )
        paned.add(right_frame, weight=2)

        self.tree = ttk.Treeview(right_frame, selectmode="browse")
        self.tree.heading("#0", text=" System File Tree", anchor=tk.W)

        # Configure red warning tag for dangerous files/folders
        self.tree.tag_configure(
            "dangerous", foreground="red", font=("Arial", 9, "bold")
        )
        self.tree.tag_configure("safe", foreground="black")

        scrollbar = ttk.Scrollbar(
            right_frame, orient=tk.VERTICAL, command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)

    def _check_first_run(self):
        if self.snapshot_mgr.is_first_run():
            drives = ["C:\\"] if os.name == "nt" else ["/"]
            self.snapshot_mgr.prompt_first_time_setup(drives)

    def start_scan(self):
        self.scan_btn.config(state=tk.DISABLED)
        self.status_lbl.config(text=" Status: Analyzing files...")

        # Clear existing entries
        for item in self.tree.get_children():
            self.tree.delete(item)
        for item in self.stats_tree.get_children():
            self.stats_tree.delete(item)

        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        self.scan_data = scan_system_with_analytics(
            max_depth=self.depth_var.get()
        )
        self.after(0, self._render_results)

    def _render_results(self):
        # 1. Populate Analytics Table
        stats = self.scan_data["stats"]
        for ext, count in sorted(
            stats.items(), key=lambda x: x[1], reverse=True
        ):
            self.stats_tree.insert("", tk.END, text=ext, values=(f"{count:,}",))

        # 2. Populate Tree View with Safety Tags
        root_data = self.scan_data["tree"]
        root_node = self.tree.insert(
            "", tk.END, text=f" 💻 {root_data['name']}", open=True
        )
        self._populate_tree_nodes(root_node, root_data.get("children", []))

        self.status_lbl.config(text=" Status: Scan Complete!")
        self.scan_btn.config(state=tk.NORMAL)

    def _populate_tree_nodes(self, parent_node, children):
        for child in children:
            tag = "dangerous" if child.get("is_dangerous") else "safe"
            prefix = "⚠️ " if child.get("is_dangerous") else ""

            if child["type"] == "folder":
                display_text = f" {prefix}📁 {child['name']}"
                node = self.tree.insert(
                    parent_node,
                    tk.END,
                    text=display_text,
                    open=False,
                    tags=(tag,),
                )
                if child.get("children"):
                    self._populate_tree_nodes(node, child["children"])
            else:
                display_text = f" {prefix}📄 {child['name']}"
                self.tree.insert(
                    parent_node, tk.END, text=display_text, tags=(tag,)
                )

    def prompt_gather_extension(self):
        selected_item = self.stats_tree.selection()
        if not selected_item:
            messagebox.showwarning(
                "Selection Required",
                "Please select an extension from the left panel first (e.g., .png or .pdf).",
            )
            return

        ext = self.stats_tree.item(selected_item[0])["text"]
        file_paths = self.scan_data["extension_map"].get(ext, [])

        if not file_paths:
            messagebox.showinfo("Empty", f"No files found for {ext}")
            return

        # Target Folder Dialog
        dest_folder = filedialog.askdirectory(
            title=f"Select Destination Folder to Gather ALL '{ext}' Files"
        )
        if not dest_folder:
            return

        confirm = messagebox.askyesno(
            "Confirm Gathering",
            f"Found {len(file_paths)} files with extension '{ext}'.\n\n"
            f"Do you want to move all of them to:\n{dest_folder}?",
        )

        if confirm:
            self._execute_gather(file_paths, dest_folder)

    def _execute_gather(self, file_paths, dest_folder):
        moved_count = 0
        failed_count = 0
        self.last_action_log.clear()

        for src in file_paths:
            if not os.path.exists(src):
                failed_count += 1
                continue

            file_name = os.path.basename(src)
            dst = os.path.join(dest_folder, file_name)

            # Smart Renaming to avoid overwriting or skipping identical file names
            counter = 1
            base, extension = os.path.splitext(file_name)
            while os.path.exists(dst):
                dst = os.path.join(dest_folder, f"{base}_{counter}{extension}")
                counter += 1

            try:
                shutil.move(src, dst)
                self.last_action_log[dst] = src  # Track for Undo/Restate
                moved_count += 1
            except Exception as e:
                print(f"Permission Error moving {src}: {e}")
                failed_count += 1

        msg = f"Gathering Complete!\n\n Successfully Moved: {moved_count} personal files"
        if failed_count > 0:
            msg += f"\n Skipped/Locked: {failed_count} files"

        messagebox.showinfo("Gather Results", msg)
        self.start_scan()  # Refresh display

    def undo_gather(self):
        if not self.last_action_log:
            messagebox.showinfo(
                "No Actions", "No recent gather actions available to undo."
            )
            return

        self.snapshot_mgr.revert_last_sort(self.last_action_log)
        self.last_action_log.clear()
        self.start_scan()


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Smart System Sorter & Extension Gatherer")
    root.geometry("850x580")

    app = AdvancedSorterApp(root)
    app.pack(fill=tk.BOTH, expand=True)

    root.mainloop()