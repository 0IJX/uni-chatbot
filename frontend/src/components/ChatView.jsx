import React from 'react';

function sourceLabel(sourceMap, sourceId) {
  if (!sourceId) return 'Unknown source';
  return sourceMap?.[sourceId] || sourceId;
}

export default function ChatView({ messages, sourceMap }) {
  if (!messages.length) {
    return (
      <section className="chat-empty">
        <h3>Start a chat</h3>
      </section>
    );
  }

  return (
    <div className="chat-log">
      {messages.map((msg) => (
        <article key={msg.id} className={`bubble ${msg.role === 'user' ? 'user' : 'assistant'}`}>
          <strong>{msg.role === 'user' ? 'You' : 'Assistant'}</strong>
          <p>{msg.content}</p>
          {msg.role === 'assistant' && Array.isArray(msg.citations) && msg.citations.length > 0 ? (
            <details className="evidence-panel">
              <summary>Evidence ({msg.citations.length})</summary>
              <ul className="evidence-list">
                {msg.citations.map((item) => (
                  <li key={`${msg.id}_${item.chunk_id}`} className="evidence-item">
                    <div className="evidence-head">
                      <span>{sourceLabel(sourceMap, item.source_id)}</span>
                      <span>score {Number(item.score).toFixed(2)}</span>
                    </div>
                    <div className="evidence-meta">
                      <code>{item.chunk_id}</code>
                      {item.section_title ? <span>{item.section_title}</span> : null}
                      {item.page_start ? (
                        <span>
                          p.{item.page_start}
                          {item.page_end && item.page_end !== item.page_start ? `-${item.page_end}` : ''}
                        </span>
                      ) : null}
                    </div>
                    <p>{item.preview}</p>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </article>
      ))}
    </div>
  );
}
