"""Discovery-phase analysis script — NOT part of the production pipeline.

Builds a flat, one-row-per-building table of RAW signals (counts, not tiers)
from data/map_dataset_violations_raw.json, for exploratory analysis of
whether the open-violation data contains recurring building-condition
configurations. Read-only against existing data; writes only to
data/building_signals_raw.csv. Does not touch building_story.py/.js,
map_dataset.json, or any production file.

See docs/data-analysis-log.md for the analytical plan this supports.
"""
import csv
import ijson
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from building_story import ADMINISTRATIVE_ORDERNUMBERS, _parse_date  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TODAY = datetime(2026, 8, 16)

NON_COMPLIANCE_STATUSES = {"NOT COMPLIED WITH", "FALSE CERTIFICATION", "INVALID CERTIFICATION"}
STALLED_STATUSES = {"NOT COMPLIED WITH", "FIRST NO ACCESS TO RE-INSPECT VIOLATION",
                     "SECOND NO ACCESS TO RE-INSPECT VIOLATION"}
MOVING_STATUSES = {"VIOLATION WILL BE REINSPECTED", "NOV CERTIFIED ON TIME", "NOV CERTIFIED LATE"}
REJECTED_CERT_STATUSES = {"FALSE CERTIFICATION", "INVALID CERTIFICATION"}


