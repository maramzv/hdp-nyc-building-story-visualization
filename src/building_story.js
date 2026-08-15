/**
 * JavaScript port of src/building_story.py - must stay in exact behavioral
 * sync with the Python version. Verified against it in
 * scripts/verify_js_port.py before being trusted in the live map.
 *
 * Dates are parsed via explicit UTC construction (not `new Date(str)`)
 * because JS treats date-time strings without a timezone as LOCAL time,
 * while Python's naive datetime just does arithmetic on the literal
 * numbers. Using Date.UTC() for both "today" and record dates keeps the
 * day-difference math identical to Python regardless of the visitor's
 * browser timezone.
 */

const NON_COMPLIANCE_STATUSES = new Set(["NOT COMPLIED WITH", "FALSE CERTIFICATION", "INVALID CERTIFICATION"]);
const ACCEPTED_CERT_STATUSES = new Set(["NOV CERTIFIED ON TIME", "NOV CERTIFIED LATE"]);
const MIN_CERT_ATTEMPTS_FOR_ENGAGEMENT = 3;

const ADMINISTRATIVE_ORDERNUMBERS = new Set([
  "780", "1507", "700", "1501", "778", "484", "623",
]);

function parseDate(s) {
  if (!s) return null;
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/);
  if (!m) return null;
  const [, y, mo, d, h, mi, se] = m.map(Number);
  return new Date(Date.UTC(y, mo - 1, d, h, mi, se));
}

function daysBetween(later, earlier) {
  return Math.round((later - earlier) / 86400000); // ms per day
}

function levelScale(n) {
  if (n <= 3) return "Minimal";
  if (n <= 7) return "Low";
  if (n <= 18) return "Moderate";
  if (n <= 66) return "Large";
  return "Severe";
}

function levelRecency(ratio) {
  if (ratio < 0.15) return "Dormant";
  if (ratio <= 0.70) return "Mixed";
  return "Active surge";
}

function levelSeverity(rate) {
  if (rate < 0.10) return "Low";
  if (rate <= 0.30) return "Elevated";
  if (rate <= 0.70) return "Severe";
  return "Extreme";
}

function levelEngagement(accepted, rejected) {
  const attempts = accepted + rejected;
  if (attempts < MIN_CERT_ATTEMPTS_FOR_ENGAGEMENT) return "Untested";
  const rate = accepted / attempts;
  if (rate < 0.30) return "Resistant";
  if (rate <= 0.70) return "Mixed engagement";
  return "Responsive";
}

function levelPattern(nPersistent, nChronic) {
  if (nChronic > 0) return "Chronic";
  if (nPersistent > 0) return "Persistent";
  return "Isolated";
}

function levelBacklog(days) {
  const years = days / 365;
  if (years < 2) return "Current";
  if (years <= 9.7) return "Aging";
  if (years <= 25) return "Very aged";
  return "Extreme";
}

/**
 * @param {string} buildingid
 * @param {Array<Object>} violations - raw Socrata rows for this building
 * @param {Date} today - reference date (real "now" in production, fixed in tests)
 */
