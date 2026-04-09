import React, { useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../api';
import ConfirmModal from '../components/ConfirmModal';

const ADMIN_REQUIRED_ACTIONS = new Set(['clear_uploads', 'clear_all', 'reset_local_state']);

export default function SettingsPage() {
  const inputRef = useRef(null);
  const [sources, setSources] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [status, setStatus] = useState('');
  const [lastUploads, setLastUploads] = useState([]);
  const [busy, setBusy] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [urlInput, setUrlInput] = useState('');
  const [selectedSourceId, setSelectedSourceId] = useState('');
  const [modalAction, setModalAction] = useState(null);
  const [adminPassword, setAdminPassword] = useState('');

  const uploadSources = useMemo(
    () => sources.filter((item) => item.kind === 'upload'),
    [sources]
  );

  async function loadState() {
    const data = await api.listConversations();
    setSources(data.sources || []);
    setConversations(data.conversations || []);
    if (selectedSourceId && !(data.sources || []).some((item) => item.id === selectedSourceId)) {
      setSelectedSourceId('');
    }
  }

  async function onFilesSelected(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setBusy(true);
    try {
      const response = await api.uploadFiles(files);
      const count = response.uploaded?.length || 0;
      setLastUploads(response.uploaded || []);
      setStatus(`Uploaded ${count} file(s).`);
      await loadState();
    } catch (error) {
      setLastUploads([]);
      setStatus(error.message);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  async function ingestUrl() {
    const url = urlInput.trim();
    if (!url || busy) return;
    setBusy(true);
    try {
      const response = await api.uploadUrl({ url });
      setLastUploads(response.uploaded || []);
      const first = (response.uploaded || [])[0];
      const modeLabel =
        first?.ingest_mode === 'google_public'
          ? 'public Google Sheet'
          : first?.ingest_mode === 'google_private_api'
          ? 'private Google Sheets API'
          : first?.ingest_mode || 'URL';
      setStatus(first?.ingest_note ? `${first.ingest_note} (${modeLabel})` : `Link ingested. (${modeLabel})`);
      setUrlInput('');
      await loadState();
    } catch (error) {
      setStatus(error.message);
    } finally {
      setBusy(false);
    }
  }

  function openAction(action, title, message, sourceId = '') {
    setAdminPassword('');
    setModalAction({
      action,
      title,
      message,
      sourceId,
      requiresPassword: ADMIN_REQUIRED_ACTIONS.has(action),
    });
  }

  async function confirmAction() {
    if (!modalAction) return;
    setBusy(true);
    try {
      const payload = {
        action: modalAction.action,
        sourceId: modalAction.sourceId || undefined,
        adminPassword: modalAction.requiresPassword ? adminPassword : undefined,
      };
      const result = await api.settingsAction(payload);
      setStatus(result.message || 'Action completed.');
      setLastUploads([]);
      if (modalAction.action === 'reset_local_state') {
        window.localStorage.clear();
        window.sessionStorage.clear();
      }
      await loadState();
      setModalAction(null);
      setAdminPassword('');
    } catch (error) {
      setStatus(error.message);
    } finally {
      setBusy(false);
    }
  }

  function onDrop(event) {
    event.preventDefault();
    event.stopPropagation();
    setDragActive(false);
    if (busy) return;
    const files = event.dataTransfer?.files;
    if (files?.length) {
      void onFilesSelected(files);
    }
  }

  useEffect(() => {
    void loadState();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="panel-stack">
      <section className="workspace simple-page">
        <h2>Data and sources</h2>

        <div
          className={`upload-dropzone ${dragActive ? 'drag-active' : ''}`}
          onDragEnter={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            if (event.currentTarget.contains(event.relatedTarget)) return;
            setDragActive(false);
          }}
          onDrop={onDrop}
        >
          <h3>{dragActive ? 'Drop files here' : 'Upload files'}</h3>
          <p className="status">{dragActive ? 'Release to upload.' : 'Drag files here or use browse.'}</p>
          <div className="row gap wrap">
            <button onClick={() => inputRef.current?.click()} disabled={busy}>
              {busy ? 'Working...' : 'Browse Files'}
            </button>
            <input
              ref={inputRef}
              type="file"
              multiple
              hidden
              onChange={(event) => onFilesSelected(event.target.files)}
            />
          </div>
          <p className="drop-hint">Supported: txt, md, json, pdf, docx, csv, xlsx</p>
        </div>

        <div className="section-divider" />

        <h3>Ingest from link</h3>
        <div className="row gap wrap">
          <input
            placeholder="https://example.com/course-outline"
            value={urlInput}
            onChange={(event) => setUrlInput(event.target.value)}
          />
          <button onClick={ingestUrl} disabled={busy || !urlInput.trim()}>
            Ingest URL
          </button>
        </div>

        <div className="section-divider" />

        <h3>Uploaded sources</h3>
        {!uploadSources.length ? (
          <p className="status">No files.</p>
        ) : (
          <>
            <label className="panel-stack">
              <span>Select source</span>
              <select value={selectedSourceId} onChange={(event) => setSelectedSourceId(event.target.value)}>
                <option value="">Choose uploaded source</option>
                {uploadSources.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="row gap wrap">
              <button
                onClick={() =>
                  openAction(
                    'delete_source',
                    'Delete selected source?',
                    'This will remove the selected source and its indexed data.',
                    selectedSourceId
                  )
                }
                disabled={!selectedSourceId || busy}
              >
                Delete Selected Source
              </button>
              <button
                onClick={() =>
                  openAction(
                    'clear_uploads',
                    'Clear all uploaded files?',
                    'This removes all uploaded sources. Catalog files will stay.'
                  )
                }
                disabled={busy}
              >
                Clear all uploaded files
              </button>
            </div>
          </>
        )}

        <div className="section-divider" />

        <h3>History & reset</h3>
        <div className="row gap wrap">
          <button
            onClick={() =>
              openAction(
                'clear_conversations',
                'Clear all conversation history?',
                'All saved chats and messages will be deleted.'
              )
            }
            disabled={busy}
          >
            Clear conversation history
          </button>
          <button
            onClick={() =>
              openAction(
                'clear_all',
                'Clear files and history together?',
                'This removes uploaded files and chat history.'
              )
            }
            disabled={busy}
          >
            Clear files + history
          </button>
          <button
            onClick={() =>
              openAction(
                'reset_local_state',
                'Reset local app state?',
                'This clears files, chats, and local browser state. Catalog knowledge stays.'
              )
            }
            disabled={busy}
          >
            Reset local app state
          </button>
        </div>
        {status ? <p className="status workspace-status">{status}</p> : null}
        {lastUploads.length ? (
          <ul className="upload-result-list">
            {lastUploads.map((item) => (
              <li key={item.source_id}>
                <strong>{item.name}</strong> | source <code>{item.source_id}</code> | indexed chunks: {item.chunks_indexed}
                {item.ingest_mode ? ` | mode: ${item.ingest_mode}` : ''}
                {item.ingest_note ? ` | ${item.ingest_note}` : ''}
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <ConfirmModal
        open={Boolean(modalAction)}
        title={modalAction?.title || ''}
        message={modalAction?.message || ''}
        requiresPassword={Boolean(modalAction?.requiresPassword)}
        password={adminPassword}
        onPasswordChange={setAdminPassword}
        confirmLabel="Confirm"
        busy={busy}
        onCancel={() => {
          if (busy) return;
          setModalAction(null);
          setAdminPassword('');
        }}
        onConfirm={confirmAction}
      />
    </div>
  );
}
