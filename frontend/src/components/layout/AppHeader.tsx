import type { MouseEvent } from "react";

import type { DemoUser } from "../../types/api";
import { ThemeToggle } from "./ThemeToggle";
import {
  DashboardIcon,
  ExitIcon,
  HistoryIcon,
  QpMark,
  ReviewIcon,
  UploadIcon,
} from "../icons/Icons";

export type DemoView = "dashboard" | "create" | "queue" | "history";

export const DEMO_VIEW_PATHS: Record<DemoView, string> = {
  dashboard: "/demo/dashboard",
  create: "/demo/generate",
  queue: "/demo/review",
  history: "/demo/papers",
};

interface AppHeaderProps {
  view: DemoView;
  user: DemoUser;
  onViewChange: (view: DemoView) => void;
  onLogout: () => void;
  onExitDemo: () => void;
}

const ROLE_LABELS: Record<DemoUser["role"], string> = {
  faculty: "Faculty",
  hod: "HOD",
  coe: "CoE",
};

function navigateInApp(
  event: MouseEvent<HTMLAnchorElement>,
  navigate: () => void,
) {
  if (
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey
  ) {
    return;
  }
  event.preventDefault();
  navigate();
}

export function AppHeader({
  view,
  user,
  onViewChange,
  onLogout,
  onExitDemo,
}: AppHeaderProps) {
  const navigation = ({
    faculty: [
      ["dashboard", "Faculty dashboard", DashboardIcon],
      ["create", "Generate paper", UploadIcon],
      ["queue", "Drafts", ReviewIcon],
      ["history", "Generated papers", HistoryIcon],
    ],
    hod: [
      ["dashboard", "Department dashboard", DashboardIcon],
      ["queue", "Approval queue", ReviewIcon],
      ["history", "Department papers", HistoryIcon],
    ],
    coe: [
      ["dashboard", "Examination overview", DashboardIcon],
      ["queue", "Pending decisions", ReviewIcon],
      ["history", "Decision records", HistoryIcon],
    ],
  } as const)[user.role];

  return (
    <aside className="app-sidebar">
      <a
        className="demo-brand"
        href="/"
        onClick={(event) => navigateInApp(event, onExitDemo)}
      >
        <span aria-hidden="true" className="demo-brand-mark">
          <QpMark />
        </span>
        <span className="demo-brand-copy">
          <strong>REC QP Studio</strong>
          <span>Rajalakshmi Engineering College</span>
        </span>
      </a>

      <nav aria-label="Primary navigation" className="demo-nav">
        <div className="demo-nav-section">
          <span className="demo-nav-label">Workspace</span>
          <div className="demo-nav-list">
            {navigation.map(([target, label, Icon]) => (
              <a
                aria-current={view === target ? "page" : undefined}
                className={
                  view === target ? "demo-nav-item is-active" : "demo-nav-item"
                }
                href={DEMO_VIEW_PATHS[target]}
                key={target}
                onClick={(event) =>
                  navigateInApp(event, () => onViewChange(target))
                }
              >
                <Icon />
                <span>{label}</span>
              </a>
            ))}
          </div>
        </div>
      </nav>

      <div className="demo-sidebar-end">
        <div className="demo-sidebar-card">
          <p>Local demonstration. Papers stay on this machine.</p>
          <button onClick={onExitDemo} type="button">
            Product site
          </button>
        </div>
        <div className="demo-sidebar-footer">
          <ThemeToggle variant="row" />
          <div className="demo-role-select">
            <span className="demo-role-avatar" aria-hidden="true">
              {ROLE_LABELS[user.role].slice(0, 1)}
            </span>
            <span className="demo-role-copy">
              <strong>{user.displayName}</strong>
              <span>{ROLE_LABELS[user.role]} demo account</span>
            </span>
          </div>
          <button className="demo-nav-item demo-exit" onClick={onLogout} type="button">
            <ExitIcon />
            <span>Sign out</span>
          </button>
        </div>
      </div>
    </aside>
  );
}
