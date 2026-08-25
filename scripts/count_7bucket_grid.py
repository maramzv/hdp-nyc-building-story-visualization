"""Exact counts for the 7 valid cells of the volume x recurrence grid
(Low/Moderate/High real-defect-count crossed with None/Persistent/Chronic
recurrence; Low+Persistent and Low+Chronic are structurally impossible).

Run: python scripts/count_7bucket_grid.py
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
    if p.real_defect_count == 0:
        label = "No real defects"
    else:
        if p.real_defect_count == 1:
            vol = "Low"
        elif p.real_defect_count <= 9:
            vol = "Moderate"
        else:
            vol = "High"

        if p.pattern == "Chronic":
            rec = "Chronic"
        elif p.pattern == "Persistent":
            rec = "Persistent"
        else:
            rec = "None"

        label = f"{vol}+{rec}"
    buckets[label] += 1
    n_done += 1
    if n_done % 50000 == 0:
        print(f"  profiled {n_done}/{len(by_building)}...")

print("\nFinal counts (7-bucket grid + No real defects):")
order = ["No real defects", "Low+None", "Moderate+None", "Moderate+Persistent",
         "Moderate+Chronic", "High+None", "High+Persistent", "High+Chronic"]
for label in order:
    print(f"  {label}: {buckets[label]}")
print(f"  TOTAL: {sum(buckets.values())}")
print("\nAny unexpected labels (should be none):")
for label, n in buckets.items():
    if label not in order:
        print(f"  UNEXPECTED {label}: {n}")
