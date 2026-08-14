"""Phase 3 prep: get real distributions to calibrate story-taxonomy thresholds.

Answers, with actual numbers instead of guesses:
- Percentile distribution of violations per building (p50/p75/p90/p95/p99/max)
- Overdue count using the correct deadline field (OriginalCorrectByDate,
  falling back only where NewCorrectByDate applies) - not the rare New* field alone
- Top 50 recurring building+apartment+problem-category signatures, with count
  and date span, to calibrate "persistent" vs "chronic" thresholds pragmatically
  (a full distribution of all recurring groups isn't practical via aggregate
  SoQL, so this top-N sample anchors the high end of the range instead)

Run: python scripts/calibrate_thresholds.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from socrata_client import soql_query  # noqa: E402

results = {}


def run(label, **kwargs):
    print(f"--- {label} ---", flush=True)
    start = time.time()
    try:
        rows = soql_query(timeout=300, **kwargs)
    except Exception as exc:  # noqa: BLE001
        elapsed = time.time() - start
        print(f"FAILED after {elapsed:.1f}s: {exc}\n", flush=True)
        results[label] = {"error": str(exc)}
        return []
    elapsed = time.time() - start
    print(f"({elapsed:.1f}s, {len(rows)} rows)", flush=True)
    results[label] = rows
    return rows


def percentile(sorted_vals, pct):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def main():
    # 1. Full per-building violation counts -> percentiles
    rows = run(
        "violations_per_building",
        select="buildingid, count(*) as n",
        group="buildingid",
        order="n DESC",
        limit=200000,
    )
    counts = sorted(int(r["n"]) for r in rows)
    if counts:
        print("Violations-per-building distribution:")
        for p in [50, 75, 90, 95, 99]:
            print(f"  p{p}: {percentile(counts, p):.1f}")
        print(f"  max: {counts[-1]}")
        print(f"  n buildings: {len(counts)}")
    print()

    # 2. Overdue counts using the CORRECT deadline field
    run("overdue_via_original_deadline",
        select="count(*) as n",
        where="newcorrectbydate IS NULL AND originalcorrectbydate < '2026-08-13T00:00:00'")
    run("overdue_via_new_deadline",
        select="count(*) as n",
        where="newcorrectbydate IS NOT NULL AND newcorrectbydate < '2026-08-13T00:00:00'")

    # 3. Top recurring building+apartment+problem-category signatures
    run("top_recurring_signatures",
        select="buildingid, apartment, ordernumber, count(*) as n, "
               "min(novissueddate) as first_date, max(novissueddate) as last_date",
        group="buildingid, apartment, ordernumber",
        order="n DESC",
        limit=50)

    out_path = Path(__file__).resolve().parent.parent / "data" / "threshold_calibration_raw.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nSaved raw results to {out_path}")


if __name__ == "__main__":
    main()
