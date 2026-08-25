"""Build the full-picture breakdown of the Isolated/Widespread candidate pool
(buildings with >=1 real defect, no Persistent/Chronic recurring pattern —
i.e. explicitly excludes "No real defects" paperwork-only buildings and
excludes any building with a recurring signature) for visual inspection:

  - how many buildings sit at each real_defect_count
  - within each count bucket, what severity (class_c_rate) looks like
  - within each count bucket, what age/recency (recency_ratio) looks like

Run: python scripts/visualize_isolated_widespread.py
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import ijson

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from building_story import build_profile, _level_severity, _level_recency  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_PATH = DATA_DIR / "map_dataset_violations_raw.json"
TODAY = datetime(2026, 8, 14)

BUCKETS = [
    (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 8), (9, 9),
    (10, 11), (12, 13), (14, 16), (17, 20), (21, 30), (31, 50), (51, 100), (101, 10_000),
]


def bucket_label(n):
    for lo, hi in BUCKETS:
        if lo <= n <= hi:
            return f"{lo}" if lo == hi else f"{lo}-{hi}"
    return "101+"


def main():
    print(f"Streaming {RAW_PATH} ...")
    by_building = defaultdict(list)
    n_rows = 0
    with open(RAW_PATH, "rb") as f:
        for row in ijson.items(f, "item"):
            by_building[row["buildingid"]].append(row)
            n_rows += 1
            if n_rows % 500000 == 0:
                print(f"  {n_rows} rows read...")
    print(f"Total rows: {n_rows}, buildings: {len(by_building)}")

    bucket_counts = defaultdict(int)
    bucket_severity = defaultdict(lambda: defaultdict(int))
    bucket_recency = defaultdict(lambda: defaultdict(int))
    n_done = 0
    n_candidates = 0

    for bid, violations in by_building.items():
        p = build_profile(bid, violations, TODAY)
        n_done += 1
        if n_done % 50000 == 0:
            print(f"  profiled {n_done}/{len(by_building)}...")
        if p.real_defect_count == 0:
            continue
        if p.pattern in ("Persistent", "Chronic"):
            continue
        n_candidates += 1

        label = bucket_label(p.real_defect_count)
        bucket_counts[label] += 1

        sev = _level_severity(p.class_c_rate)
        bucket_severity[label][sev] += 1

        rec = _level_recency(p.recency_ratio)
        bucket_recency[label][rec] += 1

    print(f"\nCandidate pool (Isolated/Widespread only, no admin-only, no Persistent/Chronic): {n_candidates}")

    ordered_labels = [bucket_label(lo) for lo, hi in BUCKETS]

    out = {
        "total_candidates": n_candidates,
        "bucket_order": ordered_labels,
        "counts": {lbl: bucket_counts.get(lbl, 0) for lbl in ordered_labels},
        "severity": {
            lbl: {
                "Low": bucket_severity[lbl].get("Low", 0),
                "Elevated": bucket_severity[lbl].get("Elevated", 0),
                "Severe": bucket_severity[lbl].get("Severe", 0),
                "Extreme": bucket_severity[lbl].get("Extreme", 0),
            }
            for lbl in ordered_labels
        },
        "recency": {
            lbl: {
                "Dormant": bucket_recency[lbl].get("Dormant", 0),
                "Mixed": bucket_recency[lbl].get("Mixed", 0),
                "Active surge": bucket_recency[lbl].get("Active surge", 0),
            }
            for lbl in ordered_labels
        },
    }

    out_path = DATA_DIR / "isolated_widespread_breakdown.json"
    json.dump(out, open(out_path, "w"), indent=2)
    print(f"Saved to {out_path}")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
