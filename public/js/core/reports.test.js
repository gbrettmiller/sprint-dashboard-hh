import { describe, it, expect } from 'vitest';
import {
  isSprintComplete,
  isPastMonth,
  toReportMonthKey,
  availableSprintDocs,
  reportsEnabledFor,
  officeHtml,
  buildReleaseNotesDoc,
  buildReleaseNotesFromSprint,
  buildTestPlanDoc,
  buildSprintReportDoc,
  buildMonthlyReportDoc,
} from './reports.js';

// downloadDoc is a DOM-only wrapper (in utils.js) with no logic — not tested here.

describe('isSprintComplete', () => {
  const today = '2026-06-30';

  it('is true for a sprint whose end date has passed and is not current', () => {
    expect(isSprintComplete({ id: 1, end_date: '2026-05-15' }, null, today)).toBe(true);
    expect(isSprintComplete({ id: 1, end_date: '2026-05-15' }, { id: 2 }, today)).toBe(true);
  });

  it('is false for the current/active sprint even if its end date passed', () => {
    expect(isSprintComplete({ id: 7, end_date: '2026-05-15' }, { id: 7 }, today)).toBe(false);
  });

  it('is false for an in-progress or future sprint', () => {
    expect(isSprintComplete({ id: 1, end_date: '2026-06-30' }, null, today)).toBe(false); // ends today
    expect(isSprintComplete({ id: 1, end_date: '2026-08-01' }, null, today)).toBe(false);
  });

  it('is false when end_date is missing', () => {
    expect(isSprintComplete({ id: 1 }, null, today)).toBe(false);
    expect(isSprintComplete(null, null, today)).toBe(false);
  });
});

describe('isPastMonth / toReportMonthKey', () => {
  const today = new Date('2026-06-15T12:00:00Z');

  it('treats earlier months as past', () => {
    expect(isPastMonth('05-may-2026', today)).toBe(true);
    expect(isPastMonth('12-dec-2025', today)).toBe(true);
  });

  it('treats the current and future months as not past', () => {
    expect(isPastMonth('06-jun-2026', today)).toBe(false);
    expect(isPastMonth('07-jul-2026', today)).toBe(false);
  });

  it('returns false for a malformed key', () => {
    expect(isPastMonth('nonsense', today)).toBe(false);
    expect(isPastMonth('', today)).toBe(false);
  });

  it('converts the dashboard month key to the report month key', () => {
    expect(toReportMonthKey('06-jun-2026')).toBe('2026-06');
    expect(toReportMonthKey('12-dec-2025')).toBe('2025-12');
    expect(toReportMonthKey('bad')).toBeNull();
  });
});

describe('availableSprintDocs', () => {
  it('offers all three docs for milestone-sourced sprints (Cloud Services)', () => {
    expect(availableSprintDocs({ source: 'milestone' }))
      .toEqual({ releaseNotes: true, testPlan: true, sprintReport: true });
  });

  it('offers only the sprint report for Jira-sourced sprints (Data Services)', () => {
    expect(availableSprintDocs({ source: 'jira' }))
      .toEqual({ releaseNotes: false, testPlan: false, sprintReport: true });
  });

  it('offers release notes + sprint report for a reports-enabled standard group (Service Management)', () => {
    expect(availableSprintDocs({ source: 'iteration' }, { reports: true }))
      .toEqual({ releaseNotes: true, testPlan: false, sprintReport: true });
  });

  it('offers nothing for iteration-sourced or unknown sprints', () => {
    expect(availableSprintDocs({ source: 'iteration' }))
      .toEqual({ releaseNotes: false, testPlan: false, sprintReport: false });
    expect(availableSprintDocs({ source: 'iteration' }, { slug: 'other' })) // group without reports flag
      .toEqual({ releaseNotes: false, testPlan: false, sprintReport: false });
    expect(availableSprintDocs({}))
      .toEqual({ releaseNotes: false, testPlan: false, sprintReport: false });
    expect(availableSprintDocs(null))
      .toEqual({ releaseNotes: false, testPlan: false, sprintReport: false });
  });
});