def main():
    src_path = DATA_DIR / "map_dataset_violations_raw.json"
    out_path = DATA_DIR / "building_signals_raw.csv"

    # Pass 1: group raw records by building (streamed, not all held at full detail)
    by_building = defaultdict(list)
    n = 0
    with open(src_path, "rb") as f:
        for obj in ijson.items(f, "item"):
            by_building[obj["buildingid"]].append(obj)
            n += 1
            if n % 500000 == 0:
                print(f"  read {n} records, {len(by_building)} buildings so far...")
    print(f"Total records read: {n}, distinct buildings: {len(by_building)}")

    fieldnames = [
        "buildingid", "boro",
        "total_records_raw", "total_records_deduped",
        "real_defect_records", "admin_records",
        "distinct_ordernumbers_real", "distinct_apartments_real",
        "building_wide_signature_max_notices", "building_wide_signature_max_span_years",
        "apartment_only_signature_max_notices", "apartment_only_signature_max_span_years",
        "bw_n_persistent_sigs", "bw_n_chronic_sigs",
        "apt_n_persistent_sigs", "apt_n_chronic_sigs",
        "class_A", "class_B", "class_C", "class_I",
        "status_nov_sent_out", "status_not_complied", "status_no_access",
        "status_reinspect_pending", "status_certified", "status_invalid_or_false_cert",
        "status_other",
        "recent_count_1yr", "oldest_violation_date", "newest_violation_date",
        "max_days_overdue",
    ]

    with open(out_path, "w", newline="", encoding="utf-8") as outf:
        writer = csv.DictWriter(outf, fieldnames=fieldnames)
        writer.writeheader()

        processed = 0
        for bid, records in by_building.items():
            # dedupe exactly as build_profile() does: (apartment, description, date)
            seen = set()
            deduped = []
            for v in records:
                key = (v.get("apartment"), v.get("novdescription"), v.get("novissueddate"))
                if key not in seen:
                    seen.add(key)
                    deduped.append(v)

            boro = records[0].get("boro", "")
            real = [v for v in deduped if v.get("ordernumber") not in ADMINISTRATIVE_ORDERNUMBERS]
            admin = [v for v in deduped if v.get("ordernumber") in ADMINISTRATIVE_ORDERNUMBERS]

            distinct_ordernumbers_real = len({v.get("ordernumber") for v in real})
            distinct_apartments_real = len({v.get("apartment") for v in real if v.get("apartment")})

            class_counts = defaultdict(int)
            status_counts = defaultdict(int)
            dates = []
            max_days_overdue = 0
            recent_count = 0

            # building-wide signature: same ordernumber, ANY apartment (ignores apartment)
            bw_sig = defaultdict(dict)  # ordernumber -> {novid: date}
            # apartment-only signature: current production logic (apartment, ordernumber)
            apt_sig = defaultdict(dict)  # (apartment, ordernumber) -> {novid: date}

            for v in deduped:
                cls = v.get("class") or "?"
                class_counts[cls] += 1

                status = (v.get("currentstatus") or "").strip()
                if status == "NOV SENT OUT":
                    status_counts["nov_sent_out"] += 1
                elif status == "NOT COMPLIED WITH":
                    status_counts["not_complied"] += 1
                elif "NO ACCESS" in status:
                    status_counts["no_access"] += 1
                elif status == "VIOLATION WILL BE REINSPECTED":
                    status_counts["reinspect_pending"] += 1
                elif status in ("NOV CERTIFIED ON TIME", "NOV CERTIFIED LATE"):
                    status_counts["certified"] += 1
                elif status in REJECTED_CERT_STATUSES:
                    status_counts["invalid_or_false_cert"] += 1
                else:
                    status_counts["other"] += 1

                nov_date = _parse_date(v.get("novissueddate"))
                if nov_date:
                    dates.append(nov_date)
                    if (TODAY - nov_date).days <= 365:
                        recent_count += 1

                deadline = _parse_date(v.get("newcorrectbydate")) or _parse_date(v.get("originalcorrectbydate"))
                if deadline and deadline < TODAY:
                    max_days_overdue = max(max_days_overdue, (TODAY - deadline).days)

                ordernum = v.get("ordernumber")
                novid = v.get("novid")
                if nov_date and novid and ordernum not in ADMINISTRATIVE_ORDERNUMBERS:
                    if novid not in bw_sig[ordernum] or nov_date < bw_sig[ordernum][novid]:
                        bw_sig[ordernum][novid] = nov_date
                    apt_key = (v.get("apartment"), ordernum)
                    if novid not in apt_sig[apt_key] or nov_date < apt_sig[apt_key][novid]:
                        apt_sig[apt_key][novid] = nov_date

            def signature_stats(sig_dict):
                """Returns (top_notices, top_span_of_top_signature, n_persistent_sigs, n_chronic_sigs)
                — n_persistent/n_chronic check EVERY signature for qualification (matches
                build_profile()'s method exactly), not just the highest-count one, since a
                building can have its best-qualifying signature be a different ordernumber
                than the one with the single highest raw notice count."""
                best_n, best_span = 0, 0.0
                n_persistent = n_chronic = 0
                for key, novid_dates in sig_dict.items():
                    ds = list(novid_dates.values())
                    if len(ds) >= 2:
                        span = (max(ds) - min(ds)).days / 365
                        if len(ds) > best_n or (len(ds) == best_n and span > best_span):
                            best_n, best_span = len(ds), span
                        if len(ds) >= 10 and span >= 5:
                            n_chronic += 1
                        elif len(ds) >= 3 and span >= 2:
                            n_persistent += 1
                return best_n, round(best_span, 2), n_persistent, n_chronic

            bw_notices, bw_span, bw_n_persistent, bw_n_chronic = signature_stats(bw_sig)
            apt_notices, apt_span, apt_n_persistent, apt_n_chronic = signature_stats(apt_sig)

            writer.writerow({
                "buildingid": bid,
                "boro": boro,
                "total_records_raw": len(records),
                "total_records_deduped": len(deduped),
                "real_defect_records": len(real),
                "admin_records": len(admin),
                "distinct_ordernumbers_real": distinct_ordernumbers_real,
                "distinct_apartments_real": distinct_apartments_real,
                "building_wide_signature_max_notices": bw_notices,
                "building_wide_signature_max_span_years": bw_span,
                "apartment_only_signature_max_notices": apt_notices,
                "apartment_only_signature_max_span_years": apt_span,
                "bw_n_persistent_sigs": bw_n_persistent,
                "bw_n_chronic_sigs": bw_n_chronic,
                "apt_n_persistent_sigs": apt_n_persistent,
                "apt_n_chronic_sigs": apt_n_chronic,
                "class_A": class_counts.get("A", 0),
                "class_B": class_counts.get("B", 0),
                "class_C": class_counts.get("C", 0),
                "class_I": class_counts.get("I", 0),
                "status_nov_sent_out": status_counts.get("nov_sent_out", 0),
                "status_not_complied": status_counts.get("not_complied", 0),
                "status_no_access": status_counts.get("no_access", 0),
                "status_reinspect_pending": status_counts.get("reinspect_pending", 0),
                "status_certified": status_counts.get("certified", 0),
                "status_invalid_or_false_cert": status_counts.get("invalid_or_false_cert", 0),
                "status_other": status_counts.get("other", 0),
                "recent_count_1yr": recent_count,
                "oldest_violation_date": min(dates).date().isoformat() if dates else "",
                "newest_violation_date": max(dates).date().isoformat() if dates else "",
                "max_days_overdue": max_days_overdue,
            })

            processed += 1
            if processed % 25000 == 0:
                print(f"  processed {processed}/{len(by_building)} buildings...")

    print(f"Done. Wrote {processed} rows to {out_path}")


if __name__ == "__main__":
    main()
