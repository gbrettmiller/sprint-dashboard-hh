// UI: Home page (index.html).
//
// Single-page experience: groups are shown as tabs; selecting a group lists its
// project cards; selecting a card renders that project's full dashboard inline
// below the cards via the shared controller (js/dashboard.js). Cards still link
// to group.html so middle-click / open-in-new-tab yields the standalone page,
// but a normal click renders inline.

import { $, getParams } from './core/utils.js';
import { fetchJSON } from './services/api.js';
import { calculateProgress } from './core/calculations.js';
import { mountDashboard, renderDashboard } from './dashboard.js';

// -----------------------------------------------------------------------
// State
// -----------------------------------------------------------------------
let groupModels = [];       // [{ group, entries: [{ project|null, sprint }] }]
let selectedModel = null;   // currently selected group model
let currentFilter = 'active';

// -----------------------------------------------------------------------
// URL sync — reflect the current group/card selection in the query string so
// selections are shareable (deep-links) and Back/Forward navigable.
//   urlMode: 'push'    → new history entry (user tab/card navigation)
//            'replace' → overwrite current entry (initial load, filter sync)
//            'none'    → don't touch history (popstate restoration)
// -----------------------------------------------------------------------
function writeURL(urlMode) {
  if (urlMode === 'none' || !selectedModel) return;
  const groupSlug = selectedModel.group.slug;
  const sel = $('groups-grid').querySelector('.group-card.selected');
  const projectSlug = (sel && sel._project) ? sel._project.slug : null;

  const params = new URLSearchParams();
  params.set('group', groupSlug);
  if (projectSlug) params.set('project', projectSlug);
  const url = `?${params.toString()}`;
  const state = { group: groupSlug, project: projectSlug };
  if (urlMode === 'push') history.pushState(state, '', url);
  else history.replaceState(state, '', url);
}

// -----------------------------------------------------------------------
// Pure helper: classify a current-sprint record
// -----------------------------------------------------------------------
function sprintStateOf(sprint) {
  if (!sprint || !sprint.start_date || !sprint.end_date) return 'none';
  const today = new Date().toISOString().slice(0, 10);
  const todayMs = new Date(today + 'T00:00:00').getTime();
  const startMs = new Date(sprint.start_date + 'T00:00:00').getTime();
  const endMs = new Date(sprint.end_date + 'T00:00:00').getTime();
  if (todayMs < startMs) return 'upcoming';
  if (todayMs > endMs) return 'ended';
  return 'active';
}

// -----------------------------------------------------------------------
// Render a card (shared between group and project cards)
// -----------------------------------------------------------------------
function buildCard(href, cardName, sprint, subtitle, logoSrc) {
  const card = document.createElement('a');
  card.href = href;
  card.className = 'card group-card';
  card.setAttribute('role', 'listitem');
  card.dataset.sprintState = sprintStateOf(sprint);

  if (logoSrc) {
    const logo = document.createElement('img');
    logo.src = logoSrc;
    logo.alt = '';
    logo.className = 'group-card-logo';
    card.appendChild(logo);
  }

  if (subtitle) {
    const sub = document.createElement('div');
    sub.className = 'group-card-group';
    sub.textContent = subtitle;
    card.appendChild(sub);
  }

  const name = document.createElement('h2');
  name.className = 'group-card-name';
  name.textContent = cardName;
  card.appendChild(name);

  if (sprint) {
    const progress = calculateProgress(sprint);
    const displayTitle = sprint.title || `${sprint.start_date} → ${sprint.end_date}`;

    const title = document.createElement('div');
    title.className = 'group-card-sprint';
    title.textContent = displayTitle;
    card.appendChild(title);

    const dates = document.createElement('div');
    dates.className = 'group-card-dates';
    dates.textContent = `${sprint.start_date} → ${sprint.end_date}`;
    card.appendChild(dates);

    // Progress bar
    const barContainer = document.createElement('div');
    barContainer.className = 'progress-bar-container';
    const bar = document.createElement('div');
    bar.className = 'progress-bar';
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-valuenow', progress.completedPct);
    bar.setAttribute('aria-valuemin', '0');
    bar.setAttribute('aria-valuemax', '100');
    bar.setAttribute('aria-label', `Sprint completion: ${progress.completedPct}%`);

    const completedSeg = document.createElement('div');
    completedSeg.className = 'progress-segment completed';
    completedSeg.style.width = progress.completedPct + '%';

    const openSeg = document.createElement('div');
    openSeg.className = 'progress-segment open';
    openSeg.style.width = (100 - progress.completedPct) + '%';

    bar.appendChild(completedSeg);
    bar.appendChild(openSeg);
    barContainer.appendChild(bar);
    card.appendChild(barContainer);

    // Meta row
    const meta = document.createElement('div');
    meta.className = 'group-card-meta';

    const countSpan = document.createElement('span');
    countSpan.textContent = `${progress.completed} / ${progress.initial} issues completed`;
    meta.appendChild(countSpan);

    if (progress.timeStatus) {
      const timeSpan = document.createElement('span');
      timeSpan.className = 'group-card-time';
      timeSpan.textContent = progress.timeStatus;
      meta.appendChild(timeSpan);
    }

    card.appendChild(meta);
  } else {
    const empty = document.createElement('div');
    empty.className = 'group-card-empty';
    empty.textContent = 'No active sprint';
    card.appendChild(empty);
  }

  return card;
}

