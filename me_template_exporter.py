"""
基于模板的ME格式导出器 v2
使用状态跟踪确保正确替换
"""
import gzip
import math
from datetime import datetime
from typing import List, Tuple


def polylines_to_me_template(
    polylines: List[List[Tuple[int, int]]],
    output_path: str,
    template_path: str,
    scale: float = 0.1
):
    """基于模板生成ME文件"""
    # 读取模板
    with gzip.open(template_path, 'rt', encoding='utf-8') as f:
        template_lines = f.readlines()

    # 准备新数据
    all_points = []
    bsplines = []

    all_y = [y for pl in polylines for x, y in pl]
    max_y = max(all_y) if all_y else 0

    for polyline in polylines:
        start_idx = len(all_points)
        pt_ids = []
        for x, y in polyline:
            mx = x * scale
            my = (max_y - y) * scale
            all_points.append((mx, my))
            pt_ids.append(2750 + start_idx + len(pt_ids))
        bsplines.append(pt_ids)

    # 计算边界
    if all_points:
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
    else:
        min_x = max_x = min_y = max_y = 0.0

    # 生成新内容
    output_lines = []
    i = 0
    in_dessin_section = False
    skip_until = None

    while i < len(template_lines):
        line = template_lines[i].rstrip('\n')

        # 如果在跳过模式，继续跳过
        if skip_until:
            if line == skip_until:
                skip_until = None
            i += 1
            continue

        # 检测进入dessin段
        if line == "dessin" and i > 0 and template_lines[i-1].strip() == "#~6":
            in_dessin_section = True
            output_lines.append(line)
            i += 1
            continue

        # 检测离开dessin段
        if in_dessin_section and line == "#~6":
            in_dessin_section = False

        # 替换#~2段
        if line == "#~2":
            output_lines.extend(_generate_section_2(len(all_points), len(bsplines)))
            skip_until = "#~3"
            i += 1
            continue

        # 替换#~3段
        if line == "#~3":
            output_lines.extend(_generate_section_3(min_x, max_x, min_y, max_y))
            skip_until = "#~31"
            i += 1
            continue

        # 替换dessin组的#~61段（点定义）
        if line == "#~61" and in_dessin_section:
            output_lines.extend(_generate_points_section(all_points))
            skip_until = "#~62"
            i += 1
            continue

        # 替换dessin组的#~62段（BSPL定义）
        if line == "#~62" and in_dessin_section:
            output_lines.extend(_generate_bspl_section(bsplines, all_points))
            skip_until = "#~71"
            i += 1
            continue

        # 其他行保持不变
        output_lines.append(line)
        i += 1

    # 写入文件
    content = '\n'.join(output_lines) + '\n'
    with gzip.open(output_path, 'wt', encoding='utf-8') as f:
        f.write(content)

    print(f"已导出 {len(polylines)} 条折线到 {output_path}")


def _generate_section_2(n_points: int, n_bsplines: int) -> List[str]:
    """生成#~2段"""
    last_pt_id = 2750 + n_points - 1
    last_bspl_id = 11755 + n_bsplines - 1
    return [
        "#~2", "2", "TC41:1", f"TC5:{n_bsplines + 1}",
        "dessin", "4", "TC61:2750", "TC62:11755",
        f"TC72:{last_bspl_id + 1}", f"PLAST:{last_bspl_id + 1}",
        "aufsatz", "3", f"TC61:{last_pt_id + 1}",
        f"TC62:{last_bspl_id + 2}", f"PLAST:{last_bspl_id + 3}",
        "temp", "3", f"TC61:{last_pt_id + 4}",
        f"TC62:{last_bspl_id + 5}", f"PLAST:{last_bspl_id + 6}",
        "stich_part", "3", f"TC61:{last_pt_id + 7}",
        f"TC62:{last_bspl_id + 8}", f"PLAST:{last_bspl_id + 8}",
        "Top", "1", f"PLAST:{last_bspl_id + 8}", f"LAST:{last_bspl_id + 8}",
    ]


def _generate_section_3(min_x: float, max_x: float, min_y: float, max_y: float) -> List[str]:
    """生成#~3段"""
    now = datetime.now()
    return [
        "#~3", "isp_dbmv.me", "", "", "", "", "", "",
        now.strftime("%d-%b-%Y"), now.strftime("%H:%M:%S"), "",
        "HP ME10 Rev. 08.70G 30-Jun-1999", "2.50", "2D",
        f"{min_x:.6f}", f"{max_x:.6f}", f"{min_y:.6f}", f"{max_y:.6f}",
        "0", "0", "1", "A1", "1", "mm", "RAD",
        "1e-12", "0.0001", "32",
        "0", "0", "1", "0", "0", "0", "0", "1",
        "0", "0", "0", "0", "1", "0", "0", "0", "0", "1",
        "4", "1", "0", "0", "3.5",
    ]


def _generate_points_section(points: List[Tuple[float, float]]) -> List[str]:
    """生成点定义段"""
    lines = ["#~61"]
    for i, (x, y) in enumerate(points):
        lines.extend(["P", str(2750 + i), f"{x:.6f}", f"{y:.6f}", "|~"])
    return lines


def _generate_bspl_section(bsplines: List[List[int]], points: List[Tuple[float, float]]) -> List[str]:
    """生成BSPL定义段"""
    lines = ["#~62"]
    for i, pt_ids in enumerate(bsplines):
        n_pts = len(pt_ids)
        degree = 4
        chord_lengths = [0.0]
        for j in range(1, n_pts):
            pt1 = points[pt_ids[j-1] - 2750]
            pt2 = points[pt_ids[j] - 2750]
            dx = pt2[0] - pt1[0]
            dy = pt2[1] - pt1[1]
            dist = math.sqrt(dx*dx + dy*dy)
            chord_lengths.append(chord_lengths[-1] + dist)
        total_length = chord_lengths[-1] if chord_lengths[-1] > 0 else 1.0
        knots = []
        for j in range(degree):
            knots.append(0.0)
        for j in range(1, n_pts - degree + 1):
            avg = sum(chord_lengths[j:j+degree]) / degree
            knots.append(avg)
        for j in range(degree):
            knots.append(total_length)
        lines.extend([
            "BSPL", str(11755 + i), "751514381",
            "2", "0", "0", "4", "56", "345", "80", "624",
            str(degree), "0", "0.000000", f"{total_length:.6f}",
            str(pt_ids[0]), str(pt_ids[-1]), str(n_pts),
        ])
        for pt_id in pt_ids:
            lines.append(str(pt_id))
        lines.append(str(len(knots)))
        for k in knots:
            lines.append(f"{k:.6f}")
        lines.append(str(n_pts))
        for pt_id in pt_ids:
            lines.extend([str(pt_id), "0", "0", "0", "0", "0", "0"])
        lines.append("|~")
    return lines
