"""
苏绣轮廓生成器 — 入口
用法：
    python main.py
"""
import tkinter as tk

from gui import EmbroideryGUI


def main():
    root = tk.Tk()
    EmbroideryGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
