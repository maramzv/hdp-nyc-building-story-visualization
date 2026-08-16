"""Discovery-phase analysis script — NOT part of the production pipeline.

Pulls the full process-timeline fields (inspectiondate, approveddate,
certifieddate, currentstatusdate, originalcertifybydate, newcertifybydate)
for a random sample of buildings, live from csn4-vhvf — these fields exist
in the source dataset but were never cached locally. Writes only to
data/violation_timeline_sample.json. Read-only against the live API and
existing data/map_dataset.json (for the buildingid population to sample
from); does not touch any production file.

See docs/data-analysis-log.md for why this was needed.
"""
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from socrata_client import soql_query  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

FIELDS = ("buildingid,class,ordernumber,inspectiondate,approveddate,"
          "originalcorrectbydate,newcorrectbydate,originalcertifybydate,"
          "newcertifybydate,novissueddate,certifieddate,currentstatus,"
          "currentstatusdate")


def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def main():
    random.seed(2026)
    with open(DATA_DIR / "map_dataset.json") as f:
        buildings = json.load(f)
    all_ids = [b["buildingid"] for b in buildings]
    sample_ids = random.sample(all_ids, 1500)
    print(f"Sampling {len(sample_ids)} buildings out of {len(all_ids)}")

    all_rows = []
    for i, batch in enumerate(chunked(sample_ids, 200)):
        clause = " OR ".join(f"buildingid='{bid}'" for bid in batch)
        start = time.time()
        rows = soql_query(select=FIELDS, where=clause, limit=5000, timeout=60)
        all_rows.extend(rows)
        print(f"  batch {i+1}: {len(rows)} rows in {time.time()-start:.1f}s")

    out_path = DATA_DIR / "violation_timeline_sample.json"
    with open(out_path, "w") as f:
        json.dump(all_rows, f)
    print(f"Done. {len(all_rows)} records written to {out_path}")


if __name__ == "__main__":
    main()