describe('reportsEnabledFor', () => {
  it('is true for a project-mode project (Cloud Services)', () => {
    expect(reportsEnabledFor({ slug: 'cloud-services' }, { slug: 'orbit' })).toBe(true);
  });

  it('is true for a Jira-sourced standard group (Data Services)', () => {
    expect(reportsEnabledFor({ slug: 'data-services', source: 'jira' }, null)).toBe(true);
  });

  it('is true for a reports-enabled standard group (Service Management)', () => {
    expect(reportsEnabledFor({ slug: 'service-management', reports: true }, null)).toBe(true);
  });

  it('is false for a plain standard group and no group', () => {
    expect(reportsEnabledFor({ slug: 'other' }, null)).toBe(false);
    expect(reportsEnabledFor(null, null)).toBe(false);
  });
});

describe('officeHtml', () => {
  it('wraps body in the Office namespace and escapes the title', () => {
    const html = officeHtml('A & B <x>', '<p>hi</p>');
    expect(html).toContain('urn:schemas-microsoft-com:office:word');
    expect(html).toContain('<title>A &amp; B &lt;x&gt;</title>');
    expect(html).toContain('<body><p>hi</p></body>');
  });
});

describe('buildReleaseNotesDoc', () => {
  const milestoneData = {
    project_name: 'ORBIT',
    milestone_title: 'v3.3.0',
    issues: [
      { iid: 2, title: 'Closed feature', state: 'closed', labels: ['type::improvement'],
        description: '## Description\nAdds an export button.\n\n## User Story\nAs a user...' },
      { iid: 1, title: 'Open item', state: 'opened', labels: [], description: 'wip' },
      { iid: 3, title: 'Hidden', state: 'closed', labels: ['release-notes::no'], description: 'secret' },
    ],
  };

  it('includes a project/milestone heading and a .doc filename', () => {
    const { filename, html } = buildReleaseNotesDoc(milestoneData);
    expect(filename).toBe('ORBIT v3.3.0 Release Notes.doc');
    expect(html).toContain('ORBIT v3.3.0 Release Notes');
  });

  it('includes only delivered (closed, non-excluded) issues and summarizes them', () => {
    const { html } = buildReleaseNotesDoc(milestoneData);
    expect(html).toContain('#2 Closed feature');
    expect(html).toContain('Adds an export button.'); // from the Description section
    expect(html).not.toContain('Open item');          // open issue excluded
    expect(html).not.toContain('Hidden');             // release-notes::no excluded
  });

  it('handles a sprint with no delivered issues', () => {
    const { html } = buildReleaseNotesDoc({ project_name: 'P', milestone_title: 'v1', issues: [] });
    expect(html).toContain('No completed issues');
  });

  it('escapes issue titles', () => {
    const { html } = buildReleaseNotesDoc({
      project_name: 'P', milestone_title: 'v1',
      issues: [{ iid: 1, title: '<script>x</script>', state: 'closed', labels: [], description: 'd' }],
    });
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<script>x</script>');
  });
});

describe('buildReleaseNotesFromSprint', () => {
  const sprint = {
    title: 'FY26 Q1-4',
    issues: [
      { iid: 5, title: 'RAMS closed', state: 'closed', project_name: 'rams', labels: [],
        description: '## Description\nAdds a RAMS export.\n\n## User Story\nAs a user...' },
      { iid: 2, title: 'OAMS closed', state: 'closed', project_name: 'oams', labels: [],
        description: 'Fixes an OAMS bug.' },
      { iid: 9, title: 'OAMS open', state: 'opened', project_name: 'oams', labels: [], description: 'wip' },
      { iid: 3, title: 'Hidden', state: 'closed', project_name: 'oams', labels: ['release-notes::no'], description: 'secret' },
    ],
  };

  it('uses the group subject + sprint title in the heading and filename', () => {
    const { filename, html } = buildReleaseNotesFromSprint(sprint, 'Service Management');
    expect(filename).toBe('Service Management FY26 Q1-4 Release Notes.doc');
    expect(html).toContain('Service Management FY26 Q1-4 Release Notes');
  });

  it('groups delivered issues by project and summarizes them', () => {
    const { html } = buildReleaseNotesFromSprint(sprint, 'Service Management');
    // Projects appear as h2 headings (alphabetical: oams before rams).
    expect(html).toContain('<h2>oams</h2>');
    expect(html).toContain('<h2>rams</h2>');
    expect(html.indexOf('<h2>oams</h2>')).toBeLessThan(html.indexOf('<h2>rams</h2>'));
    expect(html).toContain('#2 OAMS closed');
    expect(html).toContain('Adds a RAMS export.'); // from the Description section
  });

  it('excludes open and release-notes::no issues', () => {
    const { html } = buildReleaseNotesFromSprint(sprint, 'Service Management');
    expect(html).not.toContain('OAMS open');
    expect(html).not.toContain('Hidden');
  });

  it('handles a sprint with no delivered issues', () => {
    const { html } = buildReleaseNotesFromSprint({ title: 'Empty', issues: [] }, 'Service Management');
    expect(html).toContain('No completed issues');
  });

  it('falls back when an issue has no description', () => {
    const { html } = buildReleaseNotesFromSprint(
      { title: 'S', issues: [{ iid: 1, title: 'X', state: 'closed', project_name: 'oams', labels: [], description: '' }] },
      'Service Management',
    );
    expect(html).toContain('No description provided.');
  });
});

