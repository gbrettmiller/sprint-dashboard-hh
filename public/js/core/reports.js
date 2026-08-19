// Report document building — pure functions.
//
// Turns dashboard JSON (existing milestone data + the CI-generated report JSON
// from scripts/generate_reports.py) into MS Word-openable documents using the
// lightweight Office-HTML approach. Each build* function returns
// { filename, html }; the UI hands html to downloadDoc() in utils.js.
//
// No DOM, no fetch — fully testable in Node.

import { esc, formatText } from './utils.js';
import { parseSection } from './parsing.js';

const MONTH_FULL = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

// ---------------------------------------------------------------------------
// State predicates (used by the UI to decide when buttons appear)
// ---------------------------------------------------------------------------

// A sprint is "complete" once its end date has passed and it is not the active
// (current) sprint. Scheduled/in-progress sprints return false.
export function isSprintComplete(sprint, currentSprint, todayISO) {
  if (!sprint || !sprint.end_date) return false;
  if (currentSprint && sprint.id === currentSprint.id) return false;
  return sprint.end_date < todayISO;
}

// monthKey is the dashboard month-file key "MM-mon-YYYY" (e.g. "06-jun-2026").
// Returns true when that month is strictly before the current calendar month.
export function isPastMonth(monthKey, today) {
  const parsed = parseMonthKey(monthKey);
  if (!parsed) return false;
  const y = today.getFullYear();
  const m = today.getMonth() + 1;
  return parsed.year < y || (parsed.year === y && parsed.month < m);
}

// Which downloadable documents a completed sprint supports, keyed off its data
// source and the group config. Release Notes and Test Plan need per-issue
// descriptions: milestone-sourced sprints (project-mode groups, e.g. CASS) carry
// them per project and get all three. Jira-sourced sprints (P2DS) get only the
// Sprint Report (goals/summary + metrics). Reports-enabled standard GitLab groups
// (STAR, `reports: true`) collect issue descriptions in the sprint record, so
// they get Release Notes (built client-side from those issues) and the Sprint
// Report, but no Test Plan. All other iteration-sourced sprints get none.
export function availableSprintDocs(sprint, group) {
  const source = sprint && sprint.source;
  if (source === 'milestone') return { releaseNotes: true, testPlan: true, sprintReport: true };
  if (source === 'jira') return { releaseNotes: false, testPlan: false, sprintReport: true };
  if (group && group.reports) return { releaseNotes: true, testPlan: false, sprintReport: true };
  return { releaseNotes: false, testPlan: false, sprintReport: false };
}

// Whether sprint/monthly report JSON is generated for this dashboard context,
// gating the Monthly Report button. True for project-mode projects (CASS),
// Jira-sourced standard groups (P2DS), and reports-enabled standard groups (STAR).
export function reportsEnabledFor(group, project) {
  if (project) return true;
  return !!group && (group.source === 'jira' || !!group.reports);
}

// "06-jun-2026" -> "2026-06" (the report month-file key written by the backend).
export function toReportMonthKey(monthKey) {
  const parsed = parseMonthKey(monthKey);
  if (!parsed) return null;
  return `${parsed.year}-${String(parsed.month).padStart(2, '0')}`;
}

function parseMonthKey(monthKey) {
  if (!monthKey) return null;
  const parts = String(monthKey).split('-');
  if (parts.length !== 3) return null;
  const month = parseInt(parts[0], 10);
  const year = parseInt(parts[2], 10);
  if (!month || !year) return null;
  return { month, year };
}

// ---------------------------------------------------------------------------
// HTML helpers
// ---------------------------------------------------------------------------

// Wrap body markup in the MS-Office HTML namespace header so Word opens it
// cleanly as a document.
export function officeHtml(title, bodyHtml) {
  return [
    '<html xmlns:o="urn:schemas-microsoft-com:office:office" ',
    'xmlns:w="urn:schemas-microsoft-com:office:word" ',
    'xmlns="http://www.w3.org/TR/REC-html40">',
    '<head><meta charset="utf-8"><title>', esc(title), '</title>',
    '<style>',
    'body{font-family:Calibri,Arial,sans-serif;font-size:11pt;}',
    'h1{font-size:18pt;}h2{font-size:14pt;}h3{font-size:12pt;}',
    'table{border-collapse:collapse;}td,th{border:1px solid #999;padding:4px 8px;text-align:left;}',
    '</style></head><body>', bodyHtml, '</body></html>',
  ].join('');
}

