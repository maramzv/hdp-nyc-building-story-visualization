"""Phase 4, step 1: build the dataset that feeds the 3D map visualization.

1. Randomly sample ~3,000 buildings from the full citywide list (uniform
   random over all 167,857 buildings, not weighted toward high-violation
   ones - gives a geographically representative sample, not just the
   troubled outliers we've been testing against).
2. Pull their violation records (batched - too many buildingids for one
   query) and compute each one's six-dimension story profile.
3. Join each building to PLUTO (NYC's tax-lot dataset) for lat/lon and
   real floor count via borough+block+lot (batched, verified ~97.5% match
   rate in Phase 3 testing).
4. Export one JSON file: one row per successfully-profiled, successfully-
   located building, ready for the deck.gl/MapLibre frontend to read directly.

Run: python scripts/build_map_dataset.py
"""
import json
import random
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from socrata_client import soql_query  # noqa: E402
from building_story import build_profile, generate_narrative  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TODAY = datetime(2026, 8, 14)
SAMPLE_SIZE = 3000
BATCH_SIZE = 250
PLUTO_DATASET_ID = "64uk-42ks"
BORO_MAP = {"MANHATTAN": "MN", "BRONX": "BX", "BROOKLYN": "BK", "QUEENS": "QN", "STATEN ISLAND": "SI"}


def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def main():
    random.seed(42)  # reproducible sample

    cache_path = DATA_DIR / "map_dataset_violations_raw.json"
    if cache_path.exists():
        all_rows = json.load(open(cache_path))
        print(f"Loaded {len(all_rows)} violation rows from cache (skipping re-pull)")
    else:
        cal = json.load(open(DATA_DIR / "threshold_calibration_raw.json"))
        all_ids = [r["buildingid"] for r in cal["violations_per_building"]]
        sample_ids = random.sample(all_ids, SAMPLE_SIZE)
        print(f"Sampled {len(sample_ids)} buildings from {len(all_ids)} citywide")

        all_rows = []
        for i, batch in enumerate(chunked(sample_ids, BATCH_SIZE)):
            where = "buildingid IN(" + ",".join(f"'{b}'" for b in batch) + ")"
            start = time.time()
            rows = soql_query(select="*", where=where, limit=20000, timeout=180)
            print(f"  batch {i+1}: {time.time()-start:.1f}s, {len(rows)} rows"
                  f"{' WARNING near limit' if len(rows) > 19000 else ''}")
            all_rows.extend(rows)
        json.dump(all_rows, open(cache_path, "w"))
    print(f"Total violation rows: {len(all_rows)}")

    by_building = defaultdict(list)
    for r in all_rows:
        by_building[r["buildingid"]].append(r)
    print(f"Buildings with at least one violation record: {len(by_building)}")

    # --- Step 2: compute story profiles ---
    profiles = {}
    for bid, viols in by_building.items():
        p = build_profile(bid, viols, TODAY)
        profiles[bid] = p
    print(f"Profiles computed: {len(profiles)}")

    # --- Step 3: PLUTO join for coordinates + floors, batched ---
    building_loc = {}  # buildingid -> (boro, block, lot)
    for bid, viols in by_building.items():
        v = viols[0]
        boro = BORO_MAP.get(v.get("boro"))
        block, lot = v.get("block"), v.get("lot")
        if boro and block and lot and block != "0" and lot != "0":
            building_loc[bid] = (boro, block, lot)

    loc_items = list(building_loc.items())
    pluto_matches = {}  # (boro, block, lot) -> pluto row
    for i, batch in enumerate(chunked(loc_items, 200)):
        clauses = " OR ".join(f"(borough='{boro}' AND block={block} AND lot={lot})"
                               for _, (boro, block, lot) in batch)
        start = time.time()
        rows = soql_query(select="borough,block,lot,latitude,longitude,numfloors,bldgarea",
                           where=clauses, limit=500, timeout=120, dataset_id=PLUTO_DATASET_ID)
        print(f"  pluto batch {i+1}: {time.time()-start:.1f}s, {len(rows)} rows")
        for r in rows:
            key = (r["borough"], str(r["block"]), str(r["lot"]))
            if key not in pluto_matches:
                pluto_matches[key] = r

    matched = 0
    for bid, (boro, block, lot) in building_loc.items():
        key = (boro, str(block), str(lot))
        if key in pluto_matches:
            matched += 1
    print(f"PLUTO matches: {matched}/{len(building_loc)}")

    # --- Step 4: assemble final dataset ---
    output = []
    for bid, p in profiles.items():
        loc = building_loc.get(bid)
        if not loc:
            continue
        pluto = pluto_matches.get((loc[0], str(loc[1]), str(loc[2])))
        if not pluto or not pluto.get("latitude") or not pluto.get("longitude"):
            continue
        try:
            lat, lon = float(pluto["latitude"]), float(pluto["longitude"])
            floors = float(pluto.get("numfloors") or 0) or 3.0  # default 3 if missing/zero
        except (ValueError, TypeError):
            continue

        output.append({
            "buildingid": bid,
            "address": p.address,
            "boro": by_building[bid][0].get("boro", ""),
            "lat": lat,
            "lon": lon,
            "floors": floors,
            "active_count": p.active_count,
            "scale": p.scale,
            "recency": p.recency,
            "severity": p.severity,
            "engagement": p.engagement,
            "pattern": p.pattern,
            "backlog_age": p.backlog_age,
            "narrative": generate_narrative(p),
        })

    out_path = DATA_DIR / "map_dataset.json"
    json.dump(output, open(out_path, "w"))
    print(f"\nFinal dataset: {len(output)} buildings ready for the map")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
