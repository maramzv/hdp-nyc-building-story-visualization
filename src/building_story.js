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
// p75 of real_defect_count within the Isolated/Widespread candidate pool -
// see the matching comment in building_story.py.
const REAL_DEFECT_WIDESPREAD_THRESHOLD = 9;

const ADMINISTRATIVE_ORDERNUMBERS = new Set([
  "780", "1507", "700", "1501", "778", "484", "623",
]);

const DESCRIPTION_STOPWORDS = new Set([
  "PROPERLY", "REPAIR", "REPLACE", "REMOVE", "MAINTAIN", "PROVIDE", "CLEAN",
  "CONDITION", "ADM", "CODE", "HMC", "SECTION", "MDL", "LAW", "REQUIRED",
  "SIMILAR", "MATERIAL", "ACCORDANCE", "DESCRIBED", "NOTICE", "VIOLATION",
  "BUILDING", "APARTMENT", "LOCATED", "ENTIRE", "WHICH", "THEREFORE",
  "SUBJECT", "ABATE", "DEFECTIVE", "BROKEN", "STORY", "FRONT", "REAR",
]);

function defectKeywords(desc) {
  if (!desc) return new Set();
  const words = desc.toUpperCase().match(/[A-Z]{4,}/g) || [];
  return new Set(words.filter(w => !DESCRIPTION_STOPWORDS.has(w)));
}

function signatureIsCoherent(descriptions) {
  const distinct = [...new Set(descriptions.filter(Boolean))];
  if (distinct.length <= 1) return true;
  const counts = new Map();
  for (const d of distinct) {
    for (const kw of defectKeywords(d)) {
      counts.set(kw, (counts.get(kw) || 0) + 1);
    }
  }
  if (counts.size === 0) return false;
  return Math.max(...counts.values()) / distinct.length >= 0.6;
}

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

