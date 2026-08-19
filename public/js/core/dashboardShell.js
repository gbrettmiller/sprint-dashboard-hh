// Dashboard markup — pure template shared by the group page and the home page.
//
// Returns the full sprint-dashboard shell (FY/Month nav-bar, loading element,
// and the #dashboard block) as an HTML string. It is injected into a mount
// container by `mountDashboard()` in js/dashboard.js so both group.html and
// index.html render the identical dashboard without duplicating this markup.
//
// This is a pure string builder (no DOM access, no fetch, no side effects),
// mirroring the Office-HTML builders in js/core/reports.js.

export function dashboardShellHTML() {
  return `
  <nav class="nav-bar" aria-label="Data selection">
    <label for="fy-select">Fiscal Year</label>
    <select id="fy-select"></select>
    <label for="month-select">Month</label>
    <select id="month-select"></select>
    <button id="btn-monthly-report" class="action-btn primary" type="button" style="display:none">Monthly Report</button>
    <span id="monthly-report-status" class="report-status" role="status" aria-live="polite"></span>
  </nav>

  <div id="dash-loading" class="empty-msg" aria-live="polite">Loading data&hellip;</div>

  <div id="dashboard" style="display:none">
    <nav aria-label="Sprint selection">
      <div id="sprint-tabs" class="sprint-tabs" role="tablist" aria-label="Available sprints"></div>
    </nav>

    <div id="project-filter" class="project-filter" role="group" aria-label="Filter by project">
      <span class="filter-label">Project:</span>
      <div id="project-chips" class="project-chips"></div>
    </div>

    <section id="sprint-detail" aria-labelledby="sprint-stats-heading">
      <h2 id="sprint-stats-heading" class="visually-hidden">Sprint Statistics</h2>

      <div id="sprint-reports" class="action-bar" style="display:none" role="group" aria-label="Generate documents for this sprint">
        <span class="filter-label">Generate:</span>
        <button id="btn-release-notes" class="action-btn primary" type="button">Release Notes</button>
        <button id="btn-test-plan" class="action-btn primary" type="button">Test Plan</button>
        <button id="btn-sprint-report" class="action-btn primary" type="button">Sprint Report</button>
        <span id="report-status" class="report-status" role="status" aria-live="polite"></span>
      </div>

      <div class="stat-cards" role="list">
        <div class="card stat-card" role="listitem">
          <div class="value" id="stat-init-count" aria-describedby="label-init-count">&mdash;</div>
          <div class="label" id="label-init-count">Initial Issues</div>
        </div>
        <div class="card stat-card" role="listitem">
          <div class="value" id="stat-init-weight" aria-describedby="label-init-weight">&mdash;</div>
          <div class="label" id="label-init-weight">Initial Weight</div>
        </div>
        <div class="card stat-card" role="listitem">
          <div class="value" id="stat-done-count" aria-describedby="label-done-count">&mdash;</div>
          <div class="label" id="label-done-count">Completed Issues</div>
        </div>
        <div class="card stat-card" role="listitem">
          <div class="value" id="stat-done-weight" aria-describedby="label-done-weight">&mdash;</div>
          <div class="label" id="label-done-weight">Completed Weight</div>
        </div>
      </div>

      <section class="card sprint-summary" id="sprint-summary" aria-labelledby="summary-heading">
        <div class="summary-header">
          <h2 id="summary-heading">Overall sprint progress (<span id="summary-mode">Issue Count</span>)</h2>
          <span class="time-remaining" id="summary-time-remaining"></span>
        </div>
        <p class="sprint-goal" id="sprint-goal" hidden></p>
        <div class="progress-bar-container">
          <div class="progress-bar" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" aria-label="Sprint completion progress">
            <div class="progress-segment completed" id="progress-completed">
              <span class="segment-label" id="progress-completed-label"></span>
            </div>
            <div class="progress-segment open" id="progress-open">
              <span class="segment-label" id="progress-open-label"></span>
            </div>
          </div>
          <div class="progress-legend">
            <span class="legend-item"><span class="legend-swatch completed"></span> Completed</span>
            <span class="legend-item"><span class="legend-swatch open"></span> Open</span>
          </div>
        </div>
        <div class="metrics-row">
          <div class="metric">
            <span class="metric-label">Time elapsed</span>
            <span class="metric-value" id="metric-time-elapsed">&mdash;</span>
          </div>
          <div class="metric">
            <span class="metric-label">Work complete</span>
            <span class="metric-value" id="metric-work-complete">&mdash;</span>
          </div>
          <div class="metric">
            <span class="metric-label">Scope change</span>
            <span class="metric-value" id="metric-scope-change">&mdash;</span>
          </div>
        </div>
      </section>

      <div class="charts-row">
        <section class="card" aria-labelledby="burndown-heading">
          <div class="chart-header">
            <h2 id="burndown-heading">Burndown</h2>
            <div class="toggle-group" role="group" aria-label="Burndown chart metric">
              <button class="toggle-btn active" data-chart="burndown" data-mode="count" aria-pressed="true">Count</button>
              <button class="toggle-btn" data-chart="burndown" data-mode="weight" aria-pressed="false">Weight</button>
            </div>
          </div>
          <canvas id="burndown-chart" role="img" aria-label="Sprint burndown chart showing progress over time"></canvas>
        </section>
        <section class="card" aria-labelledby="type-heading">
          <div class="chart-header">
            <h2 id="type-heading">Type Breakdown</h2>
            <div class="toggle-group" role="group" aria-label="Type breakdown filter">
              <button class="toggle-btn active" data-chart="type" data-mode="initial" aria-pressed="true">Initial</button>
              <button class="toggle-btn" data-chart="type" data-mode="completed" aria-pressed="false">Completed</button>
            </div>
          </div>
          <div id="type-empty" class="empty-msg" style="display:none">
            No issues in this sprint.
          </div>
          <canvas id="type-chart" role="img" aria-label="Doughnut chart showing issue types distribution"></canvas>
        </section>
      </div>

      <section class="card table-wrap" aria-labelledby="issues-heading">
        <div class="chart-header">
          <h2 id="issues-heading">Issues</h2>
          <button id="issues-toggle" class="collapse-toggle" aria-expanded="false" aria-controls="issues-table-container">
            <span class="toggle-icon">&#9654;</span> <span class="toggle-text">Show</span>
          </button>
        </div>
        <div id="issues-table-container" class="collapsible collapsed">
          <table id="issues-table" aria-describedby="issues-heading">
            <thead>
              <tr>
                <th scope="col" data-col="iid" aria-sort="none"><button type="button">IID <span class="sort-arrow" aria-hidden="true">&#9650;</span></button></th>
                <th scope="col" data-col="title" aria-sort="none"><button type="button">Title <span class="sort-arrow" aria-hidden="true">&#9650;</span></button></th>
                <th scope="col" data-col="project_name" aria-sort="none"><button type="button">Project <span class="sort-arrow" aria-hidden="true">&#9650;</span></button></th>
                <th scope="col" data-col="weight" aria-sort="none"><button type="button">Weight <span class="sort-arrow" aria-hidden="true">&#9650;</span></button></th>
                <th scope="col" data-col="state" aria-sort="none"><button type="button">State <span class="sort-arrow" aria-hidden="true">&#9650;</span></button></th>
                <th scope="col" data-col="date_added_to_sprint" aria-sort="none"><button type="button">Added <span class="sort-arrow" aria-hidden="true">&#9650;</span></button></th>
                <th scope="col" data-col="date_closed" aria-sort="none"><button type="button">Closed <span class="sort-arrow" aria-hidden="true">&#9650;</span></button></th>
                <th scope="col" data-col="date_removed_from_sprint" aria-sort="none"><button type="button">Removed <span class="sort-arrow" aria-hidden="true">&#9650;</span></button></th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>
    </section>

    <section class="velocity-section card" aria-labelledby="velocity-heading">
      <div class="chart-header">
        <h2 id="velocity-heading">Velocity (Last 6 Sprints)</h2>
      </div>
      <div id="velocity-empty" class="empty-msg" style="display:none">
        Not enough data to display velocity chart. At least 3 completed sprints are required.
      </div>
      <canvas id="velocity-chart" role="img" aria-label="Bar chart showing committed vs completed weight per sprint"></canvas>
    </section>
  </div>
`;
}
