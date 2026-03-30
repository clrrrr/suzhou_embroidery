"""
独立刺绣文件查看器
支持 DST / PES / JEF / VP3 等格式
可独立运行，或从主程序调用

用法：
    python dst_app.py
    python dst_app.py path/to/file.dst
"""
import math
import os
import sys
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, ttk

import cv2
import numpy as np
import pyembroidery
from PIL import Image, ImageTk

_STITCH       = pyembroidery.STITCH
_JUMP         = pyembroidery.JUMP
_TRIM         = pyembroidery.TRIM
_COLOR_CHANGE = pyembroidery.COLOR_CHANGE
_END          = pyembroidery.END


class DSTApp:
    ZOOM_STEP = 1.25
    ZOOM_MIN  = 0.005
    ZOOM_MAX  = 80.0
    PAD       = 50        # 渲染图四周留白（像素）
    MAX_DIM   = 4000      # 单边最大渲染分辨率

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("刺绣文件查看器")
        self.root.geometry("1440x900")
        self.root.minsize(960, 640)

        # ── 原始数据 ──────────────────────────────────────────────────
        self._pattern  = None
        self._filepath = ""

        # 各图层数据（parse 之后填充）
        self._stitch_runs: list = []   # [(color_rgb, [(x,y)...]), ...]
        self._jump_segs:   list = []   # [((x0,y0),(x1,y1)), ...]
        self._trim_pts:    list = []   # [(x,y), ...]
        self._stats:       dict = {}

        # 渲染参数（render 之后填充）
        self._render_base:  Image.Image | None = None
        self._render_scale: float = 1.0
        self._render_pad:   int   = self.PAD
        self._min_x: float = 0.0
        self._min_y: float = 0.0

        # ── 图层开关 & 颜色 ───────────────────────────────────────────
        self._show_stitch = tk.BooleanVar(value=True)
        self._show_jump   = tk.BooleanVar(value=True)
        self._show_trim   = tk.BooleanVar(value=True)
        self._jump_color  = "#aaaaaa"
        self._trim_color  = "#ff3333"

        # ── 缩放 / 平移 ───────────────────────────────────────────────
        self._zoom   = 1.0
        self._pan_x  = 0.0
        self._pan_y  = 0.0
        self._drag_origin: tuple | None = None

        self._tk_image: ImageTk.PhotoImage | None = None

        self._setup_style()
        self._build_ui()

    # ------------------------------------------------------------------
    # 样式
    # ------------------------------------------------------------------

    def _setup_style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("Title.TLabel",  font=("Microsoft YaHei", 13, "bold"))
        s.configure("H2.TLabel",     font=("Microsoft YaHei", 9,  "bold"))
        s.configure("Mono.TLabel",   font=("Consolas", 8))
        s.configure("Small.TLabel",  font=("Microsoft YaHei", 7), foreground="#999")

    # ------------------------------------------------------------------
    # 界面构建
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ── 顶部标题栏 ────────────────────────────────────────────────
        title_bar = ttk.Frame(self.root, padding=(12, 6))
        title_bar.pack(fill=tk.X, side=tk.TOP)

        ttk.Label(title_bar, text="刺绣文件查看器", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Button(title_bar, text="📂  打开文件…", command=self._open_file).pack(side=tk.LEFT, padx=14)

        self._filename_var = tk.StringVar(value="未加载文件")
        ttk.Label(title_bar, textvariable=self._filename_var,
                  foreground="#666", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # ── 主内容区 ──────────────────────────────────────────────────
        content = ttk.Frame(self.root)
        content.pack(fill=tk.BOTH, expand=True)

        # 画布区（左）
        canvas_wrap = ttk.Frame(content)
        canvas_wrap.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 画布工具栏
        tb = ttk.Frame(canvas_wrap, padding=(6, 3))
        tb.pack(fill=tk.X, side=tk.TOP)
        ttk.Button(tb, text="适合窗口", command=self._fit, width=7).pack(side=tk.LEFT)
        ttk.Button(tb, text="＋", command=lambda: self._set_zoom(self._zoom * self.ZOOM_STEP), width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="－", command=lambda: self._set_zoom(self._zoom / self.ZOOM_STEP), width=3).pack(side=tk.LEFT)
        self._zoom_lbl = ttk.Label(tb, text="", width=7, anchor=tk.CENTER, style="Mono.TLabel")
        self._zoom_lbl.pack(side=tk.LEFT, padx=6)
        ttk.Label(tb, text="拖拽平移  滚轮缩放", style="Small.TLabel").pack(side=tk.RIGHT, padx=6)

        self.canvas = tk.Canvas(canvas_wrap, bg="#2b2b2b", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>",   self._drag_start)
        self.canvas.bind("<B1-Motion>",       self._drag_cb)
        self.canvas.bind("<ButtonRelease-1>", lambda _: setattr(self, "_drag_origin", None))
        self.canvas.bind("<MouseWheel>",      self._wheel)
        self.canvas.bind("<Button-4>",        self._wheel)
        self.canvas.bind("<Button-5>",        self._wheel)
        self.canvas.bind("<Configure>",       lambda _: self._redraw())
        self.canvas.bind("<Motion>",          self._mouse_move)

        # 右侧面板
        right = ttk.Frame(content, width=300, padding=(8, 6))
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)
        self._build_right(right)

        # ── 状态栏 ────────────────────────────────────────────────────
        status_bar = ttk.Frame(self.root, padding=(8, 3))
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, side=tk.BOTTOM)

        self._progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(status_bar, variable=self._progress_var,
                        maximum=100, length=160).pack(side=tk.LEFT, padx=(0, 10))
        self._status_var = tk.StringVar(value="就绪 — 请打开刺绣文件")
        ttk.Label(status_bar, textvariable=self._status_var, foreground="#555").pack(side=tk.LEFT)

        self._coord_var = tk.StringVar(value="")
        ttk.Label(status_bar, textvariable=self._coord_var,
                  foreground="#888", style="Mono.TLabel").pack(side=tk.RIGHT, padx=8)

    def _build_right(self, parent):
        # ── 渲染图层 ──────────────────────────────────────────────────
        lyr_lf = ttk.LabelFrame(parent, text="渲染图层", padding=8)
        lyr_lf.pack(fill=tk.X, pady=(0, 8))

        # STITCH（只有开关，颜色来自线色列表）
        ttk.Checkbutton(lyr_lf, text="针迹  STITCH",
                        variable=self._show_stitch,
                        command=self._rerender).pack(anchor=tk.W, pady=2)

        # JUMP / TRIM 带颜色选择
        def layer_row(parent_frame, label, bool_var, color_attr, init_color):
            row = ttk.Frame(parent_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Checkbutton(row, text=label, variable=bool_var,
                            command=self._rerender).pack(side=tk.LEFT)
            swatch = tk.Label(row, bg=init_color, width=3, relief="groove", cursor="hand2")
            swatch.pack(side=tk.RIGHT)

            def pick(attr=color_attr, btn=swatch):
                res = colorchooser.askcolor(color=getattr(self, attr), title="选择颜色")
                if res[1]:
                    setattr(self, attr, res[1])
                    btn.config(bg=res[1])
                    self._rerender()
            swatch.bind("<Button-1>", lambda _: pick())

        layer_row(lyr_lf, "跳针  JUMP", self._show_jump, "_jump_color", self._jump_color)
        layer_row(lyr_lf, "剪线  TRIM", self._show_trim, "_trim_color", self._trim_color)

        ttk.Label(lyr_lf, text="点击右侧色块可自定义颜色", style="Small.TLabel").pack(anchor=tk.W, pady=(4, 0))

        # ── 线色列表 ──────────────────────────────────────────────────
        thread_lf = ttk.LabelFrame(parent, text="线色列表", padding=8)
        thread_lf.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        # Scrollable thread list
        thread_scroll = ttk.Frame(thread_lf)
        thread_scroll.pack(fill=tk.BOTH, expand=True)
        self._thread_canvas = tk.Canvas(thread_scroll, highlightthickness=0, bg="#f5f5f5")
        sb = ttk.Scrollbar(thread_scroll, orient=tk.VERTICAL, command=self._thread_canvas.yview)
        self._thread_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._thread_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._thread_inner = ttk.Frame(self._thread_canvas)
        self._thread_canvas.create_window((0, 0), window=self._thread_inner, anchor=tk.NW)
        self._thread_inner.bind("<Configure>",
            lambda e: self._thread_canvas.configure(scrollregion=self._thread_canvas.bbox("all")))

        # ── 文件信息 ──────────────────────────────────────────────────
        info_lf = ttk.LabelFrame(parent, text="文件信息", padding=8)
        info_lf.pack(fill=tk.X)
        self._info_var = tk.StringVar(value="—")
        ttk.Label(info_lf, textvariable=self._info_var,
                  wraplength=270, foreground="#333",
                  font=("Consolas", 8), justify=tk.LEFT).pack(anchor=tk.W)

    # ------------------------------------------------------------------
    # 文件加载
    # ------------------------------------------------------------------

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="打开刺绣文件",
            filetypes=[
                ("刺绣文件", "*.dst *.pes *.jef *.vp3 *.exp *.hus *.xxx *.vip"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self._load(path)

    def _load(self, path: str):
        self._status_var.set("正在读取文件…")
        self._progress_var.set(5)
        self.root.update_idletasks()

        def _worker():
            try:
                pattern = pyembroidery.read(path)
                if pattern is None:
                    raise ValueError("无法解析文件格式")
                self.root.after(0, lambda: self._on_loaded(pattern, path))
            except Exception as exc:
                self.root.after(0, lambda: (
                    self._status_var.set(f"加载失败：{exc}"),
                    self._progress_var.set(0),
                ))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_loaded(self, pattern, path: str):
        self._pattern  = pattern
        self._filepath = path
        self._filename_var.set(os.path.basename(path))
        self._progress_var.set(15)

        self._parse_layers(pattern)
        self._progress_var.set(45)

        self._render_base = self._render_full()
        self._progress_var.set(85)

        self._update_thread_panel(pattern)
        self._update_info()
        self._fit()

        self._progress_var.set(100)
        ns = self._stats.get("n_stitch", 0)
        nj = self._stats.get("n_jump",   0)
        nc = self._stats.get("n_color",  1)
        self._status_var.set(f"已加载  |  针迹 {ns:,}  跳针 {nj:,}  颜色 {nc}")

    # ------------------------------------------------------------------
    # 数据解析
    # ------------------------------------------------------------------

    def _parse_layers(self, pattern):
        colors    = self._extract_colors(pattern)
        color_idx = 0

        self._stitch_runs = []
        self._jump_segs   = []
        self._trim_pts    = []

        n_stitch = n_jump = 0
        cur_run  = []
        cur_color = colors[0]
        prev = None

        for sx, sy, cmd in pattern.stitches:
            base = cmd & 0xFF

            if base == _STITCH:
                if not cur_run and prev is not None:
                    cur_run.append(prev)   # 把 JUMP 落点纳入 run，保证第一段不丢失
                cur_run.append((sx, sy))
                n_stitch += 1
                prev = (sx, sy)

            elif base == _JUMP:
                if cur_run:
                    self._stitch_runs.append((cur_color, cur_run))
                    cur_run = []
                if prev:
                    self._jump_segs.append((prev, (sx, sy)))
                    n_jump += 1
                prev = (sx, sy)

            elif base == _TRIM:
                if cur_run:
                    self._stitch_runs.append((cur_color, cur_run))
                    cur_run = []
                if prev:
                    self._trim_pts.append((sx, sy))
                prev = (sx, sy)

            elif base == _COLOR_CHANGE:
                if cur_run:
                    self._stitch_runs.append((cur_color, cur_run))
                    cur_run = []
                color_idx = min(color_idx + 1, len(colors) - 1)
                cur_color = colors[color_idx]
                prev = (sx, sy)

            elif base == _END:
                if cur_run:
                    self._stitch_runs.append((cur_color, cur_run))
                    cur_run = []
                break

        if cur_run:
            self._stitch_runs.append((cur_color, cur_run))

        self._stats = {
            "n_stitch": n_stitch,
            "n_jump":   n_jump,
            "n_trim":   len(self._trim_pts),
            "n_color":  len(colors),
        }

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------

    def _render_full(self) -> Image.Image:
        """把当前图层数据渲染成固定分辨率的 PIL Image。"""
        # 包围盒只用针迹点（stitch_runs）来计算，
        # 排除 JUMP/TRIM 的机器行程坐标（如回原点的(0,0)），避免设计图被挤到角落
        stitch_pts: list = []
        for _, run in self._stitch_runs:
            stitch_pts.extend(run)

        if not stitch_pts:
            return Image.new("RGB", (600, 400), "#2b2b2b")

        xs = [p[0] for p in stitch_pts]
        ys = [p[1] for p in stitch_pts]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        w_u = max(max_x - min_x, 1)
        h_u = max(max_y - min_y, 1)
        scale = min(self.MAX_DIM / w_u, self.MAX_DIM / h_u)

        pw = int(w_u * scale) + 2 * self.PAD
        ph = int(h_u * scale) + 2 * self.PAD

        self._render_scale = scale
        self._render_pad   = self.PAD
        self._min_x = min_x
        self._min_y = min_y

        canvas_np = np.full((ph, pw, 3), 252, dtype=np.uint8)   # 近白背景

        def px(x, y):
            return (int((x - min_x) * scale) + self.PAD,
                    int((y - min_y) * scale) + self.PAD)

        # ── JUMP（虚线，底层先画）────────────────────────────────────
        if self._show_jump.get() and self._jump_segs:
            jbgr = self._hex_to_bgr(self._jump_color)
            for (ax, ay), (bx, by) in self._jump_segs:
                pa, pb = px(ax, ay), px(bx, by)
                # 跳过任一端点超出画布的线段（如 DST 回原点的机器行程）
                if (0 <= pa[0] < pw and 0 <= pa[1] < ph and
                        0 <= pb[0] < pw and 0 <= pb[1] < ph):
                    self._draw_dashed(canvas_np, pa, pb, jbgr, dash=6, gap=4)

        # ── STITCH（实线）────────────────────────────────────────────
        if self._show_stitch.get() and self._stitch_runs:
            for color_rgb, run in self._stitch_runs:
                if len(run) < 2:
                    continue
                r, g, b = color_rgb
                pts = np.array([px(x, y) for x, y in run], dtype=np.int32).reshape(-1, 1, 2)
                cv2.polylines(canvas_np, [pts], False, (b, g, r), 1, cv2.LINE_AA)

        # ── TRIM（十字标记）──────────────────────────────────────────
        if self._show_trim.get() and self._trim_pts:
            tbgr = self._hex_to_bgr(self._trim_color)
            for x, y in self._trim_pts:
                tx, ty = px(x, y)
                if 0 <= tx < pw and 0 <= ty < ph:
                    cv2.drawMarker(canvas_np, (tx, ty), tbgr,
                                   cv2.MARKER_CROSS, 9, 1, cv2.LINE_AA)

        return Image.fromarray(cv2.cvtColor(canvas_np, cv2.COLOR_BGR2RGB))

    def _rerender(self):
        if self._pattern is None:
            return
        self._render_base = self._render_full()
        self._redraw()

    # ------------------------------------------------------------------
    # 右侧面板更新
    # ------------------------------------------------------------------

    def _update_thread_panel(self, pattern):
        for w in self._thread_inner.winfo_children():
            w.destroy()
        colors = self._extract_colors(pattern)
        for i, (r, g, b) in enumerate(colors):
            hx = f"#{r:02x}{g:02x}{b:02x}"
            row = ttk.Frame(self._thread_inner)
            row.pack(fill=tk.X, padx=4, pady=2)
            tk.Label(row, bg=hx, width=3, height=1, relief="solid").pack(side=tk.LEFT, padx=(0, 6))
            ttk.Label(row, text=f"线色 {i+1:>2}   {hx.upper()}",
                      font=("Consolas", 8), foreground="#444").pack(side=tk.LEFT)

    def _update_info(self):
        s = self._stats
        ext = self._pattern.extents() if self._pattern else (0, 0, 0, 0)
        try:
            w_mm = (ext[2] - ext[0]) / 10.0
            h_mm = (ext[3] - ext[1]) / 10.0
        except Exception:
            w_mm = h_mm = 0.0
        fname = os.path.basename(self._filepath)
        txt = (
            f"文件：{fname}\n"
            f"针迹：{s.get('n_stitch', 0):,}\n"
            f"跳针：{s.get('n_jump',   0):,}\n"
            f"剪线：{s.get('n_trim',   0):,}\n"
            f"颜色：{s.get('n_color',  0)}\n"
            f"尺寸：{w_mm:.1f} × {h_mm:.1f} mm"
        )
        self._info_var.set(txt)

    # ------------------------------------------------------------------
    # 缩放 / 平移 / 重绘
    # ------------------------------------------------------------------

    def _fit(self):
        if self._render_base is None:
            return
        self.canvas.update_idletasks()
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        bw, bh = self._render_base.size
        self._zoom  = min(cw / bw, ch / bh)
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._redraw()

    def _set_zoom(self, new_zoom: float,
                  cx: float | None = None, cy: float | None = None):
        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, new_zoom))
        if cx is None:
            self.canvas.update_idletasks()
            cx = self.canvas.winfo_width()  / 2.0
            cy = self.canvas.winfo_height() / 2.0
        f = new_zoom / self._zoom
        self._pan_x = self._pan_x * f + cx * (f - 1)
        self._pan_y = self._pan_y * f + cy * (f - 1)
        self._zoom  = new_zoom
        self._redraw()

    def _drag_start(self, event):
        self._drag_origin = (event.x, event.y)

    def _drag_cb(self, event):
        if self._drag_origin is None:
            return
        self._pan_x -= event.x - self._drag_origin[0]
        self._pan_y -= event.y - self._drag_origin[1]
        self._drag_origin = (event.x, event.y)
        self._redraw()

    def _wheel(self, event):
        if event.num == 4 or (hasattr(event, "delta") and event.delta > 0):
            self._set_zoom(self._zoom * self.ZOOM_STEP, event.x, event.y)
        else:
            self._set_zoom(self._zoom / self.ZOOM_STEP, event.x, event.y)

    def _mouse_move(self, event):
        if self._render_base is None:
            self._coord_var.set("")
            return
        bw, bh = self._render_base.size
        sw = bw * self._zoom
        sh = bh * self._zoom
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        off_x = max(0, (cw - sw) / 2)
        off_y = max(0, (ch - sh) / 2)
        img_x = (event.x - off_x + self._pan_x) / self._zoom
        img_y = (event.y - off_y + self._pan_y) / self._zoom
        if self._render_scale > 0:
            dst_x = (img_x - self._render_pad) / self._render_scale + self._min_x
            dst_y = (img_y - self._render_pad) / self._render_scale + self._min_y
            self._coord_var.set(f"{dst_x/10:+.1f} mm,  {dst_y/10:+.1f} mm")

    def _redraw(self):
        if self._render_base is None:
            return
        self.canvas.update_idletasks()
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        bw, bh = self._render_base.size

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

        cropped = self._render_base.crop((int(cx0), int(cy0), int(cx1), int(cy1)))
        dw = max(1, min(cw, int((cx1 - cx0) * self._zoom)))
        dh = max(1, min(ch, int((cy1 - cy0) * self._zoom)))
        resample = Image.NEAREST if self._zoom > 6 else Image.LANCZOS
        displayed = cropped.resize((dw, dh), resample)

        self._tk_image = ImageTk.PhotoImage(displayed)
        self.canvas.delete("all")
        self.canvas.create_image(off_x, off_y, anchor=tk.NW, image=self._tk_image)

        pct = self._zoom * 100
        self._zoom_lbl.config(text=f"{pct:.0f}%" if pct >= 1 else f"{pct:.1f}%")

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _draw_dashed(img, p1, p2, color, dash=6, gap=4):
        x1, y1 = p1
        x2, y2 = p2
        dx, dy = x2 - x1, y2 - y1
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            return
        ux, uy = dx / length, dy / length
        pos, draw = 0.0, True
        while pos < length:
            seg = dash if draw else gap
            end_pos = min(pos + seg, length)
            if draw:
                a = (int(x1 + ux * pos),     int(y1 + uy * pos))
                b = (int(x1 + ux * end_pos), int(y1 + uy * end_pos))
                cv2.line(img, a, b, color, 1, cv2.LINE_AA)
            pos = end_pos
            draw = not draw

    @staticmethod
    def _extract_colors(pattern) -> list:
        tl = getattr(pattern, "threadlist", None) or getattr(pattern, "threads", []) or []
        out = []
        for t in tl:
            c = t.get("color", 0) if isinstance(t, dict) else getattr(t, "color", 0)
            out.append(((c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF))
        return out or [(0, 0, 0)]

    @staticmethod
    def _hex_to_bgr(hex_color: str) -> tuple:
        h = hex_color.lstrip("#")
        return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


# ----------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------

def main():
    root = tk.Tk()
    app  = DSTApp(root)
    # 如果命令行传了文件路径，直接加载
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        root.after(200, lambda: app._load(sys.argv[1]))
    root.mainloop()


if __name__ == "__main__":
    main()
