import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  calculateProgress,
  getFilteredIssues,
  getUniqueProjects,
  calculateFilteredBurndown,
  calculateTypeBreakdown,
  getRecentCompletedSprints,
  sortMilestones,
  computeSprintTotals,
  computeSprintTimeMetrics,
  computeIdealBurndown,
  computeVelocitySeries,
  monthKeyToCutoff,
  buildSprintTabModel,
} from './calculations.js';

afterEach(() => {
  vi.useRealTimers();
});

function makeSprint(overrides = {}) {
  return {
    initial_totals: { count: 10 },
    completed: { count: 5 },
    start_date: '2020-01-06',
    end_date: '2020-01-17',
    issues: [],
    ...overrides,
  };
}

describe('calculateProgress', () => {
  it('returns null for a null sprint', () => {
    expect(calculateProgress(null)).toBeNull();
  });

  it('calculates completedPct correctly', () => {
    const sprint = makeSprint({ initial_totals: { count: 10 }, completed: { count: 4 } });
    expect(calculateProgress(sprint).completedPct).toBe(40);
  });

  it('returns 0% when initial count is 0', () => {
    const sprint = makeSprint({ initial_totals: { count: 0 }, completed: { count: 0 } });
    expect(calculateProgress(sprint).completedPct).toBe(0);
  });

  it('returns "Sprint ended" for a past sprint', () => {
    // 2020 dates are well in the past — deterministic regardless of when tests run
    expect(calculateProgress(makeSprint()).timeStatus).toBe('Sprint ended');
  });

  it('returns "Starts in N days" for a future sprint', () => {
    const sprint = makeSprint({ start_date: '2099-01-01', end_date: '2099-01-14' });
    expect(calculateProgress(sprint).timeStatus).toMatch(/^Starts in \d+ days?$/);
  });

  it('returns working days left for an active sprint', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-04-22T12:00:00Z')); // Wednesday mid-sprint
    const sprint = makeSprint({ start_date: '2026-04-20', end_date: '2026-04-30' });
    expect(calculateProgress(sprint).timeStatus).toMatch(/^\d+ working days? left$/);
  });

  it('returns singular "day" when exactly 1 working day remains', () => {
    vi.useFakeTimers();
    // Set today to the day before a single remaining working day
    vi.setSystemTime(new Date('2026-04-29T12:00:00Z')); // Wednesday — 1 working day left (Thu Apr 30)
    const sprint = makeSprint({ start_date: '2026-04-20', end_date: '2026-04-30' });
    expect(calculateProgress(sprint).timeStatus).toBe('1 working day left');
  });
});

describe('getFilteredIssues', () => {
  const issues = [
    { project_name: 'Alpha', id: 1 },
    { project_name: 'Beta', id: 2 },
    { project_name: 'Alpha', id: 3 },
  ];
  const sprint = { issues };

  it('returns empty array for null sprint', () => {
    expect(getFilteredIssues(null, null)).toEqual([]);
  });

  it('returns all issues when no filter is applied', () => {
    expect(getFilteredIssues(sprint, null)).toHaveLength(3);
  });

  it('filters to the specified project', () => {
    expect(getFilteredIssues(sprint, 'Alpha')).toHaveLength(2);
    expect(getFilteredIssues(sprint, 'Beta')).toHaveLength(1);
  });

  it('returns empty array when project is not found', () => {
    expect(getFilteredIssues(sprint, 'Gamma')).toHaveLength(0);
  });
});

describe('getUniqueProjects', () => {
  it('returns empty array for null sprint', () => {
    expect(getUniqueProjects(null)).toEqual([]);
  });

  it('returns unique project names sorted alphabetically', () => {
    const sprint = { issues: [
      { project_name: 'Zebra' },
      { project_name: 'Alpha' },
      { project_name: 'Zebra' },
    ]};
    expect(getUniqueProjects(sprint)).toEqual(['Alpha', 'Zebra']);
  });

  it('returns empty array for a sprint with no issues', () => {
    expect(getUniqueProjects({ issues: [] })).toEqual([]);
  });
});

