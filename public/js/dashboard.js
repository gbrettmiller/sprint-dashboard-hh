import { $, esc, formatLastUpdated, slugify, downloadDoc } from './core/utils.js';
import { dashboardShellHTML } from './core/dashboardShell.js';
import { isWorkingDay, generateDateRange } from './core/holidays.js';
import { getFilteredIssues, getUniqueProjects, calculateFilteredBurndown, calculateTypeBreakdown, getRecentCompletedSprints, computeSprintTotals, computeSprintTimeMetrics, computeIdealBurndown, computeVelocitySeries, monthKeyToCutoff, buildSprintTabModel } from './core/calculations.js';
import { isSprintComplete, isPastMonth, toReportMonthKey, availableSprintDocs, reportsEnabledFor, buildReleaseNotesDoc, buildReleaseNotesFromSprint, buildTestPlanDoc, buildSprintReportDoc, buildMonthlyReportDoc } from './core/reports.js';
import { loadFY, loadCurrentSprint as loadCurrentSprintAPI, discoverFYs, fyMonths, monthFileKey, MONTH_LABELS, loadSprintReport, loadMonthlyReport, loadMilestone } from './services/api.js';

// -----------------------------------------------------------------------
// Chart colors — resolved from CSS tokens at module load.
// Chart.js cannot consume CSS variables directly; read them once here.
// -----------------------------------------------------------------------
const _rootStyle = getComputedStyle(document.documentElement);
const _cssVar = name => _rootStyle.getPropertyValue(name).trim();
const CHART_COLORS = {
  purple:        _cssVar('--purple'),
  grayLight:     _cssVar('--gray-light'),
  purpleFaint:   _cssVar('--purple-faint'),
  purpleOverlay: _cssVar('--purple-overlay'),
  red:           _cssVar('--red'),
  blue:          _cssVar('--blue'),
  green:         _cssVar('--green'),
  gray:          _cssVar('--gray'),
  white:         _cssVar('--white'),
};

// -----------------------------------------------------------------------
// State
// -----------------------------------------------------------------------
let activeGroup = null;
let activeProject = null;
let allData = {};
let currentSprint = null;
let selectedSprint = null;
let burndownChart = null;
let typeChart = null;
let velocityChart = null;
let burndownMode = 'count';
let typeMode = 'initial';
let tableSortCol = 'iid';
let tableSortAsc = true;
let projectFilter = null;
// Monotonic token — bumped on each renderDashboard() so a slow in-flight load
// from a previous selection can detect it was superseded and bail out.
let requestToken = 0;

// -----------------------------------------------------------------------
// Project filtering (UI)
// -----------------------------------------------------------------------
function renderProjectChips() {
  const container = $('project-chips');
  if (activeProject) {
    $('project-filter').style.display = 'none';
    return;
  }
  if (!selectedSprint) {
    container.innerHTML = '';
    return;
  }

  const projects = getUniqueProjects(selectedSprint);
  container.innerHTML = '';

  const allChip = document.createElement('button');
  allChip.className = 'project-chip' + (!projectFilter ? ' active' : '');
  allChip.textContent = 'All';
  allChip.setAttribute('aria-pressed', !projectFilter ? 'true' : 'false');
  allChip.addEventListener('click', () => {
    projectFilter = null;
    updateProjectChipStates();
    refreshFilteredViews();
  });
  container.appendChild(allChip);

  projects.forEach(project => {
    const chip = document.createElement('button');
    chip.className = 'project-chip' + (projectFilter === project ? ' active' : '');
    chip.textContent = project;
    chip.title = project;
    chip.setAttribute('aria-pressed', projectFilter === project ? 'true' : 'false');
    chip.addEventListener('click', () => {
      projectFilter = project;
      updateProjectChipStates();
      refreshFilteredViews();
    });
    container.appendChild(chip);
  });
}

function updateProjectChipStates() {
  const chips = $('project-chips').querySelectorAll('.project-chip');
  chips.forEach((chip, i) => {
    const isAll = i === 0;
    const isActive = isAll ? !projectFilter : chip.textContent === projectFilter;
    chip.classList.toggle('active', isActive);
    chip.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });
}

