import { escapeHtml } from '../../utils/dom.js';

export function renderEntitiesTab(data) {
  const el = document.getElementById('entities-content');
  if (!el) return;

  const entities = (data.mentions && data.mentions.length) ? data.mentions : (data.entities_involved || []);
  if (!entities.length) {
    el.innerHTML = '<p style="color: var(--text-muted);">No entities detected in this document.</p>';
    return;
  }

  let html = '<div class="table-scroll-container"><table class="data-table"><thead><tr><th>Type (Schema.org)</th><th>Entity Name</th><th>Role / Description</th></tr></thead><tbody>';
  entities.forEach(e => {
    const typeStr = escapeHtml(e['@type'] || e.type || 'Thing');
    const nameStr = escapeHtml(e.name || '-');
    const descStr = escapeHtml(e.description || e.role_or_description || '-');
    html += `<tr><td><code>${typeStr}</code></td><td><strong>${nameStr}</strong></td><td>${descStr}</td></tr>`;
  });
  html += '</tbody></table></div>';
  el.innerHTML = html;
}
