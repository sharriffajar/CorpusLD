import { escapeHtml } from '../../utils/dom.js';

export function renderMetricsTab(data) {
  const el = document.getElementById('metrics-content');
  if (!el) return;

  const rawProps = (data.additionalProperty && data.additionalProperty.length) ? data.additionalProperty : (data.properties_and_metrics || []);
  if (!rawProps.length) {
    el.innerHTML = '<p style="color: var(--text-muted);">No quantitative metrics detected.</p>';
    return;
  }

  let html = '<table class="data-table"><thead><tr><th>Parameter (PropertyValue)</th><th>Value</th><th>Unit</th><th>Page Reference</th><th>Condition / Context</th></tr></thead><tbody>';
  rawProps.forEach(m => {
    const mName = escapeHtml(m.name || '-');
    const mVal = escapeHtml(m.value !== undefined ? m.value : '-');
    const uText = escapeHtml(m.unitText || m.unit_text || '-');
    const refPage = escapeHtml(m.valueReference || (m.page_number ? `Page ${m.page_number}` : '-'));
    const descText = escapeHtml(m.description || m.condition_or_context || m.context_or_condition || '-');
    html += `<tr><td><strong>${mName}</strong></td><td><code>${mVal}</code></td><td>${uText}</td><td>${refPage}</td><td>${descText}</td></tr>`;
  });
  html += '</tbody></table>';
  el.innerHTML = html;
}
