"""
Generate 892.me from template with minimal changes
"""
import gzip
import math

# Simple test pattern: a small square
test_polylines = [
    [(100, 100), (200, 100), (200, 200), (100, 200), (100, 100)],
]

# Read template
template_path = '/Users/clrrrr/Library/Mobile Documents/com~apple~CloudDocs/Personal/Notes/work_notes/Projects/suzhou_embroidery/me_files/114339.me'
with gzip.open(template_path, 'rt', encoding='utf-8') as f:
    lines = f.readlines()

# Prepare new geometry
scale = 0.1
all_y = [y for pl in test_polylines for x, y in pl]
max_y = max(all_y) if all_y else 0

all_points = []
bsplines = []

for polyline in test_polylines:
    pt_ids = []
    for x, y in polyline:
        mx = x * scale
        my = (max_y - y) * scale
        all_points.append((mx, my))
        pt_ids.append(2750 + len(all_points) - 1)
    bsplines.append(pt_ids)

# Calculate bounds
xs = [p[0] for p in all_points]
ys = [p[1] for p in all_points]
min_x, max_x = min(xs), max(xs)
min_y, max_y = min(ys), max(ys)

n_points = len(all_points)
n_bsplines = len(bsplines)
last_pt_id = 2750 + n_points - 1
last_bspl_id = 11755 + n_bsplines - 1

print(f"Points: {n_points}, BSPL: {n_bsplines}")
print(f"Bounds: x=[{min_x}, {max_x}], y=[{min_y}, {max_y}]")

# Find section boundaries in template
output = []
i = 0
in_dessin = False
skip_mode = None

while i < len(lines):
    line = lines[i].rstrip('\n')

    # Detect dessin section start
    if i > 0 and lines[i-1].strip() == '#~6' and line == 'dessin':
        in_dessin = True
        output.append(line + '\n')
        i += 1
        continue

    # Detect dessin section end
    if in_dessin and line == '#~6':
        in_dessin = False

    # Replace #~2 section
    if line == '#~2' and not skip_mode:
        output.append('#~2\n')
        output.append('2\n')
        output.append('TC41:1\n')
        output.append(f'TC5:{n_bsplines + 1}\n')
        output.append('dessin\n')
        output.append('4\n')
        output.append('TC61:2750\n')
        output.append('TC62:11755\n')
        output.append(f'TC72:{last_bspl_id + 1}\n')
        output.append(f'PLAST:{last_bspl_id + 1}\n')
        skip_mode = '#~3'
        i += 1
        continue

    # Replace #~3 section
    if line == '#~3' and skip_mode == '#~3':
        from datetime import datetime
        now = datetime.now()
        output.append('#~3\n')
        output.append('isp_dbmv.me\n')
        for _ in range(6):
            output.append('\n')
        output.append(now.strftime('%d-%b-%Y') + '\n')
        output.append(now.strftime('%H:%M:%S') + '\n')
        output.append('\n')
        output.append('HP ME10 Rev. 08.70G 30-Jun-1999\n')
        output.append('2.50\n')
        output.append('2D\n')
        output.append(f'{min_x:.6f}\n')
        output.append(f'{max_x:.6f}\n')
        output.append(f'{min_y:.6f}\n')
        output.append(f'{max_y:.6f}\n')
        skip_mode = '#~31'
        i += 1
        continue

    # End skip mode when reaching target section
    if skip_mode and line == skip_mode:
        skip_mode = None

    # Skip lines in skip mode
    if skip_mode:
        i += 1
        continue

    # Replace dessin #~61 (points)
    if line == '#~61' and in_dessin:
        output.append('#~61\n')
        for idx, (x, y) in enumerate(all_points):
            output.append('P\n')
            output.append(f'{2750 + idx}\n')
            output.append(f'{x:.6f}\n')
            output.append(f'{y:.6f}\n')
            output.append('|~\n')
        skip_mode = '#~62'
        i += 1
        continue

    # Replace dessin #~62 (BSPL)
    if line == '#~62' and in_dessin and skip_mode == '#~62':
        output.append('#~62\n')
        for bspl_idx, pt_ids in enumerate(bsplines):
            n_pts = len(pt_ids)
            degree = 4

            # Calculate chord lengths
            chord_lengths = [0.0]
            for j in range(1, n_pts):
                pt1 = all_points[pt_ids[j-1] - 2750]
                pt2 = all_points[pt_ids[j] - 2750]
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

            # Write BSPL
            output.append('BSPL\n')
            output.append(f'{11755 + bspl_idx}\n')
            output.append('751514381\n')
            output.append('2\n0\n0\n4\n56\n345\n80\n624\n')
            output.append(f'{degree}\n')
            output.append('0\n')
            output.append('0.000000\n')
            output.append(f'{total_length:.6f}\n')
            output.append(f'{pt_ids[0]}\n')
            output.append(f'{pt_ids[-1]}\n')
            output.append(f'{n_pts}\n')

            for pt_id in pt_ids:
                output.append(f'{pt_id}\n')

            output.append(f'{len(knots)}\n')
            for k in knots:
                output.append(f'{k:.6f}\n')

            output.append(f'{n_pts}\n')
            for pt_id in pt_ids:
                output.append(f'{pt_id}\n')
                for _ in range(6):
                    output.append('0\n')

            output.append('|~\n')

        skip_mode = '#~71'
        i += 1
        continue

    # Copy all other lines unchanged
    output.append(line + '\n')
    i += 1

# Write output
output_path = '/Users/clrrrr/Library/Mobile Documents/com~apple~CloudDocs/Personal/Notes/work_notes/Projects/suzhou_embroidery/dev_me_files/892.me'
with gzip.open(output_path, 'wt', encoding='utf-8') as f:
    f.writelines(output)

print(f"Generated: {output_path}")
print(f"Total lines: {len(output)}")

