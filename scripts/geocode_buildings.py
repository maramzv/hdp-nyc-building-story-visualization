"""Geocode every building in map_dataset.json to a real per-address point,
via NYC GeoSearch (https://geosearch.planninglabs.nyc — free, keyless,
Pelias-based, backed by the city's own address data).

Why: the PLUTO join gives one coordinate per *tax lot* (the lot centroid),
so every building on a lot stacks on the same point, and the map's
client-side de-collision spreads them into an artificial grid (very visible
at superblocks like Co-op City / NYCHA campuses). Geocoding the street
address instead puts each building where it actually is - and distinct
addresses on one lot (650 vs 690 Gates Ave) get distinct points.

Output: data/building_geocodes.json  {buildingid: [lon, lat, "match label"]}
Checkpointed to a .jsonl so a killed run resumes. Threaded (GeoSearch
tolerates modest concurrency). PLUTO is still used for floor count and
footprint area, which GeoSearch doesn't provide.

Run: python scripts/geocode_buildings.py
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GEOSEARCH = "https://geosearch.planninglabs.nyc/v2/search"
# GeoSearch stalled once at 12 workers; tested clean and steady at 5-6
# (~20/s, 0 errors over 1200 requests). ~2-2.5 hr for the full population,
# checkpointed so it resumes if killed.
WORKERS = 6
PER_REQ_PAUSE = 0.0


def geocode_one(session, buildingid, address):
    """address is 'HOUSENUMBER STREETNAME, BORO' as stored in map_dataset.json."""
    text = address.strip()
    if not text.endswith(", NY"):
        text = text + ", NY"
    for attempt in range(5):
        try:
            r = session.get(GEOSEARCH, params={"text": text, "size": 1}, timeout=20)
            if r.status_code == 429:
                time.sleep(6 * (attempt + 1))
                continue
            r.raise_for_status()
            feats = r.json().get("features") or []
            time.sleep(PER_REQ_PAUSE)
            if not feats:
                return buildingid, None
            f = feats[0]
            lon, lat = f["geometry"]["coordinates"]
            return buildingid, [round(lon, 6), round(lat, 6), f["properties"].get("label", "")]
        except Exception:
            if attempt == 4:
                return buildingid, None
            time.sleep(2.0 * (attempt + 1))


def main():
    dataset = json.load(open(DATA_DIR / "map_dataset.json", encoding="utf-8"))
    print(f"{len(dataset)} buildings to geocode")

    out_path = DATA_DIR / "building_geocodes.json"
    partial = DATA_DIR / "building_geocodes.partial.jsonl"

    done = {}
    if partial.exists():
        for line in open(partial, encoding="utf-8"):
            rec = json.loads(line)
            done[rec["b"]] = rec["g"]
        print(f"Resuming: {len(done)} already geocoded")

    todo = [(b["buildingid"], b["address"]) for b in dataset if b["buildingid"] not in done]
    print(f"{len(todo)} remaining")

    hits = sum(1 for v in done.values() if v)
    misses = len(done) - hits
    start = time.time()

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=WORKERS, pool_maxsize=WORKERS)
    session.mount("https://", adapter)

    with session, open(partial, "a", encoding="utf-8") as pf, \
            ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(geocode_one, session, bid, addr): bid for bid, addr in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            bid, g = fut.result()
            done[bid] = g
            hits += 1 if g else 0
            misses += 0 if g else 1
            pf.write(json.dumps({"b": bid, "g": g}) + "\n")
            if i % 200 == 0:
                pf.flush()
            if i % 1000 == 0 or i == len(todo):
                rate = i / (time.time() - start)
                eta = (len(todo) - i) / rate / 60
                pf.flush()
                print(f"  {i}/{len(todo)}  ({hits} matched, {misses} no-match)  "
                      f"{rate:.0f}/s  eta {eta:.0f} min", flush=True)

    result = {b: g for b, g in done.items() if g}
    json.dump(result, open(out_path, "w"))
    print(f"\nGeocoded {len(result)}/{len(dataset)} buildings "
          f"({len(dataset) - len(result)} had no GeoSearch match, will fall back to PLUTO)")
    print(f"Saved to {out_path.name}")
    partial.unlink()


if __name__ == "__main__":
    main()
