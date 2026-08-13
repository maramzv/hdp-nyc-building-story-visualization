"""Step 3: Data discovery — aggregate queries only, no full-dataset download.

Answers: how many unique buildings, what date range, class/status/borough
breakdowns, missing-value rates for key fields, and a sanity check on
records-per-building distribution.

Run: python scripts/data_discovery.py
Prints progress as it goes (some aggregates are slow on this dataset) and
saves raw JSON results to data/data_discovery_raw.json (git-ignored).
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
        rows = soql_query(timeout=240, **kwargs)
    except Exception as exc:  # noqa: BLE001 - keep discovery going even if one query fails
        elapsed = time.time() - start
        print(f"FAILED after {elapsed:.1f}s: {exc}\n", flush=True)
        results[label] = {"error": str(exc)}
        return []
    elapsed = time.time() - start
    print(f"({elapsed:.1f}s, {len(rows)} rows)", flush=True)
    for r in rows[:15]:
        print(" ", r)
    if len(rows) > 15:
        print(f"  ... ({len(rows) - 15} more rows)")
    print()
    results[label] = rows
    return rows


def main():
    run("distinct_building_count", select="count(distinct buildingid) as n")
    run("distinct_registration_count", select="count(distinct registrationid) as n")

    run("date_range_inspection", select="min(inspectiondate) as earliest, max(inspectiondate) as latest")
    run("date_range_novissued", select="min(novissueddate) as earliest, max(novissueddate) as latest")

    run("by_class", select="class, count(*) as n", group="class", order="n DESC")
    run("by_status", select="currentstatus, count(*) as n", group="currentstatus", order="n DESC")
    run("by_borough", select="boro, count(*) as n", group="boro", order="n DESC")

    # Missing-value rates for a few fields that matter for the analysis
    for field in ["buildingid", "registrationid", "class", "currentstatus",
                  "inspectiondate", "certifieddate", "novdescription", "apartment"]:
        run(f"missing_{field}", select="count(*) as n", where=f"{field} IS NULL")

    # Records-per-building sanity check: top 15 buildings by violation count
    run("top_buildings_by_violations",
        select="buildingid, boro, housenumber, streetname, count(*) as n",
        group="buildingid, boro, housenumber, streetname",
        order="n DESC", limit=15)

    out_path = Path(__file__).resolve().parent.parent / "data" / "data_discovery_raw.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Saved raw results to {out_path}")


if __name__ == "__main__":
    main()
