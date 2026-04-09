const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:4000';

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail ?? 'Request failed');
  }
  return payload;
}

async function parseSse(response, handlers) {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    while (buffer.includes('\n\n')) {
      const idx = buffer.indexOf('\n\n');
      const rawEvent = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);

      const eventLine = rawEvent.match(/^event:\s*(.+)$/m);
      const dataLine = rawEvent.match(/^data:\s*(.+)$/m);
      const eventName = eventLine ? eventLine[1].trim() : 'message';
      const data = dataLine ? JSON.parse(dataLine[1]) : {};

      if (eventName === 'meta' && handlers?.onMeta) handlers.onMeta(data);
      if (eventName === 'token' && handlers?.onToken) handlers.onToken(data.token ?? '');
      if (eventName === 'done' && handlers?.onDone) handlers.onDone(data);
    }
  }
}

export const api = {
  health: () => request('/api/health'),

  listConversations: (conversationId) =>
    request(`/api/conversations${conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : ''}`),

  createConversation: (title = 'New Chat', sourceId = '') =>
    request('/api/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, source_id: sourceId || undefined }),
    }),

  deleteConversation: (conversationId) =>
    request(`/api/conversations?conversation_id=${encodeURIComponent(conversationId)}`, {
      method: 'DELETE',
    }),

  deleteSource: (sourceId) =>
    request(`/api/sources?source_id=${encodeURIComponent(sourceId)}`, {
      method: 'DELETE',
    }),

  settingsAction: ({ action, sourceId, adminPassword }) =>
    request('/api/settings/actions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action,
        source_id: sourceId || undefined,
        admin_password: adminPassword || undefined,
      }),
    }),

  chat: ({ message, conversationId, sourceId }) =>
    request('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, conversation_id: conversationId || undefined, source_id: sourceId || undefined }),
    }),

  chatStream: async ({ message, conversationId, sourceId, handlers }) => {
    const response = await fetch(`${API_BASE}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, conversation_id: conversationId || undefined, source_id: sourceId || undefined }),
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail ?? 'Streaming failed');
    }

    await parseSse(response, handlers);
  },

  uploadFiles: (files, conversationId = '') => {
    const form = new FormData();
    files.forEach((file) => form.append('files', file));
    const query = conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : '';
    return request(`/api/upload${query}`, {
      method: 'POST',
      body: form,
    });
  },

  uploadUrl: ({ url, conversationId }) =>
    request('/api/upload-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        conversation_id: conversationId || undefined,
      }),
    }),
};
