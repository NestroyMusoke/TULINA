import {
  Activity,
  Building2,
  ClipboardCheck,
  LayoutDashboard,
  Radio,
  Smartphone,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { useTulina } from "../state/TulinaContext";
import type { DemoRole } from "../types";

const navigation = [
  { to: "/judge", label: "Judge Demo", icon: ClipboardCheck },
  { to: "/district", label: "District View", icon: LayoutDashboard },
  { to: "/network", label: "Stock network", icon: Building2 },
  { to: "/facility", label: "Facility phone", icon: Smartphone },
  { to: "/audit", label: "Activity", icon: Activity },
];

export function Shell() {
  const { role, setRole, online } = useTulina();
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            T
          </div>
          <div>
            <strong>Tulina</strong>
            <span>District stock coordination</span>
          </div>
        </div>
        <nav>
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
              <Icon size={19} strokeWidth={1.8} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-note">
          <Radio size={17} aria-hidden="true" />
          <span>Quiet background watch</span>
          <strong>70 stock positions</strong>
        </div>
      </aside>
      <div className="app-column">
        <header className="topbar">
          <div className={`network-state ${online ? "online" : "offline"}`} role="status">
            <span aria-hidden="true" />
            {online ? "Connected" : "Offline"}
          </div>
          <label className="role-select">
            <span>Demo role</span>
            <select value={role} onChange={(event) => setRole(event.target.value as DemoRole)}>
              <option value="dho_approver">District Health Officer</option>
              <option value="facility_worker">Facility worker</option>
              <option value="auditor">Auditor</option>
            </select>
          </label>
        </header>
        <main id="main-content" tabIndex={-1}>
          <Outlet />
        </main>
        <nav className="mobile-nav" aria-label="Mobile navigation">
          {navigation.slice(0, 4).map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
              <Icon size={20} aria-hidden="true" />
              <span>{label.replace(" View", "")}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
