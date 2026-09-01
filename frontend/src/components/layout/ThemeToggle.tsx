import { useState } from "react";

import { toggleTheme } from "../../theme";

interface ThemeToggleProps {
  variant?: "icon" | "row";
}

export function ThemeToggle({ variant = "icon" }: ThemeToggleProps) {
  const [dark, setDark] = useState(
    () => document.documentElement.classList.contains("dark"),
  );

  const glyph = (
    <svg
      aria-hidden="true"
      className={dark ? "theme-glyph theme-glyph-sun" : "theme-glyph theme-glyph-moon"}
      fill="none"
      key={dark ? "sun" : "moon"}
      viewBox="0 0 24 24"
    >
      {dark ? (
        <>
          <circle
            cx="12"
            cy="12"
            pathLength={1}
            r="4"
            stroke="currentColor"
            strokeWidth="1.6"
          />
          <path
            d="M12 3.5v1.6M12 18.9v1.6M4.6 4.6l1.1 1.1M18.3 18.3l1.1 1.1M3.5 12h1.6M18.9 12h1.6M4.6 19.4l1.1-1.1M18.3 5.7l1.1-1.1"
            pathLength={1}
            stroke="currentColor"
            strokeLinecap="round"
            strokeWidth="1.6"
          />
        </>
      ) : (
        <path
          d="M16.5 13.2A6.2 6.2 0 0 1 10.8 7.5 6.4 6.4 0 1 0 16.5 13.2Z"
          pathLength={1}
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.6"
        />
      )}
    </svg>
  );

  return (
    <button
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className={variant === "row" ? "demo-nav-item" : "theme-toggle"}
      onClick={() => setDark(toggleTheme() === "dark")}
      type="button"
    >
      {glyph}
      {variant === "row" ? <span>Appearance</span> : null}
    </button>
  );
}
