import { appState, saveSettingsToStorage, resetSettingsToDefault } from '../state.js';
import { testLlmConnection, testParserService, testGraphdbConnection } from '../api.js';

export function applySettingsToUI() {
  const settingProvider = document.getElementById('setting-provider');
  const settingOllamaModel = document.getElementById('setting-ollama-model');
  const settingBaseUrl = document.getElementById('setting-base-url');
  const settingCloudModel = document.getElementById('setting-cloud-model');
  const settingApiKey = document.getElementById('setting-api-key');
  const settingParser = document.getElementById('setting-parser');
  const settingLlamaparseKey = document.getElementById('setting-llamaparse-key');
  const settingUnstructuredKey = document.getElementById('setting-unstructured-key');
  const settingGraphdbType = document.getElementById('setting-graphdb-type');
  const settingNeo4jUri = document.getElementById('setting-neo4j-uri');
  const settingNeo4jUser = document.getElementById('setting-neo4j-user');
  const settingNeo4jPass = document.getElementById('setting-neo4j-pass');
  const settingNeo4jDb = document.getElementById('setting-neo4j-db');
  const settingSparqlUrl = document.getElementById('setting-sparql-url');

  if (settingProvider) settingProvider.value = appState.settings.provider || 'ollama';
  if (settingOllamaModel) settingOllamaModel.value = appState.settings.ollamaModel || 'qwen2.5:3b';
  if (settingBaseUrl) settingBaseUrl.value = appState.settings.baseUrl || '';
  if (settingCloudModel) settingCloudModel.value = appState.settings.cloudModel || 'gemini-3.5-flash-lite';
  if (settingApiKey) settingApiKey.value = appState.settings.apiKey || '';
  if (settingParser) settingParser.value = appState.settings.parser || 'pypdf';
  if (settingLlamaparseKey) settingLlamaparseKey.value = appState.settings.llamaparseKey || '';
  if (settingUnstructuredKey) settingUnstructuredKey.value = appState.settings.unstructuredKey || '';

  if (settingGraphdbType) settingGraphdbType.value = appState.settings.graphdbType || 'neo4j';
  if (settingNeo4jUri) settingNeo4jUri.value = appState.settings.neo4jUri || 'bolt://localhost:7687';
  if (settingNeo4jUser) settingNeo4jUser.value = appState.settings.neo4jUser || 'neo4j';
  if (settingNeo4jPass) settingNeo4jPass.value = appState.settings.neo4jPass || '';
  if (settingNeo4jDb) settingNeo4jDb.value = appState.settings.neo4jDb || 'neo4j';
  if (settingSparqlUrl) settingSparqlUrl.value = appState.settings.sparqlUrl || 'http://localhost:3030/dataset/update';

  toggleSettingsVisibility();
}

export function toggleSettingsVisibility() {
  const settingProvider = document.getElementById('setting-provider');
  const groupOllamaModel = document.getElementById('group-ollama-model');
  const groupCloudModel = document.getElementById('group-cloud-model');
  const groupApiKey = document.getElementById('group-api-key');
  const groupBaseUrl = document.getElementById('group-base-url');
  const settingParser = document.getElementById('setting-parser');
  const groupLlamaparseKey = document.getElementById('group-llamaparse-key');
  const groupUnstructuredKey = document.getElementById('group-unstructured-key');
  const settingGraphdbType = document.getElementById('setting-graphdb-type');
  const groupNeo4jFields = document.getElementById('group-neo4j-fields');
  const groupSparqlFields = document.getElementById('group-sparql-fields');

  if (!settingProvider) return;

  const provider = settingProvider.value;
  const isCloudLLM = provider !== 'ollama';
  const isCustom = provider === 'custom';

  if (groupOllamaModel) groupOllamaModel.classList.toggle('hidden', isCloudLLM);
  if (groupCloudModel) groupCloudModel.classList.toggle('hidden', !isCloudLLM);
  if (groupApiKey) groupApiKey.classList.toggle('hidden', !isCloudLLM);
  if (groupBaseUrl) groupBaseUrl.classList.toggle('hidden', !isCustom);

  if (settingParser) {
    const needsLlamaKey = settingParser.value === 'llamaparse' || settingParser.value === 'hybrid';
    if (groupLlamaparseKey) groupLlamaparseKey.classList.toggle('hidden', !needsLlamaKey);
    if (groupUnstructuredKey) groupUnstructuredKey.classList.toggle('hidden', settingParser.value !== 'unstructured');
  }

  if (settingGraphdbType) {
    const isSparql = settingGraphdbType.value === 'sparql';
    if (groupNeo4jFields) groupNeo4jFields.classList.toggle('hidden', isSparql);
    if (groupSparqlFields) groupSparqlFields.classList.toggle('hidden', !isSparql);
  }
}