describe('calculateFilteredBurndown', () => {
  it('counts all open issues before any are closed', () => {
    const issues = [
      { date_added_to_sprint: null, date_removed_from_sprint: null, date_closed: '2026-04-23', weight: 2 },
      { date_added_to_sprint: null, date_removed_from_sprint: null, date_closed: null, weight: 3 },
    ];
    const result = calculateFilteredBurndown(issues, ['2026-04-20', '2026-04-21'], '2026-04-20');
    expect(result[0].count).toBe(2);
    expect(result[0].weight).toBe(5);
  });

  it('excludes a closed issue on its close date', () => {
    const issues = [
      { date_added_to_sprint: null, date_removed_from_sprint: null, date_closed: '2026-04-22', weight: 2 },
      { date_added_to_sprint: null, date_removed_from_sprint: null, date_closed: null, weight: 3 },
    ];
    const result = calculateFilteredBurndown(issues, ['2026-04-21', '2026-04-22', '2026-04-23'], '2026-04-20');
    expect(result[0].count).toBe(2); // Apr 21: both open
    expect(result[1].count).toBe(1); // Apr 22: first issue closed
    expect(result[2].weight).toBe(3); // Apr 23: only second issue remains
  });

  it('excludes issues added to the sprint after the date', () => {
    const issues = [
      { date_added_to_sprint: '2026-04-22', date_removed_from_sprint: null, date_closed: null, weight: 1 },
    ];
    const result = calculateFilteredBurndown(issues, ['2026-04-20', '2026-04-22', '2026-04-23'], '2026-04-19');
    expect(result[0].count).toBe(0); // Apr 20: not yet added
    expect(result[1].count).toBe(1); // Apr 22: added on this date (added <= date)
    expect(result[2].count).toBe(1); // Apr 23: still open
  });

  it('excludes removed issues on their removal date', () => {
    const issues = [
      { date_added_to_sprint: null, date_removed_from_sprint: '2026-04-22', date_closed: null, weight: 1 },
    ];
    const result = calculateFilteredBurndown(issues, ['2026-04-21', '2026-04-22'], '2026-04-20');
    expect(result[0].count).toBe(1); // Apr 21: still in sprint
    expect(result[1].count).toBe(0); // Apr 22: removed
  });

  it('returns weight 0 for issues with no weight', () => {
    const issues = [
      { date_added_to_sprint: null, date_removed_from_sprint: null, date_closed: null, weight: undefined },
    ];
    const result = calculateFilteredBurndown(issues, ['2026-04-20'], '2026-04-20');
    expect(result[0].weight).toBe(0);
  });
});

describe('calculateTypeBreakdown', () => {
  it('counts issues by type label', () => {
    const issues = [
      { labels: ['type::bug'] },
      { labels: ['type::bug'] },
      { labels: ['type::improvement'] },
    ];
    const result = calculateTypeBreakdown(issues);
    expect(result.counts[result.labels.indexOf('Bug')]).toBe(2);
    expect(result.counts[result.labels.indexOf('Improvement')]).toBe(1);
  });

  it('counts issues with no type label as Task', () => {
    const result = calculateTypeBreakdown([{ labels: [] }, { labels: ['priority::high'] }]);
    expect(result.labels).toContain('Task');
    expect(result.counts[result.labels.indexOf('Task')]).toBe(2);
  });

  it('normalizes hyphenated type labels (type::new-feature → New Feature)', () => {
    const result = calculateTypeBreakdown([{ labels: ['type::new-feature'] }]);
    expect(result.labels).toContain('New Feature');
  });

  it('omits types with a zero count', () => {
    const result = calculateTypeBreakdown([{ labels: ['type::bug'] }]);
    expect(result.labels).not.toContain('Improvement');
    expect(result.labels).not.toContain('New Feature');
  });

  it('maps unknown type labels to Task', () => {
    const result = calculateTypeBreakdown([{ labels: ['type::research'] }]);
    expect(result.labels).toContain('Task');
    expect(result.labels).not.toContain('Research');
  });

  it('returns empty labels and counts for an empty issue list', () => {
    const result = calculateTypeBreakdown([]);
    expect(result.labels).toEqual([]);
    expect(result.counts).toEqual([]);
  });
});

describe('getRecentCompletedSprints', () => {
  const allData = {
    fy2026: {
      '10-oct-2025': { sprints: [
        { title: 'Sprint B', end_date: '2025-10-31' },
        { title: 'Sprint A', end_date: '2025-10-15' },
      ]},
      '11-nov-2025': { sprints: [
        { title: 'Sprint C', end_date: '2025-11-28' },
      ]},
    },
  };

  it('returns sprints in chronological order (oldest first)', () => {
    const result = getRecentCompletedSprints(allData, 3, '2026-01-01');
    expect(result.map(s => s.title)).toEqual(['Sprint A', 'Sprint B', 'Sprint C']);
  });

  it('respects the count limit', () => {
    expect(getRecentCompletedSprints(allData, 2, '2026-01-01')).toHaveLength(2);
  });

  it('excludes sprints on or after the cutoff date', () => {
    const result = getRecentCompletedSprints(allData, 10, '2025-10-31');
    expect(result.every(s => s.end_date < '2025-10-31')).toBe(true);
    expect(result).toHaveLength(1); // only Sprint A (Oct 15) qualifies
  });

  it('returns empty array when all sprints are after the cutoff', () => {
    expect(getRecentCompletedSprints(allData, 5, '2025-10-01')).toHaveLength(0);
  });
});

