"""Build the evidence layer: actual violation records behind each building's story.

Card (map column) -> Detail (story panel) -> Evidence (this) is the 3-level
UI design from docs/story-taxonomy.md. This closes the third level, which was
missing: someone should be able to verify a building's story against the real
records, not just take the generated sentence on faith.

Reads the already-cached raw violation pull (no new API calls needed) and
produces one trimmed, per-building record list for the map to show on click.

Run: python scripts/build_evidence_index.py
"""
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace(".000", ""))
    except Exception:
        return None


def main():
    rows = json.load(open(DATA_DIR / "map_dataset_violations_raw.json"))
    by_building = defaultdict(list)

    for v in rows:
        bid = v["buildingid"]
        nov_date = v.get("novissueddate")
        desc = (v.get("novdescription") or "").strip()
        # Trim the legal-citation prefix (e.g. "S 27-2005 ADM CODE ") for readability
        if desc and len(desc) > 140:
            desc = desc[:140].rsplit(" ", 1)[0] + "..."
        by_building[bid].append({
            "date": nov_date[:10] if nov_date else None,
            "class": v.get("class"),
            "status": v.get("currentstatus"),
            "description": desc,
        })

    # Dedup + sort newest-first per building, same key as build_profile's dedup
    output = {}
    for bid, viols in by_building.items():
        seen = set()
        deduped = []
        for v in viols:
            key = (v["date"], v["class"], v["description"])
            if key not in seen:
                seen.add(key)
                deduped.append(v)
        deduped.sort(key=lambda v: v["date"] or "", reverse=True)
        output[bid] = deduped

    out_path = DATA_DIR / "building_evidence.json"
    json.dump(output, open(out_path, "w"))
    total_records = sum(len(v) for v in output.values())
    print(f"Evidence index: {len(output)} buildings, {total_records} records")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
