import type { MouseEvent } from "react";

import type { DemoUser } from "../../types/api";
import {
  DashboardIcon,
  ExitIcon,
  FileIcon,
  HistoryIcon,
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
      ["dashboard", "CoE dashboard", DashboardIcon],
      ["queue", "Final review", ReviewIcon],
      ["history", "Decision history", HistoryIcon],
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
          <FileIcon />
        </span>
        <span className="demo-brand-copy">
          <strong>REC QP Studio</strong>
          <span>Rajalakshmi Engineering College</span>
        </span>
      </a>

      <nav aria-label="Primary navigation" className="demo-nav">
        {navigation.map(([target, label, Icon]) => (
            <a
              aria-current={view === target ? "page" : undefined}
              className={view === target ? "demo-nav-active" : ""}
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
      </nav>

      <div className="demo-sidebar-footer">
        <div className="demo-role-select">
          <span className="demo-role-avatar" aria-hidden="true">
            {ROLE_LABELS[user.role].slice(0, 1)}
          </span>
          <span className="demo-role-copy">
            <strong>{user.displayName}</strong>
            <span>{ROLE_LABELS[user.role]} demo account</span>
          </span>
        </div>
        <button
          className="demo-exit"
          onClick={onLogout}
          type="button"
        >
          <ExitIcon />
          <span>Sign out</span>
        </button>
      </div>
    </aside>
  );
}
