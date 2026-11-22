import { NavLink, useParams } from "react-router-dom";
import "./LabTabs.css";

const TABS = [
  { segment: "overview", label: "Overview" },
  { segment: "grow", label: "Grow" },
  { segment: "hosts", label: "Hosts" },
  { segment: "deploy", label: "Deploy" },
] as const;

export function LabTabs() {
  const { labId = "" } = useParams();
  const base = `/labs/${encodeURIComponent(labId)}`;

  return (
    <nav className="lab-tabs" aria-label="Lab">
      {TABS.map((tab) => (
        <NavLink
          key={tab.segment}
          to={`${base}/${tab.segment}`}
          className={({ isActive }) =>
            isActive ? "lab-tabs__link lab-tabs__link--active" : "lab-tabs__link"
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