function renderGroupCard(group, sprint) {
  return buildCard(
    `group.html?group=${encodeURIComponent(group.slug)}`,
    group.name, sprint, null, group.logo
  );
}

function renderProjectCard(group, project, sprint) {
  return buildCard(
    `group.html?group=${encodeURIComponent(group.slug)}&project=${encodeURIComponent(project.slug)}`,
    project.name, sprint, group.name, project.logo || group.logo
  );
}

// -----------------------------------------------------------------------
// Group tabs
// -----------------------------------------------------------------------
function buildGroupTabs() {
  const tablist = $('group-tabs');
  tablist.innerHTML = '';
  groupModels.forEach((model, i) => {
    const tab = document.createElement('button');
    tab.type = 'button';
    tab.className = 'group-tab';
    tab.id = `group-tab-${model.group.slug}`;
    tab.textContent = model.group.name;
    tab.dataset.groupSlug = model.group.slug;
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-controls', 'dashboard-root');
    tab.setAttribute('aria-selected', 'false');
    tab.setAttribute('tabindex', '-1');
    tab.addEventListener('click', () => selectGroup(model, { urlMode: 'push' }));
    tab.addEventListener('keydown', e => onTabKeydown(e, i));
    tablist.appendChild(tab);
  });
  tablist.style.display = '';
}

// Roving-tabindex keyboard nav with automatic activation.
function onTabKeydown(e, i) {
  const tabs = [...$('group-tabs').querySelectorAll('.group-tab')];
  let target = null;
  if (e.key === 'ArrowRight') target = tabs[(i + 1) % tabs.length];
  else if (e.key === 'ArrowLeft') target = tabs[(i - 1 + tabs.length) % tabs.length];
  else if (e.key === 'Home') target = tabs[0];
  else if (e.key === 'End') target = tabs[tabs.length - 1];
  else return;
  e.preventDefault();
  target.focus();
  target.click();
}

function selectGroup(model, { urlMode = 'replace', preferProject } = {}) {
  selectedModel = model;
  $('group-tabs').querySelectorAll('.group-tab').forEach(t => {
    const sel = t.dataset.groupSlug === model.group.slug;
    t.classList.toggle('active', sel);
    t.setAttribute('aria-selected', sel ? 'true' : 'false');
    t.setAttribute('tabindex', sel ? '0' : '-1');
  });
  $('dashboard-root').setAttribute('aria-labelledby', `group-tab-${model.group.slug}`);
  renderCardsForGroup(model);
  applyFilter({ urlMode, preferProject });
}

