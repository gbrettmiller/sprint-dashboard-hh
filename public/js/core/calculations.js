// Business logic calculations — pure functions, no DOM access.

import { isWorkingDay, generateDateRange } from './holidays.js';

export function calculateProgress(sprint) {
  if (!sprint) return null;

  const initial = sprint.initial_totals.count;
  const completed = sprint.completed.count;
  const completedPct = initial > 0 ? Math.round((completed / initial) * 100) : 0;

  const today = new Date().toISOString().slice(0, 10);
  let timeStatus = '';

  if (sprint.start_date && sprint.end_date) {
    const startMs = new Date(sprint.start_date + 'T00:00:00').getTime();
    const endMs = new Date(sprint.end_date + 'T00:00:00').getTime();
    const todayMs = new Date(today + 'T00:00:00').getTime();

    if (todayMs < startMs) {
      const daysUntil = Math.ceil((startMs - todayMs) / 86400000);
      timeStatus = `Starts in ${daysUntil} day${daysUntil !== 1 ? 's' : ''}`;
    } else if (todayMs > endMs) {
      timeStatus = 'Sprint ended';
    } else {
      const dates = [];
      for (let d = new Date(sprint.start_date + 'T00:00:00'); d <= new Date(sprint.end_date + 'T00:00:00'); d.setDate(d.getDate() + 1)) {
        dates.push(d.toISOString().slice(0, 10));
      }
      const workingDaysLeft = dates.filter(d => d > today && isWorkingDay(d)).length;
      timeStatus = `${workingDaysLeft} working day${workingDaysLeft !== 1 ? 's' : ''} left`;
    }
  }

  return { initial, completed, completedPct, timeStatus };
}

export function getFilteredIssues(sprint, projectFilter) {
  if (!sprint) return [];
  if (!projectFilter) return sprint.issues;
  return sprint.issues.filter(i => i.project_name === projectFilter);
}

export function getUniqueProjects(sprint) {
  if (!sprint || !sprint.issues) return [];
  const projects = [...new Set(sprint.issues.map(i => i.project_name))];
  return projects.sort((a, b) => a.localeCompare(b));
}

export function calculateFilteredBurndown(issues, dates, sprintStartDate) {
  return dates.map(date => {
    const remaining = issues.filter(issue => {
      const added = issue.date_added_to_sprint || sprintStartDate;
      const removed = issue.date_removed_from_sprint;
      const closed = issue.date_closed;

      if (added > date) return false;
      if (removed && removed <= date) return false;
      if (closed && closed <= date) return false;

      return true;
    });

    return {
      count: remaining.length,
      weight: remaining.reduce((sum, i) => sum + (i.weight || 0), 0)
    };
  });
}

const TYPE_CATEGORIES = ['Bug', 'Improvement', 'New Feature', 'Task'];
const TYPE_KNOWN = new Set(TYPE_CATEGORIES.slice(0, 3)); // Bug, Improvement, New Feature

export function calculateTypeBreakdown(issues) {
  const counts = { Bug: 0, Improvement: 0, 'New Feature': 0, Task: 0 };
  issues.forEach(issue => {
    const typeLabel = (issue.labels || []).find(l => l.toLowerCase().startsWith('type::'));
    if (typeLabel) {
      const raw = typeLabel.substring(6).replace(/-/g, ' ');
      const name = raw.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
      counts[TYPE_KNOWN.has(name) ? name : 'Task']++;
    } else {
      counts['Task']++;
    }
  });

  const labels = TYPE_CATEGORIES.filter(k => counts[k] > 0);
  return { labels, counts: labels.map(k => counts[k]) };
}

export function getRecentCompletedSprints(allData, count, cutoffDate) {
  const today = new Date().toISOString().slice(0, 10);
  const effectiveCutoff = cutoffDate && cutoffDate < today ? cutoffDate : today;
  const allSprints = [];

  Object.values(allData).forEach(fyData => {
    Object.values(fyData).forEach(monthData => {
      if (monthData.sprints) {
        monthData.sprints.forEach(sprint => {
          if (sprint.end_date < effectiveCutoff) {
            allSprints.push(sprint);
          }
        });
      }
    });
  });

  allSprints.sort((a, b) => b.end_date.localeCompare(a.end_date));
  return allSprints.slice(0, count).reverse();
}

// Shared internal helpers for sprint totals/velocity.
function sumWeight(issues) {
  return issues.reduce((sum, i) => sum + (i.weight || 0), 0);
}

// Issues present at sprint start: no add date, or added on/before the start date.
function getInitialIssues(issues, sprintStart) {
  return issues.filter(i => {
    const added = i.date_added_to_sprint;
    return !added || added <= sprintStart;
  });
}

// Initial/completed/total counts + weights for the stat cards and progress summary.
// When a projectFilter is set, everything is derived from that project's issues;
// otherwise the sprint's precomputed group totals are used (with totals from the
// full issue list, matching the summary's scope-change calculation).
export function computeSprintTotals(sprint, projectFilter) {
  const issues = getFilteredIssues(sprint, projectFilter);
  const totalCount = issues.length;
  const totalWeight = sumWeight(issues);

  let initialCount, initialWeight, completedCount, completedWeight;
  if (projectFilter) {
    const initialIssues = getInitialIssues(issues, sprint.start_date);
    initialCount = initialIssues.length;
    initialWeight = sumWeight(initialIssues);
    const closedIssues = issues.filter(i => i.state === 'closed');
    completedCount = closedIssues.length;
    completedWeight = sumWeight(closedIssues);
  } else {
    initialCount = sprint.initial_totals.count;
    initialWeight = sprint.initial_totals.weight;
    completedCount = sprint.completed.count;
    completedWeight = sprint.completed.weight;
  }

  return { initialCount, initialWeight, completedCount, completedWeight, totalCount, totalWeight };
}

