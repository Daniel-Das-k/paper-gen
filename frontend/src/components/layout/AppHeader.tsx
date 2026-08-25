import type { DemoRole } from "../../types/api";

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
  return (
    <header className="app-header">
      <div className="header-inner demo-header-inner">
        <button
          className="demo-brand"
          onClick={onExitDemo}
          type="button"
        >
          <strong>REC Question Paper Studio</strong>
          <span>Local demonstration</span>
        </button>

        <nav aria-label="Primary navigation" className="demo-nav">
          {([
            ["dashboard", "Dashboard"],
            ["create", "Create paper"],
            ["queue", "Review queue"],
            ["history", "Paper history"],
          ] as const).map(([target, label]) => (
            <button
              className={view === target ? "demo-nav-active" : ""}
              key={target}
              onClick={() => onViewChange(target)}
              type="button"
            >
              {label}
            </button>
          ))}
        </nav>

        <label className="demo-role-select">
          <span>Viewing as</span>
          <select
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
      </div>
    </header>
  );
}
