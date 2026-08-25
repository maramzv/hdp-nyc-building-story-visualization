"""Exact counts for the new decision-tree taxonomy:
No real defects -> Isolated (exactly 1 real defect) -> Scattered (2+ real
defects, nothing has repeated 3+ times) -> Persistent -> Chronic.

Run: python scripts/count_new_tree_buckets.py
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

buckets = Counter()
n_done = 0
for bid, violations in by_building.items():
    p = build_profile(bid, violations, TODAY)
    if p.pattern == "Chronic":
        label = "Chronic"
    elif p.pattern == "Persistent":
        label = "Persistent"
    elif p.real_defect_count == 0:
        label = "No real defects"
    elif p.real_defect_count == 1:
        label = "Isolated"
    else:
        label = "Scattered"
    buckets[label] += 1
    n_done += 1
    if n_done % 50000 == 0:
        print(f"  profiled {n_done}/{len(by_building)}...")

print("\nFinal counts (new tree):")
for label in ["No real defects", "Isolated", "Scattered", "Persistent", "Chronic"]:
    print(f"  {label}: {buckets[label]}")
print(f"  TOTAL: {sum(buckets.values())}")