function safeFilename(name) {
  return String(name).replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, ' ').trim();
}

function metricsTable(metrics) {
  if (!metrics) return '';
  const rows = [
    ['Initial Issues', metrics.initial_count, metrics.initial_breakdown],
    ['Initial Weight', metrics.initial_weight, ''],
    ['Completed Issues', metrics.completed_count, metrics.completed_breakdown],
    ['Completed Weight', metrics.completed_weight, ''],
  ];
  const body = rows.map(([label, value, detail]) =>
    `<tr><th>${esc(label)}</th><td>${esc(String(value ?? 0))}</td>` +
    `<td>${detail ? esc(detail) : ''}</td></tr>`
  ).join('');
  return `<table>${body}</table>`;
}

// ISO "YYYY-MM-DD" -> "May 4, 2026" (falls back to the raw value).
function fmtDate(iso) {
  if (!iso) return 'TBD';
  const parts = iso.split('-');
  if (parts.length !== 3) return iso;
  const [y, m, d] = parts.map(p => parseInt(p, 10));
  if (!y || !m || !d) return iso;
  return `${MONTH_FULL[m - 1]} ${d}, ${y}`;
}

// First meaningful line of an issue description, for a one-line release-notes blurb.
function summarize(description) {
  if (!description) return '';
  const desc = parseSection(description, 'Description');
  const source = desc || description;
  const skip = /^(#{1,6}\s|[-*]\s*$|(as an?|i want|so that|scenario|user story|acceptance criteria|description|background|overview|problem)\b)/i;
  for (const line of source.split('\n')) {
    const t = line.trim();
    if (t && !skip.test(t)) return t.replace(/^[-*]\s+/, '');
  }
  return '';
}

const RELEASE_NOTES_EXCLUDE_LABEL = 'release-notes::no';

// ---------------------------------------------------------------------------
// Document builders
// ---------------------------------------------------------------------------

// Release notes — built client-side from the existing milestone JSON.
export function buildReleaseNotesDoc(milestoneData) {
  const project = milestoneData.project_name || '';
  const title = milestoneData.milestone_title || '';
  const heading = `${project} ${title} Release Notes`.trim();

  const delivered = (milestoneData.issues || [])
    .filter(i => i.state === 'closed' && !(i.labels || []).includes(RELEASE_NOTES_EXCLUDE_LABEL))
    .sort((a, b) => a.iid - b.iid);

  let body = `<h1>${esc(heading)}</h1>`;
  if (!delivered.length) {
    body += '<p>No completed issues for this sprint.</p>';
  } else {
    delivered.forEach(issue => {
      body += `<h2>#${esc(String(issue.iid))} ${esc(issue.title)}</h2>`;
      const summary = summarize(issue.description);
      body += `<p>${summary ? esc(summary) : 'No description provided.'}</p>`;
    });
  }

  return { filename: safeFilename(`${heading}.doc`), html: officeHtml(heading, body) };
}

// Release notes for a standard group (e.g. STAR) built from the loaded sprint
// record itself — these groups have no per-project milestone JSON, but their
// sprint issues carry descriptions. A standard-group sprint spans several
// projects, so delivered issues are grouped under a per-project heading.
// subjectName is the group name used in the document title.
export function buildReleaseNotesFromSprint(sprint, subjectName) {
  const title = (sprint && sprint.title) || '';
  const heading = `${subjectName || ''} ${title} Release Notes`.trim();

  const delivered = ((sprint && sprint.issues) || [])
    .filter(i => i.state === 'closed' && !(i.labels || []).includes(RELEASE_NOTES_EXCLUDE_LABEL));

  let body = `<h1>${esc(heading)}</h1>`;
  if (!delivered.length) {
    body += '<p>No completed issues for this sprint.</p>';
    return { filename: safeFilename(`${heading}.doc`), html: officeHtml(heading, body) };
  }

  // Group by project, projects alphabetical, issues by iid within each.
  const byProject = new Map();
  delivered.forEach(issue => {
    const project = issue.project_name || 'Other';
    if (!byProject.has(project)) byProject.set(project, []);
    byProject.get(project).push(issue);
  });

  [...byProject.keys()].sort((a, b) => a.localeCompare(b)).forEach(project => {
    body += `<h2>${esc(project)}</h2>`;
    byProject.get(project).sort((a, b) => a.iid - b.iid).forEach(issue => {
      body += `<h3>#${esc(String(issue.iid))} ${esc(issue.title)}</h3>`;
      const summary = summarize(issue.description);
      body += `<p>${summary ? esc(summary) : 'No description provided.'}</p>`;
    });
  });

  return { filename: safeFilename(`${heading}.doc`), html: officeHtml(heading, body) };
}

// Test plan — uses the CI-generated test_plan steps; names from milestone data.
export function buildTestPlanDoc(reportJson, milestoneData) {
  const project = (milestoneData && milestoneData.project_name) || '';
  const title = (milestoneData && milestoneData.milestone_title) || (reportJson && reportJson.title) || '';
  const heading = `${project} ${title} Test Plan`.trim();

  const entries = (reportJson && reportJson.test_plan) || [];

  let body = `<h1>${esc(heading)}</h1>`;
  if (!entries.length) {
    body += '<p>No test-eligible issues in this sprint.</p>';
  } else {
    entries.forEach(entry => {
      body += `<h2>#${esc(String(entry.iid))} ${esc(entry.title)}</h2>`;
      // steps arrive as a markdown bullet list; formatText renders <ul><li>.
      body += formatText(entry.steps || '');
    });
  }

  return { filename: safeFilename(`${heading}.doc`), html: officeHtml(heading, body) };
}

// Sprint report — leadership briefing for a single completed sprint.
export function buildSprintReportDoc(reportJson, projectName) {
  const title = (reportJson && reportJson.title) || '';
  const heading = `${projectName || ''} ${title} Sprint Report`.trim();
  const sr = (reportJson && reportJson.sprint_report) || {};

  let body = `<h1>${esc(heading)}</h1>`;
  body += `<p><strong>Sprint:</strong> ${esc(fmtDate(reportJson && reportJson.start_date))} ` +
          `&ndash; ${esc(fmtDate(reportJson && reportJson.end_date))}</p>`;
  body += sprintReportSections(sr);

  return { filename: safeFilename(`${heading}.doc`), html: officeHtml(heading, body) };
}

// Monthly report — rollup of every sprint that overlapped a past month.
export function buildMonthlyReportDoc(reportJson, projectName) {
  const monthLabel = monthKeyLabel(reportJson && reportJson.month);
  const heading = `${projectName || ''} Monthly Report ${monthLabel}`.trim();
  const sprints = (reportJson && reportJson.sprints) || [];

  let body = `<h1>${esc(heading)}</h1>`;
  if (!sprints.length) {
    body += '<p>No completed sprints in this month.</p>';
  } else {
    sprints.forEach(block => {
      body += `<h2>${esc(block.title || '')} ` +
              `(${esc(fmtDate(block.start_date))} &ndash; ${esc(fmtDate(block.end_date))})</h2>`;
      body += sprintReportSections({
        goals: block.goals,
        summary: block.summary,
        metrics: block.metrics,
      }, 'h3');
    });
  }

  return { filename: safeFilename(`${heading}.doc`), html: officeHtml(heading, body) };
}

function sprintReportSections(sr, headingTag = 'h2') {
  let out = '';
  if (sr.goals) out += `<${headingTag}>Goals</${headingTag}>${formatText(sr.goals)}`;
  if (sr.summary) out += `<${headingTag}>Summary</${headingTag}>${formatText(sr.summary)}`;
  if (sr.metrics) out += `<${headingTag}>Metrics</${headingTag}>${metricsTable(sr.metrics)}`;
  return out;
}

// "2026-05" -> "May 2026"
function monthKeyLabel(reportMonth) {
  if (!reportMonth) return '';
  const parts = String(reportMonth).split('-');
  if (parts.length !== 2) return reportMonth;
  const y = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  if (!y || !m) return reportMonth;
  return `${MONTH_FULL[m - 1]} ${y}`;
}
