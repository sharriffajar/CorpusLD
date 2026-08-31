import { escapeHtml } from '../../utils/dom.js';

export function renderRefsTab(data) {
  const el = document.getElementById('refs-content');
  if (!el) return;

  const refs = (data.citation && data.citation.length) ? data.citation : (data.references_or_sources || []);
  if (!refs.length) {
    el.innerHTML = '<p style="color: var(--text-muted);">No references detected.</p>';
    return;
  }

  let html = '<div style="display: flex; flex-direction: column; gap: 8px;">';
  refs.forEach(r => {
    const refText = typeof r === 'string' ? r : (r.name || JSON.stringify(r));
    html += `
      <div style="background: var(--bg-surface-elevated); padding: 10px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); font-size: 12px; line-height: 1.5;">
        ${escapeHtml(refText)}
      </div>
    `;
  });
  html += '</div>';
  el.innerHTML = html;
}