function levelPattern(nPersistent, nChronic, realDefectCount) {
  if (nChronic > 0) return "Chronic";
  if (nPersistent > 0) return "Persistent";
  if (realDefectCount === 0) return "No real defects";
  if (realDefectCount >= REAL_DEFECT_WIDESPREAD_THRESHOLD) return "Widespread";
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
  const realDefectCount = deduped.filter(v => !ADMINISTRATIVE_ORDERNUMBERS.has(v.ordernumber)).length;

  let recentCount = 0, classCRecent = 0, classCTotal = 0;
  let nonComplianceTotal = 0, nonComplianceRecent = 0;
  let acceptedCert = 0, rejectedCert = 0;
  let maxDaysOverdue = 0;
  // Building-wide signatures (same OrderNumber, ANY apartment) - see the
  // matching comment in building_story.py for why apartment-scoped grouping
  // was replaced rather than kept alongside this.
  const signatures = new Map();     // ordernumber -> Map(novid -> earliest date)
  const sigApartments = new Map();  // ordernumber -> Set(apartments touched)
  const sigDescriptions = new Map(); // ordernumber -> Map(novid -> description)
  // Distinct calendar dates a REAL defect was cited, regardless of
  // ordernumber - see the matching comment in building_story.py.
  const defectVisitDates = new Set();

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
    if (deadline && deadline < today && !ACCEPTED_CERT_STATUSES.has(status)) {
      maxDaysOverdue = Math.max(maxDaysOverdue, daysBetween(today, deadline));
    }

    const ordernumber = v.ordernumber;
    const novid = v.novid;
    if (novDate && !ADMINISTRATIVE_ORDERNUMBERS.has(ordernumber)) {
      defectVisitDates.add(novDate.toISOString().slice(0, 10));
    }
    if (novDate && novid && !ADMINISTRATIVE_ORDERNUMBERS.has(ordernumber)) {
      if (!signatures.has(ordernumber)) {
        signatures.set(ordernumber, new Map());
        sigDescriptions.set(ordernumber, new Map());
      }
      const novidMap = signatures.get(ordernumber);
      if (!novidMap.has(novid) || novDate < novidMap.get(novid)) {
        novidMap.set(novid, novDate);
        sigDescriptions.get(ordernumber).set(novid, v.novdescription);
      }
      if (v.apartment) {
        if (!sigApartments.has(ordernumber)) sigApartments.set(ordernumber, new Set());
        sigApartments.get(ordernumber).add(v.apartment);
      }
    }
  }

  const recurringSigs = [];
  for (const [ordernumber, novidMap] of signatures.entries()) {
    const dates = [...novidMap.values()];
    if (dates.length >= 2) {
      const spanYears = daysBetween(
        new Date(Math.max(...dates)), new Date(Math.min(...dates))
      ) / 365;
      const breadth = (sigApartments.get(ordernumber) || new Set()).size;
      const coherent = signatureIsCoherent([...sigDescriptions.get(ordernumber).values()]);
      recurringSigs.push([dates.length, spanYears, breadth, coherent, ordernumber]);
    }
  }
  recurringSigs.sort((a, b) => b[0] - a[0]);

  const [topSigNotices, topSigSpan, topSigBreadth, topSigCoherent, topSigOrdernumber] = recurringSigs[0] || [0, 0.0, 0, true, null];
  const nPersistent = recurringSigs.filter(([n, s]) => n >= 3 && s >= 2).length;
  const nChronic = recurringSigs.filter(([n, s]) => n >= 10 && s >= 5).length;
  const certAttempts = acceptedCert + rejectedCert;

  const nDefectVisits = defectVisitDates.size;
  const sortedVisitDates = [...defectVisitDates].sort();
  const defectVisitSpanYears = nDefectVisits >= 2
    ? daysBetween(new Date(sortedVisitDates[sortedVisitDates.length - 1]), new Date(sortedVisitDates[0])) / 365
    : 0.0;

  const p = {
    buildingid,
    address,
    active_count: activeCount,
    real_defect_count: realDefectCount,
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
    top_sig_breadth: topSigBreadth,
    top_sig_coherent: topSigCoherent,
    top_sig_ordernumber: topSigOrdernumber,
    n_persistent_sigs: nPersistent,
    n_chronic_sigs: nChronic,
    n_defect_visits: nDefectVisits,
    defect_visit_span_years: defectVisitSpanYears,
  };
  p.scale = levelScale(p.active_count);
  p.recency = levelRecency(p.recency_ratio);
  p.severity = levelSeverity(p.class_c_rate);
  p.engagement = levelEngagement(p.accepted_cert, p.rejected_cert);
  p.pattern = levelPattern(p.n_persistent_sigs, p.n_chronic_sigs, p.real_defect_count);
  p.backlog_age = levelBacklog(p.max_days_overdue);
  // Independent of pattern (recurrence) - see the matching comment in
  // building_story.py for why this isn't folded into levelPattern().
  p.long_unresolved = (
    p.recency === "Dormant" &&
    p.engagement === "Untested" &&
    (p.backlog_age === "Very aged" || p.backlog_age === "Extreme")
  );
  return p;
}

