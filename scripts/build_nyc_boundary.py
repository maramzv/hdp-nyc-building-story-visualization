"""Builds a lightweight outer-boundary GeoJSON for the map's "city limits" line.

Reuses the same NTA (Neighborhood Tabulation Area) boundaries already pulled
in add_neighborhoods.py (dataset 9nt8-h7nd) - unions all 262 polygons into
one outline instead of fetching a separate borough-boundary dataset, and
simplifies it so the line layer stays cheap to render.

Run: python scripts/build_nyc_boundary.py
Writes data/nyc_boundary.geojson.
"""
import json
import sys
import time
from pathlib import Path

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from socrata_client import soql_query  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NTA_DATASET_ID = "9nt8-h7nd"
SIMPLIFY_TOLERANCE = 0.0004  # degrees (~40m) - keeps the outline light without visibly distorting it


def main():
    print("Pulling NTA neighborhood boundaries...")
    start = time.time()
    nta_rows = soql_query(select="the_geom", limit=300, timeout=120, dataset_id=NTA_DATASET_ID)
    print(f"  {time.time()-start:.1f}s, {len(nta_rows)} neighborhoods")

    polys = []
    for r in nta_rows:
        geom = r.get("the_geom")
        if not geom:
            continue
        try:
            polys.append(shape(geom))
        except Exception:
            continue
    print(f"  {len(polys)} valid polygons parsed")

    print("Unioning into a single outline...")
    outline = unary_union(polys)
    before = sum(len(p.exterior.coords) for p in (outline.geoms if outline.geom_type == "MultiPolygon" else [outline]))
    outline = outline.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
    after = sum(len(p.exterior.coords) for p in (outline.geoms if outline.geom_type == "MultiPolygon" else [outline]))
    print(f"  simplified {before} -> {after} boundary points")

    geojson = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": mapping(outline)}],
    }
    out_path = DATA_DIR / "nyc_boundary.geojson"
    json.dump(geojson, open(out_path, "w"))
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
