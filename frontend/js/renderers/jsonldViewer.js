import { appState } from '../state.js';
import { renderValidatorReport } from './validator.js';
import { renderAuthorTab } from './tabs/authorTab.js';
import { renderKgTab } from './tabs/kgTab.js';
import { renderEntitiesTab } from './tabs/entitiesTab.js';
import { renderMetricsTab } from './tabs/metricsTab.js';
import { renderSectionsTab } from './tabs/sectionsTab.js';
import { renderTablesTab } from './tabs/tablesTab.js';
import { renderProceduresTab } from './tabs/proceduresTab.js';
import { renderFormulasTab } from './tabs/formulasTab.js';
import { renderTermsTab } from './tabs/termsTab.js';
import { renderRefsTab } from './tabs/refsTab.js';
import { renderLogsTab } from './tabs/logsTab.js';
import { renderRawTab } from './tabs/rawTab.js';
import { renderScholarTab } from './scholar.js';

export function renderJsonLdData(rawPayload) {
  const jsonldResultsContainer = document.getElementById('jsonld-results-container');
  const btnDownloadExport = document.getElementById('btn-download-export');
  const btnDownloadJsonld = document.getElementById('btn-download-jsonld');
  const selectExportFormat = document.getElementById('select-export-format');
  const btnSyncGraphdb = document.getElementById('btn-sync-graphdb');
  const btnCopyScholarTags = document.getElementById('btn-copy-scholar-tags');

  if (jsonldResultsContainer) jsonldResultsContainer.classList.remove('hidden');
  if (btnDownloadJsonld) btnDownloadJsonld.disabled = false;
  if (selectExportFormat) selectExportFormat.disabled = false;
  if (btnDownloadExport) btnDownloadExport.disabled = false;
  if (btnSyncGraphdb) btnSyncGraphdb.disabled = false;

  const data = rawPayload.schema_json_ld || rawPayload;
  const telemetry = rawPayload.telemetry || {};

  // Extract clean DOI if present
  let cleanDoi = '';
  const doiVal = data.identifier;
  if (Array.isArray(doiVal)) {
    for (const it of doiVal) {
      if (typeof it === 'object' && String(it.propertyID).toUpperCase() === 'DOI' && it.value) {
        cleanDoi = String(it.value).trim();
        break;
      }
    }
  } else if (typeof doiVal === 'object' && doiVal?.value) {
    cleanDoi = String(doiVal.value).trim();
  } else if (typeof doiVal === 'string') {
    cleanDoi = doiVal.replace('https://doi.org/', '').trim();
  }
  if (!cleanDoi && data.sameAs && String(data.sameAs).includes('10.')) {
    const m = String(data.sameAs).match(/10\.\d{4,9}\/[^\s"\]\[}<>]+/);
    if (m) cleanDoi = m[0];
  }

  const hasDate = Boolean(data.datePublished && String(data.datePublished).trim() !== '' && String(data.datePublished).toLowerCase() !== 'null');
  const hasAuthor = Boolean(data.author && Array.isArray(data.author) && data.author.length > 0);
  const hasDoi = Boolean(cleanDoi);

  // Hero title & description
  const heroTitle = document.getElementById('doc-hero-title');
  const heroDesc = document.getElementById('doc-hero-desc');
  if (heroTitle) heroTitle.textContent = data.name || appState.selectedDoc;
  if (heroDesc) heroDesc.textContent = data.description || '-';

  // Hero metadata pills
  const typeStr = Array.isArray(data['@type']) ? data['@type'].join(', ') : (data['@type'] || 'ScholarlyArticle');
  const heroType = document.getElementById('hero-badge-type');
  if (heroType) {
    heroType.className = 'hero-meta-pill pill-valid';
    heroType.textContent = `🏷️ ${typeStr}`;
  }

  const heroLang = document.getElementById('hero-badge-lang');
  if (heroLang) {
    heroLang.className = 'hero-meta-pill pill-valid';
    heroLang.textContent = `🌐 ${data.inLanguage || 'en'}`;
  }

  const heroDate = document.getElementById('hero-badge-date');
  if (heroDate) {
    if (hasDate) {
      heroDate.className = 'hero-meta-pill pill-valid';
      heroDate.textContent = `📅 ${data.datePublished}`;
    } else {
      heroDate.className = 'hero-meta-pill pill-missing';
      heroDate.textContent = '⚠️ Date: Not Identified in PDF';
    }
  }

  const heroDoi = document.getElementById('hero-badge-doi');
  if (heroDoi) {
    if (hasDoi) {
      heroDoi.className = 'hero-meta-pill pill-valid';
      heroDoi.textContent = `🔗 ${cleanDoi}`;
    } else {
      heroDoi.className = 'hero-meta-pill pill-warning';
      heroDoi.textContent = '⚠️ DOI: Unindexed';
    }
  }

  const heroAuthors = document.getElementById('hero-badge-authors');
  if (heroAuthors) {
    if (hasAuthor) {
      heroAuthors.className = 'hero-meta-pill pill-valid';
      heroAuthors.textContent = `👥 ${data.author.length} Authors`;
    } else {
      heroAuthors.className = 'hero-meta-pill pill-missing';
      heroAuthors.textContent = '⚠️ Author: 0 Detected';
    }
  }

  const heroCitations = document.getElementById('hero-badge-citations');
  if (heroCitations) {
    const citCount = data.citation?.length || data.references_or_sources?.length || 0;
    heroCitations.className = 'hero-meta-pill pill-valid';
    heroCitations.textContent = `📚 ${citCount} Citations`;
  }

  // Render Validator & Completeness Alerts
  renderValidatorReport(data, rawPayload, { hasDate, hasAuthor, hasDoi });

  // Render Subtabs
  renderAuthorTab(data, { hasDate, hasDoi, cleanDoi });
  renderKgTab(data);
  renderEntitiesTab(data);
  renderMetricsTab(data);
  renderSectionsTab(data);
  renderTablesTab(data);
  renderProceduresTab(data);
  renderFormulasTab(data);
  renderTermsTab(data);
  renderRefsTab(data);
  renderScholarTab(data);
  renderLogsTab(telemetry);
  renderRawTab(data);

  if (btnCopyScholarTags) btnCopyScholarTags.disabled = false;
}
