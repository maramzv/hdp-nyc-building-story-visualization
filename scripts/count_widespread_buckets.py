"""Get exact building counts for the proposed 5-bucket pattern taxonomy
(splitting Isolated into Isolated vs Widespread at real_defect_count >= 10),
by streaming the full raw violation pull and running build_profile() on
every building - same source data and logic as build_map_dataset.py.

Run: python scripts/count_widespread_buckets.py
"""
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import ijson

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from building_story import build_profile, ADMINISTRATIVE_ORDERNUMBERS  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_PATH = DATA_DIR / "map_dataset_violations_raw.json"
TODAY = datetime(2026, 8, 14)
WIDESPREAD_THRESHOLD = 10

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
    if p.pattern == "Isolated":
        label = "Widespread" if p.real_defect_count >= WIDESPREAD_THRESHOLD else "Isolated"
    else:
        label = p.pattern
    buckets[label] += 1
    n_done += 1
    if n_done % 50000 == 0:
        print(f"  profiled {n_done}/{len(by_building)}...")

print("\nFinal 5-bucket counts:")
for label in ["No real defects", "Isolated", "Widespread", "Persistent", "Chronic"]:
    print(f"  {label}: {buckets[label]}")
print(f"  TOTAL: {sum(buckets.values())}")