function refreshFilteredViews() {
  updateStats();
  renderSprintSummary();
  renderBurndown();
  renderTypeChart();
  renderIssuesTable();
  renderVelocity();
}

// -----------------------------------------------------------------------
// Stat cards
// -----------------------------------------------------------------------
function updateStats() {
  if (!selectedSprint) return;

  const { initialCount, initialWeight, completedCount, completedWeight } =
    computeSprintTotals(selectedSprint, projectFilter);

  $('stat-init-count').textContent = initialCount;
  $('stat-init-weight').textContent = initialWeight;
  $('stat-done-count').textContent = completedCount;
  $('stat-done-weight').textContent = completedWeight;
}

// -----------------------------------------------------------------------
// Sprint progress summary
// -----------------------------------------------------------------------
function renderSprintSummary() {
  const s = selectedSprint;
  const container = $('sprint-summary');
  if (!s) { container.style.display = 'none'; return; }
  container.style.display = '';

  const goalEl = $('sprint-goal');
  goalEl.textContent = s.goal ? `Goal: ${s.goal}` : '';
  goalEl.hidden = !s.goal;

  const { initialCount, initialWeight, completedCount, completedWeight, totalCount, totalWeight } =
    computeSprintTotals(s, projectFilter);

  const isWeight = burndownMode === 'weight';
  const completed = isWeight ? completedWeight : completedCount;
  const initial = isWeight ? initialWeight : initialCount;
  const total = isWeight ? totalWeight : totalCount;
  const open = total - completed;

  $('summary-mode').textContent = isWeight ? 'Story Points' : 'Issue Count';

  const today = new Date().toISOString().slice(0, 10);
  const { timeRemainingText, timeElapsedPct } = computeSprintTimeMetrics(s, today);
  $('summary-time-remaining').textContent = timeRemainingText;
  $('metric-time-elapsed').textContent = timeElapsedPct === null ? 'N/A' : timeElapsedPct + '%';

  const progressBar = container.querySelector('.progress-bar');
  const completedSeg = $('progress-completed');
  const openSeg = $('progress-open');

  if (total > 0) {
    const completedPct = (completed / total) * 100;
    const openPct = (open / total) * 100;
    completedSeg.style.width = completedPct + '%';
    openSeg.style.width = openPct + '%';

    const barWidth = progressBar.offsetWidth;
    $('progress-completed-label').textContent = completed;
    $('progress-completed-label').style.display = barWidth * completedPct / 100 >= 40 ? '' : 'none';
    $('progress-open-label').textContent = open;
    $('progress-open-label').style.display = barWidth * openPct / 100 >= 40 ? '' : 'none';

    progressBar.setAttribute('aria-valuenow', Math.round(completedPct));
    progressBar.setAttribute('aria-valuetext', `${completed} of ${total} ${isWeight ? 'story points' : 'issues'} completed`);
  } else {
    completedSeg.style.width = '0%';
    openSeg.style.width = '0%';
    $('progress-completed-label').style.display = 'none';
    $('progress-open-label').style.display = 'none';
    progressBar.setAttribute('aria-valuenow', '0');
    progressBar.setAttribute('aria-valuetext', 'No data');
  }

  if (initial > 0) {
    const workPct = Math.round((completed / initial) * 100);
    $('metric-work-complete').textContent = workPct + '%';
  } else {
    $('metric-work-complete').textContent = 'N/A';
  }

  const scopeEl = $('metric-scope-change');
  if (initial > 0) {
    const scopeChange = ((total - initial) / initial) * 100;
    const sign = scopeChange > 0 ? '+' : '';
    scopeEl.textContent = sign + Math.round(scopeChange) + '%';
    scopeEl.classList.toggle('warning', Math.abs(scopeChange) > 10);
  } else {
    scopeEl.textContent = 'N/A';
    scopeEl.classList.remove('warning');
  }
}