describe('computeSprintTotals', () => {
  it('uses precomputed group totals when no project filter is set', () => {
    const sprint = {
      initial_totals: { count: 10, weight: 30 },
      completed: { count: 4, weight: 12 },
      start_date: '2026-04-01',
      issues: [
        { project_name: 'Alpha', weight: 5 },
        { project_name: 'Beta', weight: 2 },
      ],
    };
    const r = computeSprintTotals(sprint, null);
    expect(r.initialCount).toBe(10);
    expect(r.initialWeight).toBe(30);
    expect(r.completedCount).toBe(4);
    expect(r.completedWeight).toBe(12);
    // totals always derived from the (filtered) issue list
    expect(r.totalCount).toBe(2);
    expect(r.totalWeight).toBe(7);
  });

  it('derives totals from the filtered project issues when a filter is set', () => {
    const sprint = {
      initial_totals: { count: 99, weight: 99 },
      completed: { count: 99, weight: 99 },
      start_date: '2026-04-10',
      issues: [
        // Alpha, present at start, closed
        { project_name: 'Alpha', weight: 5, date_added_to_sprint: null, state: 'closed' },
        // Alpha, added mid-sprint (not initial), open
        { project_name: 'Alpha', weight: 3, date_added_to_sprint: '2026-04-15', state: 'opened' },
        // Beta, ignored by the filter
        { project_name: 'Beta', weight: 50, date_added_to_sprint: null, state: 'closed' },
      ],
    };
    const r = computeSprintTotals(sprint, 'Alpha');
    expect(r.initialCount).toBe(1);      // only the null-added Alpha issue
    expect(r.initialWeight).toBe(5);
    expect(r.completedCount).toBe(1);    // only the closed Alpha issue
    expect(r.completedWeight).toBe(5);
    expect(r.totalCount).toBe(2);        // both Alpha issues
    expect(r.totalWeight).toBe(8);
  });

  it('treats an issue added on the start date as initial', () => {
    const sprint = {
      initial_totals: { count: 0, weight: 0 },
      completed: { count: 0, weight: 0 },
      start_date: '2026-04-10',
      issues: [{ project_name: 'Alpha', weight: 2, date_added_to_sprint: '2026-04-10', state: 'opened' }],
    };
    expect(computeSprintTotals(sprint, 'Alpha').initialCount).toBe(1);
  });
});

describe('computeSprintTimeMetrics', () => {
  // Apr 20–30, 2026 is holiday-free: 9 working days (Mon 20 … Thu 30).
  const sprint = { start_date: '2026-04-20', end_date: '2026-04-30' };

  it('reports "Starts in N days" and 0% before the sprint starts', () => {
    const r = computeSprintTimeMetrics(sprint, '2026-04-10');
    expect(r.timeRemainingText).toMatch(/^Starts in \d+ days?$/);
    expect(r.timeElapsedPct).toBe(0);
  });

  it('reports "Sprint ended N days ago" and 100% after the sprint ends', () => {
    const r = computeSprintTimeMetrics(sprint, '2026-05-10');
    expect(r.timeRemainingText).toMatch(/^Sprint ended \d+ days? ago$/);
    expect(r.timeElapsedPct).toBe(100);
  });

  it('reports working days left and elapsed percentage mid-sprint', () => {
    const r = computeSprintTimeMetrics(sprint, '2026-04-22'); // Wed: 3 of 9 working days elapsed
    expect(r.timeRemainingText).toBe('6 working days left');
    expect(r.timeElapsedPct).toBe(33);
  });

  it('returns empty text and null percentage when dates are missing', () => {
    const r = computeSprintTimeMetrics({ start_date: null, end_date: null }, '2026-04-22');
    expect(r).toEqual({ timeRemainingText: '', timeElapsedPct: null });
  });
});

describe('computeIdealBurndown', () => {
  it('decrements linearly across a full working week', () => {
    const dates = ['2026-04-20', '2026-04-21', '2026-04-22', '2026-04-23', '2026-04-24']; // Mon–Fri
    expect(computeIdealBurndown(dates, 10)).toEqual([10, 7.5, 5, 2.5, 0]);
  });

  it('holds flat across weekend days', () => {
    // Thu,Fri,Sat,Sun,Mon,Tue,Wed — 5 working days, decrement 2.5
    const dates = ['2026-04-23', '2026-04-24', '2026-04-25', '2026-04-26', '2026-04-27', '2026-04-28', '2026-04-29'];
    const ideal = computeIdealBurndown(dates, 10);
    expect(ideal).toEqual([10, 7.5, 5, 5, 5, 2.5, 0]);
    // Sat(2), Sun(3), Mon(4) share the same non-zero level: no decrement over the weekend
    expect(ideal[2]).toBe(5);
    expect(ideal[3]).toBe(5);
    expect(ideal[4]).toBe(5);
  });

  it('returns the starting value unchanged for a single working day', () => {
    expect(computeIdealBurndown(['2026-04-20'], 10)).toEqual([10]);
  });
});

