import React, { useEffect, useState } from 'react';

import { api } from '../api';
import ConfirmModal from '../components/ConfirmModal';

export default function HistoryPage() {
  const [conversations, setConversations] = useState([]);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [deleteConversationId, setDeleteConversationId] = useState('');
  const [clearAllOpen, setClearAllOpen] = useState(false);

  async function load() {
    try {
      const data = await api.listConversations();
      setConversations(data.conversations || []);
      setStatus('');
    } catch (error) {
      setStatus(error.message);
    }
  }

  async function deleteConversationConfirmed() {
    if (!deleteConversationId) return;
    setBusy(true);
    try {
      await api.deleteConversation(deleteConversationId);
      setStatus('Conversation deleted.');
      await load();
    } catch (error) {
      setStatus(error.message);
    } finally {
      setBusy(false);
      setDeleteConversationId('');
    }
  }

  async function clearAllConversations() {
    setBusy(true);
    try {
      const result = await api.settingsAction({ action: 'clear_conversations' });
      setStatus(result.message || 'All conversations cleared.');
      await load();
    } catch (error) {
      setStatus(error.message);
    } finally {
      setBusy(false);
      setClearAllOpen(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="panel-stack">
      <section className="workspace simple-page">
        <div className="workspace-top row between wrap gap">
          <div>
            <h2>Conversation History</h2>
          </div>
          <div className="row gap">
            <button onClick={load}>Refresh</button>
            <button onClick={() => setClearAllOpen(true)} disabled={!conversations.length}>
              Clear All
            </button>
          </div>
        </div>
        {!conversations.length ? (
          <p className="status workspace-status">No chats.</p>
        ) : (
          <ul className="plain-list">
            {conversations.map((row) => (
              <li key={row.id} className="row between history-row">
                <div className="panel-stack">
                  <strong>{row.title}</strong>
                  <span className="status">{new Date(row.updated_at).toLocaleString()}</span>
                </div>
                <button className="session-x" onClick={() => setDeleteConversationId(row.id)} aria-label="Delete conversation">
                  x
                </button>
              </li>
            ))}
          </ul>
        )}
        {status ? <p className="status workspace-status">{status}</p> : null}
      </section>

      <ConfirmModal
        open={Boolean(deleteConversationId)}
        title="Delete this conversation?"
        message="This action cannot be undone."
        confirmLabel="Delete"
        busy={busy}
        onCancel={() => setDeleteConversationId('')}
        onConfirm={deleteConversationConfirmed}
      />

      <ConfirmModal
        open={clearAllOpen}
        title="Clear all conversation history?"
        message="All saved conversations and message history will be permanently removed."
        confirmLabel="Clear All"
        busy={busy}
        onCancel={() => setClearAllOpen(false)}
        onConfirm={clearAllConversations}
      />
    </div>
  );
}
