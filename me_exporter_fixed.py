"""
ME Format Exporter - Fixed Version
Includes all validation requirements and correct gzip format
"""
import math
import zlib
import struct
import time
from datetime import datetime
from typing import List, Tuple


class MEExporterFixed:
    def __init__(self):
        self.points: List[Tuple[float, float]] = []
        self.bsplines: List[List[int]] = []
        self.point_id = 2750
        self.bspl_id = 11755

    def add_polyline(self, coords: List[Tuple[float, float]]):
        if len(coords) < 2:
            return
        pt_ids = []
        for x, y in coords:
            self.points.append((x, y))
            pt_ids.append(self.point_id)
            self.point_id += 1
        self.bsplines.append(pt_ids)

    def export(self, output_path: str):
        content = self._generate_me_content()
        self._write_with_correct_gzip(content, output_path)

    def _write_with_correct_gzip(self, content: str, output_path: str):
        """Write with OS=0x03, XFL=0x00, compression level 6"""
        data = content.encode('utf-8')
        compressed = zlib.compress(data, level=6)

        # Build gzip header
        import os
        filename = os.path.basename(output_path).encode('ascii') + b'\x00'
        header = struct.pack('<BBBBLBB',
            0x1f, 0x8b, 0x08, 0x08,
            int(time.time()),
            0x00, 0x03
        )

        crc = zlib.crc32(data) & 0xffffffff
        size = len(data) & 0xffffffff

        with open(output_path, 'wb') as f:
            f.write(header)
            f.write(filename)
            f.write(compressed[2:-4])
            f.write(struct.pack('<I', crc))
            f.write(struct.pack('<I', size))

    def _generate_me_content(self) -> str:
        lines = []

        # Calculate IDs
        n_points = len(self.points)
        n_bsplines = len(self.bsplines)
        last_pt_id = 2750 + n_points - 1
        last_bspl_id = 11755 + n_bsplines - 1

        # Assembly IDs
        asse_dessin = n_bsplines + 1
        asse_aufsatz = asse_dessin + 1
        asse_temp = asse_aufsatz + 1
        asse_stich = asse_temp + 1

        # Auxiliary group IDs
        aux_pt_start = last_pt_id + 1
        aux_bspl_start = last_bspl_id + 1

        # #~2 section
        lines.extend([
            "#~2", "2", "TC41:1", f"TC5:{asse_dessin}",
            "dessin", "4",
            "TC61:2750", "TC62:11755",
            f"TC72:{last_bspl_id + 1}", f"PLAST:{last_bspl_id + 1}",
            "aufsatz", "3",
            f"TC61:{aux_pt_start}", f"TC62:{aux_bspl_start}",
            f"PLAST:{aux_bspl_start + 2}",
            "temp", "3",
            f"TC61:{aux_pt_start + 5}", f"TC62:{aux_bspl_start + 3}",
            f"PLAST:{aux_bspl_start + 3}",
            "stich_part", "3",
            f"TC61:{aux_pt_start + 8}", f"TC62:{aux_bspl_start + 4}",
            f"PLAST:{aux_bspl_start + 4}",
            "Top", "1",
            f"PLAST:{aux_bspl_start + 4}", f"LAST:{aux_bspl_start + 4}",
        ])

        # Calculate bounds
        if self.points:
            xs = [p[0] for p in self.points]
            ys = [p[1] for p in self.points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
        else:
            min_x = max_x = min_y = max_y = 0.0

        # #~3 section
        now = datetime.now()
        lines.extend([
            "#~3", "isp_dbmv.me", "", "", "", "", "", "",
            now.strftime("%d-%b-%Y"), now.strftime("%H:%M:%S"), "",
            "HP ME10 Rev. 08.70G 30-Jun-1999", "2.50", "2D",
            f"{min_x:.6f}", f"{max_x:.6f}", f"{min_y:.6f}", f"{max_y:.6f}",
            "0", "0", "1", "A1", "1", "mm", "RAD",
            "1e-12", "0.0001", "32",
            "0", "0", "1", "0", "0", "0", "0", "1",
            "0", "0", "0", "0", "1", "0", "0", "0", "0", "1",
            "4", "1", "0", "0", "3.5",
        ])

        # #~31 and #~41 sections
        lines.extend([
            "#~31", "PXMAP", "1", "-1", "preview",
            "441", "361", "8", "0", "0", "441", "361",
            "1", "1", "0", "1", "0", "0", "0", "1",
            "#~41", "PSTAT", "1", "0", "0", "|~",
        ])

        # #~5 section - assemblies for ALL groups
        lines.extend([
            "#~5",
            "ASSE", f"{asse_dessin}", "1", "1", "dessin",
            "1", "0", "0", "0.000000", "0.000000", "0", "|~",
            "ASSE", f"{asse_aufsatz}", "1", "1", "aufsatz",
            "1", "0", "0", "0.000000", "0.000000", "0", "|~",
            "ASSE", f"{asse_temp}", "1", "1", "temp",
            "1", "0", "0", "0.000000", "0.000000", "0", "|~",
            "ASSE", f"{asse_stich}", "1", "1", "stich_part",
            "1", "0", "0", "0.000000", "0.000000", "0", "|~",
        ])

        # #~6 dessin geometry
        lines.extend(["#~6", "#~61"])
        for i, (x, y) in enumerate(self.points):
            lines.extend(["P", str(2750 + i), f"{x:.6f}", f"{y:.6f}", "|~"])

        # #~62 BSPL definitions
        lines.append("#~62")
        for i, pt_ids in enumerate(self.bsplines):
            lines.extend(self._generate_bspl(i, pt_ids))

        lines.extend(["#~71", "#~72"])

        # Auxiliary groups with assemblies
        # aufsatz group
        lines.extend([
            "#~6", "aufsatz", "#~61",
            "P", str(aux_pt_start), "0.000000", "0.000000", "|~",
            "P", str(aux_pt_start + 1), f"{max_x:.6f}", "0.000000", "|~",
            "P", str(aux_pt_start + 2), "0.000000", "0.000000", "|~",
            "P", str(aux_pt_start + 3), "0.000000", "0.000000", "|~",
            "P", str(aux_pt_start + 4), "0.000000", f"{min_y:.6f}", "|~",
            "#~62",
            "LIN", str(aux_bspl_start), "1073741888", "3", "0", "0", "4",
            "53", "343", "61", "580", str(aux_pt_start + 1), str(aux_pt_start + 2), "|~",
            "LIN", str(aux_bspl_start + 1), "1073741888", "3", "0", "0", "4",
            "53", "343", "61", "591", str(aux_pt_start + 3), str(aux_pt_start + 4), "|~",
            "PMA", str(aux_bspl_start + 2), "0", "1", "0", "0", "3",
            "52", "343", "61", "1", str(aux_pt_start), "|~",
            "#~71", "#~72"
        ])

        # temp group
        lines.extend([
            "#~6", "temp", "#~61",
            "P", str(aux_pt_start + 5), "0.000000", "0.000000", "|~",
            "P", str(aux_pt_start + 6), "0.000000", "0.000000", "|~",
            "P", str(aux_pt_start + 7), "0.000000", "0.000000", "|~",
            "#~62",
            "PMA", str(aux_bspl_start + 3), "0", "1", "0", "0", "3",
            "52", "343", "61", "1", str(aux_pt_start + 5), "|~",
            "#~71", "#~72"
        ])

        # stich_part group
        lines.extend([
            "#~6", "stich_part", "#~61",
            "P", str(aux_pt_start + 8), "0.000000", "0.000000", "|~",
            "#~62",
            "PMA", str(aux_bspl_start + 4), "0", "1", "0", "0", "3",
            "52", "343", "61", "1", str(aux_pt_start + 8), "|~",
            "#~71", "#~72"
        ])

        # Ending sections (required by industrial software)
        for _ in range(100):
            lines.append("#~")

        lines.extend([
            "#B", "27", "1010", "1067", "0",
            "0.000", "0.000", "0.000", "0.000", "#~"
        ])

        lines.extend([
            "#C", "pixmap.counter=0", "#~"
        ])

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
            "", "#~", "#~ISP"
        ])

        return '\n'.join(lines) + '\n'

    def _generate_bspl(self, idx: int, pt_ids: List[int]) -> List[str]:
        """Generate BSPL definition"""
        n_pts = len(pt_ids)
        degree = 4

        # Calculate chord lengths
        chord_lengths = [0.0]
        for j in range(1, n_pts):
            pt1 = self.points[pt_ids[j-1] - 2750]
            pt2 = self.points[pt_ids[j] - 2750]
            dx = pt2[0] - pt1[0]
            dy = pt2[1] - pt1[1]
            dist = math.sqrt(dx*dx + dy*dy)
            chord_lengths.append(chord_lengths[-1] + dist)

        total_length = chord_lengths[-1] if chord_lengths[-1] > 0 else 1.0

        # Generate knot vector
        knots = []
        for j in range(degree):
            knots.append(0.0)
        for j in range(1, n_pts - degree + 1):
            avg = sum(chord_lengths[j:j+degree]) / degree
            knots.append(avg)
        for j in range(degree):
            knots.append(total_length)

        lines = [
            "BSPL", str(11755 + idx), "751514381",
            "2", "0", "0", "4", "56", "345", "80", "624",
            str(degree), "0", "0.000000", f"{total_length:.6f}",
            str(pt_ids[0]), str(pt_ids[-1]), str(n_pts),
        ]

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


def polylines_to_me(polylines: List[List[Tuple[int, int]]],
                    output_path: str,
                    scale: float = 0.1):
    """
    Convert polylines to ME format with correct validation

    Args:
        polylines: List of polylines, each is [(x, y), ...]
        output_path: Output file path
        scale: Scale factor (pixels → mm), default 0.1
    """
    exporter = MEExporterFixed()

    # Find Y range for flipping
    all_y = [y for pl in polylines for x, y in pl]
    max_y = max(all_y) if all_y else 0

    for polyline in polylines:
        # Convert: pixels → mm, Y-axis flip
        coords = [(x * scale, (max_y - y) * scale) for x, y in polyline]
        exporter.add_polyline(coords)

    exporter.export(output_path)