describe('computeVelocitySeries', () => {
  it('uses precomputed weights and averages completed when unfiltered', () => {
    const sprints = [
      { initial_totals: { weight: 20 }, completed: { weight: 15 } },
      { initial_totals: { weight: 10 }, completed: { weight: 10 } },
    ];
    const r = computeVelocitySeries(sprints, null);
    expect(r.committed).toEqual([20, 10]);
    expect(r.completed).toEqual([15, 10]);
    expect(r.avgVelocity).toBe(12.5);
  });

  it('sums project-scoped initial and closed weights when filtered', () => {
    const sprints = [{
      start_date: '2026-04-01',
      issues: [
        { project_name: 'Alpha', weight: 5, date_added_to_sprint: null, state: 'closed' },
        { project_name: 'Alpha', weight: 3, date_added_to_sprint: '2026-04-15', state: 'opened' },
        { project_name: 'Beta', weight: 99, date_added_to_sprint: null, state: 'closed' },
      ],
    }];
    const r = computeVelocitySeries(sprints, 'Alpha');
    expect(r.committed).toEqual([5]); // only the initial Alpha issue
    expect(r.completed).toEqual([5]); // only the closed Alpha issue
    expect(r.avgVelocity).toBe(5);
  });
});

describe('monthKeyToCutoff', () => {
  it('returns the first day of the following month', () => {
    expect(monthKeyToCutoff('04-apr-2026')).toBe('2026-05-01');
  });

  it('rolls December over into the next January', () => {
    expect(monthKeyToCutoff('12-dec-2026')).toBe('2027-01-01');
  });

  it('returns undefined when no month key is given', () => {
    expect(monthKeyToCutoff('')).toBeUndefined();
    expect(monthKeyToCutoff(undefined)).toBeUndefined();
  });
});

describe('buildSprintTabModel', () => {
  it('appends the current sprint and activates it in the current month', () => {
    const { sprints, activeIndex } = buildSprintTabModel([{ id: 1 }], { id: 2 }, true);
    expect(sprints).toHaveLength(2);
    expect(sprints[1]._isCurrent).toBe(true);
    expect(activeIndex).toBe(1);
  });

  it('does not duplicate a current sprint already in the list', () => {
    const { sprints, activeIndex } = buildSprintTabModel([{ id: 1 }, { id: 2 }], { id: 2 }, true);
    expect(sprints).toHaveLength(2);
    expect(activeIndex).toBe(1);
  });

  it('does not append when the month is not the current month', () => {
    const { sprints, activeIndex } = buildSprintTabModel([{ id: 1 }], { id: 2 }, false);
    expect(sprints).toHaveLength(1);
    expect(activeIndex).toBe(0);
  });

  it('defaults the active index to 0 when there is no current sprint', () => {
    const { sprints, activeIndex } = buildSprintTabModel([{ id: 1 }], null, true);
    expect(sprints).toHaveLength(1);
    expect(activeIndex).toBe(0);
  });

  it('does not mutate the input month sprint list', () => {
    const month = [{ id: 1 }];
    buildSprintTabModel(month, { id: 2 }, true);
    expect(month).toHaveLength(1);
  });
});

describe('sortMilestones', () => {
  it('sorts newest due_date first', () => {
    const milestones = [
      { due_date: '2026-01-01' },
      { due_date: '2026-06-01' },
      { due_date: '2026-03-01' },
    ];
    const sorted = sortMilestones(milestones);
    expect(sorted[0].due_date).toBe('2026-06-01');
    expect(sorted[2].due_date).toBe('2026-01-01');
  });

  it('places null due_date at the end', () => {
    const milestones = [{ due_date: null }, { due_date: '2026-06-01' }];
    const sorted = sortMilestones(milestones);
    expect(sorted[0].due_date).toBe('2026-06-01');
    expect(sorted[1].due_date).toBeNull();
  });

  it('places two null due_dates both at the end without error', () => {
    const milestones = [{ due_date: null }, { due_date: '2026-06-01' }, { due_date: null }];
    const sorted = sortMilestones(milestones);
    expect(sorted[0].due_date).toBe('2026-06-01');
  });

  it('does not mutate the original array', () => {
    const milestones = [{ due_date: '2026-01-01' }, { due_date: '2026-06-01' }];
    sortMilestones(milestones);
    expect(milestones[0].due_date).toBe('2026-01-01');
  });
});