describe('buildTestPlanDoc', () => {
  const milestoneData = { project_name: 'ORBIT', milestone_title: 'v3.3.0' };
  const reportJson = {
    title: 'v3.3.0',
    test_plan: [
      { iid: 5, title: 'Login works', web_url: 'http://x/5', steps: '- Open login\n- Enter creds' },
    ],
  };

  it('renders each entry with steps as a list', () => {
    const { filename, html } = buildTestPlanDoc(reportJson, milestoneData);
    expect(filename).toBe('ORBIT v3.3.0 Test Plan.doc');
    expect(html).toContain('#5 Login works');
    expect(html).toContain('<li>Open login</li>');
    expect(html).toContain('<li>Enter creds</li>');
  });

  it('handles an empty test plan', () => {
    const { html } = buildTestPlanDoc({ title: 'v3.3.0', test_plan: [] }, milestoneData);
    expect(html).toContain('No test-eligible issues');
  });
});

describe('buildSprintReportDoc', () => {
  const reportJson = {
    title: 'v3.3.0',
    start_date: '2026-05-04',
    end_date: '2026-05-15',
    sprint_report: {
      goals: 'Deliver the export feature.',
      summary: 'Shipped CSV export and fixed two bugs.',
      metrics: {
        initial_count: 10, initial_weight: 22,
        completed_count: 8, completed_weight: 18,
        initial_breakdown: '6 Improvements, 4 Bugs',
        completed_breakdown: '5 Improvements, 3 Bugs',
      },
    },
  };

  it('includes goals, summary, a metrics table and formatted dates', () => {
    const { filename, html } = buildSprintReportDoc(reportJson, 'ORBIT');
    expect(filename).toBe('ORBIT v3.3.0 Sprint Report.doc');
    expect(html).toContain('May 4, 2026');
    expect(html).toContain('May 15, 2026');
    expect(html).toContain('Deliver the export feature.');
    expect(html).toContain('Shipped CSV export');
    expect(html).toContain('<table>');
    expect(html).toContain('Completed Issues');
    expect(html).toContain('6 Improvements, 4 Bugs');
  });
});

describe('buildMonthlyReportDoc', () => {
  const reportJson = {
    month: '2026-05',
    sprints: [
      { title: 'v1.0.0', start_date: '2026-05-04', end_date: '2026-05-15',
        goals: 'Goal one.', summary: 'Summary one.',
        metrics: { initial_count: 3, initial_weight: 5, completed_count: 3, completed_weight: 5,
                   initial_breakdown: '3 Bugs', completed_breakdown: '3 Bugs' } },
      { title: 'v1.1.0', start_date: '2026-04-27', end_date: '2026-05-08',
        goals: 'Goal two.', summary: 'Summary two.',
        metrics: { initial_count: 2, initial_weight: 4, completed_count: 1, completed_weight: 2,
                   initial_breakdown: '2 Tasks', completed_breakdown: '1 Task' } },
    ],
  };

  it('labels the month and includes every sprint block', () => {
    const { filename, html } = buildMonthlyReportDoc(reportJson, 'ORBIT');
    expect(filename).toBe('ORBIT Monthly Report May 2026.doc');
    expect(html).toContain('May 2026');
    expect(html).toContain('v1.0.0');
    expect(html).toContain('v1.1.0');
    expect(html).toContain('Summary one.');
    expect(html).toContain('Summary two.');
  });

  it('handles a month with no sprints', () => {
    const { html } = buildMonthlyReportDoc({ month: '2026-05', sprints: [] }, 'ORBIT');
    expect(html).toContain('No completed sprints');
  });
});
