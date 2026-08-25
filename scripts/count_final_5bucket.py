"""Exact counts for the final 5-bucket taxonomy: No real defects, Isolated
(<=7 real defects, none recurring - reusing _level_scale's own Low/Minimal
boundary), Widespread (8+ real defects, none recurring), Persistent, Chronic.

Run: python scripts/count_final_5bucket.py
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
WIDESPREAD_THRESHOLD = 8  # first value outside _level_scale's "Low" tier (<=7)

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
    elif p.real_defect_count < WIDESPREAD_THRESHOLD:
        label = "Isolated"
    else:
        label = "Widespread"
    buckets[label] += 1
    n_done += 1
    if n_done % 50000 == 0:
        print(f"  profiled {n_done}/{len(by_building)}...")

print("\nFinal counts (5-bucket, Widespread cut at 8+):")
for label in ["No real defects", "Isolated", "Widespread", "Persistent", "Chronic"]:
    print(f"  {label}: {buckets[label]}")
print(f"  TOTAL: {sum(buckets.values())}")
