import React from 'react';

export default function HelpPage() {
  return (
    <div className="panel-stack">
      <section className="workspace simple-page">
        <h2>Quick guide</h2>
        <ul className="plain-list">
          <li>Go to Home, type your message, and press Enter to send.</li>
          <li>Use Shift + Enter if you want a new line.</li>
          <li>Catalog is used by default.</li>
          <li>In Home, you can pick a source from the source dropdown.</li>
          <li>If a source is selected, answers focus on that source.</li>
        </ul>

        <h3>Settings page</h3>
        <ul className="plain-list">
          <li>Upload files with drag and drop or browse.</li>
          <li>Supported: txt, md, json, pdf, docx, csv, xlsx.</li>
          <li>Paste links in Ingest from link. Google Sheets links are supported.</li>
          <li>Delete one uploaded source or clear all uploaded files.</li>
          <li>Clear conversation history or clear all data.</li>
        </ul>

        <h3>History page</h3>
        <ul className="plain-list">
          <li>See all saved chats.</li>
          <li>Delete one chat or clear all chats.</li>
        </ul>

        <h3>Answer behavior</h3>
        <ul className="plain-list">
          <li>The assistant tries to use the best source for your question.</li>
          <li>If evidence is missing, it says that clearly.</li>
          <li>It should not guess exact dates, times, or locations.</li>
        </ul>
      </section>
    </div>
  );
}
