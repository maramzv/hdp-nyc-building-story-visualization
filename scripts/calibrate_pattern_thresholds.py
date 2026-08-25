"""Calibrate the Persistent/Chronic pattern thresholds against the REAL,
complete distribution of recurring-defect-signature counts, instead of the
top-50-only sample that originally anchored calibrate_thresholds.py.

The original 3+/2yr (Persistent) and 10+/5yr (Chronic) cutoffs in
building_story.py were a pragmatic gut call, not derived from a percentile
distribution the way _level_scale()'s buckets were. This script closes that
gap: it streams data/map_dataset_violations_raw.json (the full ~2.9M-row,
167k-building violation pull already on disk - no new API calls needed),
replicates build_profile()'s exact signature logic (building-wide grouping
by OrderNumber, administrative-code exclusion, novid dedup), and reports
the true p50/p75/p90/p95/p99 distribution of how many times a recurring
real defect signature repeats.

Run: python scripts/calibrate_pattern_thresholds.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import ijson

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from building_story import ADMINISTRATIVE_ORDERNUMBERS, _parse_date  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_PATH = DATA_DIR / "map_dataset_violations_raw.json"


def percentile(sorted_vals, pct):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def main():
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

    # Per-building-per-signature recurrence counts (only signatures that
    # recur at all, i.e. cited under >=2 distinct NOVIDs) - mirrors
    # build_profile()'s `signatures` dict and `recurring_sigs` list exactly.
    all_recurring = []  # (buildingid, ordernumber, n_notices, span_years)
    buildings_with_any_real_defect = 0
    buildings_with_recurrence = 0

    for bid, violations in by_building.items():
        seen = set()
        deduped = []
        for v in violations:
            key = (v.get("apartment"), v.get("novdescription"), v.get("novissueddate"))
            if key not in seen:
                seen.add(key)
                deduped.append(v)

        real_defect_count = sum(1 for v in deduped if v.get("ordernumber") not in ADMINISTRATIVE_ORDERNUMBERS)
        if real_defect_count == 0:
            continue
        buildings_with_any_real_defect += 1

        signatures = defaultdict(dict)  # ordernumber -> {novid: date}
        for v in deduped:
            ordernumber = v.get("ordernumber")
            novid = v.get("novid")
            nov_date = _parse_date(v.get("novissueddate"))
            if nov_date and novid and ordernumber not in ADMINISTRATIVE_ORDERNUMBERS:
                if novid not in signatures[ordernumber] or nov_date < signatures[ordernumber][novid]:
                    signatures[ordernumber][novid] = nov_date

        building_has_recurrence = False
        for ordernumber, novid_dates in signatures.items():
            dates = list(novid_dates.values())
            if len(dates) >= 2:
                span_years = (max(dates) - min(dates)).days / 365
                all_recurring.append((bid, ordernumber, len(dates), span_years))
                building_has_recurrence = True
        if building_has_recurrence:
            buildings_with_recurrence += 1

    print(f"\nBuildings with >=1 real (non-administrative) defect: {buildings_with_any_real_defect}")
    print(f"Buildings with >=1 recurring signature (any repeat count): {buildings_with_recurrence}")
    print(f"Total recurring signatures found: {len(all_recurring)}")

    counts = sorted(n for _, _, n, _ in all_recurring)
    spans = sorted(s for _, _, _, s in all_recurring)

    print("\nRecurrence-count distribution (per recurring signature, notices):")
    for p in [50, 75, 90, 95, 99]:
        print(f"  p{p}: {percentile(counts, p):.1f}")
    print(f"  max: {counts[-1]}")

    print("\nSpan distribution (years between first and last notice, per recurring signature):")
    for p in [50, 75, 90, 95, 99]:
        print(f"  p{p}: {percentile(spans, p):.2f}")
    print(f"  max: {spans[-1]:.1f}")

    # How the current 3+/2yr and 10+/5yr cutoffs actually partition the data
    n_isolated_recurrence = sum(1 for n, s in zip(counts, spans) if not (n >= 3 and s >= 2))
    n_persistent_only = sum(1 for _, _, n, s in all_recurring if n >= 3 and s >= 2 and not (n >= 10 and s >= 5))
    n_chronic = sum(1 for _, _, n, s in all_recurring if n >= 10 and s >= 5)
    print(f"\nOf {len(all_recurring)} recurring signatures, under CURRENT thresholds:")
    print(f"  below Persistent bar (still counts as Isolated at the building level): {n_isolated_recurrence}")
    print(f"  Persistent (3+/2yr, not Chronic): {n_persistent_only}")
    print(f"  Chronic (10+/5yr): {n_chronic}")

    # Distribution of notice counts specifically at the low end (2-15) to see
    # where a natural breakpoint actually sits
    print("\nCount histogram (2-15 notices):")
    from collections import Counter
    hist = Counter(counts)
    for n in range(2, 16):
        print(f"  {n} notices: {hist.get(n, 0)}")

    out = {
        "n_rows": n_rows,
        "n_buildings": len(by_building),
        "buildings_with_any_real_defect": buildings_with_any_real_defect,
        "buildings_with_recurrence": buildings_with_recurrence,
        "n_recurring_signatures": len(all_recurring),
        "count_percentiles": {str(p): percentile(counts, p) for p in [50, 75, 90, 95, 99]},
        "span_percentiles": {str(p): percentile(spans, p) for p in [50, 75, 90, 95, 99]},
        "count_histogram_2_15": {str(n): hist.get(n, 0) for n in range(2, 16)},
    }
    out_path = DATA_DIR / "pattern_threshold_calibration.json"
    json.dump(out, open(out_path, "w"), indent=2)
    print(f"\nSaved summary to {out_path}")


if __name__ == "__main__":
    main()
