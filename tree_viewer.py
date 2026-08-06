from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from scanner_engine import scan_system_with_analytics
from snapshot_manager import SnapshotManager

try:
    from PIL import Image, ImageTk

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

CATEGORIES = {
    "All": [],
    "Images": [
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".bmp",
        ".svg",
        ".ico",
    ],
    "Documents": [
        ".pdf",
        ".docx",
        ".doc",
        ".txt",
        ".pptx",
        ".xlsx",
        ".csv",
        ".rtf",
    ],
    "Code": [
        ".py",
        ".java",
        ".js",
        ".html",
        ".css",
        ".cpp",
        ".json",
        ".sql",
        ".php",
        ".c",
    ],
    "Media": [".mp3", ".mp4", ".mkv", ".wav", ".avi", ".mov", ".flv"],
    "Archives": [".zip", ".tar", ".gz", ".7z", ".rar", ".iso"],
}


class DeleteCommentDialog(tk.Toplevel):
    """Pop-up modal asking for confirmation and an optional deletion comment."""

    def __init__(self, parent, file_path, on_confirm_callback):
        super().__init__(parent)
        self.title("Confirm Soft Delete")
        self.geometry("450x220")
        self.resizable(False, False)

        self.file_path = file_path
        self.on_confirm_callback = on_confirm_callback

        self._build_ui()
        self.transient(parent)
        self.grab_set()

    def _build_ui(self):
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        file_name = os.path.basename(self.file_path)
        ttk.Label(
            frame,
            text=f"Move to 'File_Sorter_Deleted' Vault?",
            font=("Arial", 10, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            frame,
            text=f"Item: {file_name}",
            font=("Arial", 8),
            foreground="gray",
            wraplength=400,
        ).pack(anchor=tk.W, pady=(2, 10))

        ttk.Label(
            frame, text="Reason / Comment for deletion (Optional):"
        ).pack(anchor=tk.W)
        self.comment_entry = ttk.Entry(frame, width=50)
        self.comment_entry.pack(fill=tk.X, pady=(2, 15))
        self.comment_entry.focus_set()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(
            btn_frame, text="🗑️ Move to Vault", command=self._confirm
        ).pack(side=tk.RIGHT)

    def _confirm(self):
        comment = self.comment_entry.get().strip() or "No comment provided"
        self.on_confirm_callback(self.file_path, comment)
        self.destroy()


class DeletedVaultWindow(tk.Toplevel):
    """Window displaying all soft-deleted items with comments and restore actions."""

    def __init__(self, parent, vault_dir="File_Sorter_Deleted"):
        super().__init__(parent)
        self.title("File_Sorter_Deleted Vault Manager")
        self.geometry("800x480")

        self.parent_app = parent
        self.vault_dir = Path(vault_dir)
        self.vault_dir.mkdir(exist_ok=True)
        self.manifest_file = self.vault_dir / "vault_manifest.json"

        self._build_ui()
        self.load_vault_items()

    def _build_ui(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            main_frame,
            text="📁 Vault: File_Sorter_Deleted",
            font=("Arial", 11, "bold"),
        ).pack(anchor=tk.W, pady=(0, 5))
        ttk.Label(
            main_frame,
            text="Right-click any file below to Recover, Move, or Permanently Delete.",
            font=("Arial", 9, "italic"),
            foreground="gray",
        ).pack(anchor=tk.W, pady=(0, 10))

        # Vault Items Table
        columns = ("name", "comment", "date", "original_path")
        self.tree = ttk.Treeview(
            main_frame, columns=columns, show="headings", selectmode="browse"
        )

        self.tree.heading("name", text="File Name")
        self.tree.heading("comment", text="Deletion Comment")
        self.tree.heading("date", text="Deleted Date")
        self.tree.heading("original_path", text="Original Location")

        self.tree.column("name", width=150)
        self.tree.column("comment", width=220)
        self.tree.column("date", width=130)
        self.tree.column("original_path", width=250)

        scrollbar = ttk.Scrollbar(
            main_frame, orient=tk.VERTICAL, command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.tree.bind("<Button-3>", self._on_vault_right_click)

    def load_vault_items(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not self.manifest_file.exists():
            return

        with open(self.manifest_file, "r") as f:
            try:
                manifest = json.load(f)
            except Exception:
                manifest = {}

        for vault_id, data in manifest.items():
            self.tree.insert(
                "",
                tk.END,
                iid=vault_id,
                values=(
                    data["name"],
                    data["comment"],
                    data["date"],
                    data["original_path"],
                ),
            )

    def _on_vault_right_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        self.tree.selection_set(item_id)

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="♻️ Recover (Restore to Original Location)",
            command=lambda: self.recover_item(item_id),
        )
        menu.add_command(
            label="📦 Move To...", command=lambda: self.move_item(item_id)
        )
        menu.add_separator()
        menu.add_command(
            label="🔥 Permanently Delete",
            command=lambda: self.delete_permanently(item_id),
        )

        menu.tk_popup(event.x_root, event.y_root)

    def _get_manifest_data(self):
        if not self.manifest_file.exists():
            return {}
        with open(self.manifest_file, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return {}

    def _save_manifest_data(self, data):
        with open(self.manifest_file, "w") as f:
            json.dump(data, f, indent=4)

    def recover_item(self, vault_id):
        manifest = self._get_manifest_data()
        item_data = manifest.get(vault_id)
        if not item_data:
            return

        vault_path = self.vault_dir / item_data["vault_filename"]
        orig_path = item_data["original_path"]

        if not vault_path.exists():
            messagebox.showerror(
                "Error", "File no longer exists inside vault folder!"
            )
            return

        # Restore original directory structure if needed
        os.makedirs(os.path.dirname(orig_path), exist_ok=True)

        try:
            shutil.move(str(vault_path), orig_path)
            del manifest[vault_id]
            self._save_manifest_data(manifest)
            messagebox.showinfo(
                "Restored", f"Successfully recovered file back to:\n{orig_path}"
            )
            self.load_vault_items()
            self.parent_app.start_scan()  # Refresh live tree view
        except Exception as e:
            messagebox.showerror("Restore Error", f"Failed to restore file: {e}")

    def move_item(self, vault_id):
        manifest = self._get_manifest_data()
        item_data = manifest.get(vault_id)
        if not item_data:
            return

        vault_path = self.vault_dir / item_data["vault_filename"]
        dest_dir = filedialog.askdirectory(title="Select Destination Directory")
        if dest_dir:
            dest_path = os.path.join(dest_dir, item_data["name"])
            try:
                shutil.move(str(vault_path), dest_path)
                del manifest[vault_id]
                self._save_manifest_data(manifest)
                messagebox.showinfo(
                    "Moved", f"File moved to:\n{dest_path}"
                )
                self.load_vault_items()
                self.parent_app.start_scan()
            except Exception as e:
                messagebox.showerror("Move Error", f"Failed to move file: {e}")

    def delete_permanently(self, vault_id):
        confirm = messagebox.askyesno(
            "Permanent Delete Warning",
            "This will permanently erase the file from disk. Continue?",
            icon="warning",
        )
        if not confirm:
            return

        manifest = self._get_manifest_data()
        item_data = manifest.get(vault_id)
        if not item_data:
            return

        vault_path = self.vault_dir / item_data["vault_filename"]
        try:
            if vault_path.exists():
                if vault_path.is_dir():
                    shutil.rmtree(vault_path)
                else:
                    os.remove(vault_path)
            del manifest[vault_id]
            self._save_manifest_data(manifest)
            messagebox.showinfo("Deleted", "File permanently erased.")
            self.load_vault_items()
        except Exception as e:
            messagebox.showerror("Delete Error", f"Failed to delete file: {e}")


class FilePreviewWindow(tk.Toplevel):

    def __init__(self, parent, file_paths, extension_name, on_move_callback):
        super().__init__(parent)
        self.title(
            f"Previewing '{extension_name}' Files ({len(file_paths)} files)"
        )
        self.geometry("700x550")

        self.file_paths = file_paths
        self.current_idx = 0
        self.on_move_callback = on_move_callback
        self.current_img = None

        self._build_ui()
        self.bind("<Left>", lambda e: self.prev_file())
        self.bind("<Right>", lambda e: self.next_file())
        self.focus_set()

        self.show_current_file()

    def _build_ui(self):
        top_bar = ttk.Frame(self, padding=10)
        top_bar.pack(fill=tk.X)

        self.counter_lbl = ttk.Label(
            top_bar, text="", font=("Arial", 10, "bold")
        )
        self.counter_lbl.pack(side=tk.LEFT)

        ttk.Label(
            top_bar,
            text=" Use  ←  and  →  Arrow Keys to Navigate ",
            font=("Arial", 9, "italic"),
            foreground="gray",
        ).pack(side=tk.RIGHT)

        info_frame = ttk.Frame(self, padding=(10, 0))
        info_frame.pack(fill=tk.X)

        self.path_lbl = ttk.Label(
            info_frame, text="", font=("Arial", 8), wraplength=680
        )
        self.path_lbl.pack(anchor=tk.W)

        self.preview_frame = ttk.Frame(self, padding=10)
        self.preview_frame.pack(fill=tk.BOTH, expand=True)

        self.display_lbl = ttk.Label(
            self.preview_frame, text="Loading preview...", anchor=tk.CENTER
        )
        self.display_lbl.pack(fill=tk.BOTH, expand=True)

        btn_bar = ttk.Frame(self, padding=10)
        btn_bar.pack(fill=tk.X)

        ttk.Button(btn_bar, text="◀ Previous", command=self.prev_file).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(btn_bar, text="Next ▶", command=self.next_file).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Button(
            btn_bar,
            text="📦 Move ALL These Files...",
            command=self._move_all,
        ).pack(side=tk.RIGHT, padx=5)
        ttk.Button(
            btn_bar,
            text="🎯 Move THIS File Only...",
            command=self._move_current,
        ).pack(side=tk.RIGHT, padx=5)

    def show_current_file(self):
        if not self.file_paths:
            self.display_lbl.config(text="No files left to display.")
            return

        current_path = self.file_paths[self.current_idx]
        file_name = os.path.basename(current_path)

        self.counter_lbl.config(
            text=f"File {self.current_idx + 1} of {len(self.file_paths)}: {file_name}"
        )
        self.path_lbl.config(text=f"Path: {current_path}")

        ext = os.path.splitext(file_name)[1].lower()
        if HAS_PIL and ext in {
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".bmp",
        }:
            try:
                img = Image.open(current_path)
                img.thumbnail((500, 350))
                self.current_img = ImageTk.PhotoImage(img)
                self.display_lbl.config(image=self.current_img, text="")
            except Exception as e:
                self.display_lbl.config(
                    image="", text=f"📄 [Image Preview Error: {e}]"
                )
        else:
            size_kb = (
                round(os.path.getsize(current_path) / 1024, 1)
                if os.path.exists(current_path)
                else 0
            )
            self.display_lbl.config(
                image="",
                text=f"📄 {file_name}\n\nType: {ext.upper()}\nSize: {size_kb} KB\n\n(Use Move button below to organize)",
                font=("Arial", 11),
            )

    def prev_file(self):
        if self.file_paths:
            self.current_idx = (self.current_idx - 1) % len(self.file_paths)
            self.show_current_file()

    def next_file(self):
        if self.file_paths:
            self.current_idx = (self.current_idx + 1) % len(self.file_paths)
            self.show_current_file()

    def _move_current(self):
        if not self.file_paths:
            return
        dest = filedialog.askdirectory(title="Select Destination Folder")
        if dest:
            file_to_move = self.file_paths[self.current_idx]
            self.on_move_callback([file_to_move], dest)
            self.file_paths.remove(file_to_move)
            if self.file_paths:
                self.current_idx %= len(self.file_paths)
                self.show_current_file()
            else:
                self.destroy()

    def _move_all(self):
        if not self.file_paths:
            return
        dest = filedialog.askdirectory(title="Select Destination Folder")
        if dest:
            self.on_move_callback(list(self.file_paths), dest)
            self.destroy()


class AdvancedSorterApp(ttk.Frame):

    def __init__(self, parent):
        super().__init__(parent, padding="10")

        self.snapshot_mgr = SnapshotManager()
        self.scan_data = None
        self.last_action_log = {}
        self.node_path_map = {}

        self.vault_dir = Path("File_Sorter_Deleted")
        self.vault_dir.mkdir(exist_ok=True)
        self.vault_manifest = self.vault_dir / "vault_manifest.json"

        self._build_top_controls()
        self._build_main_layout()
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

        # BUTTON TO OPEN DELETED VAULT
        self.vault_btn = ttk.Button(
            top, text="🗑️ Deleted Vault", command=self.open_deleted_vault
        )
        self.vault_btn.pack(side=tk.LEFT, padx=2)

        self.status_lbl = ttk.Label(
            top, text=" Status: Ready", font=("Arial", 9, "bold")
        )
        self.status_lbl.pack(side=tk.RIGHT, padx=5)

    def _build_main_layout(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.LabelFrame(
            paned, text=" File Type Analytics ", padding="10"
        )
        paned.add(left_frame, weight=1)

        filter_bar = ttk.Frame(left_frame)
        filter_bar.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(filter_bar, text="Search:").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 2)
        )
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.apply_extension_filter)
        search_entry = ttk.Entry(
            filter_bar, textvariable=self.search_var, width=12
        )
        search_entry.grid(row=0, column=1, sticky=tk.W, padx=(0, 5))

        ttk.Label(filter_bar, text="Cat:").grid(
            row=0, column=2, sticky=tk.W, padx=(0, 2)
        )
        self.cat_var = tk.StringVar(value="All")
        cat_combo = ttk.Combobox(
            filter_bar,
            textvariable=self.cat_var,
            values=list(CATEGORIES.keys()),
            state="readonly",
            width=10,
        )
        cat_combo.grid(row=0, column=3, sticky=tk.W)
        cat_combo.bind(
            "<<ComboboxSelected>>", lambda e: self.apply_extension_filter()
        )

        self.stats_tree = ttk.Treeview(
            left_frame, columns=("count",), show="tree headings"
        )
        self.stats_tree.heading("#0", text="Extension")
        self.stats_tree.heading("count", text="Total Files")
        self.stats_tree.column("#0", width=110)
        self.stats_tree.column("count", width=80, anchor=tk.E)
        self.stats_tree.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        ttk.Button(
            left_frame,
            text="👁️ View / Preview Files (Arrow Keys)",
            command=self.open_file_preview,
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            left_frame,
            text="📦 Move All to Directory...",
            command=self.prompt_gather_extension,
        ).pack(fill=tk.X, pady=2)

        right_frame = ttk.LabelFrame(
            paned, text=" Directory Tree Explorer ", padding="10"
        )
        paned.add(right_frame, weight=2)

        self.tree = ttk.Treeview(right_frame, selectmode="browse")
        self.tree.heading("#0", text=" System File Tree", anchor=tk.W)

        self.tree.tag_configure(
            "dangerous", foreground="red", font=("Arial", 9, "bold")
        )
        self.tree.tag_configure("safe", foreground="black")

        self.tree.bind("<Button-3>", self._on_tree_right_click)

        scrollbar = ttk.Scrollbar(
            right_frame, orient=tk.VERTICAL, command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)

    def open_deleted_vault(self):
        """Launches the Deleted Vault window."""
        DeletedVaultWindow(self)

    def _on_tree_right_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        self.tree.selection_set(item_id)
        path = self.node_path_map.get(item_id)
        if not path:
            return

        context_menu = tk.Menu(self, tearoff=0)
        context_menu.add_command(
            label="📂 Open Location", command=lambda: self._open_location(path)
        )
        context_menu.add_command(
            label="📋 Copy Path", command=lambda: self._copy_path(path)
        )
        context_menu.add_separator()
        context_menu.add_command(
            label="📦 Move To...", command=lambda: self._move_single_item(path)
        )
        context_menu.add_command(
            label="🗑️ Delete (Soft-Delete to Vault)",
            command=lambda: self._delete_single_item(path),
        )

        context_menu.tk_popup(event.x_root, event.y_root)

    def _open_location(self, path):
        if not os.path.exists(path):
            return
        folder = os.path.dirname(path) if os.path.isfile(path) else path
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.run(["open", folder])
        else:
            subprocess.run(["xdg-open", folder])

    def _copy_path(self, path):
        self.clipboard_clear()
        self.clipboard_append(path)
        messagebox.showinfo("Copied", f"Path copied to clipboard:\n{path}")

    def _move_single_item(self, src_path):
        if not os.path.exists(src_path):
            return
        dest_dir = filedialog.askdirectory(
            title="Select Destination Directory"
        )
        if dest_dir:
            self._execute_gather([src_path], dest_dir)

    def _delete_single_item(self, path):
        """Triggers Delete Comment Dialog instead of permanent delete."""
        if not os.path.exists(path):
            return
        DeleteCommentDialog(self, path, self._process_soft_delete)

    def _process_soft_delete(self, path, comment):
        """Moves file to File_Sorter_Deleted folder and logs comment."""
        file_name = os.path.basename(path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        vault_filename = f"{timestamp}_{file_name}"
        vault_dest = self.vault_dir / vault_filename

        try:
            shutil.move(path, str(vault_dest))

            # Update vault_manifest.json
            manifest = {}
            if self.vault_manifest.exists():
                with open(self.vault_manifest, "r") as f:
                    try:
                        manifest = json.load(f)
                    except Exception:
                        manifest = {}

            vault_id = f"item_{timestamp}"
            manifest[vault_id] = {
                "name": file_name,
                "vault_filename": vault_filename,
                "original_path": path,
                "comment": comment,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            with open(self.vault_manifest, "w") as f:
                json.dump(manifest, f, indent=4)

            messagebox.showinfo(
                "Moved to Vault",
                f"File moved to 'File_Sorter_Deleted' vault!\n\nComment: {comment}",
            )
            self.start_scan()  # Refresh live view
        except Exception as e:
            messagebox.showerror(
                "Delete Error", f"Could not move item to vault: {e}"
            )

    def apply_extension_filter(self, *args):
        if not self.scan_data or "stats" not in self.scan_data:
            return

        query = self.search_var.get().strip().lower()
        selected_cat = self.cat_var.get()
        allowed_exts = CATEGORIES.get(selected_cat, [])

        for item in self.stats_tree.get_children():
            self.stats_tree.delete(item)

        stats = self.scan_data["stats"]
        for ext, count in sorted(
            stats.items(), key=lambda x: x[1], reverse=True
        ):
            if selected_cat != "All" and ext not in allowed_exts:
                continue
            if query and query not in ext:
                continue
            self.stats_tree.insert("", tk.END, text=ext, values=(f"{count:,}",))

    def _check_first_run(self):
        if self.snapshot_mgr.is_first_run():
            drives = ["C:\\"] if os.name == "nt" else ["/"]
            self.snapshot_mgr.prompt_first_time_setup(drives)

    def start_scan(self):
        self.scan_btn.config(state=tk.DISABLED)
        self.status_lbl.config(text=" Status: Analyzing files...")

        self.node_path_map.clear()
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
        self.apply_extension_filter()

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
                self.node_path_map[node] = child["path"]
                if child.get("children"):
                    self._populate_tree_nodes(node, child["children"])
            else:
                display_text = f" {prefix}📄 {child['name']}"
                node = self.tree.insert(
                    parent_node, tk.END, text=display_text, tags=(tag,)
                )
                self.node_path_map[node] = child["path"]

    def open_file_preview(self):
        selected_item = self.stats_tree.selection()
        if not selected_item:
            messagebox.showwarning(
                "Select Extension",
                "Please select an extension from the table first.",
            )
            return

        ext = self.stats_tree.item(selected_item[0])["text"]
        file_paths = self.scan_data["extension_map"].get(ext, [])

        if not file_paths:
            messagebox.showinfo("Empty", f"No files found for {ext}")
            return

        FilePreviewWindow(self, list(file_paths), ext, self._execute_gather)

    def prompt_gather_extension(self):
        selected_item = self.stats_tree.selection()
        if not selected_item:
            messagebox.showwarning(
                "Select Extension",
                "Please select an extension from the table first.",
            )
            return

        ext = self.stats_tree.item(selected_item[0])["text"]
        file_paths = self.scan_data["extension_map"].get(ext, [])

        if not file_paths:
            messagebox.showinfo("Empty", f"No files found for {ext}")
            return

        dest_folder = filedialog.askdirectory(
            title=f"Select Destination Folder for '{ext}' Files"
        )
        if dest_folder:
            self._execute_gather(file_paths, dest_folder)

    def _execute_gather(self, file_paths, dest_folder):
        moved_count = 0
        self.last_action_log.clear()

        for src in file_paths:
            if not os.path.exists(src):
                continue

            file_name = os.path.basename(src)
            dst = os.path.join(dest_folder, file_name)

            counter = 1
            base, extension = os.path.splitext(file_name)
            while os.path.exists(dst):
                dst = os.path.join(dest_folder, f"{base}_{counter}{extension}")
                counter += 1

            try:
                shutil.move(src, dst)
                self.last_action_log[dst] = src
                moved_count += 1
            except Exception as e:
                print(f"Error moving {src}: {e}")

        messagebox.showinfo(
            "Moved", f"Successfully moved {moved_count} files into '{dest_folder}'!"
        )
        self.start_scan()

    def undo_gather(self):
        if not self.last_action_log:
            messagebox.showinfo("No Actions", "No recent gather actions to undo.")
            return
        self.snapshot_mgr.revert_last_sort(self.last_action_log)
        self.last_action_log.clear()
        self.start_scan()


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Smart Sorter - Explorer & Safe Delete Vault")
    root.geometry("960x620")

    app = AdvancedSorterApp(root)
    app.pack(fill=tk.BOTH, expand=True)

    root.mainloop()