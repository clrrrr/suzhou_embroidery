"""
ME 文件查看器 - 可视化 HP ME10 CAD 格式
"""
import gzip
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageDraw, ImageTk


class MEViewer(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("ME 文件查看器")
        self.geometry("960x700")
        self.minsize(600, 400)

        self._base_image = None
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._drag_start = None
        self._tk_img = None

        self._points = {}  # {id: (x, y)}
        self._lines = []   # [(pt1_id, pt2_id), ...]

        self._build_ui()

    def _build_ui(self):
        # 工具栏
        bar = ttk.Frame(self, padding=(6, 4))
        bar.pack(fill=tk.X, side=tk.TOP)

        ttk.Button(bar, text="打开 ME…", command=self._open).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=(0, 4))

        ttk.Button(bar, text="－", command=self._zoom_out, width=3).pack(side=tk.LEFT)
        self._zoom_lbl = ttk.Label(bar, text="—", width=7, anchor=tk.CENTER)
        self._zoom_lbl.pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="＋", command=self._zoom_in, width=3).pack(side=tk.LEFT)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=(6, 4))
        ttk.Button(bar, text="适合窗口", command=self._fit).pack(side=tk.LEFT)

        self._info_lbl = ttk.Label(bar, text="请打开 ME 文件", foreground="#666")
        self._info_lbl.pack(side=tk.RIGHT, padx=8)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # 画布
        self._canvas = tk.Canvas(self, bg="#e8e8e8", cursor="fleur", highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # 事件绑定
        self._canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", lambda _: setattr(self, "_drag_start", None))
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<Button-4>", self._on_wheel)
        self._canvas.bind("<Button-5>", self._on_wheel)
        self._canvas.bind("<Configure>", lambda _: self._redraw())

    def _open(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="打开 ME 文件",
            filetypes=[("ME CAD 文件", "*.me"), ("所有文件", "*.*")],
        )
        if path:
            self._load(path)

    def _load(self, path: str):
        try:
            self._points, self._lines = self._parse_me(path)
            if not self._points:
                raise ValueError("文件中没有找到点数据")

            self._base_image = self._render_lines()
            self._info_lbl.config(
                text=f"{os.path.basename(path)} - {len(self._points)} 点 / {len(self._lines)} 线"
            )
            self.title(f"ME 查看器 — {os.path.basename(path)}")
            self._fit()
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc), parent=self)

    def _parse_me(self, path: str):
        """解析 ME 文件，提取点和线"""
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                content = f.read()
        except:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

        lines = content.split('\n')
        points = {}
        line_segments = []

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 点定义：P \n id \n x \n y \n |~
            if line == 'P' and i + 4 < len(lines):
                try:
                    pt_id = int(lines[i + 1].strip())
                    x = float(lines[i + 2].strip())
                    y = float(lines[i + 3].strip())
                    points[pt_id] = (x, y)
                    i += 5
                    continue
                except:
                    pass

            # 线定义：LIN \n id \n ... \n pt1_id \n pt2_id \n |~
            if line == 'LIN' and i + 12 < len(lines):
                try:
                    pt1 = int(lines[i + 11].strip())
                    pt2 = int(lines[i + 12].strip())
                    line_segments.append(('LIN', [pt1, pt2]))
                    i += 14
                    continue
                except:
                    pass

            # BSPL（B样条）：提取控制点序列
            if line == 'BSPL':
                try:
                    # 跳过前面的元数据，找到控制点数量和点ID列表
                    j = i + 1
                    while j < len(lines) and lines[j].strip() != '|~':
                        j += 1

                    # 在 BSPL 块中查找点ID序列
                    bspl_lines = [lines[k].strip() for k in range(i, min(j, i + 100))]
                    pt_ids = []
                    for idx, val in enumerate(bspl_lines):
                        if val.isdigit() and int(val) >= 2750:  # 点ID通常从2750开始
                            pt_id = int(val)
                            if pt_id < 1000000:  # 过滤掉大数字（标志位）
                                pt_ids.append(pt_id)

                    # 去重并保持顺序
                    seen = set()
                    unique_pts = []
                    for pt in pt_ids:
                        if pt not in seen:
                            seen.add(pt)
                            unique_pts.append(pt)

                    if len(unique_pts) >= 2:
                        line_segments.append(('BSPL', unique_pts))

                    i = j + 1
                    continue
                except:
                    pass

            i += 1

        return points, line_segments

    def _render_lines(self):
        """渲染线条为图像"""
        if not self._points:
            return None

        xs = [p[0] for p in self._points.values()]
        ys = [p[1] for p in self._points.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        w = max_x - min_x
        h = max_y - min_y
        if w == 0 or h == 0:
            w = h = 100

        pad = 30
        scale = min(3000 / w, 3000 / h)
        img_w = int(w * scale) + pad * 2
        img_h = int(h * scale) + pad * 2

        img = Image.new("RGB", (img_w, img_h), "white")
        draw = ImageDraw.Draw(img)

        for geom_type, pt_ids in self._lines:
            if geom_type == 'LIN' and len(pt_ids) == 2:
                # 直线
                pt1_id, pt2_id = pt_ids
                if pt1_id in self._points and pt2_id in self._points:
                    x1, y1 = self._points[pt1_id]
                    x2, y2 = self._points[pt2_id]
                    px1 = int((x1 - min_x) * scale) + pad
                    py1 = int((max_y - y1) * scale) + pad  # Y轴翻转
                    px2 = int((x2 - min_x) * scale) + pad
                    py2 = int((max_y - y2) * scale) + pad  # Y轴翻转
                    draw.line([(px1, py1), (px2, py2)], fill="black", width=2)

            elif geom_type == 'BSPL' and len(pt_ids) >= 2:
                # B样条曲线：用折线近似
                coords = []
                for pt_id in pt_ids:
                    if pt_id in self._points:
                        x, y = self._points[pt_id]
                        px = int((x - min_x) * scale) + pad
                        py = int((max_y - y) * scale) + pad  # Y轴翻转
                        coords.append((px, py))

                if len(coords) >= 2:
                    draw.line(coords, fill="black", width=2)

        return img

    def _fit(self):
        if self._base_image is None:
            return
        self._canvas.update_idletasks()
        cw = max(1, self._canvas.winfo_width())
        ch = max(1, self._canvas.winfo_height())
        bw, bh = self._base_image.size
        self._zoom = min(cw / bw, ch / bh)
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._redraw()

    def _zoom_in(self):
        self._set_zoom(self._zoom * 1.25)

    def _zoom_out(self):
        self._set_zoom(self._zoom / 1.25)

    def _set_zoom(self, new_zoom):
        self._zoom = max(0.01, min(50.0, new_zoom))
        self._redraw()

    def _on_drag_start(self, event):
        self._drag_start = (event.x, event.y)

    def _on_drag(self, event):
        if self._drag_start is None:
            return
        self._pan_x -= event.x - self._drag_start[0]
        self._pan_y -= event.y - self._drag_start[1]
        self._drag_start = (event.x, event.y)
        self._redraw()

    def _on_wheel(self, event):
        if event.num == 4 or (hasattr(event, "delta") and event.delta > 0):
            self._set_zoom(self._zoom * 1.25)
        else:
            self._set_zoom(self._zoom / 1.25)

    def _redraw(self):
        if self._base_image is None:
            return
        self._canvas.update_idletasks()
        cw = max(1, self._canvas.winfo_width())
        ch = max(1, self._canvas.winfo_height())
        bw, bh = self._base_image.size

        sw = max(1, int(bw * self._zoom))
        sh = max(1, int(bh * self._zoom))
        off_x = max(0, (cw - sw) // 2)
        off_y = max(0, (ch - sh) // 2)

        self._pan_x = max(0.0, min(float(max(0, sw - cw)), self._pan_x))
        self._pan_y = max(0.0, min(float(max(0, sh - ch)), self._pan_y))

        cx0 = self._pan_x / self._zoom
        cy0 = self._pan_y / self._zoom
        cx1 = cx0 + (cw - off_x * 2) / self._zoom
        cy1 = cy0 + (ch - off_y * 2) / self._zoom
        cx0, cy0 = max(0.0, cx0), max(0.0, cy0)
        cx1, cy1 = min(float(bw), cx1), min(float(bh), cy1)

        if cx1 <= cx0 or cy1 <= cy0:
            return

        cropped = self._base_image.crop((int(cx0), int(cy0), int(cx1), int(cy1)))
        disp_w = max(1, min(cw, int((cx1 - cx0) * self._zoom)))
        disp_h = max(1, min(ch, int((cy1 - cy0) * self._zoom)))
        displayed = cropped.resize((disp_w, disp_h), Image.LANCZOS)

        self._tk_img = ImageTk.PhotoImage(displayed)
        self._canvas.delete("all")
        self._canvas.create_image(off_x, off_y, anchor=tk.NW, image=self._tk_img)

        pct = self._zoom * 100
        self._zoom_lbl.config(text=f"{pct:.0f}%" if pct >= 1 else f"{pct:.1f}%")


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    viewer = MEViewer(root)
    viewer.mainloop()