function buildProfile(buildingid, violations, today) {
  const seen = new Set();
  const deduped = [];
  for (const v of violations) {
    const key = `${v.apartment || ""}|${v.novdescription || ""}|${v.novissueddate || ""}`;
    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(v);
    }
  }

  const first = violations[0] || {};
  const address = `${first.housenumber || ""} ${first.streetname || ""}, ${first.boro || ""}`;
  const activeCount = deduped.length;

  let recentCount = 0, classCRecent = 0, classCTotal = 0;
  let nonComplianceTotal = 0, nonComplianceRecent = 0;
  let acceptedCert = 0, rejectedCert = 0;
  let maxDaysOverdue = 0;
  const signatures = new Map(); // sigKey -> Map(novid -> earliest date)

  for (const v of deduped) {
    const novDate = parseDate(v.novissueddate);
    const cls = v.class;
    const status = v.currentstatus;
    const isRecent = !!(novDate && daysBetween(today, novDate) <= 365);

    if (isRecent) {
      recentCount++;
      if (cls === "C") classCRecent++;
      if (NON_COMPLIANCE_STATUSES.has(status)) nonComplianceRecent++;
    }
    if (cls === "C") classCTotal++;
    if (NON_COMPLIANCE_STATUSES.has(status)) nonComplianceTotal++;
    if (ACCEPTED_CERT_STATUSES.has(status)) acceptedCert++;
    if (status === "FALSE CERTIFICATION" || status === "INVALID CERTIFICATION") rejectedCert++;

    const deadline = parseDate(v.newcorrectbydate) || parseDate(v.originalcorrectbydate);
    if (deadline && deadline < today) {
      maxDaysOverdue = Math.max(maxDaysOverdue, daysBetween(today, deadline));
    }

    const sigKey = `${v.apartment || ""}|${v.ordernumber || ""}`;
    const novid = v.novid;
    if (novDate && novid && !ADMINISTRATIVE_ORDERNUMBERS.has(v.ordernumber)) {
      if (!signatures.has(sigKey)) signatures.set(sigKey, new Map());
      const novidMap = signatures.get(sigKey);
      if (!novidMap.has(novid) || novDate < novidMap.get(novid)) {
        novidMap.set(novid, novDate);
      }
    }
  }

  const recurringSigs = [];
  for (const novidMap of signatures.values()) {
    const dates = [...novidMap.values()];
    if (dates.length >= 2) {
      const spanYears = daysBetween(
        new Date(Math.max(...dates)), new Date(Math.min(...dates))
      ) / 365;
      recurringSigs.push([dates.length, spanYears]);
    }
  }
  recurringSigs.sort((a, b) => b[0] - a[0]);

  const [topSigNotices, topSigSpan] = recurringSigs[0] || [0, 0.0];
  const nPersistent = recurringSigs.filter(([n, s]) => n >= 3 && s >= 2).length;
  const nChronic = recurringSigs.filter(([n, s]) => n >= 10 && s >= 5).length;
  const certAttempts = acceptedCert + rejectedCert;

  const p = {
    buildingid,
    address,
    active_count: activeCount,
    recent_count: recentCount,
    recency_ratio: activeCount ? recentCount / activeCount : 0.0,
    class_c_total: classCTotal,
    class_c_recent: classCRecent,
    class_c_rate: activeCount ? classCTotal / activeCount : 0.0,
    non_compliance_total: nonComplianceTotal,
    non_compliance_recent: nonComplianceRecent,
    accepted_cert: acceptedCert,
    rejected_cert: rejectedCert,
    cert_acceptance_rate: certAttempts ? acceptedCert / certAttempts : null,
    max_days_overdue: maxDaysOverdue,
    max_years_overdue: maxDaysOverdue / 365,
    top_sig_notices: topSigNotices,
    top_sig_span_years: topSigSpan,
    n_persistent_sigs: nPersistent,
    n_chronic_sigs: nChronic,
  };
  p.scale = levelScale(p.active_count);
  p.recency = levelRecency(p.recency_ratio);
  p.severity = levelSeverity(p.class_c_rate);
  p.engagement = levelEngagement(p.accepted_cert, p.rejected_cert);
  p.pattern = levelPattern(p.n_persistent_sigs, p.n_chronic_sigs);
  p.backlog_age = levelBacklog(p.max_days_overdue);
  return p;
}

function generateNarrative(p) {
  const parts = [];

  let opener;
  if (p.recency === "Active surge") {
    let recencyPhrase;
    if (p.recency_ratio >= 0.98) {
      recencyPhrase = "all issued in roughly the past year";
    } else if (p.recency_ratio >= 0.90) {
      recencyPhrase = `nearly all (${p.recent_count} of ${p.active_count}) issued in roughly the past year`;
    } else {
      recencyPhrase = `the large majority (${p.recent_count} of ${p.active_count}) issued in roughly the past year`;
    }
    opener = `A wave of ${p.active_count} violation${p.active_count !== 1 ? "s" : ""}, ${recencyPhrase}`;
  } else if (p.recency === "Dormant") {
    opener = `${p.active_count} open violation${p.active_count !== 1 ? "s" : ""}, with little to no activity in the past year`;
  } else {
    opener = `${p.active_count} open violations, ${p.recent_count} of them issued in the past year`;
  }
  if (p.severity === "Severe" || p.severity === "Extreme") {
    opener += `, ${p.class_c_total} of them serious (Class C)`;
  }
  parts.push(opener + ".");

  if (p.pattern === "Chronic") {
    parts.push(`The same defect signature has been cited ${p.top_sig_notices} times over ${p.top_sig_span_years.toFixed(1)} years.`);
  } else if (p.pattern === "Persistent") {
    parts.push(`At least one specific problem has recurred ${p.top_sig_notices} times over ${p.top_sig_span_years.toFixed(1)} years.`);
  }

  if (p.engagement === "Untested") {
    if (p.non_compliance_total > 0) {
      parts.push("No certifications have been accepted or rejected on record, though some violations show non-compliance status.");
    }
  } else if (p.engagement === "Responsive") {
    parts.push(`Every certification attempt on record has been accepted (${p.accepted_cert} of ${p.accepted_cert + p.rejected_cert}).`);
  } else if (p.engagement === "Resistant") {
    parts.push(`Certification attempts have mostly been rejected (${p.rejected_cert} of ${p.accepted_cert + p.rejected_cert} on record).`);
  } else if (p.engagement === "Mixed engagement") {
    parts.push(`Certification attempts have had mixed outcomes (${p.accepted_cert} accepted, ${p.rejected_cert} rejected).`);
  }

  if (p.backlog_age === "Very aged" || p.backlog_age === "Extreme") {
    parts.push(`The oldest outstanding violation is ${p.max_years_overdue.toFixed(1)} years past its correction deadline.`);
  }

  return parts.join(" ");
}
