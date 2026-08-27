import { useCallback, useEffect, useState } from "react";

import { DashboardPage } from "../pages/DashboardPage";
import { DemoLoginPage } from "../pages/DemoLoginPage";
import { ProductLandingPage } from "../pages/ProductLandingPage";
import type { DemoUser } from "../types/api";

const DEMO_SESSION_KEY = "rec-qp-demo-user";

export type AppRoute =
  | { page: "landing" }
  | { page: "login" }
  | {
      page: "demo";
      view: "dashboard" | "create" | "queue" | "history";
      paperId?: string;
    };

function routeFromPath(pathname: string): AppRoute | null {
  const segments = pathname.split("/").filter(Boolean);

  if (segments.length === 0) return { page: "landing" };
  if (segments.length === 1 && segments[0] === "login") {
    return { page: "login" };
  }
  if (segments[0] !== "demo") return null;
  if (segments.length === 1) {
    return { page: "demo", view: "dashboard" };
  }
  if (segments[1] === "dashboard" && segments.length === 2) {
    return { page: "demo", view: "dashboard" };
  }
  if (segments[1] === "generate" && segments.length === 2) {
    return { page: "demo", view: "create" };
  }
  if (segments[1] === "review" && segments.length === 2) {
    return { page: "demo", view: "queue" };
  }
  if (segments[1] === "papers" && segments.length === 2) {
    return { page: "demo", view: "history" };
  }
  if (segments[1] === "papers" && segments.length === 3) {
    let paperId: string;
    try {
      paperId = decodeURIComponent(segments[2]);
    } catch {
      return null;
    }
    return {
      page: "demo",
      view: "create",
      paperId,
    };
  }
  return null;
}

export function App() {
  const [route, setRoute] = useState<AppRoute>(() =>
    routeFromPath(window.location.pathname) ?? { page: "landing" },
  );
  const [user, setUser] = useState<DemoUser | null>(() => {
    try {
      const stored = window.sessionStorage.getItem(DEMO_SESSION_KEY);
      return stored ? (JSON.parse(stored) as DemoUser) : null;
    } catch {
      return null;
    }
  });

  const navigate = useCallback((path: string, replace = false) => {
    const next = routeFromPath(path) ?? { page: "landing" as const };
    window.history[replace ? "replaceState" : "pushState"]({}, "", path);
    setRoute(next);
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);

  useEffect(() => {
    const onPopState = () => {
      setRoute(routeFromPath(window.location.pathname) ?? { page: "landing" });
    };
    window.addEventListener("popstate", onPopState);

    const requestedPath = window.location.pathname;
    const requestedRoute = routeFromPath(requestedPath);
    if (!requestedRoute) {
      navigate("/", true);
    } else if (requestedPath === "/demo" || requestedPath === "/demo/") {
      navigate("/demo/dashboard", true);
    }

    return () => window.removeEventListener("popstate", onPopState);
  }, [navigate]);

  useEffect(() => {
    if (route.page === "demo" && !user) navigate("/login", true);
  }, [navigate, route.page, user]);

  const login = (nextUser: DemoUser) => {
    window.sessionStorage.setItem(DEMO_SESSION_KEY, JSON.stringify(nextUser));
    setUser(nextUser);
    navigate("/demo/dashboard");
  };

  const logout = () => {
    window.sessionStorage.removeItem(DEMO_SESSION_KEY);
    setUser(null);
    navigate("/login");
  };

  if (route.page === "login" || (route.page === "demo" && !user)) {
    return <DemoLoginPage onBack={() => navigate("/")} onLogin={login} />;
  }

  return route.page === "demo" && user ? (
    <DashboardPage
      onExitDemo={() => navigate("/")}
      onLogout={logout}
      onNavigate={navigate}
      paperId={route.paperId}
      user={user}
      view={route.view}
    />
  ) : (
    <ProductLandingPage
      onLaunchDemo={() => navigate(user ? "/demo/dashboard" : "/login")}
    />
  );
}