// -----------------------------------------------------------------------
// Cards for the selected group
// -----------------------------------------------------------------------
function renderCardsForGroup(model) {
  const grid = $('groups-grid');
  grid.innerHTML = '';
  model.entries.forEach(entry => {
    const card = entry.project
      ? renderProjectCard(model.group, entry.project, entry.sprint)
      : renderGroupCard(model.group, entry.sprint);
    card._group = model.group;
    card._project = entry.project || null;
    card.addEventListener('click', e => {
      e.preventDefault();
      selectCard(card, { urlMode: 'push', scroll: true });
    });
    grid.appendChild(card);
  });
  grid.style.display = '';
}

// Labeled header for the inline dashboard so the detail panel is tied to the
// selected project (e.g. "CASS" / "PPMT — Sprint Dashboard"). Home-page only.
function renderDashboardHeader(group, project) {
  const header = $('dashboard-header');
  header.innerHTML = '';

  const logoSrc = (project && project.logo) || group.logo;
  if (logoSrc) {
    const logo = document.createElement('img');
    logo.src = logoSrc;
    logo.alt = '';
    logo.className = 'dashboard-header-logo';
    header.appendChild(logo);
  }

  const text = document.createElement('div');
  text.className = 'dashboard-header-text';

  if (project) {
    const eyebrow = document.createElement('div');
    eyebrow.className = 'dashboard-header-eyebrow';
    eyebrow.textContent = group.name;
    text.appendChild(eyebrow);
  }

  const title = document.createElement('h2');
  title.className = 'dashboard-header-title';
  title.textContent = project ? project.name : group.name;
  const suffix = document.createElement('span');
  suffix.className = 'dashboard-header-suffix';
  suffix.textContent = 'Sprint Dashboard';
  title.appendChild(suffix);
  text.appendChild(title);

  header.appendChild(text);
  header.hidden = false;
}

