"""
苏绣轮廓生成引擎

流程：手稿纹样图 → 二值化 → 骨架化 → 折线追踪 → D-P 简化 → DST 格式
"""
import math
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pyembroidery
from PIL import Image
from skimage.morphology import skeletonize as _sk_skeletonize

DST_MAX_STITCH = 120   # DST 单位 0.1mm，超过 12mm 须拆分
MIN_PATH_PIXELS = 5    # 骨架追踪时丢弃像素数不足的短路径（去噪）
DST_MAX_DIM_MM  = 200.0


class EmbroideryProcessor:
    def __init__(self):
        self.original_image: Optional[Image.Image] = None
        self.polylines: List[List[Tuple[int, int]]] = []
        self._img_w_px: int = 1
        self._img_h_px: int = 1
        self.width_mm:  float = 200.0
        self.height_mm: float = 200.0

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def load_image(self, path: str) -> Image.Image:
        self.original_image = Image.open(path).convert("RGB")
        self.polylines = []
        return self.original_image

    def process(
        self,
        detail_level: int,       # 1（最粗）~ 100（最精细）
        mode: str = 'outline',   # 'outline' 或 'fill'
        fill_type: str = 'tatami',  # 'tatami' 或 'simple'
        fill_angle: int = 0,     # 填充角度 0-180
        progress_cb=None,
    ) -> List[List[Tuple[int, int]]]:
        """
        提取轮廓并简化为折线列表。
        detail_level : 1=最少线段，100=最贴近原图（线段最多）
        mode : 'outline'=仅轮廓, 'fill'=带填充
        fill_type : 'tatami'=平行填充, 'simple'=简单填充
        fill_angle : 填充角度（度）
        """
        if self.original_image is None:
            raise ValueError("请先加载图片")

        def _cb(v):
            if progress_cb:
                progress_cb(v)

        _cb(5)

        # 将图片缩放到处理分辨率（最长边不超过 2000px）
        img_np = np.array(self.original_image)
        H, W = img_np.shape[:2]
        max_dim = 2000
        scale_down = min(max_dim / max(H, W), 1.0)
        if scale_down < 1.0:
            new_W = max(1, int(W * scale_down))
            new_H = max(1, int(H * scale_down))
            img_np = cv2.resize(img_np, (new_W, new_H), interpolation=cv2.INTER_AREA)
            H, W = new_H, new_W

        self._img_w_px = W
        self._img_h_px = H

        # 1. 二值化
        binary = self._binarize(img_np)
        self._binary = binary  # 保存二值图用于填充判断
        _cb(15)

        # 2. 骨架化（skimage 返回 bool 数组）
        skeleton = _sk_skeletonize(binary > 127)
        _cb(30)

        # 3. 追踪骨架 → 原始折线列表
        raw_polylines = self._trace_skeleton(skeleton)
        _cb(55)

        # 4. Douglas-Peucker 简化
        epsilon = self._detail_to_epsilon(detail_level, W, H)
        simplified = []
        for pl in raw_polylines:
            s = self._simplify_polyline(pl, epsilon)
            if len(s) >= 2:
                simplified.append(s)
        # 4.5 串联首尾相邻折线 + 自动闭合环形路径
        self.polylines = self._chain_polylines(simplified)
        _cb(80)

        # 5. 如果是填充模式，生成填充针迹
        if mode == 'fill':
            self.polylines = self._generate_fill_patterns(self.polylines, fill_type, fill_angle)

        _cb(90)

        # 6. 计算 DST 物理尺寸（保持宽高比，最长边 = 200mm）
        self._compute_dst_size(W, H)
        _cb(100)

        return self.polylines

    def render_preview(self) -> Optional[Image.Image]:
        """将折线渲染为黑线白底 PIL 图像供 GUI 预览。"""
        if not self.polylines:
            return None

        from PIL import ImageDraw
        W, H = self._img_w_px, self._img_h_px
        preview = Image.new("RGB", (W, H), "white")
        draw = ImageDraw.Draw(preview)
        for pl in self.polylines:
            if len(pl) >= 2:
                draw.line(pl, fill="black", width=1)
        return preview

    def save_me(self, output_path: str):
        """导出为 ME 格式（HP ME10 CAD）"""
        if not self.polylines:
            raise ValueError("没有折线数据，请先生成轮廓")
        from me_exporter_fixed import polylines_to_me
        polylines_to_me(self.polylines, output_path, scale=0.1)

    def save_dst(self, output_path: str):
        """导出为 DST 机绣格式（单色轮廓针）。导出前先做路径排序优化，最小化跳针。"""
        if not self.polylines:
            raise ValueError("没有折线数据，请先生成轮廓")

        # 贪心最近邻排序：大幅减少折线间的跳针距离
        ordered = self._optimize_path_order(self.polylines)

        W, H = self._img_w_px, self._img_h_px
        sx = self.width_mm  * 10.0 / W   # 像素 → DST 单位（0.1mm）
        sy = self.height_mm * 10.0 / H

        pattern = pyembroidery.EmbPattern()
        pattern.add_thread({"color": 0x000000, "name": "Black"})

        first = True
        last_x, last_y = 0, 0
        for pl in ordered:
            if len(pl) < 2:
                continue
            x0 = int(pl[0][0] * sx)
            y0 = int(pl[0][1] * sy)
            if not first:
                pattern.add_stitch_absolute(pyembroidery.TRIM, x0, y0)
            pattern.add_stitch_absolute(pyembroidery.JUMP, x0, y0)
            first = False

            prev_x, prev_y = x0, y0
            for px, py in pl[1:]:
                dx = int(px * sx)
                dy = int(py * sy)
                for mx, my in self._split_long(prev_x, prev_y, dx, dy):
                    pattern.add_stitch_absolute(pyembroidery.STITCH, mx, my)
                prev_x, prev_y = dx, dy
            last_x, last_y = prev_x, prev_y

        # END 放在最后一针位置，避免 pyembroidery 插入回原点(0,0)的多余 JUMP
        pattern.add_stitch_absolute(pyembroidery.END, last_x, last_y)
        pyembroidery.write(pattern, output_path)

    # ------------------------------------------------------------------
    # 填充图案生成
    # ------------------------------------------------------------------

    def _generate_fill_patterns(self, polylines: list, fill_type: str = 'simple', fill_angle: int = 0) -> list:
        """为闭合多边形生成填充针迹"""
        from simple_fill import SimpleFillGenerator

        # 根据填充类型选择生成器
        if fill_type == 'tatami':
            from fill_generator import FillPatternGenerator
            fill_gen = FillPatternGenerator(stitch_length=20.0, row_spacing=2.5)
        else:  # simple
            fill_gen = SimpleFillGenerator(stitch_length=20.0, row_spacing=2.5)

        result = []
        closed_count = 0
        filled_count = 0
        total_count = 0

        for pl in polylines:
            # 检查是否闭合
            if len(pl) >= 3:
                total_count += 1
                start, end = pl[0], pl[-1]
                dist = ((start[0] - end[0])**2 + (start[1] - end[1])**2)**0.5
                is_closed = dist <= 3

                if is_closed and len(pl) >= 4:
                    closed_count += 1

                    # 检查区域内部是否真的有填充
                    if self._is_region_filled(pl):
                        filled_count += 1
                        # 生成填充
                        if fill_type == 'tatami':
                            fill_points = fill_gen.generate_tatami_fill(pl, angle=float(fill_angle))
                        else:
                            fill_points = fill_gen.generate_fill(pl, angle=float(fill_angle))
                        if fill_points:
                            result.append(fill_points)

                # 保留轮廓
                result.append(pl)
            else:
                result.append(pl)

        print(f"fill stats: {closed_count} closed, {filled_count} filled")
        return result

    def _is_region_filled(self, polyline: list, threshold: float = 0.3) -> bool:
        """
        检查闭合区域内部是否有填充。
        计算区域内黑色像素的比例，超过阈值则认为是填充区域。
        """
        if not hasattr(self, '_binary'):
            return True  # 如果没有二值图，默认填充

        # 创建mask
        mask = np.zeros(self._binary.shape, dtype=np.uint8)
        pts = np.array(polyline, dtype=np.int32)
        cv2.fillPoly(mask, [pts], 255)

        # 计算区域内黑色像素比例
        region_pixels = mask > 0
        black_pixels = (self._binary > 0) & region_pixels

        total = np.sum(region_pixels)
        if total == 0:
            return False

        fill_ratio = np.sum(black_pixels) / total
        return fill_ratio > threshold

    # ------------------------------------------------------------------
    # 预处理：二值化
    # ------------------------------------------------------------------

    @staticmethod
    def _binarize(img_rgb: np.ndarray) -> np.ndarray:
        """
        RGB → uint8 H×W，线条区域 = 255，背景 = 0。
        使用自适应阈值，处理扫描件光照不均的情况。
        """
        gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        # 自适应阈值（BINARY_INV：深线条 → 255，白底 → 0）
        binary = cv2.adaptiveThreshold(
            blur, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=15,
            C=8,
        )
        # MORPH_OPEN：去掉孤立噪点
        kernel = np.ones((2, 2), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        return binary

    # ------------------------------------------------------------------
    # 轮廓提取（用于填充模式）
    # ------------------------------------------------------------------

    def _extract_contours(self, binary: np.ndarray) -> List[List[Tuple[int, int]]]:
        """
        使用轮廓检测提取黑色填充区域的边界。
        只提取外轮廓，过滤小噪点。
        """
        # 只获取外轮廓，不要嵌套的内部轮廓
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

        polylines = []
        min_area = 100  # 过滤掉面积小于100像素的噪点

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue

            # 转换为 (x, y) 列表
            points = [(int(pt[0][0]), int(pt[0][1])) for pt in contour]

            # 确保闭合
            if len(points) >= 3:
                if points[0] != points[-1]:
                    points.append(points[0])
                polylines.append(points)

        print(f"轮廓检测: 找到 {len(polylines)} 个外轮廓")
        return polylines

    # ------------------------------------------------------------------
    # 骨架追踪
    # ------------------------------------------------------------------

    def _trace_skeleton(self, skel: np.ndarray) -> List[List[Tuple[int, int]]]:
        """
        将 bool 骨架图追踪为折线列表。
        每条折线是 [(x, y), ...] 的列表（图像坐标，原点左上）。

        策略：
        - 端点（8-邻域度=1）优先出发
        - 沿方向最一致的未访问邻居前进（减少锯齿）
        - 到达交叉点（度≥3）停下，留给后续处理其余分支
        - 最后扫描剩余未访问像素（处理环形路径）
        - 丢弃像素数 < MIN_PATH_PIXELS 的短路径（去噪）
        """
        if not skel.any():
            return []

        H, W = skel.shape
        skel_u8 = skel.astype(np.uint8)

        # 计算每个骨架像素的 8-邻域度数（边界填0，不循环）
        kernel = np.array([[1, 1, 1],
                           [1, 0, 1],
                           [1, 1, 1]], dtype=np.float32)
        deg = cv2.filter2D(skel_u8.astype(np.float32), -1, kernel,
                           borderType=cv2.BORDER_CONSTANT)
        deg = (deg * skel_u8).astype(np.uint8)

        ys, xs = np.where(skel)
        if len(xs) == 0:
            return []

        visited = np.zeros_like(skel, dtype=bool)

        OFFSETS = [(-1, -1), (-1, 0), (-1, 1),
                   ( 0, -1),          ( 0, 1),
                   ( 1, -1), ( 1, 0), ( 1, 1)]

        def get_unvisited_neighbors(cx, cy):
            result = []
            for dx, dy in OFFSETS:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < W and 0 <= ny < H and skel[ny, nx] and not visited[ny, nx]:
                    result.append((nx, ny))
            return result

        def trace_from(sx, sy):
            path = [(sx, sy)]
            visited[sy, sx] = True
            cx, cy = sx, sy
            prev_dx, prev_dy = 0, 0

            while True:
                nbs = get_unvisited_neighbors(cx, cy)
                if not nbs:
                    break

                # 方向偏好：dot product 最大的邻居最接近当前运动方向
                if prev_dx != 0 or prev_dy != 0:
                    nbs.sort(
                        key=lambda p: -(p[0] - cx) * prev_dx - (p[1] - cy) * prev_dy
                    )

                nx, ny = nbs[0]
                prev_dx, prev_dy = nx - cx, ny - cy
                path.append((nx, ny))
                visited[ny, nx] = True
                cx, cy = nx, ny

                # 遇交叉点：纳入路径末尾但不继续，
                # 让后续从该点出发处理其余分支
                if deg[cy, cx] >= 3:
                    break

            return path

        polylines = []

        # 第一轮：从所有端点（度=1）出发
        for y, x in zip(ys.tolist(), xs.tolist()):
            if deg[y, x] == 1 and not visited[y, x]:
                path = trace_from(int(x), int(y))
                if len(path) >= MIN_PATH_PIXELS:
                    polylines.append(path)

        # 第二轮：处理剩余未访问像素（环形路径、交叉后的分支）
        for y, x in zip(ys.tolist(), xs.tolist()):
            if not visited[y, x]:
                path = trace_from(int(x), int(y))
                if len(path) >= MIN_PATH_PIXELS:
                    polylines.append(path)

        return polylines

    # ------------------------------------------------------------------
    # Douglas-Peucker 简化
    # ------------------------------------------------------------------

    @staticmethod
    def _simplify_polyline(
        points: List[Tuple[int, int]], epsilon: float
    ) -> List[Tuple[int, int]]:
        if len(points) <= 2:
            return points
        pts = np.array(points, dtype=np.int32).reshape(-1, 1, 2)
        simplified = cv2.approxPolyDP(pts, epsilon, closed=False)
        return [(int(p[0][0]), int(p[0][1])) for p in simplified]

    # ------------------------------------------------------------------
    # 折线串联 + 环形闭合
    # ------------------------------------------------------------------

    @staticmethod
    def _chain_polylines(polylines: list) -> list:
        """
        将端点相邻（距离 ≤ 1px）的折线串联为更长的折线，
        同时自动闭合首尾相接的环形路径。
        减少 DST 导出中的 JUMP/TRIM 断点数量。
        """
        if len(polylines) <= 1:
            return polylines

        from collections import defaultdict

        n = len(polylines)
        used = [False] * n

        # 起点 / 终点 → 折线索引列表
        head_map: dict = defaultdict(list)
        tail_map: dict = defaultdict(list)
        for i, pl in enumerate(polylines):
            head_map[pl[0]].append(i)
            tail_map[pl[-1]].append(i)

        def find_next(pt):
            """在 pt 邻域（±1px）寻找首个未用折线及其方向。"""
            x0, y0 = pt
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    cand = (x0 + dx, y0 + dy)
                    for idx in head_map.get(cand, []):
                        if not used[idx]:
                            return idx, False   # 正向
                    for idx in tail_map.get(cand, []):
                        if not used[idx]:
                            return idx, True    # 反向接入
            return None, None

        result = []
        for start_i in range(n):
            if used[start_i]:
                continue
            used[start_i] = True
            chain = list(polylines[start_i])

            while True:
                next_i, rev = find_next(chain[-1])
                if next_i is None:
                    break
                used[next_i] = True
                seg = polylines[next_i]
                if rev:
                    seg = seg[::-1]
                # 避免重复端点
                if seg[0] == chain[-1]:
                    chain.extend(seg[1:])
                else:
                    chain.extend(seg)
                # 检查链是否已闭合回起点
                sx, sy = chain[0]
                ex, ey = chain[-1]
                dist = ((sx - ex)**2 + (sy - ey)**2)**0.5
                if dist <= 30:
                    if (sx, sy) != (ex, ey):
                        chain.append((sx, sy))
                    break

            # 最终再检查一次是否可以闭合
            sx, sy = chain[0]
            ex, ey = chain[-1]
            dist = ((sx - ex)**2 + (sy - ey)**2)**0.5
            if (sx, sy) != (ex, ey) and dist <= 30:
                chain.append((sx, sy))

            result.append(chain)

        return result

    # ------------------------------------------------------------------
    # 细节程度 → epsilon 映射
    # ------------------------------------------------------------------

    @staticmethod
    def _detail_to_epsilon(detail_level: int, W: int, H: int) -> float:
        """
        对数映射：
          level=1   → eps ≈ 2.0% 对角线（最粗，线段极少）
          level=100 → eps ≈ 0.1% 对角线（最精细，贴合原图）
        """
        diag    = math.sqrt(W * W + H * H)
        eps_max = diag * 0.020
        eps_min = diag * 0.001
        t       = (detail_level - 1) / 99.0
        epsilon = eps_max * ((eps_min / eps_max) ** t)
        return max(0.5, epsilon)

    # ------------------------------------------------------------------
    # DST 物理尺寸（保持宽高比，最长边 = 200mm）
    # ------------------------------------------------------------------

    def _compute_dst_size(self, W: int, H: int):
        aspect = W / max(H, 1)
        if aspect >= 1.0:
            self.width_mm  = DST_MAX_DIM_MM
            self.height_mm = DST_MAX_DIM_MM / aspect
        else:
            self.height_mm = DST_MAX_DIM_MM
            self.width_mm  = DST_MAX_DIM_MM * aspect

    # ------------------------------------------------------------------
    # 辅助：折线顺序优化（最小化跳针总距离）
    # ------------------------------------------------------------------

    @staticmethod
    def _optimize_path_order(polylines: list) -> list:
        """
        贪心最近邻排序，最小化相邻折线之间的跳针距离。
        同时考虑每条折线正向/反向两种走法。
        使用 scipy.spatial.cKDTree，时间复杂度 O(n log n)，
        对数万条折线也能在 1 秒内完成。
        """
        if len(polylines) <= 1:
            return polylines

        from scipy.spatial import cKDTree

        n = len(polylines)
        # points[2i]   = 折线 i 正向入口（起点）
        # points[2i+1] = 折线 i 反向入口（终点）
        pts = np.empty((2 * n, 2), dtype=np.float64)
        for i, pl in enumerate(polylines):
            pts[2 * i    ] = pl[0]
            pts[2 * i + 1] = pl[-1]

        tree  = cKDTree(pts)
        used  = np.zeros(n, dtype=bool)
        result = []

        # 从第一条折线出发
        used[0] = True
        result.append(polylines[0])
        cur = np.array(polylines[0][-1], dtype=np.float64)

        k_query = min(200, 2 * n)   # 每步查询最近 200 个候选

        while len(result) < n:
            k = min(k_query, 2 * (n - len(result)) + 2)
            _, idxs = tree.query(cur, k=k)
            if k == 1:
                idxs = [int(idxs)]

            chosen = None
            for raw_idx in idxs:
                pl_i = int(raw_idx) // 2
                if not used[pl_i]:
                    used[pl_i] = True
                    pl = polylines[pl_i]
                    # 如果离终点更近，反向走
                    if int(raw_idx) % 2 == 1:
                        pl = pl[::-1]
                    chosen = pl
                    break

            if chosen is None:          # 极端回退：取第一个未用的
                for i in range(n):
                    if not used[i]:
                        used[i] = True
                        chosen = polylines[i]
                        break

            result.append(chosen)
            cur = np.array(chosen[-1], dtype=np.float64)

        return result

    # ------------------------------------------------------------------
    # 辅助：拆分超长针迹
    # ------------------------------------------------------------------

    @staticmethod
    def _split_long(x1, y1, x2, y2, max_u=DST_MAX_STITCH) -> list:
        dx, dy = x2 - x1, y2 - y1
        dist = math.sqrt(dx * dx + dy * dy)
        if dist <= max_u:
            return [(x2, y2)]
        n = math.ceil(dist / max_u)
        return [
            (int(x1 + dx * k / n), int(y1 + dy * k / n))
            for k in range(1, n + 1)
        ]
