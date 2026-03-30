#!/usr/bin/env python3
"""
grid_remover.py — 去除刺绣图稿中的密集网格，保留设计轮廓。

用法:
    python grid_remover.py input.png [-o output.png] [--debug]
    python grid_remover.py input.png --threshold 100 --kernel 7
"""

import argparse
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
from scipy.signal import find_peaks


# ─────────────────────────────────────────────
# 1. 自动检测网格周期
# ─────────────────────────────────────────────

def _autocorr_period(strip: np.ndarray) -> Optional[int]:
    """用自相关找一维信号的主周期（像素数）。"""
    s = strip.astype(float) - strip.mean()
    acf = np.correlate(s, s, mode="full")
    acf = acf[len(acf) // 2 :]
    if acf[0] == 0:
        return None
    peaks, _ = find_peaks(acf[1 : len(s) // 2], height=acf[0] * 0.05)
    return int(peaks[0] + 1) if len(peaks) > 0 else None


def detect_grid_period(gray: np.ndarray) -> Tuple[int, int]:
    """
    返回 (period_h, period_v)：水平方向（竖线间距）和垂直方向（横线间距）的像素周期。
    取图像 1/4、1/2、3/4 处三条扫描线的中位数，提高鲁棒性。
    """
    h, w = gray.shape

    h_vals = [_autocorr_period(gray[int(h * f), :]) for f in (0.25, 0.5, 0.75)]
    v_vals = [_autocorr_period(gray[:, int(w * f)]) for f in (0.25, 0.5, 0.75)]

    h_vals = [v for v in h_vals if v]
    v_vals = [v for v in v_vals if v]

    period_h = int(round(np.median(h_vals))) if h_vals else 9
    period_v = int(round(np.median(v_vals))) if v_vals else 9
    return period_h, period_v


# ─────────────────────────────────────────────
# 2. 找网格偏移量
# ─────────────────────────────────────────────

def _find_offset(profile: np.ndarray, period: int) -> int:
    """在 [0, period) 中找使 profile 均值最小的偏移（网格线最暗）。"""
    best_off, best_score = 0, float("inf")
    for off in range(period):
        score = float(np.mean(profile[off::period]))
        if score < best_score:
            best_score, best_off = score, off
    return best_off


# ─────────────────────────────────────────────
# 3. 构建网格掩码
# ─────────────────────────────────────────────

def build_grid_mask(
    gray: np.ndarray,
    period_h: int,
    period_v: int,
    offset_h: int,
    offset_v: int,
    design_threshold: int,
) -> np.ndarray:
    """
    在周期性网格位置标记掩码，但保护深色设计像素（< design_threshold）。
    返回 uint8 掩码，255 = 需要去除的网格像素。
    """
    h, w = gray.shape
    mask = np.zeros((h, w), dtype=np.uint8)

    # 竖向网格线（每隔 period_h 列）
    cols = np.arange(offset_h % period_h, w, period_h)
    mask[:, cols] = 255

    # 横向网格线（每隔 period_v 行）
    rows = np.arange(offset_v % period_v, h, period_v)
    mask[rows, :] = 255

    # 保护设计轮廓（深色像素不被覆盖）
    mask[gray < design_threshold] = 0

    return mask


# ─────────────────────────────────────────────
# 4. 快速填充：用邻域非网格像素的加权均值替换网格像素
# ─────────────────────────────────────────────

def fill_grid(img: np.ndarray, mask: np.ndarray, kernel_size: int = 7) -> np.ndarray:
    """
    对每个被掩码的像素，用其 kernel_size×kernel_size 邻域内
    非掩码像素的均值填充。比 cv2.inpaint 快得多，适合细线网格。
    """
    result = img.copy()
    non_masked = (mask == 0).astype(np.float32)
    k = np.ones((kernel_size, kernel_size), np.float32)

    for ch in range(img.shape[2]):
        channel = img[:, :, ch].astype(np.float32)
        weighted_sum = cv2.filter2D(channel * non_masked, -1, k,
                                    borderType=cv2.BORDER_REFLECT)
        weight_cnt = cv2.filter2D(non_masked, -1, k,
                                  borderType=cv2.BORDER_REFLECT)
        weight_cnt = np.maximum(weight_cnt, 1e-6)
        local_avg = weighted_sum / weight_cnt
        result[:, :, ch] = np.where(mask > 0, local_avg, channel).astype(np.uint8)

    return result


# ─────────────────────────────────────────────
# 5. 主流程
# ─────────────────────────────────────────────

def remove_grid(
    input_path: str,
    output_path: Optional[str] = None,
    design_threshold: int = 100,
    kernel_size: int = 7,
    period_h: Optional[int] = None,
    period_v: Optional[int] = None,
    debug: bool = False,
) -> np.ndarray:
    """
    去除图像中的密集网格，保留设计轮廓。

    参数
    ----
    input_path        输入图像路径
    output_path       输出路径（默认：原文件名加 _no_grid 后缀）
    design_threshold  灰度阈值：低于此值的像素视为设计轮廓，不被删除（默认 100）
    kernel_size       填充邻域大小，奇数，越大越平滑（默认 7）
    period_h          手动指定水平周期（像素），None = 自动检测
    period_v          手动指定垂直周期（像素），None = 自动检测
    debug             True 时额外保存掩码图像
    """
    img = cv2.imread(str(input_path))
    if img is None:
        raise FileNotFoundError(f"无法读取图像：{input_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # 自动检测周期
    if period_h is None or period_v is None:
        ph, pv = detect_grid_period(gray)
        period_h = period_h or ph
        period_v = period_v or pv
    print(f"Grid period: h={period_h}px, v={period_v}px")

    # 找偏移
    col_profile = np.mean(gray, axis=0)
    row_profile = np.mean(gray, axis=1)
    offset_h = _find_offset(col_profile, period_h)
    offset_v = _find_offset(row_profile, period_v)
    print(f"Grid offset: h={offset_h}px, v={offset_v}px")

    # 构建掩码
    mask = build_grid_mask(gray, period_h, period_v, offset_h, offset_v, design_threshold)
    masked_pct = 100.0 * np.sum(mask > 0) / mask.size
    print(f"Mask: {np.sum(mask > 0)} px ({masked_pct:.1f}%)")

    if debug:
        p = Path(input_path)
        mask_path = p.parent / f"{p.stem}_grid_mask.png"
        cv2.imwrite(str(mask_path), mask)
        print(f"Debug mask saved: {mask_path}")

    # 填充网格区域
    result = fill_grid(img, mask, kernel_size)

    # 保存结果
    if output_path is None:
        p = Path(input_path)
        output_path = p.parent / f"{p.stem}_no_grid{p.suffix}"
    cv2.imwrite(str(output_path), result)
    print(f"Saved: {output_path}")

    return result


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="去除刺绣图稿中的密集网格，保留设计轮廓"
    )
    parser.add_argument("input", help="输入图像路径")
    parser.add_argument("-o", "--output", help="输出图像路径（可选）")
    parser.add_argument(
        "--threshold", type=int, default=100,
        help="设计像素保护阈值，低于此灰度值的像素不被删除（默认 100）",
    )
    parser.add_argument(
        "--kernel", type=int, default=7,
        help="填充邻域大小（奇数，默认 7）",
    )
    parser.add_argument(
        "--period-h", type=int, default=None,
        help="手动指定水平网格周期（像素），默认自动检测",
    )
    parser.add_argument(
        "--period-v", type=int, default=None,
        help="手动指定垂直网格周期（像素），默认自动检测",
    )
    parser.add_argument("--debug", action="store_true", help="保存掩码调试图像")
    args = parser.parse_args()

    remove_grid(
        args.input,
        args.output,
        args.threshold,
        args.kernel,
        args.period_h,
        args.period_v,
        args.debug,
    )
