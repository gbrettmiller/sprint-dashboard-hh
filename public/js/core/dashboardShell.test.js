import { describe, it, expect } from 'vitest';
import { dashboardShellHTML } from './dashboardShell.js';

describe('dashboardShellHTML', () => {
  const html = dashboardShellHTML();

  it('returns a non-empty HTML string', () => {
    expect(typeof html).toBe('string');
    expect(html.length).toBeGreaterThan(0);
  });

  // The shared controller (js/dashboard.js) queries these IDs by hand. If any
  // is renamed/removed in the shell, the dashboard silently breaks — this test
  // is the guard against that.
  const requiredIds = [
    'fy-select', 'month-select', 'btn-monthly-report', 'monthly-report-status',
    'dash-loading', 'dashboard', 'sprint-tabs', 'project-filter', 'project-chips',
    'sprint-reports', 'btn-release-notes', 'btn-test-plan', 'btn-sprint-report', 'report-status',
    'stat-init-count', 'stat-init-weight', 'stat-done-count', 'stat-done-weight',
    'sprint-summary', 'summary-mode', 'summary-time-remaining', 'sprint-goal',
    'progress-completed', 'progress-open', 'progress-completed-label', 'progress-open-label',
    'metric-time-elapsed', 'metric-work-complete', 'metric-scope-change',
    'burndown-chart', 'type-chart', 'type-empty',
    'issues-table', 'issues-toggle', 'issues-table-container',
    'velocity-chart', 'velocity-empty',
  ];

  it.each(requiredIds)('contains element id="%s"', (id) => {
    expect(html).toContain(`id="${id}"`);
  });

  it('uses #dash-loading (not #loading) so it never collides with the home page spinner', () => {
    expect(html).toContain('id="dash-loading"');
    expect(html).not.toContain('id="loading"');
  });
});
