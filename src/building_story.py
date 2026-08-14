"""Turns a building's raw HPD violation records into a six-dimension profile
and an evidence-based narrative sentence.

This is the reusable version of the analysis done ad hoc in
scripts/phase3_derive_taxonomy.py, and it's the core of the "Building Story
Engine" from docs/story-taxonomy.md. Deterministic, rule-based — no ML.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

NON_COMPLIANCE_STATUSES = {"NOT COMPLIED WITH", "FALSE CERTIFICATION", "INVALID CERTIFICATION"}
ACCEPTED_CERT_STATUSES = {"NOV CERTIFIED ON TIME", "NOV CERTIFIED LATE"}
P90_OVERDUE_DAYS = 9.7 * 365
P99_OVERDUE_DAYS = 25.2 * 365
MIN_CERT_ATTEMPTS_FOR_ENGAGEMENT = 3

# OrderNumbers that represent recurring ADMINISTRATIVE/FILING obligations rather
# than physical defects. These recur by design (e.g. annually, for every subject
# building) and would falsely inflate Persistent/Chronic pattern detection if not
# excluded. Found via Phase 3 testing: 8 of 25 "Persistent" matches in an 80-building
# sample turned out to be the same annual-filing code (1507). Audited the other top-60
# codes by citywide frequency (data/ordernumber_counts.json) for the same pattern —
# high confidence on the first 5, moderate on the last 2 (posting/certification-type
# obligations that plausibly recur on a compliance calendar, but not as certain as the
# bedbug report). Not exhaustive — only the top 60 of 396 codes were reviewed.
ADMINISTRATIVE_ORDERNUMBERS = {
    "780",   # "OWNER FAILED TO FILE A VALID REGISTRATION STATEMENT" - recurs if unregistered
    "1507",  # "FILE ANNUAL BEDBUG REPORT" - recurs yearly by design
    "700",   # "POST A PROPER NOTICE OF SMOKE DETECTOR REQUIREMENTS" - signage, not the device
    "1501",  # "POST A PROPER NOTICE OF CARBON MONOXIDE DETECTING DEVICE REQUIREMENTS" - signage
    "778",   # "POST AND MAINTAIN A PROPER SIGN...SHOWING THE REGISTRATION NUMBER" - signage
    "484",   # "PROVIDE A COMPLETED CERTIFICATE OF INSPECTION VISITS" - MDL S329 posting (moderate confidence)
    "623",   # "CERTIFY COMPLIANCE WITH LEAD-BASED PAINT HAZARD CONTROL REQUIREMENTS" - Local Law 1 annual cert (moderate confidence)
}


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace(".000", ""))
    except Exception:
        return None


@dataclass
class BuildingProfile:
    buildingid: str
    address: str
    active_count: int
    recent_count: int
    recency_ratio: float
    class_c_total: int
    class_c_recent: int
    class_c_rate: float
    non_compliance_total: int
    non_compliance_recent: int
    accepted_cert: int
    rejected_cert: int
    cert_acceptance_rate: float | None
    max_days_overdue: int
    max_years_overdue: float
    top_sig_notices: int
    top_sig_span_years: float
    n_persistent_sigs: int
    n_chronic_sigs: int

    # Assigned dimension levels
    scale: str = ""
    recency: str = ""
    severity: str = ""
    engagement: str = ""
    pattern: str = ""
    backlog_age: str = ""


def _level_scale(n):
    if n <= 3:
        return "Minimal"
    if n <= 7:
        return "Low"
    if n <= 18:
        return "Moderate"
    if n <= 66:
        return "Large"
    return "Severe"


def _level_recency(ratio):
    if ratio < 0.15:
        return "Dormant"
    if ratio <= 0.70:
        return "Mixed"
    return "Active surge"


def _level_severity(rate):
    if rate < 0.10:
        return "Low"
    if rate <= 0.30:
        return "Elevated"
    if rate <= 0.70:
        return "Severe"
    return "Extreme"


def _level_engagement(accepted, rejected):
    attempts = accepted + rejected
    if attempts < MIN_CERT_ATTEMPTS_FOR_ENGAGEMENT:
        # Zero attempts: genuinely untested. 1-2 attempts: too little evidence
        # for a confident behavioral claim, even though technically non-zero.
        return "Untested"
    rate = accepted / attempts
    if rate < 0.30:
        return "Resistant"
    if rate <= 0.70:
        return "Mixed engagement"
    return "Responsive"


def _level_pattern(n_persistent, n_chronic):
    if n_chronic > 0:
        return "Chronic"
    if n_persistent > 0:
        return "Persistent"
    return "Isolated"


def _level_backlog(days):
    years = days / 365
    if years < 2:
        return "Current"
    if years <= 9.7:
        return "Aging"
    if years <= 25:
        return "Very aged"
    return "Extreme"


def build_profile(buildingid: str, violations: list[dict], today: datetime) -> BuildingProfile:
    """Compute the six-dimension profile for one building from its raw violation rows."""
    seen = set()
    deduped = []
    for v in violations:
        key = (v.get("apartment"), v.get("novdescription"), v.get("novissueddate"))
        if key not in seen:
            seen.add(key)
            deduped.append(v)

    addr = f"{violations[0].get('housenumber','')} {violations[0].get('streetname','')}, {violations[0].get('boro','')}"
    active_count = len(deduped)

    recent_count = class_c_recent = class_c_total = 0
    non_compliance_total = non_compliance_recent = 0
    accepted_cert = rejected_cert = 0
    max_days_overdue = 0
    signatures = defaultdict(dict)

    for v in deduped:
        nov_date = _parse_date(v.get("novissueddate"))
        cls = v.get("class")
        status = v.get("currentstatus")
        is_recent = bool(nov_date and (today - nov_date).days <= 365)

        if is_recent:
            recent_count += 1
            if cls == "C":
                class_c_recent += 1
            if status in NON_COMPLIANCE_STATUSES:
                non_compliance_recent += 1
        if cls == "C":
            class_c_total += 1
        if status in NON_COMPLIANCE_STATUSES:
            non_compliance_total += 1
        if status in ACCEPTED_CERT_STATUSES:
            accepted_cert += 1
        if status in ("FALSE CERTIFICATION", "INVALID CERTIFICATION"):
            rejected_cert += 1

        deadline = _parse_date(v.get("newcorrectbydate")) or _parse_date(v.get("originalcorrectbydate"))
        if deadline and deadline < today:
            max_days_overdue = max(max_days_overdue, (today - deadline).days)

        sig_key = (v.get("apartment"), v.get("ordernumber"))
        novid = v.get("novid")
        if nov_date and novid and v.get("ordernumber") not in ADMINISTRATIVE_ORDERNUMBERS:
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

    p = BuildingProfile(
        buildingid=buildingid,
        address=addr,
        active_count=active_count,
        recent_count=recent_count,
        recency_ratio=(recent_count / active_count) if active_count else 0.0,
        class_c_total=class_c_total,
        class_c_recent=class_c_recent,
        class_c_rate=(class_c_total / active_count) if active_count else 0.0,
        non_compliance_total=non_compliance_total,
        non_compliance_recent=non_compliance_recent,
        accepted_cert=accepted_cert,
        rejected_cert=rejected_cert,
        cert_acceptance_rate=(accepted_cert / cert_attempts) if cert_attempts else None,
        max_days_overdue=max_days_overdue,
        max_years_overdue=max_days_overdue / 365,
        top_sig_notices=top_sig_notices,
        top_sig_span_years=top_sig_span,
        n_persistent_sigs=n_persistent,
        n_chronic_sigs=n_chronic,
    )
    p.scale = _level_scale(p.active_count)
    p.recency = _level_recency(p.recency_ratio)
    p.severity = _level_severity(p.class_c_rate)
    p.engagement = _level_engagement(p.accepted_cert, p.rejected_cert)
    p.pattern = _level_pattern(p.n_persistent_sigs, p.n_chronic_sigs)
    p.backlog_age = _level_backlog(p.max_days_overdue)
    return p


def generate_narrative(p: BuildingProfile) -> str:
    """Assemble an evidence-based sentence from the six dimension values.
    Every clause traces to a specific field on the profile — no characterization
    of the building or owner, only what the records show."""
    parts = []

    # Scale + recency + severity opener
    if p.recency == "Active surge":
        if p.recency_ratio >= 0.98:
            recency_phrase = "all issued in roughly the past year"
        elif p.recency_ratio >= 0.90:
            recency_phrase = f"nearly all ({p.recent_count} of {p.active_count}) issued in roughly the past year"
        else:
            recency_phrase = f"the large majority ({p.recent_count} of {p.active_count}) issued in roughly the past year"
        opener = f"A wave of {p.active_count} violation{'s' if p.active_count != 1 else ''}, {recency_phrase}"
    elif p.recency == "Dormant":
        opener = f"{p.active_count} open violation{'s' if p.active_count != 1 else ''}, with little to no activity in the past year"
    else:
        opener = f"{p.active_count} open violations, {p.recent_count} of them issued in the past year"
    if p.severity in ("Severe", "Extreme"):
        opener += f", {p.class_c_total} of them serious (Class C)"
    parts.append(opener + ".")

    # Pattern
    if p.pattern == "Chronic":
        parts.append(
            f"The same defect signature has been cited {p.top_sig_notices} times over "
            f"{p.top_sig_span_years:.1f} years."
        )
    elif p.pattern == "Persistent":
        parts.append(
            f"At least one specific problem has recurred {p.top_sig_notices} times over "
            f"{p.top_sig_span_years:.1f} years."
        )

    # Engagement
    if p.engagement == "Untested":
        if p.non_compliance_total > 0:
            parts.append("No certifications have been accepted or rejected on record, though some violations show non-compliance status.")
    elif p.engagement == "Responsive":
        parts.append(f"Every certification attempt on record has been accepted ({p.accepted_cert} of {p.accepted_cert + p.rejected_cert}).")
    elif p.engagement == "Resistant":
        parts.append(f"Certification attempts have mostly been rejected ({p.rejected_cert} of {p.accepted_cert + p.rejected_cert} on record).")
    elif p.engagement == "Mixed engagement":
        parts.append(f"Certification attempts have had mixed outcomes ({p.accepted_cert} accepted, {p.rejected_cert} rejected).")

    # Backlog age
    if p.backlog_age in ("Very aged", "Extreme"):
        parts.append(f"The oldest outstanding violation is {p.max_years_overdue:.1f} years past its correction deadline.")

    return " ".join(parts)
