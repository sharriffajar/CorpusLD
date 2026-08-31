import { escapeHtml } from '../../utils/dom.js';

export function renderAuthorTab(data, flags = {}) {
  const el = document.getElementById('author-content');
  if (!el) return;

  const authors = data.author || [];
  const hasDate = flags.hasDate !== undefined ? flags.hasDate : Boolean(data.datePublished);
  const hasDoi = flags.hasDoi !== undefined ? flags.hasDoi : Boolean(flags.cleanDoi);
  const cleanDoi = flags.cleanDoi || (data.sameAs && String(data.sameAs).includes('10.') ? data.sameAs : '-');

  let html = `
    <div class="metadata-fields-grid">
      <div class="metadata-field-card field-valid">
        <div class="field-label">
          <span>📄 Document Title (<code>name</code>)</span>
          <span class="badge-status-valid">✅ Defined</span>
        </div>
        <div class="field-value"><strong>${escapeHtml(data.name || '-')}</strong></div>
      </div>

      <div class="metadata-field-card ${hasDate ? 'field-valid' : 'field-missing'}">
        <div class="field-label">
          <span>📅 Publication Date (<code>datePublished</code>)</span>
          <span class="${hasDate ? 'badge-status-valid' : 'badge-status-missing'}">
            ${hasDate ? '✅ Verified' : '⚠️ Missing in PDF'}
          </span>
        </div>
        <div class="field-value ${hasDate ? '' : 'text-missing'}">
          ${hasDate ? `<code>${escapeHtml(data.datePublished)}</code>` : '<em>Publication date was not found in document text. It is omitted from citation tags unless added manually.</em>'}
        </div>
      </div>

      <div class="metadata-field-card ${hasDoi ? 'field-valid' : 'field-warning'}">
        <div class="field-label">
          <span>🔗 DOI Identifier (<code>identifier</code>)</span>
          <span class="${hasDoi ? 'badge-status-valid' : 'badge-status-warning'}">
            ${hasDoi ? '✅ Indexed' : '⚠️ No DOI Found'}
          </span>
        </div>
        <div class="field-value">
          ${hasDoi ? `<code>${escapeHtml(cleanDoi)}</code>` : '<span style="color: var(--text-muted);">Unregistered or not written on cover</span>'}
        </div>
      </div>

      <div class="metadata-field-card field-valid">
        <div class="field-label">
          <span>🌐 Language &amp; Type</span>
          <span class="badge-status-valid">✅ ${escapeHtml(data.inLanguage || 'en')}</span>
        </div>
        <div class="field-value">
          <code>${escapeHtml(Array.isArray(data['@type']) ? data['@type'].join(', ') : (data['@type'] || 'ScholarlyArticle'))}</code>
        </div>
      </div>
    </div>

    <hr style="border: 0; border-top: 1px solid var(--border-subtle); margin: 16px 0;">
    <h4>Official Author List:</h4>
  `;

  if (authors.length) {
    html += '<table class="data-table"><thead><tr><th>Name</th><th>Identifier (ORCID / ID)</th><th>Affiliation</th></tr></thead><tbody>';
    authors.forEach(a => {
      const aName = escapeHtml(a.name || '-');
      const aId = a.identifier ? `<span class="badge-status-valid">${escapeHtml(a.identifier)}</span>` : '<span style="color: var(--text-dim);">-</span>';
      let affName = '-';
      let affRor = '';
      if (typeof a.affiliation === 'object' && a.affiliation) {
        affName = escapeHtml(a.affiliation.name || '-');
        if (a.affiliation.sameAs) {
          affRor = ` <a href="${escapeHtml(a.affiliation.sameAs)}" target="_blank" style="color: var(--accent-emerald); font-size: 10px;">[ROR]</a>`;
        }
      } else if (typeof a.affiliation === 'string') {
        affName = escapeHtml(a.affiliation);
      }
      html += `<tr><td><strong>${aName}</strong></td><td>${aId}</td><td>${affName}${affRor}</td></tr>`;
    });
    html += '</tbody></table>';
  } else {
    html += '<p style="color: #f87171; font-weight: 600;">⚠️ No author information detected from document cover.</p>';
  }

  el.innerHTML = html;
}
