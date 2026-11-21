import { useState } from "react";
import { submitClabJob, type Job } from "../api/client";
import { JobsDrawer } from "../components/JobsDrawer";
import { useActiveTopology } from "../state/activeTopology";
import "./OpsPage.css";

type Action = "generate" | "deploy" | "destroy" | "redeploy" | "onboard";
const actions: { value: Action; label: string }[] = [
  { value: "generate", label: "Generate" },
  { value: "deploy", label: "Deploy" },
  { value: "destroy", label: "Destroy" },
  { value: "redeploy", label: "Redeploy" },
  { value: "onboard", label: "Onboard" },
];

export function ClabPage() {
  const { active } = useActiveTopology();
  const [host, setHost] = useState("");
  const [fromAct, setFromAct] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [job, setJob] = useState<Job | null>(null);

  async function run(action: Action) {
    if (!active.path || busy) return;
    setBusy(true);
    setError("");
    try {
      const next = await submitClabJob(action, {
        path: active.path,
        ...(host.trim() ? { host: host.trim() } : {}),
        ...(action === "generate" ? {} : { from_act: fromAct }),
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
      <h1>Clab</h1>
      <p>Generate, deploy, and manage containerlab labs.</p>
      <p>Active topology: {active.name ?? "none"}</p>
      {!active.path ? <p className="page-status">Open or write a topology in Labs before running a job.</p> : null}
      <div className="ops-form">
        <label>Host override (optional)<input value={host} onChange={(event) => setHost(event.target.value)} placeholder="Use configured host" /></label>
        <label className="ops-form__check"><input type="checkbox" checked={fromAct} onChange={(event) => setFromAct(event.target.checked)} />Use active ACT topology as source</label>
        <div className="ops-form__actions">
          {actions.map(({ value, label }) => <button key={value} type="button" disabled={!active.path || busy} onClick={() => void run(value)}>{label}</button>)}
        </div>
      </div>
      {error ? <p className="page-error" role="alert">{error}</p> : null}
      <JobsDrawer job={job} onClose={() => setJob(null)} />
    </div>
  );
}
