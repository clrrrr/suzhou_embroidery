"""
Simple Embroidery Fill Pattern Generator
Uses basic geometry without external dependencies
"""
import math
from typing import List, Tuple
import numpy as np


class SimpleFillGenerator:
    def __init__(self, stitch_length: float = 2.0, row_spacing: float = 0.4):
        """
        Args:
            stitch_length: Maximum stitch length in mm
            row_spacing: Distance between fill rows in mm
        """
        self.stitch_length = stitch_length
        self.row_spacing = row_spacing

    def generate_fill(self, polygon: List[Tuple[float, float]],
                     angle: float = 0.0) -> List[Tuple[float, float]]:
        """
        Generate simple horizontal fill pattern

        Args:
            polygon: Closed polygon vertices
            angle: Fill angle in degrees

        Returns:
            List of fill stitch points
        """
        if len(polygon) < 3:
            return []

        # Get bounding box
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        fill_points = []
        y = min_y + self.row_spacing / 2
        direction = 1

        while y <= max_y:
            # Find intersections with polygon at this y
            intersections = self._find_intersections(polygon, y)

            if len(intersections) >= 2:
                # Sort intersections
                intersections.sort()

                # Create fill lines between pairs
                for i in range(0, len(intersections) - 1, 2):
                    x1, x2 = intersections[i], intersections[i + 1]

                    # Generate points along this line
                    if direction == 1:
                        line_points = self._generate_line(x1, y, x2, y)
                    else:
                        line_points = self._generate_line(x2, y, x1, y)

                    fill_points.extend(line_points)

                direction *= -1

            y += self.row_spacing

        return fill_points

    def _find_intersections(self, polygon: List[Tuple[float, float]],
                           y: float) -> List[float]:
        """Find x-coordinates where horizontal line intersects polygon"""
        intersections = []
        n = len(polygon)

        for i in range(n):
            p1 = polygon[i]
            p2 = polygon[(i + 1) % n]

            y1, y2 = p1[1], p2[1]

            # Check if line segment crosses y
            if (y1 <= y < y2) or (y2 <= y < y1):
                x1, x2 = p1[0], p2[0]
                # Linear interpolation
                t = (y - y1) / (y2 - y1) if y2 != y1 else 0
                x = x1 + t * (x2 - x1)
                intersections.append(x)

        return intersections

    def _generate_line(self, x1: float, y1: float,
                      x2: float, y2: float) -> List[Tuple[float, float]]:
        """Generate points along a line with max stitch length"""
        dx = x2 - x1
        dy = y2 - y1
        dist = math.sqrt(dx*dx + dy*dy)

        if dist <= self.stitch_length:
            return [(x1, y1), (x2, y2)]

        n = int(math.ceil(dist / self.stitch_length))
        points = []
        for i in range(n + 1):
            t = i / n
            points.append((x1 + dx * t, y1 + dy * t))

        return points
