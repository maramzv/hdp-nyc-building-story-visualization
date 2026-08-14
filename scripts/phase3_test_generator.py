"""Phase 3, step 3: run the actual story generator against a wider sample
and read the outputs for quality/threshold validation.

Run: python scripts/phase3_test_generator.py
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from socrata_client import soql_query  # noqa: E402
from building_story import build_profile, generate_narrative  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TODAY = datetime(2026, 8, 14)


def wider_percentile_buildings():
    cal = json.load(open(DATA_DIR / "threshold_calibration_raw.json"))
    rows = sorted(cal["violations_per_building"], key=lambda x: int(x["n"]))
    n = len(rows)
    pcts = list(range(1, 100, 2))  # every 2nd percentile, 1..99
    return [rows[int((n - 1) * (p / 100))]["buildingid"] for p in pcts]


def main():
    existing = json.load(open(DATA_DIR / "phase3_wide_sample_raw.ids.json"))
    building_ids = sorted(set(existing) | set(wider_percentile_buildings()))
    print(f"Total unique buildings: {len(building_ids)}")

    cache_path = DATA_DIR / "phase3_wider_sample_raw.json"
    if cache_path.exists():
        rows = json.load(open(cache_path))
        print(f"Loaded {len(rows)} rows from cache ({cache_path})")
    else:
        where = "buildingid IN(" + ",".join(f"'{b}'" for b in building_ids) + ")"
        import time
        start = time.time()
        rows = soql_query(select="*", where=where, limit=40000, timeout=280)
        print(f"Pulled: {time.time()-start:.1f}s, {len(rows)} rows "
              f"({'COMPLETE' if len(rows) < 40000 else 'WARNING: may be truncated'})")
        json.dump(rows, open(cache_path, "w"))

    by_building = defaultdict(list)
    for r in rows:
        by_building[r["buildingid"]].append(r)

    profiles = []
    for bid, viols in by_building.items():
        p = build_profile(bid, viols, TODAY)
        narrative = generate_narrative(p)
        profiles.append((p, narrative))

    profiles.sort(key=lambda x: x[0].active_count)

    for p, narrative in profiles:
        print(f"\n{'='*70}")
        print(f"[{p.scale}/{p.recency}/{p.severity}/{p.engagement}/{p.pattern}/{p.backlog_age}]")
        print(f"BuildingID {p.buildingid} — {p.address} ({p.active_count} active)")
        print(f"  {narrative}")

    # Level distribution — sanity check on how balanced the dimensions are
    print(f"\n\n{'='*70}\nLEVEL DISTRIBUTIONS (n={len(profiles)})")
    for dim in ["scale", "recency", "severity", "engagement", "pattern", "backlog_age"]:
        counts = defaultdict(int)
        for p, _ in profiles:
            counts[getattr(p, dim)] += 1
        print(f"  {dim}: {dict(counts)}")


if __name__ == "__main__":
    main()
