import tkinter as tk
from tree_viewer import AdvancedSorterApp

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Smart System Sorter & Extension Gatherer")
    root.geometry("850x580")

    app = AdvancedSorterApp(root)
    app.pack(fill=tk.BOTH, expand=True)

    root.mainloop()