import { Outlet } from "react-router-dom";
import { LeftNav } from "./LeftNav";
import { TopBar } from "./TopBar";
import { TwoPane } from "./TwoPane";
import "./AppShell.css";

export function AppShell() {
  return (
    <div className="app-shell">
      <LeftNav />
      <div className="app-shell__main">
        <TopBar />
        <div className="app-shell__content">
          <header className="app-shell__page-head">
            <Outlet />
          </header>
          <TwoPane />
        </div>
      </div>
    </div>
  );
}
