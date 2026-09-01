"""One-off: rewrite the lat/lon in an already-built map_dataset.json from
data/building_geocodes.json (scripts/geocode_buildings.py output), so we
don't have to re-run the whole ~70-min build_map_dataset.py just to swap
the coordinate source.

build_map_dataset.py already prefers geocodes on every future run - this is
only for applying them to the current dataset in place. After running this,
re-run scripts/add_neighborhoods.py (the neighborhood match keys off lat/lon).

Run: python scripts/apply_geocodes.py
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def main():
    ds_path = DATA_DIR / "map_dataset.json"
    dataset = json.load(open(ds_path, encoding="utf-8"))
    geocodes = json.load(open(DATA_DIR / "building_geocodes.json", encoding="utf-8"))

    backup = ds_path.with_suffix(".json.pre-geocode")
    if not backup.exists():
        json.dump(dataset, open(backup, "w"))
        print(f"Backed up current dataset to {backup.name}")

    moved = 0
    total_shift_m = 0.0
    for b in dataset:
        g = geocodes.get(b["buildingid"])
        if not g:
            continue
        new_lon, new_lat = float(g[0]), float(g[1])
        # rough metres moved (1 deg lat ~ 111km, lon scaled by cos(lat))
        import math
        dlat = (new_lat - b["lat"]) * 111000
        dlon = (new_lon - b["lon"]) * 111000 * math.cos(math.radians(b["lat"]))
        shift = math.hypot(dlat, dlon)
        if shift > 1:
            moved += 1
            total_shift_m += shift
        b["lat"], b["lon"] = new_lat, new_lon

    json.dump(dataset, open(ds_path, "w"))
    print(f"Applied {len(geocodes)} geocoded points to {len(dataset)} buildings.")
    print(f"{moved} moved more than 1 m (avg move {total_shift_m/max(moved,1):.0f} m).")
    print("Now re-run: python scripts/add_neighborhoods.py")


if __name__ == "__main__":
    main()