// -----------------------------------------------------------------------
// UI: populate dropdowns
// -----------------------------------------------------------------------
function populateFYDropdown(fys) {
  const sel = $('fy-select');
  sel.innerHTML = '';
  fys.forEach(fy => {
    const opt = document.createElement('option');
    opt.value = fy;
    opt.textContent = `FY${fy} (Oct ${fy-1} \u2013 Sep ${fy})`;
    sel.appendChild(opt);
  });
}

function populateMonthDropdown(fy) {
  const sel = $('month-select');
  sel.innerHTML = '';
  const data = allData[`fy${fy}`] || {};
  const months = fyMonths(fy);
  months.forEach(({month, year}) => {
    const key = monthFileKey(month, year);
    if (data[key]) {
      const opt = document.createElement('option');
      opt.value = key;
      opt.textContent = `${MONTH_LABELS[month-1]} ${year}`;
      sel.appendChild(opt);
    }
  });
  const now = new Date();
  const currentKey = monthFileKey(now.getMonth() + 1, now.getFullYear());
  if (data[currentKey]) {
    sel.value = currentKey;
  } else if (sel.options.length) {
    sel.selectedIndex = sel.options.length - 1;
  }
}

// -----------------------------------------------------------------------
// Sprint tabs
// -----------------------------------------------------------------------
function renderSprintTabs(monthKey, fy) {
  const container = $('sprint-tabs');
  container.innerHTML = '';
  const data = allData[`fy${fy}`] || {};
  const monthData = data[monthKey];
  if (!monthData) { container.innerHTML = '<div class="empty-msg">No sprints for this month.</div>'; return; }

  const now = new Date();
  const curKey = monthFileKey(now.getMonth() + 1, now.getFullYear());
  const { sprints, activeIndex } = buildSprintTabModel(monthData.sprints, currentSprint, monthKey === curKey);

  sprints.forEach((s, i) => {
    const btn = document.createElement('button');
    const isActive = i === activeIndex;
    const isCurrent = s._isCurrent || (currentSprint && s.id === currentSprint.id);
    btn.className = 'sprint-tab' + (isActive ? ' active' : '');
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    btn.setAttribute('tabindex', isActive ? '0' : '-1');

    const displayTitle = s.title || `${s.start_date} \u2192 ${s.end_date}`;
    let tabContent = `${isCurrent ? '\u25CF ' : ''}${displayTitle}<span class="dates">${s.start_date} \u2192 ${s.end_date}</span>`;

    if (isCurrent && currentSprint?.last_updated) {
      const formatted = formatLastUpdated(currentSprint.last_updated);
      tabContent += `<span class="last-updated">Updated: ${formatted}</span>`;
    }

    btn.innerHTML = tabContent;
    btn.addEventListener('click', () => {
      container.querySelectorAll('.sprint-tab').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
        b.setAttribute('tabindex', '-1');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
      btn.setAttribute('tabindex', '0');
      selectSprint(s);
    });
    container.appendChild(btn);
  });

  if (sprints.length) selectSprint(sprints[activeIndex]);
}

// -----------------------------------------------------------------------
// Select sprint – update all panels
// -----------------------------------------------------------------------
function selectSprint(sprint) {
  selectedSprint = sprint;
  projectFilter = null;

  renderProjectChips();
  updateStats();
  renderSprintSummary();
  renderBurndown();
  renderTypeChart();
  renderIssuesTable();
  updateSprintReports();
}

// -----------------------------------------------------------------------
// Sprint document generation (completed sprints, project-mode only)
// -----------------------------------------------------------------------
function setReportStatus(msg) {
  const el = $('report-status');
  if (el) el.textContent = msg || '';
}

// Name used in generated document headings: the project for project-mode
// dashboards, otherwise the group (standard-mode groups like Data Services have no
// active project).
function reportSubjectName() {
  return activeProject ? activeProject.name : (activeGroup ? activeGroup.name : '');
}

