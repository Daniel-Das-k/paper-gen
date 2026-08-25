import { useState } from "react";

import { DashboardPage } from "../pages/DashboardPage";
import { ProductLandingPage } from "../pages/ProductLandingPage";

export function App() {
  const [demoOpen, setDemoOpen] = useState(false);

  return demoOpen ? (
    <DashboardPage onExitDemo={() => setDemoOpen(false)} />
  ) : (
    <ProductLandingPage onLaunchDemo={() => setDemoOpen(true)} />
  );
}
