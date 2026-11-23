import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { listLabs, type LabSummary } from "../api/client";
import "./LeftNav.css";

const PRIMARY = [
  { to: "/new", label: "New lab", end: true },
  { to: "/settings", label: "Settings", end: true },
] as const;

const LAB_TABS = new Set(["overview", "grow", "hosts", "deploy"]);

function labIdFromPath(pathname: string): string | null {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "labs" && parts[1]) {
    return decodeURIComponent(parts[1]);
  }
  return null;
}

function tabFromPath(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  // /labs/:labId/:tab
  if (parts[0] === "labs" && parts.length >= 3 && LAB_TABS.has(parts[2])) {
    return parts[2];
  }
  return "overview";
}

export function LeftNav() {
  const navigate = useNavigate();
  const location = useLocation();
  const routeLabId = useMemo(
    () => labIdFromPath(location.pathname),
    [location.pathname],
  );
  const [labs, setLabs] = useState<LabSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setLabs(await listLabs());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Refresh the list when returning from create/write, not on every in-lab tab click.
  const pathKey =
    location.pathname === "/new"
      ? "new"
      : location.pathname.startsWith("/labs/")
        ? "lab"
        : location.pathname;
  const prevPath = useRef(pathKey);
  useEffect(() => {
    if (prevPath.current === pathKey) return;
    const leftCreate = prevPath.current === "new" && pathKey !== "new";
    prevPath.current = pathKey;
    if (leftCreate || pathKey === "/") {
      void load();
    }
  }, [pathKey, load]);

  function openLab(id: string) {
    if (id === routeLabId) return;
    const tab = tabFromPath(location.pathname);
    navigate(`/labs/${encodeURIComponent(id)}/${tab}`);
  }

  return (
    <nav className="left-nav" aria-label="Primary">
      <div className="left-nav__brand">ACTA</div>

      <div className="left-nav__section">
        <div className="left-nav__section-head">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              isActive
                ? "left-nav__section-title left-nav__section-title--active"
                : "left-nav__section-title"
            }
          >
            Topologies
          </NavLink>
          <button
            type="button"
            className="left-nav__icon-btn"
            title="Refresh topologies"
            onClick={() => void load()}
          >
            ↻
          </button>
        </div>
        {error ? <p className="left-nav__error">{error}</p> : null}
        {loading && labs.length === 0 ? (
          <p className="left-nav__empty">Loading…</p>
        ) : labs.length === 0 ? (
          <p className="left-nav__empty">No topologies yet.</p>
        ) : (
          <ul className="left-nav__list left-nav__list--topos">
            {labs.map((lab) => {
              const active = routeLabId === lab.id;
              return (
                <li key={lab.id}>
                  <button
                    type="button"
                    className={
                      active
                        ? "left-nav__topo left-nav__topo--active"
                        : "left-nav__topo"
                    }
                    title={`${lab.version_count} version${lab.version_count === 1 ? "" : "s"} · latest ${lab.latest.name}`}
                    onClick={() => openLab(lab.id)}
                  >
                    <span className="left-nav__topo-name">{lab.id}</span>
                    <span className="left-nav__topo-meta">
                      {lab.version_count}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <ul className="left-nav__list left-nav__list--primary">
        {PRIMARY.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                isActive
                  ? "left-nav__link left-nav__link--active"
                  : "left-nav__link"
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