// Show the Generate toolbar for a completed sprint, toggling each button by the
// document types its data source + group supports (see availableSprintDocs):
// milestone-sourced sprints (Cloud Services) get all three; Jira-sourced sprints (Data Services) get
// only the Sprint Report; reports-enabled standard groups (Service Management) get Release Notes
// + Sprint Report; other iteration-sourced sprints get none.
function updateSprintReports() {
  const bar = $('sprint-reports');
  if (!bar) return;
  const todayISO = new Date().toISOString().slice(0, 10);
  const complete = !!selectedSprint && isSprintComplete(selectedSprint, currentSprint, todayISO);
  const caps = complete
    ? availableSprintDocs(selectedSprint, activeGroup)
    : { releaseNotes: false, testPlan: false, sprintReport: false };

  const rn = $('btn-release-notes');
  const tp = $('btn-test-plan');
  const sr = $('btn-sprint-report');
  if (rn) rn.style.display = caps.releaseNotes ? '' : 'none';
  if (tp) tp.style.display = caps.testPlan ? '' : 'none';
  if (sr) sr.style.display = caps.sprintReport ? '' : 'none';

  const show = caps.releaseNotes || caps.testPlan || caps.sprintReport;
  bar.style.display = show ? '' : 'none';
  setReportStatus('');
}

// Fetch a JSON source, build the doc, and trigger the download — with shared
// loading/empty/error handling. setStatus targets the relevant status span.
async function generateDoc(label, setStatus, fetchAndBuild) {
  setStatus(`Preparing ${label}…`);
  try {
    const doc = await fetchAndBuild();
    if (!doc) return; // fetchAndBuild already set an explanatory status
    downloadDoc(doc.filename, doc.html);
    setStatus('');
  } catch (err) {
    console.error(err);
    setStatus(`Could not generate ${label}. Please try again.`);
  }
}

function wireSprintReportButtons() {
  const rn = $('btn-release-notes');
  const tp = $('btn-test-plan');
  const sr = $('btn-sprint-report');
  if (!rn || !tp || !sr) return;

  rn.addEventListener('click', () => generateDoc('release notes', setReportStatus, async () => {
    // Project-mode groups (Cloud Services) build from per-project milestone JSON; standard
    // reports-enabled groups (Service Management) have no milestone JSON, so build from the
    // already-loaded sprint record's issues (which carry descriptions).
    if (!activeProject) {
      return buildReleaseNotesFromSprint(selectedSprint, reportSubjectName());
    }
    const slug = slugify(selectedSprint.title);
    const milestone = await loadMilestone(activeGroup, activeProject, slug);
    if (!milestone) {
      setReportStatus('Milestone data not found for this sprint.');
      return null;
    }
    return buildReleaseNotesDoc(milestone);
  }));

  tp.addEventListener('click', () => generateDoc('test plan', setReportStatus, async () => {
    const slug = slugify(selectedSprint.title);
    const [report, milestone] = await Promise.all([
      loadSprintReport(activeGroup, activeProject, slug),
      loadMilestone(activeGroup, activeProject, slug),
    ]);
    if (!report) {
      setReportStatus('Test plan not generated yet — check back after the next scheduled run.');
      return null;
    }
    return buildTestPlanDoc(report, milestone);
  }));

  sr.addEventListener('click', () => generateDoc('sprint report', setReportStatus, async () => {
    const slug = slugify(selectedSprint.title);
    const report = await loadSprintReport(activeGroup, activeProject, slug);
    if (!report) {
      setReportStatus('Sprint report not generated yet — check back after the next scheduled run.');
      return null;
    }
    return buildSprintReportDoc(report, reportSubjectName());
  }));
}

// -----------------------------------------------------------------------
// Monthly report (project dashboards, past months only)
// -----------------------------------------------------------------------
function setMonthlyStatus(msg) {
  const el = $('monthly-report-status');
  if (el) el.textContent = msg || '';
}