function selectCard(card, { urlMode = 'replace', scroll = false } = {}) {
  $('groups-grid').querySelectorAll('.group-card').forEach(c => {
    const sel = c === card;
    c.classList.toggle('selected', sel);
    if (sel) c.setAttribute('aria-current', 'true');
    else c.removeAttribute('aria-current');
  });
  renderDashboardHeader(card._group, card._project);
  $('dashboard-root').style.display = '';
  renderDashboard(card._group, card._project);
  writeURL(urlMode);

  // Only scroll on an explicit click — not the auto-select at load / filter change.
  if (scroll) {
    $('dashboard-header').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// -----------------------------------------------------------------------
// Filter (Active Sprints / All Projects) — scoped to the selected group
// -----------------------------------------------------------------------
function buildFilter() {
  const container = $('home-filter');
  const chips = container.querySelector('.project-chips');
  chips.innerHTML = '';
  [['active', 'Active Sprints'], ['all', 'All Projects']].forEach(([value, label]) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'project-chip' + (value === currentFilter ? ' active' : '');
    btn.dataset.filter = value;
    btn.textContent = label;
    btn.setAttribute('role', 'radio');
    btn.setAttribute('aria-checked', value === currentFilter ? 'true' : 'false');
    btn.addEventListener('click', () => setFilter(value));
    chips.appendChild(btn);
  });
  container.style.display = '';
}

function syncFilterChips() {
  $('home-filter').querySelectorAll('.project-chip').forEach(c => {
    const on = c.dataset.filter === currentFilter;
    c.classList.toggle('active', on);
    c.setAttribute('aria-checked', on ? 'true' : 'false');
  });
}

function setFilter(value) {
  currentFilter = value;
  syncFilterChips();
  applyFilter({ urlMode: 'replace' });
}

// Show/hide cards per the current filter, then ensure a valid card is selected:
// prefer an explicitly requested card (deep-link), else keep the current
// selection if still visible, else the first active card (fallback first
// visible). If nothing is visible, hide the dashboard. A selection change is
// reflected in the URL per urlMode so a stale ?project= never lingers.
function applyFilter({ urlMode = 'replace', preferProject } = {}) {
  const grid = $('groups-grid');
  const cards = [...grid.querySelectorAll('.group-card')];
  cards.forEach(c => {
    c.style.display = (currentFilter === 'all' || c.dataset.sprintState === 'active') ? '' : 'none';
  });

  const visible = cards.filter(c => c.style.display !== 'none');
  const currentSel = grid.querySelector('.group-card.selected');
  const preferred = preferProject !== undefined
    ? cards.find(c => ((c._project && c._project.slug) || null) === preferProject)
    : null;

  let target;
  if (preferred && visible.includes(preferred)) target = preferred;
  else if (currentSel && visible.includes(currentSel)) target = currentSel;
  else target = visible.find(c => c.dataset.sprintState === 'active') || visible[0];

  const emptyMsg = $('cards-empty');
  if (!target) {
    cards.forEach(c => { c.classList.remove('selected'); c.removeAttribute('aria-current'); });
    $('dashboard-header').hidden = true;
    $('dashboard-root').style.display = 'none';
    emptyMsg.textContent = `No active sprints in ${selectedModel.group.name}.`;
    emptyMsg.style.display = '';
    writeURL(urlMode); // drop any stale ?project= — only the group remains selected
    return;
  }
  emptyMsg.style.display = 'none';
  if (target !== currentSel) selectCard(target, { urlMode });
}

// -----------------------------------------------------------------------
// Init
// -----------------------------------------------------------------------
async function init() {
  const groupsConfig = await fetchJSON('data/groups.json');

  if (!groupsConfig || !groupsConfig.groups || groupsConfig.groups.length === 0) {
    $('loading').textContent = 'No groups configured.';
    return;
  }

  groupModels = await Promise.all(groupsConfig.groups.map(async group => {
    if (group.mode === 'projects' && group.projects && group.projects.length > 0) {
      const sprints = await Promise.all(
        group.projects.map(p => fetchJSON(`data/${group.slug}/${p.slug}/current-sprint.json`))
      );
      return { group, entries: group.projects.map((project, i) => ({ project, sprint: sprints[i] })) };
    }
    const sprint = await fetchJSON(`data/${group.slug}/current-sprint.json`);
    return { group, entries: [{ project: null, sprint }] };
  }));

  $('loading').style.display = 'none';
  mountDashboard($('dashboard-root'));
  buildFilter();
  buildGroupTabs();

  // Restore selection from ?group=&project= (deep-link); else default. Record
  // the resolved selection with replaceState so Back never lands on a bare URL.
  const { group, project } = getParams('group', 'project');
  if (!restoreSelection(group, project)) selectDefault('replace');
  else writeURL('replace');

  window.addEventListener('popstate', () => {
    const { group, project } = getParams('group', 'project');
    // Re-select from the URL without pushing a new history entry.
    if (!restoreSelection(group, project, 'none')) selectDefault('none');
  });
}

// Apply a group/project selection from URL params. Returns false when the
// group param is missing/invalid so the caller can fall back to the default.
// A deep-link to a specific card overrides the Active filter so that card is
// visible even if its sprint isn't active.
function restoreSelection(groupSlug, projectSlug, urlMode = 'none') {
  const model = groupSlug ? groupModels.find(m => m.group.slug === groupSlug) : null;
  if (!model) return false;

  // Resolve the deep-linked card: an explicit project, or the lone card of a
  // standard-mode group. An invalid/absent project degrades to the default pick.
  let entry = null;
  if (projectSlug != null) {
    entry = model.entries.find(e => e.project && e.project.slug === projectSlug) || null;
  } else if (model.entries.length === 1 && !model.entries[0].project) {
    entry = model.entries[0];
  }

  if (entry && sprintStateOf(entry.sprint) !== 'active') {
    currentFilter = 'all';
    syncFilterChips();
  }

  const preferProject = entry ? ((entry.project && entry.project.slug) || null) : undefined;
  selectGroup(model, { urlMode, preferProject });
  return true;
}

function selectDefault(urlMode) {
  selectGroup(groupModels[0], { urlMode });
}

init();
