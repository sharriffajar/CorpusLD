import { escapeHtml } from '../../utils/dom.js';

export function renderTermsTab(data) {
  const el = document.getElementById('terms-content');
  if (!el) return;

  const terms = data.defined_terms || [];
  if (!terms.length) {
    el.innerHTML = '<p style="color: var(--text-muted);">No technical defined terms or domain abbreviations detected.</p>';
    return;
  }

  let html = '<table class="data-table"><thead><tr><th>Term / Code</th><th>Definition / Expansion</th><th>Category</th></tr></thead><tbody>';
  terms.forEach(t => {
    const tName = escapeHtml(t.name || '-');
    const tDesc = escapeHtml(t.description || '-');
    const tCat = escapeHtml(t.term_code || t.inDefinedTermSet || 'DefinedTerm');
    html += `<tr><td><strong>${tName}</strong></td><td>${tDesc}</td><td><code>${tCat}</code></td></tr>`;
  });
  html += '</tbody></table>';
  el.innerHTML = html;
}
