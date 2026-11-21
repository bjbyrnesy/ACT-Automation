import { Outlet, useLocation } from "react-router-dom";
import { TopologyPane } from "../components/TopologyPane";
import { LeftNav } from "./LeftNav";
import { TopBar } from "./TopBar";
import { TwoPane } from "./TwoPane";
import "./AppShell.css";

export function AppShell() {
  const location = useLocation();
  return (
    <div className="app-shell">
      <LeftNav />
      <div className="app-shell__main">
        <TopBar />
        <div className="app-shell__content">
          <header className="app-shell__page-head">
            <Outlet />
          </header>
          {location.pathname === "/create" || location.pathname === "/show" ? (
            <TopologyPane />
          ) : (
            <TwoPane />
          )}
        </div>
      </div>
    </div>
  );
}
