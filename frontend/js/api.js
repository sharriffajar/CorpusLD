/**
 * Unified Backend API Client & SSE Stream Handler
 */

export async function fetchSystemStatus() {
  const res = await fetch('/api/status');
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

export async function fetchDocuments() {
  const res = await fetch('/api/documents');
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

export async function deleteDocument(name) {
  const res = await fetch(`/api/documents/${encodeURIComponent(name)}`, {
    method: 'DELETE'
  });
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

export async function clearWorkspace() {
  const res = await fetch('/api/workspace/clear', {
    method: 'POST'
  });
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

export async function uploadFiles(fileList) {
  const formData = new FormData();
  for (let i = 0; i < fileList.length; i++) {
    formData.append('files', fileList[i]);
  }
  const res = await fetch('/api/upload', {
    method: 'POST',
    body: formData
  });
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

export async function syncKnowledgeBase(parserSettings) {
  const res = await fetch('/api/sync', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      parser: parserSettings.parser,
      llamaparse_key: parserSettings.llamaparseKey,
      unstructured_key: parserSettings.unstructuredKey
    })
  });
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

export async function fetchExistingJsonLd(fileName) {
  const res = await fetch(`/api/jsonld/${encodeURIComponent(fileName)}`);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

export async function extractJsonLdStream(params, signal, onEvent) {
  const response = await fetch('/api/extract-jsonld-stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal: signal,
    body: JSON.stringify({
      file_name: params.fileName,
      llm_provider: params.provider,
      llm_model: params.model,
      api_key: params.apiKey,
      base_url: params.baseUrl
    })
  });

  if (!response.ok) {
    throw new Error(`Server returned status ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop();

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('data:')) {
        const jsonStr = trimmed.replace(/^data:\s*/, '').trim();
        if (jsonStr) {
          try {
            const event = JSON.parse(jsonStr);
            onEvent(event);
          } catch (err) {
            console.warn('Failed to parse SSE JSON:', jsonStr, err);
          }
        }
      }
    }
  }

  if (buffer && buffer.trim().startsWith('data:')) {
    try {
      const event = JSON.parse(buffer.trim().replace(/^data:\s*/, ''));
      onEvent(event);
    } catch (e) {}
  }
}

export async function sendChatMessage(params) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: params.query,
      file_name: params.fileName,
      llm_provider: params.provider,
      llm_model: params.model,
      api_key: params.apiKey,
      base_url: params.baseUrl
    })
  });
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return await res.json();
}

export async function testLlmConnection(params) {
  const res = await fetch('/api/diagnostics/llm/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params)
  });
  return await res.json();
}

export async function testParserService(params) {
  const res = await fetch('/api/diagnostics/parser/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params)
  });
  return await res.json();
}

export async function testGraphdbConnection(params) {
  const res = await fetch('/api/enterprise/graphdb/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params)
  });
  return await res.json();
}

export async function syncGraphdb(params) {
  const res = await fetch('/api/enterprise/graphdb/sync', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params)
  });
  return await res.json();
}

export function getExportUrl(format, docName) {
  const encoded = encodeURIComponent(docName);
  if (format === 'ttl') return `/api/export/ttl/${encoded}`;
  if (format === 'bibtex') return `/api/export/bibtex/${encoded}`;
  if (format === 'ris') return `/api/export/ris/${encoded}`;
  if (format === 'csl') return `/api/export/csl/${encoded}`;
  if (format === 'cypher') return `/api/export/cypher/${encoded}`;
  if (format === 'graph') return `/api/export/graph/${encoded}`;
  return `/api/export/${encoded}`;
}