// Show the Monthly Report button only where monthly report JSON is generated
// (project-mode projects and Jira-sourced groups; see reportsEnabledFor) and for
// a month strictly before the current calendar month.
function updateMonthlyReportButton(monthKey) {
  const btn = $('btn-monthly-report');
  if (!btn) return;
  const show = reportsEnabledFor(activeGroup, activeProject) && !!monthKey && isPastMonth(monthKey, new Date());
  btn.style.display = show ? '' : 'none';
  setMonthlyStatus('');
}

function wireMonthlyReportButton() {
  const btn = $('btn-monthly-report');
  if (!btn) return;
  btn.addEventListener('click', () => generateDoc('monthly report', setMonthlyStatus, async () => {
    const reportKey = toReportMonthKey($('month-select').value);
    const report = await loadMonthlyReport(activeGroup, activeProject, reportKey);
    if (!report) {
      setMonthlyStatus('Monthly report not generated yet — check back after the next scheduled run.');
      return null;
    }
    return buildMonthlyReportDoc(report, reportSubjectName());
  }));
}

// -----------------------------------------------------------------------
// Burndown chart
// -----------------------------------------------------------------------
const nonWorkingDayPlugin = {
  id: 'nonWorkingDayShading',

  afterDatasetsDraw(chart) {
    const { ctx, chartArea: { left, right, top, bottom }, scales: { x } } = chart;

    const fullDates = chart.config.options.plugins.nonWorkingDayShading?.fullDates;
    if (!fullDates) return;

    ctx.fillStyle = CHART_COLORS.purpleOverlay;
    ctx.save();

    const numDates = fullDates.length;
    const totalWidth = right - left;
    const dayWidth = totalWidth / (numDates - 1);

    fullDates.forEach((date, index) => {
      if (!isWorkingDay(date)) {
        const xPos = x.getPixelForValue(index);
        const shadingWidth = dayWidth;

        ctx.fillRect(
          xPos - shadingWidth / 2,
          top,
          shadingWidth,
          bottom - top
        );
      }
    });

    ctx.restore();
  }
};

function renderBurndown() {
  const s = selectedSprint;
  if (!s) return;

  const allDates = generateDateRange(s.start_date, s.end_date);
  const labels = allDates.map(d => d.slice(5));

  const burndownMap = {};
  s.burndown.forEach(b => {
    burndownMap[b.date] = b;
  });

  let actual, start;

  if (projectFilter) {
    const issues = getFilteredIssues(s, projectFilter);
    const datesWithData = s.burndown.map(b => b.date);
    const burndownData = calculateFilteredBurndown(issues, datesWithData, s.start_date);
    const filteredMap = {};
    datesWithData.forEach((d, i) => {
      filteredMap[d] = burndownData[i];
    });

    actual = allDates.map(date => {
      const data = filteredMap[date];
      if (!data) return null;
      return burndownMode === 'count' ? data.count : data.weight;
    });
    start = actual.find(v => v !== null) ?? 0;
  } else {
    const field = burndownMode === 'count' ? 'remaining_count' : 'remaining_weight';
    actual = allDates.map(date => {
      const data = burndownMap[date];
      return data ? data[field] : null;
    });
    start = burndownMode === 'count' ? s.initial_totals.count : s.initial_totals.weight;
  }

  const ideal = computeIdealBurndown(allDates, start);

  if (burndownChart) burndownChart.destroy();
  burndownChart = new Chart($('burndown-chart'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Actual', data: actual, borderColor: CHART_COLORS.purple, fill: false, tension: .2, pointRadius: 3, spanGaps: false },
        { label: 'Ideal', data: ideal, borderColor: CHART_COLORS.grayLight, borderDash: [6,4], pointRadius: 0, fill: false },
        { label: 'Non-working day', data: [], backgroundColor: CHART_COLORS.purpleFaint, borderColor: CHART_COLORS.purpleFaint, borderWidth: 10, pointRadius: 0, fill: true }
      ]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'bottom' },
        nonWorkingDayShading: {
          fullDates: allDates
        }
      },
      scales: { y: { beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: burndownMode === 'count' ? 'Issues' : 'Weight' } } }
    },
    plugins: [nonWorkingDayPlugin]
  });
}