function generateNarrative(p) {
  const parts = [];

  let opener;
  if (p.recency === "Active surge") {
    if (p.active_count === 1) {
      opener = "The one violation on file was issued in the past year";
    } else {
      let recencyPhrase;
      if (p.recency_ratio >= 0.98) {
        recencyPhrase = "all issued in the past year";
      } else if (p.recency_ratio >= 0.90) {
        recencyPhrase = `nearly all (${p.recent_count} of ${p.active_count}) issued in the past year`;
      } else {
        recencyPhrase = `the large majority (${p.recent_count} of ${p.active_count}) issued in the past year`;
      }
      opener = `A wave of ${p.active_count} violations, ${recencyPhrase}`;
    }
  } else if (p.recency === "Dormant") {
    opener = `${p.active_count} open violation${p.active_count !== 1 ? "s" : ""}, with little to no activity in the past year`;
  } else {
    opener = `${p.active_count} open violations, ${p.recent_count} of them issued in the past year`;
  }
  if (p.class_c_total > 0) {
    opener += `, ${p.class_c_total} of them serious (Class C)`;
  }
  parts.push(opener + ".");

  if (p.pattern === "No real defects") {
    parts.push(
      "None of these are physical defect records — every one is an administrative " +
      "filing requirement (such as registration or bedbug-report compliance), not a " +
      "cited problem with the building itself."
    );
  } else if (p.pattern === "Isolated" && p.real_defect_count < p.active_count) {
    // See the matching comment in building_story.py.
    const adminCount = p.active_count - p.real_defect_count;
    parts.push(
      `${adminCount} of these are administrative filings, and only ` +
      `${p.real_defect_count} real physical defects are on record.`
    );
  }

  // Widespread earns a volume comparison ("more than most buildings ever
  // see") - true by construction since Widespread only fires at/above the
  // calibrated p75 cutoff. That claim would be FALSE for an Isolated
  // building (at or below that same cutoff), so it's never made there -
  // see the matching comment in building_story.py.
  const hasVisitDetail = p.n_defect_visits >= 3 && p.defect_visit_span_years >= 0.5;
  if (p.pattern === "Widespread") {
    if (hasVisitDetail) {
      parts.push(
        "None of these problems have repeated, but different issues have been cited " +
        `across ${p.n_defect_visits} separate inspections over ${p.defect_visit_span_years.toFixed(1)} ` +
        "years, more than most buildings ever see."
      );
    } else {
      parts.push(
        `None of these problems have repeated, but ${p.real_defect_count} separate real ` +
        "defects are on record here, more than most buildings ever see."
      );
    }
  } else if (p.pattern === "Isolated" && hasVisitDetail) {
    parts.push(
      `Different problems have been cited across ${p.n_defect_visits} separate inspections ` +
      `over ${p.defect_visit_span_years.toFixed(1)} years, even though no single defect has recurred.`
    );
  }

  if (p.pattern === "Chronic" || p.pattern === "Persistent") {
    let where;
    if (p.top_sig_breadth >= 2) {
      where = `across ${p.top_sig_breadth} different apartments`;
    } else if (p.top_sig_breadth === 1) {
      where = "in the same apartment";
    } else {
      where = "in the building's common areas";
    }
    const what = p.top_sig_coherent
      ? "The same specific problem"
      : "The same administrative code — covering several different underlying defects —";
    parts.push(`${what} has recurred ${p.top_sig_notices} times over ${p.top_sig_span_years.toFixed(1)} years, ${where}.`);
  }

  if (p.engagement === "Untested") {
    if (p.non_compliance_total > 0) {
      parts.push("No certifications have been accepted or rejected on record, though some violations show non-compliance status.");
    } else {
      parts.push("No certification has ever been attempted for any of these violations.");
    }
  } else if (p.engagement === "Responsive") {
    parts.push(`Every certification attempt on record has been accepted (${p.accepted_cert} of ${p.accepted_cert + p.rejected_cert}).`);
  } else if (p.engagement === "Resistant") {
    parts.push(`Certification attempts have mostly been rejected (${p.rejected_cert} of ${p.accepted_cert + p.rejected_cert} on record).`);
  } else if (p.engagement === "Mixed engagement") {
    parts.push(`Certification attempts have had mixed outcomes (${p.accepted_cert} accepted, ${p.rejected_cert} rejected).`);
  }

  // One sentence regardless of long_unresolved - see the matching comment
  // in building_story.py.
  if (p.backlog_age === "Very aged" || p.backlog_age === "Extreme") {
    parts.push(`The oldest outstanding violation is ${p.max_years_overdue.toFixed(1)} years past its correction deadline.`);
  }

  return parts.join(" ");
}
