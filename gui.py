"""
苏绣轮廓生成器 - GUI 界面
"""
import datetime
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from dst_viewer import DSTViewer
from me_viewer import MEViewer
from processor import EmbroideryProcessor


class EmbroideryGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("苏绣轮廓生成器 v2.1.1")
        self.root.geometry("1200x760")
        self.root.minsize(900, 600)

        self.processor = EmbroideryProcessor()
        self.image_path: str | None = None
        self._tk_orig: ImageTk.PhotoImage | None = None
        self._tk_preview: ImageTk.PhotoImage | None = None

        # 针法预览的缩放/平移状态
        self._preview_image: Image.Image | None = None
        self._prev_zoom = 1.0
        self._prev_pan_x = 0.0
        self._prev_pan_y = 0.0
        self._prev_drag: tuple | None = None
        self._PREV_STEP = 1.25
        self._PREV_MIN  = 0.02
        self._PREV_MAX  = 40.0

        self._setup_style()
        self._build_ui()

    # ------------------------------------------------------------------
    # 样式
    # ------------------------------------------------------------------

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Title.TLabel", font=("Microsoft YaHei", 15, "bold"))
        style.configure("Action.TButton", font=("Microsoft YaHei", 10, "bold"), padding=6)
        style.configure("TLabelframe.Label", font=("Microsoft YaHei", 9, "bold"))

    # ------------------------------------------------------------------
    # 界面构建
    # ------------------------------------------------------------------

    def _build_ui(self):
        # 标题栏
        title_bar = ttk.Frame(self.root, padding=(12, 6))
        title_bar.pack(fill=tk.X, side=tk.TOP)
        ttk.Label(title_bar, text="苏绣轮廓生成器", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(
            title_bar,
            text="手绘图案 → 折线轮廓 → DST 格式",
            foreground="gray",
        ).pack(side=tk.LEFT, padx=12)

        # 水印：右对齐，当天日期 + 作者
        _today = datetime.date.today().strftime("%Y-%m-%d")
        ttk.Label(
            title_bar,
            text=f"{_today}\nAuthor: Jiale Zhou",
            foreground="#bbbbbb",
            font=("Microsoft YaHei", 8),
            justify=tk.RIGHT,
        ).pack(side=tk.RIGHT, padx=8)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # 内容区
        content = ttk.Frame(self.root, padding=8)
        content.pack(fill=tk.BOTH, expand=True)

        # 左侧：原图 + 轮廓预览
        preview_frame = ttk.Frame(content)
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        orig_lf = ttk.LabelFrame(preview_frame, text="原始图片", padding=4)
        orig_lf.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.orig_canvas = tk.Canvas(orig_lf, bg="#e8e8e8", highlightthickness=0)
        self.orig_canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas_placeholder(self.orig_canvas, "加载图片后显示")

        stitch_lf = ttk.LabelFrame(preview_frame, text="轮廓预览", padding=4)
        stitch_lf.pack(fill=tk.BOTH, expand=True)

        # 预览区迷你工具栏
        _sbar = ttk.Frame(stitch_lf)
        _sbar.pack(fill=tk.X, side=tk.TOP, pady=(0, 2))
        ttk.Button(_sbar, text="适合", command=self._prev_fit, width=4).pack(side=tk.LEFT)
        self._prev_zoom_lbl = ttk.Label(
            _sbar, text="", width=6, anchor=tk.CENTER, font=("Consolas", 8)
        )
        self._prev_zoom_lbl.pack(side=tk.LEFT)
        ttk.Label(
            _sbar, text="滚轮缩放  拖拽平移", foreground="#bbb",
            font=("Microsoft YaHei", 7)
        ).pack(side=tk.RIGHT, padx=4)

        self.stitch_canvas = tk.Canvas(stitch_lf, bg="white", highlightthickness=0)
        self.stitch_canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas_placeholder(self.stitch_canvas, "生成轮廓后显示预览")

        # 缩放/平移事件绑定
        sc = self.stitch_canvas
        sc.bind("<ButtonPress-1>",   self._prev_drag_start)
        sc.bind("<B1-Motion>",       self._prev_drag_cb)
        sc.bind("<ButtonRelease-1>", lambda _: setattr(self, "_prev_drag", None))
        sc.bind("<MouseWheel>",      self._prev_wheel)
        sc.bind("<Button-4>",        self._prev_wheel)
        sc.bind("<Button-5>",        self._prev_wheel)
        sc.bind("<Configure>",       lambda _: self._prev_redraw())

        # 右侧：控制面板
        ctrl_frame = ttk.Frame(content, width=270)
        ctrl_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        ctrl_frame.pack_propagate(False)
        self._build_controls(ctrl_frame)

        # 底部状态栏
        status_bar = ttk.Frame(self.root, padding=(8, 3))
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, side=tk.BOTTOM)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            status_bar, variable=self.progress_var, maximum=100, length=200
        )
        self.progress_bar.pack(side=tk.LEFT, padx=(0, 10))

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status_bar, textvariable=self.status_var, foreground="#444").pack(side=tk.LEFT)

    def _build_controls(self, parent):
        # ── 图片文件 ──────────────────────────────────────────────────
        file_lf = ttk.LabelFrame(parent, text="图片文件", padding=8)
        file_lf.pack(fill=tk.X, pady=(0, 10))

        self.path_var = tk.StringVar(value="未选择文件")
        ttk.Label(
            file_lf,
            textvariable=self.path_var,
            wraplength=240,
            foreground="#555",
            font=("Microsoft YaHei", 8),
        ).pack(fill=tk.X, pady=(0, 4))
        ttk.Button(file_lf, text="浏览图片…", command=self._load_image).pack(fill=tk.X)

        # ── 细节程度（唯一参数）──────────────────────────────────────
        detail_lf = ttk.LabelFrame(parent, text="细节程度", padding=8)
        detail_lf.pack(fill=tk.X, pady=(0, 10))

        # 端点标签行
        label_row = ttk.Frame(detail_lf)
        label_row.pack(fill=tk.X)
        ttk.Label(label_row, text="粗略", foreground="#888",
                  font=("Microsoft YaHei", 8)).pack(side=tk.LEFT)
        ttk.Label(label_row, text="精细", foreground="#888",
                  font=("Microsoft YaHei", 8)).pack(side=tk.RIGHT)

        self.detail_var = tk.IntVar(value=50)
        self.mode_var = tk.StringVar(value='outline')
        ttk.Scale(
            detail_lf,
            from_=1, to=100,
            orient=tk.HORIZONTAL,
            variable=self.detail_var,
        ).pack(fill=tk.X, pady=(2, 4))

        # 数值显示
        val_row = ttk.Frame(detail_lf)
        val_row.pack()
        ttk.Label(val_row, textvariable=self.detail_var,
                  font=("Consolas", 13, "bold"),
                  foreground="#0055cc").pack(side=tk.LEFT)
        ttk.Label(val_row, text=" / 100",
                  font=("Consolas", 10),
                  foreground="#aaa").pack(side=tk.LEFT)

        ttk.Label(
            detail_lf,
            text="越小折线越少，越大越贴合原图",
            foreground="#999",
            font=("Microsoft YaHei", 7),
            wraplength=240,
        ).pack(fill=tk.X, pady=(2, 0))

        # ── 操作按钮 ──────────────────────────────────────────────────
        btn_lf = ttk.Frame(parent, padding=(0, 4))
        btn_lf.pack(fill=tk.X, pady=(0, 8))

        # 模式选择
        mode_frame = ttk.Frame(btn_lf)
        mode_frame.pack(fill=tk.X, pady=(0, 6))
        ttk.Radiobutton(mode_frame, text="仅轮廓", variable=self.mode_var,
                       value='outline').pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(mode_frame, text="带填充", variable=self.mode_var,
                       value='fill').pack(side=tk.LEFT)

        ttk.Button(
            btn_lf,
            text="▶  生成图案",
            command=self._generate,
            style="Action.TButton",
        ).pack(fill=tk.X, pady=(0, 6))

        ttk.Button(
            btn_lf,
            text="💾  保存 DST",
            command=self._save_dst,
        ).pack(fill=tk.X, pady=(0, 4))

        ttk.Button(
            btn_lf,
            text="📐  保存 ME",
            command=self._save_me,
        ).pack(fill=tk.X, pady=(0, 4))

        ttk.Button(
            btn_lf,
            text="🖼  保存高清 PNG",
            command=self._save_png,
        ).pack(fill=tk.X)

        ttk.Separator(btn_lf, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(8, 6))

        ttk.Button(
            btn_lf,
            text="🔍  浏览 DST 文件…",
            command=self._open_dst_viewer,
        ).pack(fill=tk.X, pady=(0, 4))

        ttk.Button(
            btn_lf,
            text="📐  浏览 ME 文件…",
            command=self._open_me_viewer,
        ).pack(fill=tk.X)

        # ── 统计信息 ──────────────────────────────────────────────────
        self.info_var = tk.StringVar(value="")
        ttk.Label(
            parent,
            textvariable=self.info_var,
            wraplength=250,
            foreground="#0066aa",
            font=("Microsoft YaHei", 8),
        ).pack(fill=tk.X, pady=(8, 0))

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _load_image(self):
        path = filedialog.askopenfilename(
            title="选择手绘图案",
            filetypes=[
                ("图片文件", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp *.gif"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self.image_path = path
            img = self.processor.load_image(path)
            self.path_var.set(os.path.basename(path))
            self._show_image(img, self.orig_canvas, "_tk_orig")
            self.status_var.set(
                f"已加载：{os.path.basename(path)}  ({img.width}×{img.height})"
            )
            self.info_var.set("")
            # 清空预览
            self._preview_image = None
            self._prev_zoom = 1.0
            self._prev_pan_x = 0.0
            self._prev_pan_y = 0.0
            self._prev_zoom_lbl.config(text="")
            self.stitch_canvas.delete("all")
            self._canvas_placeholder(self.stitch_canvas, "生成轮廓后显示预览")
        except Exception as exc:
            messagebox.showerror("加载失败", str(exc))

    def _generate(self):
        if self.image_path is None:
            messagebox.showwarning("提示", "请先加载图片")
            return

        detail_level = self.detail_var.get()
        mode = self.mode_var.get()

        def _run():
            try:
                self._set_status("正在处理…", 5)

                def _cb(v):
                    self.root.after(0, lambda: self.progress_var.set(v))

                self.processor.process(
                    detail_level=detail_level,
                    mode=mode,
                    progress_cb=_cb,
                )

                n_paths = len(self.processor.polylines)
                n_segs  = sum(len(p) - 1 for p in self.processor.polylines)
                info_text = f"共 {n_paths:,} 条路径 / {n_segs:,} 段"

                preview = self.processor.render_preview()

                def _update():
                    self.info_var.set(info_text)
                    if preview:
                        self._set_preview_image(preview)
                    self.progress_var.set(100)
                    self.status_var.set(f"生成完成 — {info_text}")

                self.root.after(0, _update)

            except Exception as exc:
                self.root.after(
                    0,
                    lambda: (
                        messagebox.showerror("生成失败", str(exc)),
                        self._set_status(f"错误：{exc}", 0),
                    ),
                )

        threading.Thread(target=_run, daemon=True).start()

    def _open_dst_viewer(self):
        viewer = DSTViewer(self.root)
        viewer.focus_set()

    def _open_me_viewer(self):
        viewer = MEViewer(self.root)
        viewer.focus_set()

    def _save_dst(self):
        if not self.processor.polylines:
            messagebox.showwarning("提示", "请先生成轮廓")
            return

        default = ""
        if self.image_path:
            default = os.path.splitext(os.path.basename(self.image_path))[0] + ".dst"

        path = filedialog.asksaveasfilename(
            title="保存 DST 文件",
            defaultextension=".dst",
            initialfile=default,
            filetypes=[("DST 绣花文件", "*.dst"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            self.processor.save_dst(path)
            self.status_var.set(f"已保存：{os.path.basename(path)}")
            messagebox.showinfo("保存成功", f"DST 文件已保存至：\n{path}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def _save_me(self):
        if not self.processor.polylines:
            messagebox.showwarning("提示", "请先生成轮廓")
            return

        default = ""
        if self.image_path:
            default = os.path.splitext(os.path.basename(self.image_path))[0] + ".me"

        path = filedialog.asksaveasfilename(
            title="保存 ME 文件",
            defaultextension=".me",
            initialfile=default,
            filetypes=[("ME CAD 文件", "*.me"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            self.processor.save_me(path)
            self.status_var.set(f"已保存：{os.path.basename(path)}")
            messagebox.showinfo("保存成功", f"ME 文件已保存至：\n{path}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def _save_png(self):
        if self._preview_image is None:
            messagebox.showwarning("提示", "请先生成轮廓")
            return

        default = ""
        if self.image_path:
            default = os.path.splitext(os.path.basename(self.image_path))[0] + ".png"

        path = filedialog.asksaveasfilename(
            title="保存高清 PNG",
            defaultextension=".png",
            initialfile=default,
            filetypes=[("PNG 图像", "*.png"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            self._preview_image.save(path, "PNG", compress_level=1)
            self.status_var.set(f"已保存：{os.path.basename(path)}")
            messagebox.showinfo(
                "保存成功",
                f"PNG 已保存至：\n{path}\n分辨率：{self._preview_image.width} × {self._preview_image.height} px",
            )
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _set_status(self, msg: str, progress: float):
        self.status_var.set(msg)
        self.progress_var.set(progress)
        self.root.update_idletasks()

    def _canvas_placeholder(self, canvas: tk.Canvas, text: str):
        canvas.update_idletasks()
        w = max(canvas.winfo_width(), 200)
        h = max(canvas.winfo_height(), 100)
        canvas.create_text(w // 2, h // 2, text=text, fill="#aaa",
                           font=("Microsoft YaHei", 10))

    def _show_image(self, img: Image.Image, canvas: tk.Canvas, attr: str):
        """将 PIL 图像缩放后静态显示在 Canvas 中。"""
        canvas.update_idletasks()
        cw = max(canvas.winfo_width(), 400)
        ch = max(canvas.winfo_height(), 200)
        scale = min(cw / img.width, ch / img.height)
        nw = max(1, int(img.width  * scale))
        nh = max(1, int(img.height * scale))
        resized = img.resize((nw, nh), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(resized)
        setattr(self, attr, tk_img)   # 防止 GC
        canvas.delete("all")
        canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=tk_img)

    # ------------------------------------------------------------------
    # 轮廓预览缩放 / 平移
    # ------------------------------------------------------------------

    def _set_preview_image(self, img: Image.Image):
        self._preview_image = img
        self._prev_fit()

    def _prev_fit(self):
        if self._preview_image is None:
            return
        self.stitch_canvas.update_idletasks()
        cw = max(1, self.stitch_canvas.winfo_width())
        ch = max(1, self.stitch_canvas.winfo_height())
        bw, bh = self._preview_image.size
        self._prev_zoom  = min(cw / bw, ch / bh)
        self._prev_pan_x = 0.0
        self._prev_pan_y = 0.0
        self._prev_redraw()

    def _prev_set_zoom(self, new_zoom: float,
                       cx: float | None = None, cy: float | None = None):
        new_zoom = max(self._PREV_MIN, min(self._PREV_MAX, new_zoom))
        if cx is None:
            self.stitch_canvas.update_idletasks()
            cx = self.stitch_canvas.winfo_width()  / 2.0
            cy = self.stitch_canvas.winfo_height() / 2.0
        factor = new_zoom / self._prev_zoom
        self._prev_pan_x = self._prev_pan_x * factor + cx * (factor - 1)
        self._prev_pan_y = self._prev_pan_y * factor + cy * (factor - 1)
        self._prev_zoom  = new_zoom
        self._prev_redraw()

    def _prev_drag_start(self, event):
        self._prev_drag = (event.x, event.y)

    def _prev_drag_cb(self, event):
        if self._prev_drag is None:
            return
        self._prev_pan_x -= event.x - self._prev_drag[0]
        self._prev_pan_y -= event.y - self._prev_drag[1]
        self._prev_drag = (event.x, event.y)
        self._prev_redraw()

    def _prev_wheel(self, event):
        if event.num == 4 or (hasattr(event, "delta") and event.delta > 0):
            self._prev_set_zoom(self._prev_zoom * self._PREV_STEP, event.x, event.y)
        else:
            self._prev_set_zoom(self._prev_zoom / self._PREV_STEP, event.x, event.y)

    def _prev_redraw(self):
        if self._preview_image is None:
            return
        self.stitch_canvas.update_idletasks()
        cw = max(1, self.stitch_canvas.winfo_width())
        ch = max(1, self.stitch_canvas.winfo_height())
        bw, bh = self._preview_image.size

        sw = max(1, int(bw * self._prev_zoom))
        sh = max(1, int(bh * self._prev_zoom))
        off_x = max(0, (cw - sw) // 2)
        off_y = max(0, (ch - sh) // 2)

        self._prev_pan_x = max(0.0, min(float(max(0, sw - cw)), self._prev_pan_x))
        self._prev_pan_y = max(0.0, min(float(max(0, sh - ch)), self._prev_pan_y))

        cx0 = self._prev_pan_x / self._prev_zoom
        cy0 = self._prev_pan_y / self._prev_zoom
        cx1 = cx0 + (cw - off_x * 2) / self._prev_zoom
        cy1 = cy0 + (ch - off_y * 2) / self._prev_zoom
        cx0, cy0 = max(0.0, cx0), max(0.0, cy0)
        cx1, cy1 = min(float(bw), cx1), min(float(bh), cy1)

        if cx1 <= cx0 or cy1 <= cy0:
            return

        cropped  = self._preview_image.crop(
            (int(cx0), int(cy0), int(cx1), int(cy1))
        )
        disp_w = max(1, min(cw, int((cx1 - cx0) * self._prev_zoom)))
        disp_h = max(1, min(ch, int((cy1 - cy0) * self._prev_zoom)))
        resample = Image.NEAREST if self._prev_zoom > 6 else Image.LANCZOS
        displayed = cropped.resize((disp_w, disp_h), resample)

        self._tk_preview = ImageTk.PhotoImage(displayed)
        self.stitch_canvas.delete("all")
        self.stitch_canvas.create_image(off_x, off_y, anchor=tk.NW,
                                        image=self._tk_preview)

        pct = self._prev_zoom * 100
        self._prev_zoom_lbl.config(
            text=f"{pct:.0f}%" if pct >= 1 else f"{pct:.1f}%"
        )