// -----------------------------------------------------------------------
// Type breakdown chart
// -----------------------------------------------------------------------
// Color palette for type breakdown chart — known types get fixed colors,
// dynamic types cycle through the extras. Uncategorized is always gray.
const TYPE_COLORS = {
  'Bug':         CHART_COLORS.red,
  'Improvement': CHART_COLORS.blue,
  'New Feature': CHART_COLORS.green,
  'Task':        CHART_COLORS.gray,
};

function typeColor(label) {
  return TYPE_COLORS[label] || CHART_COLORS.gray;
}

const doughnutLabelsPlugin = {
  id: 'doughnutLabels',
  afterDraw(chart) {
    const { ctx } = chart;
    const meta = chart.getDatasetMeta(0);
    if (!meta || !meta.data.length) return;
    const total = meta.data.reduce((sum, arc) => sum + (chart.data.datasets[0].data[arc.$context.index] || 0), 0);
    if (total === 0) return;

    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    meta.data.forEach((arc, i) => {
      const value = chart.data.datasets[0].data[i];
      if (!value) return;

      const pct = Math.round((value / total) * 100);
      const { startAngle, endAngle, innerRadius, outerRadius } = arc.getProps(['startAngle', 'endAngle', 'innerRadius', 'outerRadius']);
      const midAngle = (startAngle + endAngle) / 2;
      const midRadius = (innerRadius + outerRadius) / 2;
      const x = arc.x + Math.cos(midAngle) * midRadius;
      const y = arc.y + Math.sin(midAngle) * midRadius;

      // Only render label if the slice is large enough
      const angleDeg = ((endAngle - startAngle) * 180) / Math.PI;
      if (angleDeg < 20) return;

      ctx.fillStyle = CHART_COLORS.white;
      ctx.font = 'bold 12px sans-serif';
      ctx.fillText(`${value}`, x, y - 7);
      ctx.font = '11px sans-serif';
      ctx.fillText(`${pct}%`, x, y + 7);
    });

    ctx.restore();
  }
};

function renderTypeChart() {
  const s = selectedSprint;
  if (!s) return;

  let issues = getFilteredIssues(s, projectFilter);
  if (typeMode === 'initial') {
    const sprintStart = s.start_date;
    issues = issues.filter(i => {
      const added = i.date_added_to_sprint;
      return !added || added <= sprintStart;
    });
  } else {
    issues = issues.filter(i => i.state === 'closed');
  }

  const t = calculateTypeBreakdown(issues);

  const canvas = $('type-chart');
  const emptyMsg = $('type-empty');

  const total = t.counts.reduce((a, b) => a + b, 0);

  if (total === 0) {
    canvas.style.display = 'none';
    emptyMsg.style.display = '';
    if (typeChart) { typeChart.destroy(); typeChart = null; }
    return;
  }

  canvas.style.display = '';
  emptyMsg.style.display = 'none';

  if (typeChart) typeChart.destroy();
  typeChart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: t.labels,
      datasets: [{
        data: t.counts,
        backgroundColor: t.labels.map(l => typeColor(l)),
      }]
    },
    options: { responsive: true, plugins: { legend: { position: 'bottom' } } },
    plugins: [doughnutLabelsPlugin]
  });
}

