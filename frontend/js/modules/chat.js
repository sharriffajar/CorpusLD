import { appState } from '../state.js';
import { sendChatMessage } from '../api.js';
import { escapeHtml } from '../utils/dom.js';

export function appendChatMessage(role, text, sources = [], duration = null) {
  const chatMessages = document.getElementById('chat-messages');
  if (!chatMessages) return;

  const row = document.createElement('div');
  row.className = `msg-row ${role === 'user' ? 'msg-user' : 'msg-bot'}`;

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = role === 'user' ? '👤' : '🧬';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = `<p>${escapeHtml(text).replace(/\n/g, '<br>')}</p>`;

  if (sources && sources.length > 0) {
    const cit = document.createElement('div');
    cit.className = 'msg-citations';
    cit.innerHTML = `<strong>📌 Citations & Grounded Evidence (${duration}s):</strong><br>` + sources.map(s => `• ${escapeHtml(s)}`).join('<br>');
    bubble.appendChild(cit);
  }

  row.appendChild(avatar);
  row.appendChild(bubble);
  chatMessages.appendChild(row);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

export function initChatModule() {
  const chatForm = document.getElementById('chat-form');
  const chatInput = document.getElementById('chat-input');
  const btnSendChat = document.getElementById('btn-send-chat');
  const chatMessages = document.getElementById('chat-messages');
  const selectChatScope = document.getElementById('select-chat-scope');

  if (!chatForm || !chatInput || !btnSendChat) return;

  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = chatInput.value.trim();
    if (!query) return;

    appendChatMessage('user', query);
    chatInput.value = '';
    btnSendChat.disabled = true;
    const originalBtnIcon = btnSendChat.innerHTML;
    btnSendChat.innerHTML = '<span class="spinner"></span>';

    // Temporary loading indicator bubble
    const loadingRow = document.createElement('div');
    loadingRow.className = 'msg-row msg-bot loading-row';
    loadingRow.innerHTML = `
      <div class="msg-avatar">🧬</div>
      <div class="msg-bubble" style="display: flex; align-items: center; gap: 8px; font-style: italic; color: var(--text-secondary);">
        <span class="spinner"></span> <span>AI is analyzing documents...</span>
      </div>
    `;
    if (chatMessages) {
      chatMessages.appendChild(loadingRow);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    const provider = appState.settings.provider;
    const model = provider === 'ollama' ? appState.settings.ollamaModel : appState.settings.cloudModel;
    const apiKey = appState.settings.apiKey;
    const scopeDoc = selectChatScope?.value ? selectChatScope.value : (appState.selectedDoc || undefined);

    try {
      const data = await sendChatMessage({
        query,
        fileName: scopeDoc,
        provider,
        model,
        apiKey,
        baseUrl: appState.settings.baseUrl
      });
      loadingRow.remove();
      appendChatMessage('bot', data.answer, data.sources, data.duration_seconds);
    } catch (err) {
      loadingRow.remove();
      appendChatMessage('bot', '⚠️ An error occurred / Chat stopped: ' + err);
    } finally {
      btnSendChat.disabled = false;
      btnSendChat.innerHTML = originalBtnIcon;
    }
  });
}
