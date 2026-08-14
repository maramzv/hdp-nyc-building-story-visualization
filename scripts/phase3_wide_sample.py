"""Phase 3, data-first taxonomy derivation: step 1 - build a wide, varied sample.

Instead of testing a preset taxonomy, this builds a feature table across a
broad, varied set of real buildings so story categories can be derived
inductively from actual patterns rather than assumed up front.

Sample composition:
- ~20 buildings spread across the full violations-per-building percentile
  range (from cached data/threshold_calibration_raw.json, no API call)
- ~15 buildings from live extremity queries (highest FALSE CERTIFICATION
  count, highest recent Class C count, highest non-compliance count) to
  cover behavioral extremes that pure volume-percentile sampling would miss
- The 12 buildings from the first Phase 3 pass, for continuity

Run: python scripts/phase3_wide_sample.py
Writes data/phase3_wide_sample_raw.json (all violation rows for every
selected building) for the next script to analyze.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from socrata_client import soql_query  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def percentile_buildings():
    cal = json.load(open(DATA_DIR / "threshold_calibration_raw.json"))
    rows = sorted(cal["violations_per_building"], key=lambda x: int(x["n"]))
    n = len(rows)
    pcts = [1, 5, 10, 15, 20, 25, 30, 40, 50, 60, 65, 70, 75, 80, 85, 90, 93, 95, 97, 99]
    ids = []
    for p in pcts:
        idx = int((n - 1) * (p / 100))
        ids.append(rows[idx]["buildingid"])
    return ids


def extremity_buildings():
    print("Querying extremity samples (false certification, recent Class C, non-compliance)...", flush=True)
    ids = []

    start = time.time()
    rows = soql_query(
        select="buildingid, count(*) as n",
        where="currentstatus='FALSE CERTIFICATION'",
        group="buildingid", order="n DESC", limit=6, timeout=180)
    print(f"  false_certification top: {time.time()-start:.1f}s, {rows}")
    ids += [r["buildingid"] for r in rows]

    start = time.time()
    rows = soql_query(
        select="buildingid, count(*) as n",
        where="class='C' AND novissueddate > '2025-08-14T00:00:00'",
        group="buildingid", order="n DESC", limit=6, timeout=180)
    print(f"  recent_class_c top: {time.time()-start:.1f}s, {rows}")
    ids += [r["buildingid"] for r in rows]

    start = time.time()
    rows = soql_query(
        select="buildingid, count(*) as n",
        where="currentstatus='NOT COMPLIED WITH'",
        group="buildingid", order="n DESC", limit=6, timeout=180)
    print(f"  not_complied top: {time.time()-start:.1f}s, {rows}")
    ids += [r["buildingid"] for r in rows]

    return ids


def main():
    existing_12 = ['808705', '288857', '65175', '4172', '878031', '694446',
                    '380289', '384515', '934498', '804699', '222118', '155406']

    building_ids = set(existing_12) | set(percentile_buildings()) | set(extremity_buildings())
    building_ids = sorted(building_ids)
    print(f"\nTotal unique buildings in wide sample: {len(building_ids)}")

    where = "buildingid IN(" + ",".join(f"'{b}'" for b in building_ids) + ")"
    start = time.time()
    rows = soql_query(select="*", where=where, limit=20000, timeout=280)
    print(f"Pulled all violations: {time.time()-start:.1f}s, {len(rows)} rows "
          f"({'COMPLETE - under limit' if len(rows) < 20000 else 'WARNING: hit limit, may be truncated'})")

    out_path = DATA_DIR / "phase3_wide_sample_raw.json"
    json.dump(rows, open(out_path, "w"))
    print(f"Saved to {out_path}")

    with open(out_path.with_suffix(".ids.json"), "w") as f:
        json.dump(building_ids, f)


if __name__ == "__main__":
    main()