// -----------------------------------------------------------------------
// Issues table
// -----------------------------------------------------------------------
function renderIssuesTable() {
  const s = selectedSprint;
  if (!s) return;
  const tbody = document.querySelector('#issues-table tbody');
  const issues = [...getFilteredIssues(s, projectFilter)];

  issues.sort((a, b) => {
    let va = a[tableSortCol], vb = b[tableSortCol];
    if (va == null) va = '';
    if (vb == null) vb = '';
    if (typeof va === 'number') return tableSortAsc ? va - vb : vb - va;
    return tableSortAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
  });

  tbody.innerHTML = issues.map(i => `<tr>
    <td>${i.iid}</td>
    <td><a href="${esc(i.web_url)}" target="_blank" rel="noopener">${esc(i.title)}</a></td>
    <td>${esc(i.project_name)}</td>
    <td>${i.weight}</td>
    <td><span class="state-badge state-${i.state}">${i.state}</span></td>
    <td>${i.date_added_to_sprint || '\u2014'}</td>
    <td>${i.date_closed || '\u2014'}</td>
    <td>${i.date_removed_from_sprint || '\u2014'}</td>
  </tr>`).join('');

  document.querySelectorAll('#issues-table th').forEach(th => {
    const isSorted = th.dataset.col === tableSortCol;
    th.classList.toggle('sorted', isSorted);
    th.setAttribute('aria-sort', isSorted ? (tableSortAsc ? 'ascending' : 'descending') : 'none');
    const arrow = th.querySelector('.sort-arrow');
    if (isSorted) {
      arrow.textContent = tableSortAsc ? '\u25B2' : '\u25BC';
    } else {
      arrow.textContent = '\u25B2';
    }
  });
}

// -----------------------------------------------------------------------
// Velocity chart
// -----------------------------------------------------------------------
function renderVelocity() {
  const monthKey = $('month-select').value;
  const cutoffDate = monthKeyToCutoff(monthKey);
  const sprints = getRecentCompletedSprints(allData, 6, cutoffDate);
  const canvas = $('velocity-chart');
  const emptyMsg = $('velocity-empty');

  if (sprints.length < 3) {
    canvas.style.display = 'none';
    emptyMsg.style.display = '';
    if (velocityChart) {
      velocityChart.destroy();
      velocityChart = null;
    }
    return;
  }

  canvas.style.display = '';
  emptyMsg.style.display = 'none';

  const labels = sprints.map(s => [s.title || `${s.start_date} \u2192 ${s.end_date}`, `(${s.start_date} \u2192 ${s.end_date})`]);
  const { committed, completed, avgVelocity } = computeVelocitySeries(sprints, projectFilter);
  const avgLine = sprints.map(() => avgVelocity);

  if (velocityChart) velocityChart.destroy();
  velocityChart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Committed',
          data: committed,
          backgroundColor: CHART_COLORS.purple,
          borderRadius: 4,
        },
        {
          label: 'Completed',
          data: completed,
          backgroundColor: CHART_COLORS.green,
          borderRadius: 4,
        },
        {
          label: `Avg Velocity (${avgVelocity.toFixed(1)})`,
          data: avgLine,
          type: 'line',
          borderColor: CHART_COLORS.red,
          borderWidth: 2,
          borderDash: [6, 4],
          pointRadius: 0,
          fill: false,
        }
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'bottom' } },
      scales: { y: { beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: 'Weight' } } }
    }
  });
}

function onMonthChange() {
  const fy = +$('fy-select').value;
  const monthKey = $('month-select').value;
  updateMonthlyReportButton(monthKey);
  if (!monthKey) return;
  renderSprintTabs(monthKey, fy);
  renderVelocity();
}

