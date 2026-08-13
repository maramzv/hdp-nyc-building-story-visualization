"""Step 2: verify we can reach the live Socrata API and see what it gives us.

Run: python scripts/check_api_connectivity.py
No full-dataset download here — just metadata, a sample row, and a count.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from socrata_client import APP_TOKEN, get_metadata, row_count, soql_query  # noqa: E402


def main():
    print(f"App token loaded: {'yes (' + str(len(APP_TOKEN)) + ' chars)' if APP_TOKEN else 'no'}\n")

    print("=== Metadata ===")
    meta = get_metadata()
    print("Name:", meta.get("name"))
    print("Description:", (meta.get("description") or "")[:300])
    print("Row count (metadata estimate):", meta.get("rowsUpdatedAt"), "| viewCount:", meta.get("viewCount"))

    columns = meta.get("columns", [])
    print(f"\nColumn count: {len(columns)}")
    for col in columns:
        print(f"  - {col.get('fieldName'):35s} {col.get('dataTypeName'):12s} {col.get('name')}")

    print("\n=== Live row count (SoQL count(*)) ===")
    total = row_count()
    print("Total records:", f"{total:,}")

    print("\n=== Sample record ===")
    sample = soql_query(limit=1)
    print(json.dumps(sample[0], indent=2))

    # Save raw metadata + sample locally for reference (git-ignored)
    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2))
    (out_dir / "sample_record.json").write_text(json.dumps(sample[0], indent=2))
    print(f"\nSaved metadata.json and sample_record.json to {out_dir}")


if __name__ == "__main__":
    main()
