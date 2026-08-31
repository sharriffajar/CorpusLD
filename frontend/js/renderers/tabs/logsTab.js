import { escapeHtml } from '../../utils/dom.js';

export function renderLogsTab(telemetry = {}) {
  const el = document.getElementById('logs-content');
  if (!el) return;

  const logs = telemetry.logs || [];
  const totalTime = escapeHtml(telemetry.duration_seconds || '?');
  let html = `<p><strong>Total Extraction Time:</strong> <code>${totalTime} seconds</code></p><hr style="border:0; border-top:1px solid var(--border-subtle); margin:10px 0;"><div style="font-family: var(--font-mono); font-size: 11px; line-height: 1.6; color: #a7f3d0;">`;
  logs.forEach(l => {
    html += `<div>${escapeHtml(l)}</div>`;
  });
  html += '</div>';
  el.innerHTML = html;
}
