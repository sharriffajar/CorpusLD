import { escapeHtml } from '../../utils/dom.js';

export function renderKgTab(data) {
  const el = document.getElementById('kg-content');
  if (!el) return;
  const kg = data.knowledge_graph || {};
  const nodes = kg.nodes || kg['kg:nodes'] || [];
  const edges = kg.edges || kg['kg:edges'] || [];

  if (!nodes.length && !edges.length) {
    el.innerHTML = '<p style="color: var(--text-muted);">No Knowledge Graph nodes or triples extracted for this document yet.</p>';
    return;
  }

  let html = `
    <div style="display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap;">
      <div style="background: var(--bg-surface-elevated); padding: 10px 16px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
        <strong style="color: var(--text-accent);">Nodes Count:</strong> <span>${nodes.length}</span>
      </div>
      <div style="background: var(--bg-surface-elevated); padding: 10px 16px; border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
        <strong style="color: var(--text-accent);">Triples / Edges:</strong> <span>${edges.length}</span>
      </div>
    </div>
  `;

  // 1. Triples Table
  if (edges.length) {
    html += '<h4 style="margin-bottom: 8px;">Semantic Triples (Subject &rarr; Predicate &rarr; Object)</h4>';
    html += '<table class="data-table"><thead><tr><th>Subject (Source)</th><th>Predicate (Relation)</th><th>Object (Target)</th><th>Evidence / Source</th></tr></thead><tbody>';
    edges.forEach(e => {
      const src = escapeHtml(e.source || e['kg:source'] || '-');
      const rel = escapeHtml(e.type || e.relation || e['kg:type'] || 'relates_to');
      const tgt = escapeHtml(e.target || e['kg:target'] || '-');
      const ev = escapeHtml(e.evidence || e['kg:evidence'] || '-');
      const pg = e.source_page || e['kg:source_page'];
      const pageLabel = pg ? ` <span style="font-size: 10px; color: var(--text-muted);">(p. ${pg})</span>` : '';
      html += `<tr><td><code>${src}</code></td><td><span class="badge-tag badge-ready" style="font-size: 11px; padding: 2px 8px;">${rel}</span></td><td><code>${tgt}</code></td><td style="font-size: 11px;">${ev}${pageLabel}</td></tr>`;
    });
    html += '</tbody></table>';
  }

  // 2. Nodes Table
  if (nodes.length) {
    html += '<h4 style="margin-top: 20px; margin-bottom: 8px;">Extracted Knowledge Graph Entities & Authorities</h4>';
    html += '<table class="data-table"><thead><tr><th>Node ID</th><th>Type</th><th>Label</th><th>Authority (sameAs)</th><th>Description</th></tr></thead><tbody>';
    nodes.forEach(n => {
      const nid = escapeHtml(n.id || n['@id'] || '-');
      const ntype = escapeHtml(n.type || n['@type'] || 'kg:Concept');
      const nlabel = escapeHtml(n.label || n['kg:label'] || n.name || '-');
      const sameAs = n.sameAs || n.same_as || '';
      let authHtml = '<span style="color: var(--text-muted);">-</span>';
      if (sameAs) {
        const sameAsList = Array.isArray(sameAs) ? sameAs : [sameAs];
        authHtml = sameAsList.map(url => {
          const safeUrl = escapeHtml(url);
          const label = safeUrl.includes('wikidata') ? '🌐 Wikidata' : (safeUrl.includes('ror.org') ? '🏛️ ROR' : (safeUrl.includes('mesh') ? '🧬 MeSH' : '🔗 Authority'));
          return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer" style="color: #38bdf8; text-decoration: underline; margin-right: 6px;">${label}</a>`;
        }).join(' ');
      }
      const desc = escapeHtml(n.description || '-');
      html += `<tr><td><code>${nid}</code></td><td><span class="hero-meta-pill" style="font-size: 10px; padding: 2px 6px;">${ntype}</span></td><td><strong>${nlabel}</strong></td><td>${authHtml}</td><td style="font-size: 11px;">${desc}</td></tr>`;
    });
    html += '</tbody></table>';
  }

  el.innerHTML = html;
}
