"""Phase 3, data-first taxonomy derivation: step 2 - compute features, look for real groupings.

No preset story categories here. Just the feature vector, computed the same
way for every building in the wide sample, so patterns can be read off the
real data instead of tested against assumptions.

Run: python scripts/phase3_derive_taxonomy.py
Reads data/phase3_wide_sample_raw.json. Writes data/phase3_feature_table.csv.
"""
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

TODAY = datetime(2026, 8, 14)
NON_COMPLIANCE_STATUSES = {"NOT COMPLIED WITH", "FALSE CERTIFICATION", "INVALID CERTIFICATION"}
ACCEPTED_CERT_STATUSES = {"NOV CERTIFIED ON TIME", "NOV CERTIFIED LATE"}
P90_OVERDUE_DAYS = 9.7 * 365

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace(".000", ""))
    except Exception:
        return None


def compute_features(buildingid, viols):
    seen = set()
    deduped = []
    for v in viols:
        key = (v.get("apartment"), v.get("novdescription"), v.get("novissueddate"))
        if key not in seen:
            seen.add(key)
            deduped.append(v)

    addr = f"{viols[0].get('housenumber','')} {viols[0].get('streetname','')}, {viols[0].get('boro','')}"
    active_count = len(deduped)

    recent_count = class_c_recent = class_c_total = 0
    non_compliance_count = non_compliance_recent = 0
    accepted_cert = rejected_cert = 0
    max_days_overdue = overdue_gt_p90 = 0
    signatures = defaultdict(dict)

    for v in deduped:
        nov_date = parse_date(v.get("novissueddate"))
        cls = v.get("class")
        status = v.get("currentstatus")
        is_recent = bool(nov_date and (TODAY - nov_date).days <= 365)

        if is_recent:
            recent_count += 1
            if cls == "C":
                class_c_recent += 1
            if status in NON_COMPLIANCE_STATUSES:
                non_compliance_recent += 1
        if cls == "C":
            class_c_total += 1
        if status in NON_COMPLIANCE_STATUSES:
            non_compliance_count += 1
        if status in ACCEPTED_CERT_STATUSES:
            accepted_cert += 1
        if status in ("FALSE CERTIFICATION", "INVALID CERTIFICATION"):
            rejected_cert += 1

        deadline = parse_date(v.get("newcorrectbydate")) or parse_date(v.get("originalcorrectbydate"))
        if deadline and deadline < TODAY:
            days_overdue = (TODAY - deadline).days
            max_days_overdue = max(max_days_overdue, days_overdue)
            if days_overdue > P90_OVERDUE_DAYS:
                overdue_gt_p90 += 1

        sig_key = (v.get("apartment"), v.get("ordernumber"))
        novid = v.get("novid")
        if nov_date and novid:
            if novid not in signatures[sig_key] or nov_date < signatures[sig_key][novid]:
                signatures[sig_key][novid] = nov_date

    recurring_sigs = []
    for sig, novid_dates in signatures.items():
        dates = list(novid_dates.values())
        if len(dates) >= 2:
            span_years = (max(dates) - min(dates)).days / 365
            recurring_sigs.append((len(dates), span_years))
    recurring_sigs.sort(key=lambda x: -x[0])

    top_sig_notices, top_sig_span = recurring_sigs[0] if recurring_sigs else (0, 0.0)
    n_persistent = sum(1 for n, s in recurring_sigs if n >= 3 and s >= 2)
    n_chronic = sum(1 for n, s in recurring_sigs if n >= 10 and s >= 5)

    cert_attempts = accepted_cert + rejected_cert

    return {
        "buildingid": buildingid,
        "address": addr,
        "active_count": active_count,
        "recent_count": recent_count,
        "recency_ratio": round(recent_count / active_count, 2) if active_count else 0,
        "class_c_total": class_c_total,
        "class_c_recent": class_c_recent,
        "class_c_rate": round(class_c_total / active_count, 2) if active_count else 0,
        "non_compliance_total": non_compliance_count,
        "non_compliance_recent": non_compliance_recent,
        "non_compliance_rate": round(non_compliance_count / active_count, 2) if active_count else 0,
        "non_compliance_recent_rate": round(non_compliance_recent / recent_count, 2) if recent_count else 0,
        "accepted_cert": accepted_cert,
        "rejected_cert": rejected_cert,
        "cert_acceptance_rate": round(accepted_cert / cert_attempts, 2) if cert_attempts else None,
        "max_days_overdue": max_days_overdue,
        "max_years_overdue": round(max_days_overdue / 365, 1),
        "overdue_gt_p90_count": overdue_gt_p90,
        "top_sig_notices": top_sig_notices,
        "top_sig_span_years": round(top_sig_span, 1),
        "n_persistent_sigs": n_persistent,
        "n_chronic_sigs": n_chronic,
    }


def main():
    rows = json.load(open(DATA_DIR / "phase3_wide_sample_raw.json"))
    by_building = defaultdict(list)
    for r in rows:
        by_building[r["buildingid"]].append(r)

    features = [compute_features(bid, viols) for bid, viols in by_building.items()]
    df = pd.DataFrame(features).sort_values("active_count").reset_index(drop=True)

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 250)
    print(df.to_string(index=False))

    out_csv = DATA_DIR / "phase3_feature_table.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nSaved to {out_csv}")
    print(f"\nn buildings: {len(df)}")


if __name__ == "__main__":
    main()
