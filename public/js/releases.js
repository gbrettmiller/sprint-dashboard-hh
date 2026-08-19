import { $, getParams } from './core/utils.js';
import { fetchJSON, EARLIEST_DATE } from './services/api.js';
import { sortMilestones } from './core/calculations.js';

const INITIAL_LIMIT = 5;

function createMilestoneItem(ms, group, project) {
  const li = document.createElement('li');

  const link = document.createElement('a');
  link.href = `milestone.html?group=${encodeURIComponent(group)}&project=${encodeURIComponent(project.project_slug)}&milestone=${encodeURIComponent(ms.slug)}`;
  link.textContent = ms.title;
  li.appendChild(link);

  const state = document.createElement('span');
  state.className = 'milestone-state state-' + (ms.state === 'active' ? 'active' : 'closed');
  state.textContent = ms.state;
  li.appendChild(state);

  if (ms.due_date) {
    const due = document.createElement('span');
    due.className = 'milestone-due';
    due.textContent = ms.due_date;
    li.appendChild(due);
  }

  return li;
}

function renderReleases(data, group) {
  const container = $('releases-content');
  container.innerHTML = '';

  if (!data.projects || data.projects.length === 0) {
    container.innerHTML = '<p class="empty-msg">No milestones found for any project.</p>';
    return;
  }

  const totalMilestones = data.projects.reduce((sum, p) => sum + p.milestones.length, 0);
  $('releases-meta').textContent = `${totalMilestones} milestones across ${data.projects.length} projects`;

  data.projects.forEach(project => {
    const section = document.createElement('section');
    section.className = 'card release-project-section';

    const heading = document.createElement('h2');
    heading.textContent = project.project_name;
    section.appendChild(heading);

    const sorted = sortMilestones(project.milestones);
    const hasMore = sorted.length > INITIAL_LIMIT;

    const list = document.createElement('ul');
    list.className = 'release-list';

    sorted.forEach((ms, idx) => {
      const li = createMilestoneItem(ms, group, project);
      if (hasMore && idx >= INITIAL_LIMIT) {
        li.className = 'release-overflow';
        li.style.display = 'none';
      }
      list.appendChild(li);
    });

    section.appendChild(list);

    if (hasMore) {
      const toggle = document.createElement('button');
      toggle.className = 'action-btn secondary release-expand-btn';
      toggle.type = 'button';
      toggle.textContent = `Show all (${sorted.length})`;
      toggle.setAttribute('aria-expanded', 'false');
      toggle.addEventListener('click', () => {
        const expanded = toggle.getAttribute('aria-expanded') === 'true';
        list.querySelectorAll('.release-overflow').forEach(li => {
          li.style.display = expanded ? 'none' : '';
        });
        toggle.setAttribute('aria-expanded', String(!expanded));
        toggle.textContent = expanded ? `Show all (${sorted.length})` : `Show recent ${INITIAL_LIMIT}`;
      });
      section.appendChild(toggle);
    }

    container.appendChild(section);
  });
}

async function init() {
  const { group } = getParams('group');

  if (!group) {
    $('loading').textContent = 'Missing group parameter.';
    return;
  }

  const groupsConfig = await fetchJSON('data/groups.json');
  const groupObj = groupsConfig?.groups?.find(g => g.slug === group);
  const groupName = groupObj?.name || group;
  if (groupObj?.mode === 'projects') {
    // The releases index is group-scoped (no single originating project), so
    // deep-link to the group on the single-page home to restore that selection
    // instead of landing on the default group.
    $('group-link').href = `index.html?group=${encodeURIComponent(group)}`;
  } else {
    $('group-link').href = `group.html?group=${encodeURIComponent(group)}`;
  }
  $('group-link').textContent = groupName;

  document.title = `All Releases - ${groupName} - Sprint Metrics Dashboard`;

  const url = `data/${encodeURIComponent(group)}/milestones/index.json`;
  const data = await fetchJSON(url);

  if (!data) {
    $('loading').textContent = 'No release data found. Run a backfill to generate milestone data.';
    return;
  }

  // Filter out milestones before the data cutoff date
  data.projects.forEach(p => {
    p.milestones = p.milestones.filter(m => !m.due_date || m.due_date >= EARLIEST_DATE);
  });
  data.projects = data.projects.filter(p => p.milestones.length > 0);

  $('loading').style.display = 'none';
  $('releases-content').style.display = '';

  renderReleases(data, group);
}

init();
