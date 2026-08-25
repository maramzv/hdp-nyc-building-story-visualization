"""Calibrate the Isolated/Widespread volume cutoff against the REAL percentile
distribution of real_defect_count specifically (not active_count, which is
what _level_scale() was calibrated on and includes administrative filings).

Run: python scripts/calibrate_real_defect_count.py
"""
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import ijson

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from building_story import build_profile  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_PATH = DATA_DIR / "map_dataset_violations_raw.json"
TODAY = datetime(2026, 8, 14)


def percentile(sorted_vals, pct):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


print(f"Streaming {RAW_PATH} ...")
by_building = defaultdict(list)
n_rows = 0
with open(RAW_PATH, "rb") as f:
    for row in ijson.items(f, "item"):
        by_building[row["buildingid"]].append(row)
        n_rows += 1
        if n_rows % 500000 == 0:
            print(f"  {n_rows} rows read, {len(by_building)} buildings so far...")
print(f"Total rows: {n_rows}, buildings: {len(by_building)}")

counts_with_real_defects = []
counts_non_recurring_only = []  # real_defect_count among buildings with NO signature that hit the Persistent bar (the actual Isolated/Widespread candidate pool)
n_done = 0
for bid, violations in by_building.items():
    p = build_profile(bid, violations, TODAY)
    if p.real_defect_count > 0:
        counts_with_real_defects.append(p.real_defect_count)
        if p.pattern not in ("Persistent", "Chronic"):
            counts_non_recurring_only.append(p.real_defect_count)
    n_done += 1
    if n_done % 50000 == 0:
        print(f"  profiled {n_done}/{len(by_building)}...")

counts_with_real_defects.sort()
counts_non_recurring_only.sort()

print(f"\nBuildings with >=1 real defect: {len(counts_with_real_defects)}")
print("real_defect_count distribution (ALL buildings with a real defect):")
for p in [50, 75, 90, 95, 99]:
    print(f"  p{p}: {percentile(counts_with_real_defects, p):.1f}")
print(f"  max: {counts_with_real_defects[-1]}")

print(f"\nBuildings that are Isolated/Widespread CANDIDATES (no recurring pattern found): {len(counts_non_recurring_only)}")
print("real_defect_count distribution (within that candidate pool only):")
for p in [50, 75, 90, 95, 99]:
    print(f"  p{p}: {percentile(counts_non_recurring_only, p):.1f}")
print(f"  max: {counts_non_recurring_only[-1]}")

print("\nHistogram (1-20 real defects, candidate pool only):")
hist = Counter(counts_non_recurring_only)
for n in range(1, 21):
    print(f"  {n}: {hist.get(n, 0)}")
