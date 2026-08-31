import { escapeHtml } from '../../utils/dom.js';

export function renderSectionsTab(data) {
  const el = document.getElementById('sections-content');
  if (!el) return;

  let sections = data.sections || [];
  if (!sections.length && data.hasPart) {
    sections = data.hasPart.filter(p => p['@type'] === 'CreativeWork' || !p['@type']);
  }
  if (!sections.length) {
    el.innerHTML = '<p style="color: var(--text-muted);">No sections detected in this document.</p>';
    return;
  }

  let html = '<div style="display: flex; flex-direction: column; gap: 12px;">';
  sections.forEach(s => {
    const sName = escapeHtml(s.name || s.section_name || 'Section');
    const pageInfo = escapeHtml(s.pagination ? `(Page ${s.pagination})` : (s.page_start ? `(Page ${s.page_start} - ${s.page_end})` : ''));
    const sDesc = escapeHtml(s.description || s.summary || '-');
    html += `
      <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
        <h4 style="font-family: var(--font-brand); color: #ffffff; display: flex; align-items: center; gap: 8px;">
          <span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--accent-primary);"></span>
          <span>${sName}</span>
          <span style="font-size: 11px; color: var(--text-accent); font-weight: normal;">${pageInfo}</span>
        </h4>
        <p style="font-size: 12px; color: var(--text-secondary); margin: 6px 0;"><strong>Summary:</strong> ${sDesc}</p>
      </div>
    `;
  });
  html += '</div>';
  el.innerHTML = html;
}
