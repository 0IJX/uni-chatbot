import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import Sidebar from './components/Sidebar';
import ChatPage from './pages/ChatPage';
import HelpPage from './pages/HelpPage';
import SettingsPage from './pages/SettingsPage';
import HistoryPage from './pages/HistoryPage';

function ShellLayout({ children, title }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="content-area">
        <header className="content-topbar">
          <h1>{title}</h1>
        </header>
        {children}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/chat"
          element={
            <ShellLayout title="Home">
              <ChatPage />
            </ShellLayout>
          }
        />
        <Route
          path="/history"
          element={
            <ShellLayout title="History">
              <HistoryPage />
            </ShellLayout>
          }
        />
        <Route
          path="/settings"
          element={
            <ShellLayout title="Settings">
              <SettingsPage />
            </ShellLayout>
          }
        />
        <Route
          path="/help"
          element={
            <ShellLayout title="Help">
              <HelpPage />
            </ShellLayout>
          }
        />
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
