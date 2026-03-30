import gzip

# Read file
with gzip.open('dev_me_files/114381-1.me', 'rt', encoding='utf-8') as f:
    lines = f.readlines()

# Find dessin #~62 section and remove last BSPL
output = []
i = 0
in_dessin_62 = False
bspl_count = 0
skip_bspl = False

while i < len(lines):
    line = lines[i].rstrip('\n')

    # Update #~2 section counts
    if line == 'TC5:18659':
        output.append('TC5:18658\n')
        i += 1
        continue

    if line == 'TC72:105028':
        output.append('TC72:105027\n')
        i += 1
        continue

    if line.startswith('PLAST:105030'):
        output.append('PLAST:105029\n')
        i += 1
        continue

    # Track dessin #~62 section
    if line == '#~62' and i > 10 and i < 100000:
        in_dessin_62 = True
        bspl_count = 0

    if in_dessin_62 and line == '#~71':
        in_dessin_62 = False

    # Count BSPL in dessin section
    if in_dessin_62 and line == 'BSPL':
        bspl_count += 1
        # Skip the last BSPL (18658th)
        if bspl_count == 18658:
            skip_bspl = True
            # Skip until |~
            while i < len(lines) and lines[i].strip() != '|~':
                i += 1
            i += 1  # Skip |~
            continue

    output.append(line + '\n')
    i += 1

# Write output
with gzip.open('dev_me_files/114381-1_rmv1.me', 'wt', encoding='utf-8') as f:
    f.writelines(output)

print(f"Removed 1 BSPL curve")
print(f"Saved: dev_me_files/114381-1_rmv1.me")
print(f"Lines: {len(output)}")
