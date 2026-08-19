import { $, esc, getParams, formatText } from './core/utils.js';
import { fetchJSON } from './services/api.js';
import { parseSection } from './core/parsing.js';

// -----------------------------------------------------------------------
// Render issues
// -----------------------------------------------------------------------
function renderIssues(data) {
  const container = $('issues-list');
  container.innerHTML = '';

  const issues = [...data.issues].sort((a, b) => a.iid - b.iid);

  if (issues.length === 0) {
    container.innerHTML = '<p class="empty-msg">No issues found for this milestone.</p>';
    return;
  }

  issues.forEach(issue => {
    const card = document.createElement('div');
    card.className = 'milestone-issue card';

    const header = document.createElement('h3');
    header.innerHTML = `<a href="${esc(issue.web_url)}" target="_blank" rel="noopener">#${issue.iid}</a> &mdash; ${esc(issue.title)}`;
    card.appendChild(header);

    const userStory = parseSection(issue.description, 'User Story');
    const storyDiv = document.createElement('div');
    storyDiv.className = 'section-content';
    if (userStory) {
      storyDiv.innerHTML = '<h4>User Story</h4><div class="markdown-content">' + formatText(userStory) + '</div>';
    } else {
      storyDiv.innerHTML = '<p class="no-content">There is no user story for this issue.</p>';
    }
    card.appendChild(storyDiv);

    container.appendChild(card);
  });
}

// -----------------------------------------------------------------------
// Init
// -----------------------------------------------------------------------
let milestoneData = null;

async function init() {
  const { group, project, milestone } = getParams('group', 'project', 'milestone');

  if (!group || !project || !milestone) {
    $('loading').textContent = 'Missing required URL parameters (group, project, milestone).';
    return;
  }

  const groupsConfig = await fetchJSON('data/groups.json');
  const groupObj = groupsConfig?.groups?.find(g => g.slug === group);
  const groupName = groupObj?.name || group;
  if (groupObj?.mode === 'projects') {
    // Deep-link back to the originating project on the single-page home so the
    // user lands on the project they came from, not the default selection.
    $('group-link').href = `index.html?group=${encodeURIComponent(group)}&project=${encodeURIComponent(project)}`;
  } else {
    $('group-link').href = `group.html?group=${encodeURIComponent(group)}`;
  }
  $('group-link').textContent = groupName;
  $('releases-link').href = `releases.html?group=${encodeURIComponent(group)}`;
  $('btn-all-releases').href = `releases.html?group=${encodeURIComponent(group)}`;

  const url = `data/${encodeURIComponent(group)}/milestones/${encodeURIComponent(project)}/${encodeURIComponent(milestone)}.json`;
  milestoneData = await fetchJSON(url);

  if (!milestoneData) {
    $('loading').textContent = 'Milestone data not found. Run a backfill to generate milestone data.';
    return;
  }

  const title = milestoneData.milestone_title;
  const projName = milestoneData.project_name;
  document.title = `${projName} ${title} - Sprint Metrics Dashboard`;
  $('breadcrumb-current').textContent = `${projName} ${title}`;
  $('heading-project').textContent = projName;
  $('heading-title').textContent = title;
  $('milestone-meta').textContent = `${milestoneData.issues.length} issues`;

  $('loading').style.display = 'none';
  $('milestone-content').style.display = '';

  renderIssues(milestoneData);
}

init();
