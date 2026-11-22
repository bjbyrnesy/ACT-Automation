import { Outlet, useLocation } from "react-router-dom";
import { TopologyPane } from "../components/TopologyPane";
import { LeftNav } from "./LeftNav";
import { TopBar } from "./TopBar";
import "./AppShell.css";

function showTopologyPane(pathname: string): boolean {
  if (pathname === "/new" || pathname.startsWith("/new/")) return true;
  if (pathname.startsWith("/labs/")) return true;
  return false;
}

export function AppShell() {
  const { pathname } = useLocation();
  const pane = showTopologyPane(pathname);

  return (
    <div className="app-shell">
      <LeftNav />
      <div className="app-shell__main">
        <TopBar />
        <div
          className={
            pane
              ? "app-shell__content"
              : "app-shell__content app-shell__content--solo"
          }
        >
          <header className="app-shell__page-head">
            <Outlet />
          </header>
          {pane ? <TopologyPane /> : null}
        </div>
      </div>
    </div>
  );
}
