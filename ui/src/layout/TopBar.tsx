import { useEffect, useState, type ReactNode } from "react";
import { useActiveTopology } from "../state/activeTopology";
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
        if (!response.ok) {
          return;
        }
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

  const topoLabel = active.name
    ? active.name
    : active.isDraft
      ? "Draft"
      : active.yamlText
        ? "Active"
        : "Draft";

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
