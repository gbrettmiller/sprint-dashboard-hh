// Core utilities — pure helper functions shared across all pages.

export const $ = id => document.getElementById(id);

export function esc(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function slugify(text) {
  if (!text) return '';
  return text.toLowerCase().trim()
    .replace(/[^\w\s.\-]/g, '')
    .replace(/[\s_]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

// Trigger a download of an MS Word document built from an Office-HTML string.
// The only DOM-touching helper in Core besides $ — see ARCHITECTURE notes.
export function downloadDoc(filename, html) {
  // Leading BOM helps Word interpret the UTF-8 content correctly.
  const blob = new Blob(['﻿', html], { type: 'application/msword' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function getParams(...keys) {
  const params = new URLSearchParams(window.location.search);
  const result = {};
  keys.forEach(k => { result[k] = params.get(k); });
  return result;
}

export function formatLastUpdated(isoString) {
  if (!isoString) return null;

  // Treat timestamps without timezone info as UTC
  let normalized = isoString;
  if (!isoString.endsWith('Z') && !isoString.includes('+') && !/\d{2}:\d{2}:\d{2}-/.test(isoString)) {
    normalized = isoString + 'Z';
  }

  const date = new Date(normalized);

  // Format in US Eastern timezone (automatically handles EST/EDT)
  const options = { timeZone: 'America/New_York' };

  const day = date.toLocaleDateString('en-US', { ...options, day: '2-digit' });
  const month = date.toLocaleDateString('en-US', { ...options, month: 'short' }).toUpperCase();
  const year = date.toLocaleDateString('en-US', { ...options, year: '2-digit' });

  const time = date.toLocaleTimeString('en-US', { ...options, hour: '2-digit', minute: '2-digit', hour12: false });

  const tzAbbr = date.toLocaleTimeString('en-US', { ...options, timeZoneName: 'short' }).split(' ').pop();

  return `${day} ${month} ${year}, ${time} ${tzAbbr}`;
}

export function formatText(text) {
  // Minimal safe rendering: escape first, then apply basic formatting
  let html = esc(text);
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
  html = html.replace(/`(.*?)`/g, '<code>$1</code>');
  html = html.replace(/^- \[ \] (.+)$/gm, '<li><input type="checkbox" disabled> $1</li>');
  html = html.replace(/^- \[x\] (.+)$/gm, '<li><input type="checkbox" checked disabled> $1</li>');
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>');
  // Collapse consecutive </ul><ul> pairs
  html = html.replace(/<\/ul>\s*<ul>/g, '');
  html = html.replace(/\n/g, '<br>');
  return html;
}
