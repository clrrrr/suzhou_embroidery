"""
Embroidery Fill Pattern Generator
Implements tatami fill and satin stitch patterns
"""
import math
from typing import List, Tuple
import numpy as np
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union


class FillPatternGenerator:
    def __init__(self, stitch_length: float = 2.0, row_spacing: float = 0.4):
        """
        Args:
            stitch_length: Maximum stitch length in mm
            row_spacing: Distance between fill rows in mm
        """
        self.stitch_length = stitch_length
        self.row_spacing = row_spacing

    def generate_tatami_fill(self, polygon_points: List[Tuple[float, float]],
                            angle: float = 0.0) -> List[Tuple[float, float]]:
        """
        Generate tatami fill pattern (parallel lines)

        Args:
            polygon_points: Closed polygon vertices
            angle: Fill angle in degrees (0 = horizontal)

        Returns:
            List of stitch points in optimal order
        """
        if len(polygon_points) < 3:
            return []

        # Create polygon
        poly = Polygon(polygon_points)
        if not poly.is_valid:
            poly = poly.buffer(0)

        bounds = poly.bounds
        min_x, min_y, max_x, max_y = bounds

        # Calculate rotated bounding box
        angle_rad = math.radians(angle)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Generate fill lines
        fill_points = []
        diagonal = math.sqrt((max_x - min_x)**2 + (max_y - min_y)**2)

        y = min_y - diagonal
        direction = 1  # 1 for left-to-right, -1 for right-to-left

        while y <= max_y + diagonal:
            # Create scan line
            x1 = min_x - diagonal
            x2 = max_x + diagonal

            # Rotate line
            line_start = self._rotate_point(x1, y, min_x, min_y, angle_rad)
            line_end = self._rotate_point(x2, y, min_x, min_y, angle_rad)

            scan_line = LineString([line_start, line_end])

            # Find intersections with polygon
            intersection = poly.intersection(scan_line)

            if not intersection.is_empty:
                segments = self._extract_segments(intersection)

                # Add segments in alternating direction
                for segment in segments:
                    if direction == -1:
                        segment = segment[::-1]
                    fill_points.extend(segment)

                direction *= -1

            y += self.row_spacing

        return fill_points

    def _rotate_point(self, x: float, y: float, cx: float, cy: float,
                     angle: float) -> Tuple[float, float]:
        """Rotate point around center"""
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        dx = x - cx
        dy = y - cy
        return (
            cx + dx * cos_a - dy * sin_a,
            cy + dx * sin_a + dy * cos_a
        )

    def _extract_segments(self, geom) -> List[List[Tuple[float, float]]]:
        """Extract line segments from geometry"""
        segments = []

        if geom.geom_type == 'LineString':
            coords = list(geom.coords)
            segments.append(self._split_long_stitches(coords))
        elif geom.geom_type == 'MultiLineString':
            for line in geom.geoms:
                coords = list(line.coords)
                segments.append(self._split_long_stitches(coords))

        return segments

    def _split_long_stitches(self, coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Split long stitches into smaller segments"""
        result = []
        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]
            result.append(p1)

            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            dist = math.sqrt(dx*dx + dy*dy)

            if dist > self.stitch_length:
                n_segments = int(math.ceil(dist / self.stitch_length))
                for j in range(1, n_segments):
                    t = j / n_segments
                    result.append((
                        p1[0] + dx * t,
                        p1[1] + dy * t
                    ))

        result.append(coords[-1])
        return result
