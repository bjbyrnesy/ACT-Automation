import { NavLink } from "react-router-dom";
import "./LeftNav.css";

const NAV_ITEMS = [
  { to: "/labs", label: "Labs" },
  { to: "/create", label: "Create" },
  { to: "/extend", label: "Extend" },
  { to: "/clab", label: "Clab" },
  { to: "/act", label: "ACT" },
  { to: "/attach", label: "Attach" },
  { to: "/show", label: "Show" },
  { to: "/settings", label: "Settings" },
] as const;

export function LeftNav() {
  return (
    <nav className="left-nav" aria-label="Primary">
      <div className="left-nav__brand">ACTA</div>
      <ul className="left-nav__list">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                isActive ? "left-nav__link left-nav__link--active" : "left-nav__link"
              }
            >
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
