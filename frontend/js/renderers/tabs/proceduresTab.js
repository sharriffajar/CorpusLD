import { escapeHtml } from '../../utils/dom.js';

export function renderProceduresTab(data) {
  const el = document.getElementById('procedures-content');
  if (!el) return;

  const procs = data.procedures || [];
  if (!procs.length) {
    el.innerHTML = '<p style="color: var(--text-muted);">No structured procedures or methodology steps extracted.</p>';
    return;
  }

  let html = '<div style="display: flex; flex-direction: column; gap: 12px;">';
  procs.forEach((p, idx) => {
    const stepNum = p.step_number || (idx + 1);
    const name = escapeHtml(p.name || `Step ${stepNum}`);
    const text = escapeHtml(p.text || p.description || '-');
    const tools = p.tools_or_equipment || [];
    const toolStr = tools.length ? `<div style="margin-top: 6px; font-size: 11px; color: var(--text-accent);"><strong>Tools / Hardware:</strong> ${escapeHtml(tools.join(', '))}</div>` : '';
    html += `
      <div style="background: var(--bg-surface-elevated); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
        <h4 style="font-family: var(--font-brand); color: #ffffff;">⚙️ Step ${stepNum}: ${name}</h4>
        <p style="font-size: 12px; color: var(--text-secondary); margin: 6px 0;">${text}</p>
        ${toolStr}
      </div>
    `;
  });
  html += '</div>';
  el.innerHTML = html;
}
