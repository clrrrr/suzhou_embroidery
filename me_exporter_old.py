"""
ME 格式导出器 - HP ME10 CAD 格式
基于 114339.me 和 114342-2.me 样本文件逆向工程
"""
import gzip
import math
from datetime import datetime
from typing import List, Tuple


class MEExporter:
    def __init__(self):
        self.points: List[Tuple[float, float]] = []
        self.bsplines: List[List[int]] = []  # 每个BSPL的控制点ID列表
        self.point_id = 2750  # 起始点 ID
        self.bspl_id = 11755  # 起始BSPL ID

    def add_polyline(self, coords: List[Tuple[float, float]]):
        """添加折线（转换为BSPL）"""
        if len(coords) < 2:
            return

        start_id = self.point_id
        pt_ids = []
        for x, y in coords:
            self.points.append((x, y))
            pt_ids.append(self.point_id)
            self.point_id += 1

        # 将整条折线作为一个BSPL
        self.bsplines.append(pt_ids)

    def export(self, output_path: str, compress: bool = True):
        """导出 ME 格式文件"""
        content = self._generate_me_content()

        if compress:
            with gzip.open(output_path, 'wt', encoding='utf-8') as f:
                f.write(content)
        else:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)

    def _generate_me_content(self) -> str:
        """生成 ME 文件内容"""
        lines = []

        # 计算边界
        if not self.points:
            min_x = max_x = min_y = max_y = 0.0
        else:
            xs = [p[0] for p in self.points]
            ys = [p[1] for p in self.points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)

        last_pt_id = 2750 + len(self.points) - 1
        last_bspl_id = 11755 + len(self.bsplines) - 1

        # #~2 段：目录结构
        lines.extend([
            "#~2",
            "2",
            "TC41:1",
            f"TC5:{len(self.bsplines) + 1}",
            "dessin",
            "4",
            "TC61:2750",
            f"TC62:{11755}",
            f"TC72:{last_bspl_id + 1}",
            f"PLAST:{last_bspl_id + 1}",
            "aufsatz", "3",
            f"TC61:{last_pt_id + 1}",
            f"TC62:{last_bspl_id + 2}",
            f"PLAST:{last_bspl_id + 3}",
            "temp", "3",
            f"TC61:{last_pt_id + 4}",
            f"TC62:{last_bspl_id + 5}",
            f"PLAST:{last_bspl_id + 6}",
            "stich_part", "3",
            f"TC61:{last_pt_id + 7}",
            f"TC62:{last_bspl_id + 8}",
            f"PLAST:{last_bspl_id + 8}",
            "Top", "1",
            f"PLAST:{last_bspl_id + 8}",
            f"LAST:{last_bspl_id + 8}",
        ])

        # #~3 段：文件头
        now = datetime.now()
        lines.extend([
            "#~3",
            "isp_dbmv.me", "", "", "", "", "", "",
            now.strftime("%d-%b-%Y"),
            now.strftime("%H:%M:%S"), "",
            "HP ME10 Rev. 08.70G 30-Jun-1999",
            "2.50", "2D",
            f"{min_x:.6f}",
            f"{max_x:.6f}",
            f"{min_y:.6f}",
            f"{max_y:.6f}",
            "0", "0", "1", "A1", "1", "mm", "RAD",
            "1e-12", "0.0001", "32",
            "0", "0", "1", "0", "0", "0", "0", "1",
            "0", "0", "0", "0", "1", "0", "0", "0", "0", "1",
            "4", "1", "0", "0", "3.5",
        ])

        # #~31 段：预览图（简化版）
        lines.extend([
            "#~31", "PXMAP", "1", "-1", "preview",
            "441", "361", "8", "0", "0", "441", "361",
            "1", "1", "0", "1", "0", "0", "0", "1",
        ])

        # #~41 段：参数设置（简化）
        lines.extend([
            "#~41", "PSTAT", "1", "0", "0", "|~",
        ])

        # #~5 段：装配体
        lines.extend([
            "#~5",
            f"ASSE", f"{len(self.bsplines) + 1}", "1", "1", "dessin",
            "1", "0", "0", "0.000000", "0.000000", "0", "|~",
        ])

        # #~6 和 #~61 段：点定义
        lines.extend(["#~6", "#~61"])
        for i, (x, y) in enumerate(self.points):
            lines.extend([
                "P",
                str(2750 + i),
                f"{x:.6f}",
                f"{y:.6f}",
                "|~",
            ])

        # #~62 段：BSPL定义
        lines.append("#~62")
        for i, pt_ids in enumerate(self.bsplines):
            n_pts = len(pt_ids)
            degree = 4  # 固定使用4次B样条

            # 计算控制点之间的chord length
            chord_lengths = [0.0]
            for j in range(1, n_pts):
                pt1 = self.points[pt_ids[j-1] - 2750]
                pt2 = self.points[pt_ids[j] - 2750]
                dx = pt2[0] - pt1[0]
                dy = pt2[1] - pt1[1]
                dist = math.sqrt(dx*dx + dy*dy)
                chord_lengths.append(chord_lengths[-1] + dist)

            total_length = chord_lengths[-1]

            # 生成节点向量（n + degree个节点）
            n_knots = n_pts + degree
            knots = []
            # 前degree个为0
            for j in range(degree):
                knots.append(0.0)
            # 中间节点：使用averaging方法
            for j in range(1, n_pts - degree + 1):
                # 取相邻degree个参数的平均值
                avg = sum(chord_lengths[j:j+degree]) / degree
                knots.append(avg)
            # 后degree个为total_length
            for j in range(degree):
                knots.append(total_length)

            lines.extend([
                "BSPL",
                str(11755 + i),
                "751514381",
                "2", "0", "0", "4",
                "56", "345", "80", "624",
                str(degree),
                "0",
                "0.000000",
                f"{total_length:.6f}",
                str(pt_ids[0]),
                str(pt_ids[-1]),
                str(n_pts),
            ])

            # 控制点列表
            for pt_id in pt_ids:
                lines.append(str(pt_id))

            # 节点向量
            lines.append(str(len(knots)))
            for k in knots:
                lines.append(f"{k:.6f}")

            # 权重数据
            lines.append(str(n_pts))
            for pt_id in pt_ids:
                lines.extend([str(pt_id), "0", "0", "0", "0", "0", "0"])

            lines.append("|~")

        # #~71 和 #~72 段：纹理/结束标记
        lines.extend(["#~71", "#~72"])

        # 添加辅助组（aufsatz, temp, stich_part）
        # 这些组包含边界框等辅助几何数据
        next_pt_id = last_pt_id + 1
        next_bspl_id = last_bspl_id + 1

        # aufsatz 组
        lines.extend([
            "#~6", "aufsatz", "#~61",
            "P", str(next_pt_id), "0.000000", "0.000000", "|~",
            "P", str(next_pt_id + 1), f"{max_x:.6f}", "0.000000", "|~",
            "P", str(next_pt_id + 2), "0.000000", "0.000000", "|~",
            "P", str(next_pt_id + 3), "0.000000", "0.000000", "|~",
            "P", str(next_pt_id + 4), "0.000000", f"{min_y:.6f}", "|~",
            "#~62",
            "LIN", str(next_bspl_id), "1073741888", "3", "0", "0", "4",
            "53", "343", "61", "580", str(next_pt_id + 1), str(next_pt_id + 2), "|~",
            "LIN", str(next_bspl_id + 1), "1073741888", "3", "0", "0", "4",
            "53", "343", "61", "591", str(next_pt_id + 3), str(next_pt_id + 4), "|~",
            "PMA", str(next_bspl_id + 2), "0", "1", "0", "0", "3",
            "52", "343", "61", "1", str(next_pt_id), "|~",
            "#~71", "#~72"
        ])

        next_pt_id += 5
        next_bspl_id += 3

        # temp 组
        lines.extend([
            "#~6", "temp", "#~61",
            "P", str(next_pt_id), "0.000000", "0.000000", "|~",
            "P", str(next_pt_id + 1), "0.000000", "0.000000", "|~",
            "P", str(next_pt_id + 2), "0.000000", "0.000000", "|~",
            "#~62",
            "PMA", str(next_bspl_id), "0", "1", "0", "0", "3",
            "52", "343", "61", "1", str(next_pt_id), "|~",
            "#~71", "#~72"
        ])

        next_pt_id += 3
        next_bspl_id += 1

        # stich_part 组
        lines.extend([
            "#~6", "stich_part", "#~61",
            "P", str(next_pt_id), "0.000000", "0.000000", "|~",
            "#~62",
            "PMA", str(next_bspl_id), "0", "1", "0", "0", "3",
            "52", "343", "61", "1", str(next_pt_id), "|~",
            "#~71", "#~72"
        ])

        # 添加结尾段落（工业软件必需）
        # 多个空段落
        for _ in range(100):
            lines.append("#~")

        # #B 段
        lines.extend([
            "#B", "27", "1010", "1067", "0",
            "0.000", "0.000", "0.000", "0.000", "#~"
        ])

        # #C 段
        lines.extend([
            "#C",
            "pixmap.counter=0",
            "#~"
        ])

        # #FIG 段
        lines.extend([
            "#FIG",
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<isp>',
            '  <relationstack type="INSTANCE"></relationstack>',
            '  <relationstack type="GEO"></relationstack>',
            '  <relationstack type="ORIGINAL"></relationstack>',
            '  <relationstack type="OUTLINE"></relationstack>',
            '  <relationstack type="RESULT"></relationstack>',
            '  <relationstack type="REFERENCE"></relationstack>',
            '  <relationstack type="SUBDIVISION"></relationstack>',
            '  <relationstack type="BEGIN"></relationstack>',
            '  <relationstack type="END"></relationstack>',
            '</isp>',
            "",
            "#~",
            "#~ISP"
        ])

        return '\n'.join(lines) + '\n'


def polylines_to_me(polylines: List[List[Tuple[int, int]]],
                    output_path: str,
                    scale: float = 0.1):
    """
    将折线列表转换为 ME 格式

    参数:
        polylines: 折线列表，每条折线是 [(x, y), ...] 的点序列
        output_path: 输出文件路径
        scale: 缩放系数（像素 → mm），默认 0.1
    """
    exporter = MEExporter()

    # 找到所有点的 Y 坐标范围用于翻转
    all_y = [y for pl in polylines for x, y in pl]
    max_y = max(all_y) if all_y else 0

    for polyline in polylines:
        # 转换坐标：像素 → mm，Y 轴翻转（相对于图像顶部）
        coords = [(x * scale, (max_y - y) * scale) for x, y in polyline]
        exporter.add_polyline(coords)

    exporter.export(output_path, compress=True)
    # print(f"已导出 {len(polylines)} 条折线到 {output_path}")
