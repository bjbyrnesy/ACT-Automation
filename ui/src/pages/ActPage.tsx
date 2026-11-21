import { useState } from "react";
import { submitActJob, type Job } from "../api/client";
import { JobsDrawer } from "../components/JobsDrawer";
import { useActiveTopology } from "../state/activeTopology";
import "./OpsPage.css";

export function ActPage() {
  const { active } = useActiveTopology();
  const [tenant, setTenant] = useState("");
  const [deploy, setDeploy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [job, setJob] = useState<Job | null>(null);

  async function run(action: "upload" | "onboard") {
    if (!active.path || busy) return;
    setBusy(true);
    setError("");
    try {
      const next = await submitActJob(action, {
        path: active.path,
        ...(tenant.trim() ? { tenant: tenant.trim() } : {}),
        ...(action === "upload" ? { deploy } : {}),
      });
      setJob(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ops-page">
      <h1>ACT</h1>
      <p>Upload and operate Arista Cloud Test topologies.</p>
      <p>Active topology: {active.name ?? "none"}</p>
      {!active.path ? <p className="page-status">Open or write a topology in Labs before running a job.</p> : null}
      <div className="ops-form">
        <label>Tenant override (optional)<input value={tenant} onChange={(event) => setTenant(event.target.value)} placeholder="Use configured tenant" /></label>
        <label className="ops-form__check"><input type="checkbox" checked={deploy} onChange={(event) => setDeploy(event.target.checked)} />Deploy after upload</label>
        <div className="ops-form__actions">
          <button type="button" disabled={!active.path || busy} onClick={() => void run("upload")}>Upload</button>
          <button type="button" disabled={!active.path || busy} onClick={() => void run("onboard")}>Onboard</button>
        </div>
      </div>
      {error ? <p className="page-error" role="alert">{error}</p> : null}
      <JobsDrawer job={job} onClose={() => setJob(null)} />
    </div>
  );
}