export function initSettingsModule() {
  const settingsModal = document.getElementById('settings-modal');
  const btnOpenSettings = document.getElementById('btn-open-settings');
  const btnCloseSettings = document.getElementById('btn-close-settings');
  const btnSaveSettings = document.getElementById('btn-save-settings');
  const btnResetSettings = document.getElementById('btn-reset-settings');
  const settingProvider = document.getElementById('setting-provider');
  const settingParser = document.getElementById('setting-parser');
  const settingGraphdbType = document.getElementById('setting-graphdb-type');

  if (settingProvider) settingProvider.addEventListener('change', toggleSettingsVisibility);
  if (settingParser) settingParser.addEventListener('change', toggleSettingsVisibility);
  if (settingGraphdbType) settingGraphdbType.addEventListener('change', toggleSettingsVisibility);

  if (btnOpenSettings) {
    btnOpenSettings.addEventListener('click', () => {
      applySettingsToUI();
      settingsModal?.classList.remove('hidden');
    });
  }

  if (btnCloseSettings) {
    btnCloseSettings.addEventListener('click', () => {
      settingsModal?.classList.add('hidden');
    });
  }

  if (btnSaveSettings) {
    btnSaveSettings.addEventListener('click', () => {
      const settingOllamaModel = document.getElementById('setting-ollama-model');
      const settingBaseUrl = document.getElementById('setting-base-url');
      const settingCloudModel = document.getElementById('setting-cloud-model');
      const settingApiKey = document.getElementById('setting-api-key');
      const settingLlamaparseKey = document.getElementById('setting-llamaparse-key');
      const settingUnstructuredKey = document.getElementById('setting-unstructured-key');
      const settingNeo4jUri = document.getElementById('setting-neo4j-uri');
      const settingNeo4jUser = document.getElementById('setting-neo4j-user');
      const settingNeo4jPass = document.getElementById('setting-neo4j-pass');
      const settingNeo4jDb = document.getElementById('setting-neo4j-db');
      const settingSparqlUrl = document.getElementById('setting-sparql-url');

      saveSettingsToStorage({
        provider: settingProvider?.value || 'ollama',
        ollamaModel: settingOllamaModel?.value || 'qwen2.5:3b',
        baseUrl: settingBaseUrl ? settingBaseUrl.value.trim() : '',
        cloudModel: settingCloudModel ? settingCloudModel.value.trim() : 'gemini-3.5-flash-lite',
        apiKey: settingApiKey ? settingApiKey.value.trim() : '',
        parser: settingParser?.value || 'pypdf',
        llamaparseKey: settingLlamaparseKey ? settingLlamaparseKey.value.trim() : '',
        unstructuredKey: settingUnstructuredKey ? settingUnstructuredKey.value.trim() : '',
        graphdbType: settingGraphdbType ? settingGraphdbType.value : 'neo4j',
        neo4jUri: settingNeo4jUri ? settingNeo4jUri.value.trim() : 'bolt://localhost:7687',
        neo4jUser: settingNeo4jUser ? settingNeo4jUser.value.trim() : 'neo4j',
        neo4jPass: settingNeo4jPass ? settingNeo4jPass.value.trim() : '',
        neo4jDb: settingNeo4jDb ? settingNeo4jDb.value.trim() : 'neo4j',
        sparqlUrl: settingSparqlUrl ? settingSparqlUrl.value.trim() : 'http://localhost:3030/dataset/update'
      });

      settingsModal?.classList.add('hidden');
    });
  }

  if (btnResetSettings) {
    btnResetSettings.addEventListener('click', () => {
      resetSettingsToDefault();
      applySettingsToUI();
      alert('Settings reset to default values.');
    });
  }

  // Diagnostics: LLM Test
  const btnTestLlm = document.getElementById('btn-test-llm');
  const llmTestResult = document.getElementById('llm-test-result');
  if (btnTestLlm) {
    btnTestLlm.addEventListener('click', async () => {
      btnTestLlm.disabled = true;
      if (llmTestResult) {
        llmTestResult.style.color = 'var(--text-muted)';
        llmTestResult.textContent = 'Testing connection... ⏳';
      }
      try {
        const provider = settingProvider ? settingProvider.value : 'ollama';
        const settingOllamaModel = document.getElementById('setting-ollama-model');
        const settingCloudModel = document.getElementById('setting-cloud-model');
        const settingApiKey = document.getElementById('setting-api-key');
        const settingBaseUrl = document.getElementById('setting-base-url');

        const model = provider === 'ollama' ? (settingOllamaModel?.value || 'qwen2.5:3b') : (settingCloudModel ? settingCloudModel.value.trim() : '');
        const apiKey = settingApiKey ? settingApiKey.value.trim() : '';
        const baseUrl = settingBaseUrl ? settingBaseUrl.value.trim() : '';

        const data = await testLlmConnection({ provider, model, api_key: apiKey, base_url: baseUrl });
        if (data.status === 'ok') {
          if (llmTestResult) {
            llmTestResult.style.color = '#34d399';
            llmTestResult.textContent = `✅ ${data.message}`;
          }
        } else {
          if (llmTestResult) {
            llmTestResult.style.color = '#f87171';
            llmTestResult.textContent = `❌ ${data.message || 'Connection failed'}`;
          }
        }
      } catch (e) {
        if (llmTestResult) {
          llmTestResult.style.color = '#f87171';
          llmTestResult.textContent = `❌ Error: ${e}`;
        }
      } finally {
        btnTestLlm.disabled = false;
      }
    });
  }

  // Diagnostics: Parser Test
  const btnTestParser = document.getElementById('btn-test-parser');
  const parserTestResult = document.getElementById('parser-test-result');
  if (btnTestParser) {
    btnTestParser.addEventListener('click', async () => {
      btnTestParser.disabled = true;
      if (parserTestResult) {
        parserTestResult.style.color = 'var(--text-muted)';
        parserTestResult.textContent = 'Testing parser service... ⏳';
      }
      try {
        const parser = settingParser ? settingParser.value : 'pypdf';
        const settingLlamaparseKey = document.getElementById('setting-llamaparse-key');
        const settingUnstructuredKey = document.getElementById('setting-unstructured-key');
        const llamaparseKey = settingLlamaparseKey ? settingLlamaparseKey.value.trim() : '';
        const unstructuredKey = settingUnstructuredKey ? settingUnstructuredKey.value.trim() : '';

        const data = await testParserService({
          parser,
          llamaparse_key: llamaparseKey,
          unstructured_key: unstructuredKey
        });

        if (data.status === 'ok') {
          if (parserTestResult) {
            parserTestResult.style.color = '#34d399';
            parserTestResult.textContent = `✅ ${data.message}`;
          }
        } else if (data.status === 'warning') {
          if (parserTestResult) {
            parserTestResult.style.color = '#fbbf24';
            parserTestResult.textContent = `⚠️ ${data.message}`;
          }
        } else {
          if (parserTestResult) {
            parserTestResult.style.color = '#f87171';
            parserTestResult.textContent = `❌ ${data.message || 'Parser test failed'}`;
          }
        }
      } catch (e) {
        if (parserTestResult) {
          parserTestResult.style.color = '#f87171';
          parserTestResult.textContent = `❌ Error: ${e}`;
        }
      } finally {
        btnTestParser.disabled = false;
      }
    });
  }

  // Diagnostics: GraphDB Test
  const btnTestGraphdb = document.getElementById('btn-test-graphdb');
  const graphdbTestResult = document.getElementById('graphdb-test-result');
  if (btnTestGraphdb) {
    btnTestGraphdb.addEventListener('click', async () => {
      btnTestGraphdb.disabled = true;
      if (graphdbTestResult) graphdbTestResult.textContent = 'Testing connection... ⏳';
      try {
        const settingNeo4jUri = document.getElementById('setting-neo4j-uri');
        const settingNeo4jUser = document.getElementById('setting-neo4j-user');
        const settingNeo4jPass = document.getElementById('setting-neo4j-pass');
        const settingSparqlUrl = document.getElementById('setting-sparql-url');

        const data = await testGraphdbConnection({
          target_type: settingGraphdbType ? settingGraphdbType.value : 'neo4j',
          uri: settingNeo4jUri ? settingNeo4jUri.value.trim() : 'bolt://localhost:7687',
          user: settingNeo4jUser ? settingNeo4jUser.value.trim() : 'neo4j',
          password: settingNeo4jPass ? settingNeo4jPass.value.trim() : '',
          endpoint_url: settingSparqlUrl ? settingSparqlUrl.value.trim() : ''
        });

        if (data.success) {
          if (graphdbTestResult) {
            graphdbTestResult.style.color = '#34d399';
            graphdbTestResult.textContent = `✅ ${data.message}`;
          }
        } else {
          if (graphdbTestResult) {
            graphdbTestResult.style.color = '#f87171';
            graphdbTestResult.textContent = `❌ ${data.message}`;
          }
        }
      } catch (e) {
        if (graphdbTestResult) {
          graphdbTestResult.style.color = '#f87171';
          graphdbTestResult.textContent = `❌ Error: ${e}`;
        }
      } finally {
        btnTestGraphdb.disabled = false;
      }
    });
  }
}
