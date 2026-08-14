"""Phase 3 v2: fixes from the first pass.

Fixes applied:
1. Recurrence occurrences are now grouped by NOVID first (one notice = one
   occurrence), so same-day multi-line-item notices no longer get miscounted
   as "recurrence over time."
2. "In process / on track" allows up to 90 days overdue (a brief lag doesn't
   contradict good-faith compliance) instead of requiring literally zero.
3. Escalating concern now requires RECENT non-compliance, not any-time-ever
   non-compliance (was firing on almost every large building).
4. New bounded "Recent surge" bucket: high absolute recent-violation count,
   with no comparison to the building's own (survivorship-biased) history.
5. Reports both every matching label (diagnostic) AND a single priority-
   ordered headline, to see whether prioritization actually differentiates
   buildings that used to collapse into identical label sets.

Run: python scripts/phase3_classify_sample.py
Reads data/phase3_sample_raw.json (already pulled, no new API calls).
"""
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

TODAY = datetime(2026, 8, 14)
NON_COMPLIANCE_STATUSES = {"NOT COMPLIED WITH", "FALSE CERTIFICATION", "INVALID CERTIFICATION"}
ACCEPTED_CERT_STATUSES = {"NOV CERTIFIED ON TIME", "NOV CERTIFIED LATE"}

HEADLINE_PRIORITY = [
    "Escalating concern",
    "Chronic problem",
    "Aging backlog",
    "Mixed / complex",
    "Recent surge",
    "Persistent problem",
    "Acute concern",
    "In process / on track",
    "Minimal current concern",
]


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace(".000", ""))
    except Exception:
        return None


def main():
    rows = json.load(open(Path(__file__).resolve().parent.parent / "data" / "phase3_sample_raw.json"))

    by_building = defaultdict(list)
    for r in rows:
        by_building[r["buildingid"]].append(r)

    for buildingid, viols in by_building.items():
        seen = set()
        deduped = []
        for v in viols:
            key = (v.get("apartment"), v.get("novdescription"), v.get("novissueddate"))
            if key not in seen:
                seen.add(key)
                deduped.append(v)

        addr = f"{viols[0].get('housenumber','')} {viols[0].get('streetname','')}, {viols[0].get('boro','')}"
        active_count = len(deduped)

        recent_count = 0
        class_c_recent = 0
        class_c_total = 0
        non_compliance_count = 0
        non_compliance_recent = 0
        max_days_overdue = 0
        overdue_gt_p90 = 0
        accepted_cert = 0
        rejected_cert = 0
        # signature -> {novid: earliest_date_for_that_novid}
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
                if days_overdue > 9.7 * 365:
                    overdue_gt_p90 += 1

            sig_key = (v.get("apartment"), v.get("ordernumber"))
            novid = v.get("novid")
            if nov_date and novid:
                # one entry per NOVID (notice), not per violation line-item
                if novid not in signatures[sig_key] or nov_date < signatures[sig_key][novid]:
                    signatures[sig_key][novid] = nov_date

        recurring_sigs = []
        for sig, novid_dates in signatures.items():
            dates = list(novid_dates.values())
            if len(dates) >= 2:  # >=2 DISTINCT NOTICES, not line items
                span_years = (max(dates) - min(dates)).days / 365
                recurring_sigs.append((sig, len(dates), span_years))
        recurring_sigs.sort(key=lambda x: -x[1])

        persistent_sigs = [s for s in recurring_sigs if s[1] >= 3 and s[2] >= 2]
        chronic_sigs = [s for s in recurring_sigs if s[1] >= 10 and s[2] >= 5]

        matches = []
        if accepted_cert > 0 and rejected_cert == 0 and max_days_overdue <= 90:
            matches.append("In process / on track")
        if active_count <= 3 and class_c_total == 0 and not recurring_sigs:
            matches.append("Minimal current concern")
        if active_count <= 7 and class_c_recent >= 1:
            matches.append("Acute concern")
        if persistent_sigs:
            matches.append("Persistent problem")
        if chronic_sigs:
            matches.append("Chronic problem")
        if overdue_gt_p90 > 0:
            matches.append("Aging backlog")
        if len(persistent_sigs) >= 2:
            matches.append("Mixed / complex")
        if recent_count >= 15:
            matches.append("Recent surge")
        if class_c_recent >= 1 and non_compliance_recent >= 1:
            matches.append("Escalating concern")
        if not matches:
            matches.append("*** NO MATCH (default bucket) ***")

        headline = next((h for h in HEADLINE_PRIORITY if h in matches), matches[0])

        recency_ratio = recent_count / active_count if active_count else 0
        noncompliance_rate = non_compliance_count / active_count if active_count else 0

        print(f"\n{'='*70}")
        print(f"BuildingID {buildingid} — {addr}")
        print(f"  Active: {active_count} | Recent(12mo): {recent_count} ({recency_ratio:.0%}) | ClassC: {class_c_total} (recent {class_c_recent})")
        print(f"  Non-compliance: {non_compliance_count} total ({noncompliance_rate:.0%}), {non_compliance_recent} recent | Accepted certs: {accepted_cert} | Rejected: {rejected_cert}")
        print(f"  Max days overdue: {max_days_overdue} ({max_days_overdue/365:.1f}yr) | >p90 overdue: {overdue_gt_p90}")
        if recurring_sigs:
            top = recurring_sigs[0]
            print(f"  Top recurring signature (by distinct notices): apt={top[0][0]}, ordernumber={top[0][1]}, notices={top[1]}, span={top[2]:.1f}yr")
        print(f"  >> HEADLINE: {headline}")
        print(f"     (all matches: {matches})")


if __name__ == "__main__":
    main()
