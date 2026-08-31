import { appState, updateModelStatus } from '../state.js';
import { extractJsonLdStream } from '../api.js';
import { renderJsonLdData } from '../renderers/jsonldViewer.js';

let extractionTimerInterval = null;
let extractionSeconds = 0;
let extractionAbortController = null;

export function startExtractionTimer() {
  const stepperTimer = document.getElementById('stepper-timer');
  extractionSeconds = 0;
  if (stepperTimer) stepperTimer.textContent = '00:00';
  clearInterval(extractionTimerInterval);
  extractionTimerInterval = setInterval(() => {
    extractionSeconds++;
    const mins = String(Math.floor(extractionSeconds / 60)).padStart(2, '0');
    const secs = String(extractionSeconds % 60).padStart(2, '0');
    if (stepperTimer) stepperTimer.textContent = `${mins}:${secs}`;
  }, 1000);
}

export function stopExtractionTimer() {
  clearInterval(extractionTimerInterval);
}

export function resetStepper() {
  for (let i = 1; i <= 5; i++) {
    const card = document.getElementById(`step-${i}`);
    const status = document.getElementById(`step-status-${i}`);
    if (card) card.className = 'step-card';
    if (status) status.textContent = 'Pending';
  }
}

export function setStepperStep(stepNum, state, message) {
  const card = document.getElementById(`step-${stepNum}`);
  const status = document.getElementById(`step-status-${stepNum}`);
  if (card) {
    card.className = `step-card ${state}`;
  }
  if (status) {
    status.textContent = message || (state === 'active' ? 'Running...' : (state === 'done' ? 'Completed' : 'Failed'));
  }
}

export function appendTerminalLog(msg) {
  const terminalLogs = document.getElementById('terminal-logs');
  if (!terminalLogs) return;
  const line = document.createElement('div');
  line.textContent = msg;
  terminalLogs.appendChild(line);
  terminalLogs.scrollTop = terminalLogs.scrollHeight;
}

export function handleExtractionEvent(event) {
  const terminalPulse = document.getElementById('terminal-pulse');
  const terminalStatusText = document.getElementById('terminal-status-text');

  if (event.type === 'log') {
    const msg = event.message;
    appendTerminalLog(msg);

    // Stepper & Live Tracker
    if (msg.includes('Agent 1/5') || msg.includes('Agent 1:')) {
      setStepperStep(1, 'active', 'Analyzing...');
      updateModelStatus('running', 'Model: Agent 1/5 (Metadata & Cover)');
    } else if (msg.includes('Agent 1 Selesai') || msg.includes('Agent 1 Complete')) {
      setStepperStep(1, 'done', 'Completed');
    } else if (msg.includes('Agent 2/5') || msg.includes('Agent 2:')) {
      setStepperStep(1, 'done', 'Completed');
      setStepperStep(2, 'active', 'Analyzing...');
      updateModelStatus('running', 'Model: Agent 2/5 (Section Outline)');
    } else if (msg.includes('Agent 2 Selesai') || msg.includes('Agent 2 Complete')) {
      setStepperStep(2, 'done', 'Completed');
    } else if (msg.includes('Agent 3/5') || msg.includes('Agent 3:')) {
      setStepperStep(2, 'done', 'Completed');
      setStepperStep(3, 'active', 'Analyzing...');
      updateModelStatus('running', 'Model: Agent 3/5 (Precision Metrics)');
    } else if (msg.includes('Agent 3 Selesai') || msg.includes('Agent 3 Complete')) {
      setStepperStep(3, 'done', 'Completed');
    } else if (msg.includes('Agent 4/5') || msg.includes('Agent 4:')) {
      setStepperStep(3, 'done', 'Completed');
      setStepperStep(4, 'active', 'Formatting...');
      updateModelStatus('running', 'Model: Agent 4/5 (Tables & Data)');
    } else if (msg.includes('Agent 4 Selesai') || msg.includes('Agent 4 Complete')) {
      setStepperStep(4, 'done', 'Completed');
    } else if (msg.includes('Agent 5/5') || msg.includes('Agent 5:')) {
      setStepperStep(4, 'done', 'Completed');
      setStepperStep(5, 'active', 'Extracting...');
      updateModelStatus('running', 'Model: Agent 5/5 (Bibliography)');
    } else if (msg.includes('Agent 5 Selesai') || msg.includes('Agent 5 Complete')) {
      setStepperStep(5, 'done', 'Completed');
    }
  } else if (event.type === 'complete') {
    appendTerminalLog('Extraction 100% Complete.');
    if (terminalPulse) terminalPulse.className = 'terminal-pulse done';
    if (terminalStatusText) terminalStatusText.textContent = 'Agentic Execution: Complete (100%)';
    for (let i = 1; i <= 5; i++) setStepperStep(i, 'done', 'Completed');
    renderJsonLdData(event.result);
    updateModelStatus('ready');
  } else if (event.type === 'error') {
    appendTerminalLog(`Error: ${event.error}`);
    if (terminalPulse) terminalPulse.className = 'terminal-pulse error';
    if (terminalStatusText) terminalStatusText.textContent = 'Agentic Execution: Stopped (Error)';
    updateModelStatus('error', 'Model: Error Occurred');
  }
}

