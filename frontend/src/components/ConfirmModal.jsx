import React, { useEffect } from 'react';

export default function ConfirmModal({
  open,
  title,
  message,
  requiresPassword = false,
  password = '',
  onPasswordChange,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onCancel,
  onConfirm,
  busy = false,
}) {
  useEffect(() => {
    if (!open) return undefined;
    function onEscape(event) {
      if (event.key === 'Escape' && !busy) {
        onCancel?.();
      }
    }
    window.addEventListener('keydown', onEscape);
    return () => window.removeEventListener('keydown', onEscape);
  }, [open, busy, onCancel]);

  if (!open) return null;

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-card" role="dialog" aria-modal="true" aria-label={title}>
        <h3>{title}</h3>
        <p className="status">{message}</p>
        {requiresPassword ? (
          <label className="panel-stack">
            <span>Admin password</span>
            <input
              type="password"
              value={password}
              onChange={(event) => onPasswordChange?.(event.target.value)}
              placeholder="Enter admin password"
              autoFocus
            />
          </label>
        ) : null}
        <div className="row end gap">
          <button type="button" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button type="button" onClick={onConfirm} disabled={busy}>
            {busy ? 'Working...' : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
