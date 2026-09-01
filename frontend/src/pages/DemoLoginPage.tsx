import { useState, type FormEvent } from "react";

import { QpMark } from "../components/icons/Icons";
import { ThemeToggle } from "../components/layout/ThemeToggle";
import type { DemoRole, DemoUser } from "../types/api";

interface DemoAccount extends DemoUser {
  password: string;
}

export const DEMO_ACCOUNTS: DemoAccount[] = [
  { username: "faculty@rec.edu", password: "faculty123", displayName: "Faculty User", role: "faculty" },
  { username: "hod@rec.edu", password: "hod123", displayName: "Head of Department", role: "hod" },
  { username: "coe@rec.edu", password: "coe123", displayName: "Controller of Examinations", role: "coe" },
];

const ROLE_LABELS: Record<DemoRole, string> = {
  faculty: "Faculty",
  hod: "HOD",
  coe: "CoE",
};

interface DemoLoginPageProps {
  onBack: () => void;
  onLogin: (user: DemoUser) => void;
}

export function DemoLoginPage({ onBack, onLogin }: DemoLoginPageProps) {
  const [username, setUsername] = useState(DEMO_ACCOUNTS[0].username);
  const [password, setPassword] = useState(DEMO_ACCOUNTS[0].password);
  const [error, setError] = useState<string | null>(null);

  const selectedRole =
    DEMO_ACCOUNTS.find(
      (account) => account.username.toLowerCase() === username.trim().toLowerCase(),
    )?.role ?? null;

  const chooseAccount = (account: DemoAccount) => {
    setUsername(account.username);
    setPassword(account.password);
    setError(null);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const account = DEMO_ACCOUNTS.find(
      (candidate) =>
        candidate.username.toLowerCase() === username.trim().toLowerCase() &&
        candidate.password === password,
    );
    if (!account) {
      setError("The username or password is incorrect.");
      return;
    }
    const { password: _password, ...user } = account;
    onLogin(user);
  };

  return (
    <main className="demo-login-page">
      <header className="demo-login-chrome">
        <button className="text-button" onClick={onBack} type="button">
          {"\u2190"} Product site
        </button>
        <ThemeToggle />
      </header>

      <section className="demo-login-panel" aria-labelledby="demo-login-title">
        <div className="demo-login-brand">
          <span aria-hidden="true" className="demo-login-mark">
            <QpMark />
          </span>
          <strong>QP Studio</strong>
          <span>Rajalakshmi Engineering College</span>
        </div>

        <div className="demo-login-heading">
          <h1 id="demo-login-title">Sign in</h1>
          <p>Use a demo account to open the workspace for that role.</p>
        </div>

        <div
          aria-label="Demo role"
          className="demo-login-roles"
          role="radiogroup"
        >
          {DEMO_ACCOUNTS.map((account) => (
            <button
              aria-checked={selectedRole === account.role}
              className={
                selectedRole === account.role ? "demo-login-role-active" : ""
              }
              key={account.role}
              onClick={() => chooseAccount(account)}
              role="radio"
              type="button"
            >
              {ROLE_LABELS[account.role]}
            </button>
          ))}
        </div>

        <form className="demo-login-form" onSubmit={submit}>
          <label>
            <span>Email</span>
            <input
              autoComplete="username"
              onChange={(event) => {
                setUsername(event.target.value);
                setError(null);
              }}
              type="email"
              value={username}
            />
          </label>
          <label>
            <span>Password</span>
            <input
              autoComplete="current-password"
              onChange={(event) => {
                setPassword(event.target.value);
                setError(null);
              }}
              type="password"
              value={password}
            />
          </label>
          {error && (
            <p className="demo-login-error" role="alert">
              {error}
            </p>
          )}
          <button className="primary-button" type="submit">
            Sign in
          </button>
        </form>

        <p className="demo-login-disclaimer">
          Local demonstration only. These accounts are not production
          authentication.
        </p>
      </section>
    </main>
  );
}
