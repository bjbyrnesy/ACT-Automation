import type { ReactNode } from "react";
import "./TopBar.css";

type TopBarProps = {
  topoLabel?: string;
  clabHost?: string;
  actions?: ReactNode;
};

export function TopBar({
  topoLabel = "Draft",
  clabHost = "local",
  actions,
}: TopBarProps) {
  return (
    <header className="top-bar">
      <div className="top-bar__left">
        <span className="top-bar__topo" title="Active topology">
          {topoLabel}
        </span>
        <span className="top-bar__badge" title="containerlab host">
          {clabHost}
        </span>
      </div>
      <div className="top-bar__actions">{actions}</div>
    </header>
  );
}
