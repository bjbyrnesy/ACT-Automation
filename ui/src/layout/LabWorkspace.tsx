import { useCallback, useEffect, useState } from "react";
import { Navigate, Outlet, useNavigate, useParams } from "react-router-dom";
import {
  deleteTopology,
  getLab,
  getTopology,
  type LabSummary,
} from "../api/client";
import { useActiveTopology } from "../state/activeTopology";
import { LabTabs } from "./LabTabs";
import "./LabWorkspace.css";

export function LabWorkspace() {
  const { labId = "" } = useParams();
  const navigate = useNavigate();
  const { active, setActive, clearActive } = useActiveTopology();
  const [lab, setLab] = useState<LabSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshLab = useCallback(async () => {
    if (!labId) return;
    const next = await getLab(labId);
    setLab(next);
    return next;
  }, [labId]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    void (async () => {
      try {
        const next = await getLab(labId);
        if (cancelled) return;
        setLab(next);
        if (!active.labId || active.labId !== labId || !active.yamlText) {
          const version =
            active.name && next.versions.some((item) => item.name === active.name)
              ? next.versions.find((item) => item.name === active.name)!
              : next.latest;
          const topo = await getTopology(version.name);
          if (cancelled) return;
          setActive({
            path: topo.path,
            name: topo.name ?? version.name,
            labId,
            yamlText: topo.yaml_text ?? "",
            pngBase64: null,
            isDraft: false,
          });
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // Intentionally depend on labId only for initial open/switch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [labId]);

  useEffect(() => {
    if (!labId || !active.name) return;
    void refreshLab().catch(() => {
      /* version list refresh is best-effort */
    });
  }, [active.name, labId, refreshLab]);

  async function switchVersion(filename: string) {
    if (!filename || busy) return;
    setBusy(true);
    setError(null);
    try {
      const topo = await getTopology(filename);
      setActive({
        path: topo.path,
        name: topo.name ?? filename,
        labId,
        yamlText: topo.yaml_text ?? "",
        pngBase64: null,
        isDraft: false,
      });
      await refreshLab();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function removeVersion(filename: string) {
    if (!lab || busy) return;
    const confirmed = window.confirm(
      `Delete version ${filename}? This cannot be undone.`,
    );
    if (!confirmed) return;
    setBusy(true);
    setError(null);
    try {
      await deleteTopology(filename);
      const next = await refreshLab();
      if (!next || next.version_count === 0) {
        clearActive();
        navigate("/");
        return;
      }
      if (active.name === filename) {
        await switchVersion(next.latest.name);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!labId) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="lab-workspace">
      <div className="lab-workspace__banner">
        <div className="lab-workspace__title">
          <span className="lab-workspace__eyebrow">Topology</span>
          <h1>{labId}</h1>
        </div>
        <div className="lab-workspace__controls">
          <label className="lab-workspace__version">
            Version
            <select
              value={active.name ?? ""}
              disabled={busy || !lab}
              onChange={(event) => void switchVersion(event.target.value)}
            >
              {(lab?.versions ?? []).map((version) => (
                <option key={version.name} value={version.name}>
                  {version.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={busy || !active.name || (lab?.version_count ?? 0) < 1}
            onClick={() => active.name && void removeVersion(active.name)}
          >
            Delete version
          </button>
        </div>
      </div>
      {error ? <p className="page-error">{error}</p> : null}
      <LabTabs />
      <Outlet />
    </div>
  );
}