// Time-remaining label + elapsed percentage, counting working days only.
// todayISO ("YYYY-MM-DD") is passed in for testability. timeElapsedPct is null
// when the sprint has no start/end dates (the UI renders "N/A").
export function computeSprintTimeMetrics(sprint, todayISO) {
  if (!sprint.start_date || !sprint.end_date) {
    return { timeRemainingText: '', timeElapsedPct: null };
  }

  const startMs = new Date(sprint.start_date + 'T00:00:00').getTime();
  const endMs = new Date(sprint.end_date + 'T00:00:00').getTime();
  const todayMs = new Date(todayISO + 'T00:00:00').getTime();

  const allDates = generateDateRange(sprint.start_date, sprint.end_date);
  const workingDays = allDates.filter(d => isWorkingDay(d));

  let timeRemainingText;
  if (todayMs < startMs) {
    const daysUntil = Math.ceil((startMs - todayMs) / 86400000);
    timeRemainingText = `Starts in ${daysUntil} day${daysUntil !== 1 ? 's' : ''}`;
  } else if (todayMs > endMs) {
    const daysAgo = Math.ceil((todayMs - endMs) / 86400000);
    timeRemainingText = `Sprint ended ${daysAgo} day${daysAgo !== 1 ? 's' : ''} ago`;
  } else {
    const daysLeft = workingDays.filter(d => d > todayISO).length;
    timeRemainingText = `${daysLeft} working day${daysLeft !== 1 ? 's' : ''} left`;
  }

  const elapsed = workingDays.filter(d => d <= todayISO).length;
  const timeElapsedPct = todayMs >= endMs
    ? 100
    : todayMs < startMs
      ? 0
      : workingDays.length > 0 ? Math.round((elapsed / workingDays.length) * 100) : 0;

  return { timeRemainingText, timeElapsedPct };
}

// Ideal burndown line: linear decrement across working days only (weekends and
// holidays hold flat), from `start` down to 0.
export function computeIdealBurndown(allDates, start) {
  const totalWorkingDays = allDates.filter(d => isWorkingDay(d)).length;
  const decrementPerDay = totalWorkingDays > 1 ? start / (totalWorkingDays - 1) : 0;

  let workingDaysSoFar = 0;
  return allDates.map(date => {
    const value = +(start - (workingDaysSoFar * decrementPerDay)).toFixed(1);
    if (isWorkingDay(date)) workingDaysSoFar++;
    return value;
  });
}

// Committed (initial weight) and completed (closed weight) per sprint for the
// velocity chart, plus the average of completed. Respects the project filter.
export function computeVelocitySeries(sprints, projectFilter) {
  let committed, completed;

  if (projectFilter) {
    committed = sprints.map(sprint => {
      const projectIssues = sprint.issues.filter(i => i.project_name === projectFilter);
      return sumWeight(getInitialIssues(projectIssues, sprint.start_date));
    });
    completed = sprints.map(sprint => {
      const projectIssues = sprint.issues.filter(i => i.project_name === projectFilter && i.state === 'closed');
      return sumWeight(projectIssues);
    });
  } else {
    committed = sprints.map(s => s.initial_totals.weight);
    completed = sprints.map(s => s.completed.weight);
  }

  const avgVelocity = completed.reduce((sum, v) => sum + v, 0) / completed.length;
  return { committed, completed, avgVelocity };
}

// Convert a month file key ("MM-mon-YYYY") into a cutoff date (first day of the
// following month, "YYYY-MM-01") for velocity's recent-sprint window. Returns
// undefined when no month key is given.
export function monthKeyToCutoff(monthKey) {
  if (!monthKey) return undefined;
  const parts = monthKey.split('-');
  const month = parseInt(parts[0], 10);
  const year = parseInt(parts[2], 10);
  let nextMonth = month + 1, nextYear = year;
  if (nextMonth > 12) { nextMonth = 1; nextYear++; }
  return `${nextYear}-${String(nextMonth).padStart(2, '0')}-01`;
}

// Build the sprint-tab list for a month: append the active current sprint (tagged
// _isCurrent) when viewing the current month and it isn't already in the list,
// and resolve which tab should be active. isCurrentMonth is decided by the caller
// (it needs "now"), keeping this pure.
export function buildSprintTabModel(monthSprints, currentSprint, isCurrentMonth) {
  const sprints = [...monthSprints];

  if (currentSprint && isCurrentMonth) {
    const alreadyIncluded = sprints.some(s => s.id === currentSprint.id);
    if (!alreadyIncluded) {
      sprints.push({ ...currentSprint, _isCurrent: true });
    }
  }

  let activeIndex = 0;
  if (currentSprint) {
    const idx = sprints.findIndex(s => s._isCurrent || s.id === currentSprint.id);
    if (idx !== -1) activeIndex = idx;
  }

  return { sprints, activeIndex };
}

export function sortMilestones(milestones) {
  return milestones.slice().sort((a, b) => {
    const da = a.due_date || '';
    const db = b.due_date || '';
    if (!da && !db) return 0;
    if (!da) return 1;
    if (!db) return -1;
    return db.localeCompare(da);
  });
}
