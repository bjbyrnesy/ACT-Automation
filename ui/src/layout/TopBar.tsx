import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useActiveTopology } from "../state/activeTopology";
import { ThemePicker } from "../theme/ThemePicker";
import "./TopBar.css";

type TopBarProps = {
  actions?: ReactNode;
};

export function TopBar({ actions }: TopBarProps) {
  const { active } = useActiveTopology();
  const [clabHost, setClabHost] = useState("local");

  useEffect(() => {
    let cancelled = false;
    void fetch("/api/settings")
      .then(async (response) => {
        if (!response.ok) return;
        const body = (await response.json()) as { CLAB_HOST?: string };
        if (!cancelled) {
          const host = (body.CLAB_HOST ?? "").trim();
          setClabHost(host || "local");
        }
      })
      .catch(() => {
        /* keep default */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const inLab = Boolean(active.labId && !active.isDraft);
  const label = active.isDraft
    ? "Draft lab"
    : inLab
      ? active.labId
      : "No lab open";

  return (
    <header className="top-bar">
      <div className="top-bar__left">
        <span className="top-bar__topo" title="Active lab">
          {label}
        </span>
        {inLab && active.name ? (
          <span className="top-bar__badge" title="Open version">
            {active.name}
          </span>
        ) : null}
        <span className="top-bar__badge" title="containerlab host">
          {clabHost}
        </span>
        {active.isDraft ? (
          <span className="top-bar__badge" title="Not written yet">
            draft
          </span>
        ) : null}
        {inLab ? (
          <Link to="/" className="top-bar__switch">
            Close
          </Link>
        ) : null}
      </div>
      <div className="top-bar__actions">
        {actions}
        <ThemePicker compact />
      </div>
    </header>
  );
}
