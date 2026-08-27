import { useState, type FormEvent } from "react";

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
      setError("The demo username or password is incorrect.");
      return;
    }
    const { password: _password, ...user } = account;
    onLogin(user);
  };

  return (
    <main className="demo-login-page">
      <section className="demo-login-panel" aria-labelledby="demo-login-title">
        <div className="demo-login-heading">
          <button className="text-button" onClick={onBack} type="button">← Product site</button>
          <h1 id="demo-login-title">Sign in to REC QP Studio</h1>
          <p>Choose a local demo account to test its permitted workflow.</p>
        </div>

        <div className="demo-account-list" aria-label="Demo accounts">
          {DEMO_ACCOUNTS.map((account) => (
            <button
              className={username === account.username ? "demo-account-active" : ""}
              key={account.role}
              onClick={() => chooseAccount(account)}
              type="button"
            >
              <strong>{ROLE_LABELS[account.role]}</strong>
              <span>{account.username}</span>
              <span>{account.password}</span>
            </button>
          ))}
        </div>

        <form className="demo-login-form" onSubmit={submit}>
          <label>
            <span>Username</span>
            <input autoComplete="username" onChange={(event) => setUsername(event.target.value)} value={username} />
          </label>
          <label>
            <span>Password</span>
            <input autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} type="password" value={password} />
          </label>
          {error && <p className="demo-login-error" role="alert">{error}</p>}
          <button className="primary-button" type="submit">Sign in</button>
        </form>

        <p className="demo-login-disclaimer">Local demonstration only. These accounts are not production authentication.</p>
      </section>
    </main>
  );
}