// -----------------------------------------------------------------------
// Event listeners — wired once by mountDashboard() after the shell is in the
// DOM. Every handler reads module state at event time, so one-time wiring is
// both correct and required (wiring per render would stack duplicate handlers).
// -----------------------------------------------------------------------
function wireDashboardEvents() {
  document.querySelectorAll('.toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const group = btn.parentElement;
      group.querySelectorAll('.toggle-btn').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-pressed', 'false');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-pressed', 'true');
      if (btn.dataset.chart === 'burndown') {
        burndownMode = btn.dataset.mode;
        renderSprintSummary();
        renderBurndown();
      } else if (btn.dataset.chart === 'type') {
        typeMode = btn.dataset.mode;
        renderTypeChart();
      }
    });
  });

  document.querySelectorAll('#issues-table th button').forEach(btn => {
    btn.addEventListener('click', () => {
      const th = btn.closest('th');
      const col = th.dataset.col;
      if (tableSortCol === col) { tableSortAsc = !tableSortAsc; }
      else { tableSortCol = col; tableSortAsc = true; }
      renderIssuesTable();
    });
  });

  $('issues-toggle').addEventListener('click', () => {
    const btn = $('issues-toggle');
    const container = $('issues-table-container');
    const isExpanded = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', !isExpanded);
    container.classList.toggle('collapsed', isExpanded);
    btn.querySelector('.toggle-text').textContent = isExpanded ? 'Show' : 'Hide';
  });

  $('fy-select').addEventListener('change', async () => {
    const token = requestToken;
    const fy = +$('fy-select').value;
    await loadFY(fy, allData, activeGroup, activeProject);
    if (token !== requestToken) return; // superseded by a project/group switch
    populateMonthDropdown(fy);
    onMonthChange();
  });

  $('month-select').addEventListener('change', onMonthChange);

  let resizeTimeout;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
      if (burndownChart) burndownChart.resize();
      if (typeChart) typeChart.resize();
      if (velocityChart) velocityChart.resize();
    }, 100);
  });

  wireSprintReportButtons();
  wireMonthlyReportButton();
}

// Reset the persistent shell DOM to its default state before a re-render.
function resetDashboardDom() {
  // Chart toggles back to defaults (burndown=Count, type=Initial).
  document.querySelectorAll('.toggle-btn').forEach(btn => {
    const isDefault = btn.dataset.mode === 'count' || btn.dataset.mode === 'initial';
    btn.classList.toggle('active', isDefault);
    btn.setAttribute('aria-pressed', isDefault ? 'true' : 'false');
  });
  // Issues table collapsed.
  $('issues-table-container').classList.add('collapsed');
  const issuesToggle = $('issues-toggle');
  issuesToggle.setAttribute('aria-expanded', 'false');
  issuesToggle.querySelector('.toggle-text').textContent = 'Show';
  // Clear per-sprint content (defends the no-data path; render fns overwrite).
  $('sprint-tabs').innerHTML = '';
  document.querySelector('#issues-table tbody').innerHTML = '';
}

// -----------------------------------------------------------------------
// Public API — used by the page modules (js/group.js, js/home.js)
// -----------------------------------------------------------------------

// Inject the dashboard shell into a mount element and wire its events once.
// Call this a single time per page, before the first renderDashboard().
export function mountDashboard(mountEl) {
  mountEl.innerHTML = dashboardShellHTML();
  wireDashboardEvents();
}

// (Re)render the dashboard for a resolved group/project. Safe to call
// repeatedly — it fully resets state, so callers can switch selections at will.
// `activeProject` is null for standard-mode (group-level) groups.
export async function renderDashboard(group, project) {
  const token = ++requestToken;

  // --- Reset state synchronously (before any await) ---
  activeGroup = group;
  activeProject = project;
  allData = {};                 // FY cache is not group/project-scoped — must clear
  currentSprint = null;
  selectedSprint = null;
  projectFilter = null;
  burndownMode = 'count';
  typeMode = 'initial';
  tableSortCol = 'iid';
  tableSortAsc = true;
  if (burndownChart) { burndownChart.destroy(); burndownChart = null; }
  if (typeChart) { typeChart.destroy(); typeChart = null; }
  if (velocityChart) { velocityChart.destroy(); velocityChart = null; }
  resetDashboardDom();

  const loading = $('dash-loading');
  loading.textContent = 'Loading data…';
  loading.style.display = '';
  $('dashboard').style.display = 'none';

  currentSprint = await loadCurrentSprintAPI(activeGroup, activeProject);
  if (token !== requestToken) return;

  const fys = await discoverFYs(allData, activeGroup, activeProject);
  if (token !== requestToken) return;

  if (!fys.length) {
    loading.textContent = `No sprint data found${activeGroup ? ' for ' + activeGroup.name : ''}.`;
    return;
  }
  populateFYDropdown(fys);
  populateMonthDropdown(fys[0]);
  loading.style.display = 'none';
  $('dashboard').style.display = '';
  onMonthChange();
}
