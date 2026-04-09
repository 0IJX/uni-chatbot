import React from 'react';
import { NavLink } from 'react-router-dom';

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <section className="profile-card">
        <div className="avatar-photo logo-avatar">
          <img src="/favicon.png" alt="Local Academic AI Assistant logo" />
        </div>
        <div className="profile-meta">
          <p className="profile-label">Local Academic AI Assistant</p>
          <p className="profile-name">Academic Support</p>
        </div>
      </section>

      <nav className="sidebar-nav">
        <NavLink className="nav-link" to="/chat">Home</NavLink>
        <NavLink className="nav-link" to="/history">History</NavLink>
        <NavLink className="nav-link" to="/help">Help</NavLink>
        <NavLink className="nav-link" to="/settings">Settings</NavLink>
      </nav>
    </aside>
  );
}
