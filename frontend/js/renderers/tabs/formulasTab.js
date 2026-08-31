import { escapeHtml } from '../../utils/dom.js';

export function renderFormulasTab(data) {
  const el = document.getElementById('formulas-content');
  if (!el) return;

  const formulas = data.math_formulas || [];
  if (!formulas.length) {
    el.innerHTML = '<p style="color: var(--text-muted);">No mathematical formulas detected in this document.</p>';
    return;
  }

  let html = '<div style="display: flex; flex-direction: column; gap: 14px;">';
  formulas.forEach((f, idx) => {
    const fName = escapeHtml(f.name || `Equation ${idx + 1}`);
    const expr = escapeHtml(f.expression || '-');
    const pg = f.source_page ? ` <span style="font-size: 11px; color: var(--text-muted);">(Page ${f.source_page})</span>` : '';
    const vars = f.variable_definitions || {};
    let varsHtml = '';
    if (Object.keys(vars).length > 0) {
      varsHtml = '<div style="margin-top: 8px; font-size: 11px; color: var(--text-secondary);"><strong>Variables:</strong><ul style="margin: 4px 0 0 16px;">';
      for (const [k, v] of Object.entries(vars)) {
        varsHtml += `<li><code>${escapeHtml(k)}</code>: ${escapeHtml(v)}</li>`;
      }
      varsHtml += '</ul></div>';
    }
    html += `
      <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
        <h4 style="font-family: var(--font-brand); margin-bottom: 6px;">${fName}${pg}</h4>
        <pre style="background: #000000; padding: 10px 14px; border-radius: var(--radius-sm); color: #a7f3d0; font-family: var(--font-mono); font-size: 13px; overflow-x: auto;"><code>${expr}</code></pre>
        ${varsHtml}
      </div>
    `;
  });
  html += '</div>';
  el.innerHTML = html;
}
