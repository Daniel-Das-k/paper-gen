import type { DemoRole } from "../../types/api";
import {
  DashboardIcon,
  ExitIcon,
  FileIcon,
  HistoryIcon,
  ReviewIcon,
  UploadIcon,
} from "../icons/Icons";

export type DemoView = "dashboard" | "create" | "queue" | "history";

interface AppHeaderProps {
  view: DemoView;
  role: DemoRole;
  onViewChange: (view: DemoView) => void;
  onRoleChange: (role: DemoRole) => void;
  onExitDemo: () => void;
}

const ROLE_LABELS: Record<DemoRole, string> = {
  faculty: "Faculty",
  hod: "HOD",
  coe: "CoE",
};

export function AppHeader({
  view,
  role,
  onViewChange,
  onRoleChange,
  onExitDemo,
}: AppHeaderProps) {
  const navigation = [
    ["dashboard", "Dashboard", DashboardIcon],
    ["create", "Generate paper", UploadIcon],
    ["queue", "Review queue", ReviewIcon],
    ["history", "Question papers", HistoryIcon],
  ] as const;

  return (
    <aside className="app-sidebar">
      <button className="demo-brand" onClick={onExitDemo} type="button">
        <span aria-hidden="true" className="demo-brand-mark">
          <FileIcon />
        </span>
        <span className="demo-brand-copy">
          <strong>REC QP Studio</strong>
          <span>Rajalakshmi Engineering College</span>
        </span>
      </button>

      <nav aria-label="Primary navigation" className="demo-nav">
        {navigation.map(([target, label, Icon]) => (
            <button
              className={view === target ? "demo-nav-active" : ""}
              key={target}
              onClick={() => onViewChange(target)}
              type="button"
            >
              <Icon />
              <span>{label}</span>
            </button>
        ))}
      </nav>

      <div className="demo-sidebar-footer">
        <label className="demo-role-select">
          <span className="demo-role-avatar" aria-hidden="true">
            {ROLE_LABELS[role].slice(0, 1)}
          </span>
          <span className="demo-role-copy">
            <strong>Demo user</strong>
            <span>Viewing as {ROLE_LABELS[role]}</span>
          </span>
          <select
            aria-label="Viewing role"
            onChange={(event) => onRoleChange(event.target.value as DemoRole)}
            value={role}
          >
            {(Object.keys(ROLE_LABELS) as DemoRole[]).map((value) => (
              <option key={value} value={value}>
                {ROLE_LABELS[value]}
              </option>
            ))}
          </select>
        </label>
        <button className="demo-exit" onClick={onExitDemo} type="button">
          <ExitIcon />
          <span>Back to product site</span>
        </button>
      </div>
    </aside>
  );
}
