import { escapeHtml } from '../../utils/dom.js';

export function renderTablesTab(data) {
  const el = document.getElementById('tables-content');
  if (!el) return;

  const tables = data.tables || [];
  if (!tables.length && data.hasPart) {
    const tParts = data.hasPart.filter(p => p['@type'] === 'Table');
    if (tParts.length && !tables.length) {
      let html = '<div style="display: flex; flex-direction: column; gap: 14px;">';
      tParts.forEach((t, idx) => {
        const tName = escapeHtml(t.name || 'Table');
        const tPage = escapeHtml(t.pagination || '?');
        const tDesc = escapeHtml(t.description || '-');
        html += `
          <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
            <h4 style="font-family: var(--font-brand); margin-bottom: 6px;">Table ${idx + 1}: ${tName} <span style="font-size: 11px; color: var(--text-muted);">(Page ${tPage})</span></h4>
            <p style="font-size: 12px; color: var(--text-secondary);">${tDesc}</p>
          </div>
        `;
      });
      html += '</div>';
      el.innerHTML = html;
      return;
    }
  }

  if (!tables.length) {
    el.innerHTML = '<p style="color: var(--text-muted);">No tables detected in this document.</p>';
    return;
  }

  let html = '<div style="display: flex; flex-direction: column; gap: 20px;">';
  tables.forEach((t, idx) => {
    const tCap = escapeHtml(t.caption || 'Untitled Table');
    const tPage = escapeHtml(t.page_number || '?');
    html += `
      <div>
        <h4 style="font-family: var(--font-brand); margin-bottom: 8px;">Table ${idx + 1}: ${tCap} <span style="font-size: 11px; color: var(--text-muted);">(Page ${tPage})</span></h4>
        <div class="table-scroll-container">
          <table class="data-table">
            <thead><tr>${(t.headers || []).map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>
            <tbody>${(t.rows || []).map(row => `<tr>${row.map(cell => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`).join('')}</tbody>
          </table>
        </div>
      </div>
    `;
  });
  html += '</div>';
  el.innerHTML = html;
}
