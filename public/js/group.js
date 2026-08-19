// UI: Group dashboard page (group.html).
//
// Thin page module: resolves the group/project from the URL, sets the
// breadcrumb/title, then mounts and renders the shared dashboard controller.
// All dashboard rendering lives in js/dashboard.js (shared with the home page).

import { $, getParams } from './core/utils.js';
import { fetchJSON, resolveGroupAndProject } from './services/api.js';
import { mountDashboard, renderDashboard } from './dashboard.js';

async function init() {
  const groupsConfig = await fetchJSON('data/groups.json');
  const { group: groupSlug, project: projectSlug } = getParams('group', 'project');
  const resolved = resolveGroupAndProject(groupsConfig, groupSlug, projectSlug);

  if (resolved.shouldRedirect) {
    window.location.replace('index.html');
    return;
  }

  const { activeGroup, activeProject } = resolved;

  // Breadcrumb + page title
  if (activeGroup) {
    const bc = $('breadcrumb-group');
    const pt = $('page-title');
    if (activeProject) {
      if (bc) bc.textContent = `${activeGroup.name}: ${activeProject.name}`;
      if (pt) pt.textContent = `${activeProject.name} Sprint Dashboard`;
      document.title = `${activeProject.name} - ${activeGroup.name} - Sprint Metrics Dashboard`;
    } else {
      if (bc) bc.textContent = activeGroup.name;
      if (pt) pt.textContent = `${activeGroup.name} Sprint Dashboard`;
      document.title = `${activeGroup.name} - Sprint Metrics Dashboard`;
    }
  }

  mountDashboard($('dashboard-root'));
  await renderDashboard(activeGroup, activeProject);
}

init();