export function initExtractionModule() {
  const btnRunExtraction = document.getElementById('btn-run-extraction');
  const btnCancelExtraction = document.getElementById('btn-cancel-extraction');
  const btnClearTerminal = document.getElementById('btn-clear-terminal');
  const agentStepper = document.getElementById('agent-stepper');
  const terminalContainer = document.getElementById('terminal-container');
  const terminalPulse = document.getElementById('terminal-pulse');
  const terminalStatusText = document.getElementById('terminal-status-text');
  const terminalLogs = document.getElementById('terminal-logs');
  const jsonldResultsContainer = document.getElementById('jsonld-results-container');

  if (btnRunExtraction) {
    btnRunExtraction.addEventListener('click', async () => {
      if (!appState.selectedDoc) return;

      btnRunExtraction.disabled = true;
      btnRunExtraction.classList.add('hidden');
      if (btnCancelExtraction) {
        btnCancelExtraction.classList.remove('hidden');
        btnCancelExtraction.disabled = false;
      }

      // Show and reset stepper & terminal
      if (agentStepper) agentStepper.classList.remove('hidden');
      resetStepper();
      startExtractionTimer();

      if (terminalContainer) terminalContainer.classList.remove('hidden');
      if (terminalPulse) terminalPulse.className = 'terminal-pulse running';
      if (terminalStatusText) terminalStatusText.textContent = 'Agentic Execution: Running...';
      if (terminalLogs) terminalLogs.innerHTML = '';
      if (jsonldResultsContainer) jsonldResultsContainer.classList.add('hidden');

      const provider = appState.settings.provider;
      const model = provider === 'ollama' ? appState.settings.ollamaModel : appState.settings.cloudModel;
      const apiKey = appState.settings.apiKey;
      const baseUrl = appState.settings.baseUrl;

      updateModelStatus('running', `Model: Initializing Extraction (${model})...`);
      extractionAbortController = new AbortController();

      try {
        await extractJsonLdStream(
          {
            fileName: appState.selectedDoc,
            provider,
            model,
            apiKey,
            baseUrl
          },
          extractionAbortController.signal,
          handleExtractionEvent
        );
      } catch (e) {
        if (e.name === 'AbortError') {
          appendTerminalLog('Extraction canceled by user.');
          if (terminalPulse) terminalPulse.className = 'terminal-pulse stopped';
          if (terminalStatusText) terminalStatusText.textContent = 'Agentic Execution: Canceled';
        } else {
          appendTerminalLog(`Error occurred during extraction: ${e}`);
          if (terminalPulse) terminalPulse.className = 'terminal-pulse error';
          if (terminalStatusText) terminalStatusText.textContent = 'Agentic Execution: Stopped (Error / Interrupted)';
        }
      } finally {
        stopExtractionTimer();
        updateModelStatus('ready');
        if (btnCancelExtraction) btnCancelExtraction.classList.add('hidden');
        btnRunExtraction.classList.remove('hidden');
        btnRunExtraction.disabled = false;

        if (terminalPulse?.classList.contains('running')) {
          terminalPulse.className = 'terminal-pulse stopped';
          if (terminalStatusText) terminalStatusText.textContent = 'Agentic Execution: Stopped';
          btnRunExtraction.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg> <span>Extract JSON-LD (Agentic RAG)</span>';
        } else if (terminalPulse?.classList.contains('done')) {
          btnRunExtraction.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg> <span>Re-extract JSON-LD</span>';
        } else {
          btnRunExtraction.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg> <span>Retry Extraction</span>';
        }
      }
    });
  }

  if (btnCancelExtraction) {
    btnCancelExtraction.addEventListener('click', () => {
      if (extractionAbortController) {
        extractionAbortController.abort();
      }
    });
  }

  if (btnClearTerminal && terminalLogs) {
    btnClearTerminal.addEventListener('click', () => {
      terminalLogs.innerHTML = '';
    });
  }
}
