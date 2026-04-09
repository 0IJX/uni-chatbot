import React, { useEffect, useMemo, useState } from 'react';

import { api } from '../api';
import ChatView from '../components/ChatView';
import ConfirmModal from '../components/ConfirmModal';

export default function ChatPage() {
  const [conversations, setConversations] = useState([]);
  const [sources, setSources] = useState([]);
  const [conversationId, setConversationId] = useState('');
  const [activeSourceId, setActiveSourceId] = useState('');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [status, setStatus] = useState('');
  const [sending, setSending] = useState(false);
  const [deleteConversationId, setDeleteConversationId] = useState('');
  const [deletingConversation, setDeletingConversation] = useState(false);

  const sourceOptions = useMemo(() => [{ id: '', name: 'Auto (catalog default)' }, ...sources], [sources]);
  const sourceMap = useMemo(
    () =>
      Object.fromEntries(
        sources.map((source) => [
          source.id,
          source.kind ? `${source.name} (${source.kind})` : source.name,
        ])
      ),
    [sources]
  );
  const activeSourceLabel = useMemo(() => {
    if (!activeSourceId) return 'Auto (catalog default)';
    return sourceMap[activeSourceId] || activeSourceId;
  }, [activeSourceId, sourceMap]);

  async function refreshList(currentConversationId = conversationId) {
    const data = await api.listConversations(currentConversationId || undefined);
    setConversations(data.conversations || []);
    setSources(data.sources || []);
    if (currentConversationId) {
      setMessages(data.messages || []);
      setActiveSourceId(data.active_source_id || '');
    }
  }

  async function createNewConversation() {
    const data = await api.createConversation('New Chat', activeSourceId || undefined);
    const nextId = data.conversation?.id || '';
    setConversationId(nextId);
    setMessages([]);
    setStatus('');
    await refreshList(nextId);
  }

  async function openConversation(id) {
    setConversationId(id);
    await refreshList(id);
  }

  async function removeConversationConfirmed() {
    if (!deleteConversationId) return;
    setDeletingConversation(true);
    try {
      await api.deleteConversation(deleteConversationId);
      if (conversationId === deleteConversationId) {
        setConversationId('');
        setMessages([]);
      }
      await refreshList('');
    } finally {
      setDeleteConversationId('');
      setDeletingConversation(false);
    }
  }

  async function sendMessage() {
    const message = input.trim();
    if (!message || sending) return;

    setSending(true);
    setStatus('');

    let localConversationId = conversationId;
    if (!localConversationId) {
      const created = await api.createConversation('New Chat', activeSourceId || undefined);
      localConversationId = created.conversation?.id || '';
      setConversationId(localConversationId);
      await refreshList(localConversationId);
    }

    const userMsg = { id: `local_u_${Date.now()}`, role: 'user', content: message };
    const assistantId = `local_a_${Date.now()}`;
    setMessages((prev) => [...prev, userMsg, { id: assistantId, role: 'assistant', content: '', citations: [] }]);
    setInput('');

    try {
      await api.chatStream({
        message,
        conversationId: localConversationId,
        sourceId: activeSourceId,
        handlers: {
          onMeta: (meta) => {
            if (meta?.source_id !== undefined) {
              setActiveSourceId(meta.source_id || '');
            }
          },
          onToken: (token) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId ? { ...msg, content: `${msg.content}${token}` } : msg
              )
            );
          },
          onDone: async (done) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId
                  ? {
                      ...msg,
                      content: done?.reply || msg.content,
                      citations: Array.isArray(done?.citations) ? done.citations : [],
                    }
                  : msg
              )
            );
            await refreshList(localConversationId);
          },
        },
      });
    } catch (error) {
      setStatus(error.message);
    } finally {
      setSending(false);
    }
  }

  function handleComposerKeyDown(event) {
    if (event.key !== 'Enter') return;
    if (event.shiftKey) return;
    if (event.nativeEvent?.isComposing) return;
    event.preventDefault();
    void sendMessage();
  }

  useEffect(() => {
    void refreshList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="panel-stack">
      <section className="workspace">
        <div className="workspace-top row between wrap gap">
          <div>
            <h2>Chat</h2>
          </div>
          <div className="row gap wrap workspace-actions">
            <span className="source-label">{activeSourceLabel}</span>
            <select id="source-select" value={activeSourceId} onChange={(event) => setActiveSourceId(event.target.value)}>
              {sourceOptions.map((source) => (
                <option key={source.id || 'auto'} value={source.id}>
                  {source.name}
                </option>
              ))}
            </select>
            <button onClick={createNewConversation}>New chat</button>
          </div>
        </div>

        <div className="session-strip">
          <div className="row between wrap gap">
            <strong>Chats</strong>
            <span className="status">{conversations.length}</span>
          </div>
          {conversations.length ? (
            <ul className="session-inline-list">
              {conversations.map((conversation) => (
                <li key={conversation.id} className="session-item">
                  <button
                    className={`session-btn ${conversationId === conversation.id ? 'active' : ''}`}
                    onClick={() => openConversation(conversation.id)}
                  >
                    {conversation.title}
                  </button>
                  <button
                    className="session-x"
                    onClick={() => setDeleteConversationId(conversation.id)}
                    aria-label="Delete conversation"
                  >
                    x
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        {status ? (
          <p className="status workspace-status">{status}</p>
        ) : null}

        <ChatView messages={messages} sourceMap={sourceMap} />

        <div className="composer">
          <textarea
            rows={3}
            placeholder="Type your message..."
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleComposerKeyDown}
          />
          <div className="row between wrap gap">
            <p className="status">{sending ? 'Assistant is replying...' : 'Ready'}</p>
            <button onClick={sendMessage} disabled={sending}>
              {sending ? 'Sending...' : 'Send'}
            </button>
          </div>
        </div>
      </section>

      <ConfirmModal
        open={Boolean(deleteConversationId)}
        title="Delete conversation?"
        message="This will permanently remove the selected conversation."
        confirmLabel="Delete"
        busy={deletingConversation}
        onCancel={() => setDeleteConversationId('')}
        onConfirm={removeConversationConfirmed}
      />
    </div>
  );
}
