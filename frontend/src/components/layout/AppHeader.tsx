import { SettingsIcon, SparkIcon } from "../icons/Icons";

interface AppHeaderProps {
  onNewPaper: () => void;
}

export function AppHeader({ onNewPaper }: AppHeaderProps) {
  return (
    <header className="app-header">
      <div className="header-inner">
        <button className="brand" onClick={onNewPaper} type="button">
          <span className="brand-mark">
            <SparkIcon />
          </span>
          <span>Paperly</span>
        </button>

        <div className="institution-switcher">
          <span className="institution-icon">C</span>
          <span className="institution-name">College workspace</span>
          <span className="institution-chevron">⌄</span>
        </div>

        <nav aria-label="Primary navigation" className="primary-nav">
          <button className="nav-link nav-link-active" onClick={onNewPaper} type="button">
            Generate
          </button>
          <a className="nav-link" href="#recent-papers">
            Papers
          </a>
          <a className="nav-link" href="#paper-pattern">
            Pattern
          </a>
        </nav>

        <div className="header-actions">
          <button aria-label="Settings" className="icon-button" type="button">
            <SettingsIcon />
          </button>
          <button aria-label="Account menu" className="avatar-button" type="button">
            DD
          </button>
        </div>
      </div>
    </header>
  );
}
