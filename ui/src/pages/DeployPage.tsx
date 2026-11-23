import { useEffect, useState } from "react";
import { submitActJob, submitClabJob, type Job } from "../api/client";
import { JobsDrawer } from "../components/JobsDrawer";
import { useActiveTopology } from "../state/activeTopology";
import "./OpsPage.css";

type ClabAction = "generate" | "deploy" | "destroy" | "redeploy" | "onboard";
type RuntimeChoice = "" | "docker" | "podman";

const CLAB_ACTIONS: { value: ClabAction; label: string }[] = [
  { value: "generate", label: "Generate" },
  { value: "deploy", label: "Deploy" },
  { value: "destroy", label: "Destroy" },
  { value: "redeploy", label: "Redeploy" },
  { value: "onboard", label: "Onboard" },
];

const RUNTIME_STORAGE_KEY = "acta.clab.runtime";

function asRuntime(raw: unknown): RuntimeChoice {
  return raw === "docker" || raw === "podman" ? raw : "";
}

function readStoredRuntime(): RuntimeChoice {
  try {
    return asRuntime(window.localStorage.getItem(RUNTIME_STORAGE_KEY));
  } catch {
    return "";
  }
}

function writeStoredRuntime(value: RuntimeChoice) {
  try {
    if (value) window.localStorage.setItem(RUNTIME_STORAGE_KEY, value);
    else window.localStorage.removeItem(RUNTIME_STORAGE_KEY);
  } catch {
    /* ignore quota / private mode */
  }
}

export function DeployPage() {
  const { active } = useActiveTopology();
  const [host, setHost] = useState("");
  const [runtime, setRuntime] = useState<RuntimeChoice>(() => readStoredRuntime());
  const [fromAct, setFromAct] = useState(true);
  const [tenant, setTenant] = useState("");
  const [deployAfterUpload, setDeployAfterUpload] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetch("/api/settings")
      .then(async (response) => {
        if (!response.ok) return;
        const body = (await response.json()) as Record<string, unknown>;
        if (cancelled) return;
        const stored = readStoredRuntime();
        const fromSettings = asRuntime(body.CLAB_RUNTIME);
        // Prefer an explicit local choice, then Settings, else Auto.
        setRuntime(stored || fromSettings);
        const configuredHost = String(body.CLAB_HOST ?? "").trim();
        if (configuredHost) setHost(configuredHost);
      })
      .catch(() => {
        /* Deploy still works; settings prefill is best-effort. */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function onRuntimeChange(value: string) {
    const next = asRuntime(value);
    setRuntime(next);
    writeStoredRuntime(next);
    // Persist explicit choices to Settings so destroy/redeploy keep the same
    // runtime after navigation; clearing Auto also clears CLAB_RUNTIME.
    void fetch("/api/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ CLAB_RUNTIME: next }),
    }).catch(() => {
      /* localStorage still keeps the choice for this browser */
    });
  }

  async function runClab(action: ClabAction) {
    if (!active.path || busy) return;
    setBusy(true);
    setError("");
    try {
      setJob(
        await submitClabJob(action, {
          path: active.path,
          ...(host.trim() ? { host: host.trim() } : {}),
          ...(runtime ? { runtime } : {}),
          ...(action === "generate" ? {} : { from_act: fromAct }),
        }),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function runAct(action: "upload" | "onboard") {
    if (!active.path || busy) return;
    setBusy(true);
    setError("");
    try {
      setJob(
        await submitActJob(action, {
          path: active.path,
          ...(tenant.trim() ? { tenant: tenant.trim() } : {}),
          ...(action === "upload" ? { deploy: deployAfterUpload } : {}),
        }),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ops-page">
      <p>Deploy the open lab version with containerlab or ACT.</p>
      {!active.path ? (
        <p className="page-status">Open a lab version before deploying.</p>
      ) : null}

      <form className="ops-form" onSubmit={(event) => event.preventDefault()}>
        <h2 className="ops-form__section">Containerlab</h2>
        <label>
          Host override (optional)
          <input
            value={host}
            onChange={(event) => setHost(event.target.value)}
            placeholder="Use configured host / local"
          />
        </label>
        <label>
          Container runtime
          <select
            value={runtime}
            onChange={(event) => onRuntimeChange(event.target.value)}
          >
            <option value="">Auto (detect on lab host)</option>
            <option value="docker">docker</option>
            <option value="podman">podman</option>
          </select>
        </label>
        <p className="ops-form__hint">
          Choice is saved to Settings / this browser so Deploy and Destroy stay
          aligned. Auto probes the lab host; Docker-only hosts should pick{" "}
          <code>docker</code> if Auto still mis-detects.
        </p>
        <label className="ops-form__check">
          <input
            type="checkbox"
            checked={fromAct}
            onChange={(event) => setFromAct(event.target.checked)}
          />
          Use active ACT topology as source
        </label>
        <div className="ops-form__actions">
          {CLAB_ACTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              disabled={!active.path || busy}
              onClick={() => void runClab(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </form>

      <form className="ops-form" onSubmit={(event) => event.preventDefault()}>
        <h2 className="ops-form__section">ACT / CloudVision</h2>
        <label>
          Tenant override (optional)
          <input
            value={tenant}
            onChange={(event) => setTenant(event.target.value)}
            placeholder="Use configured tenant"
          />
        </label>
        <label className="ops-form__check">
          <input
            type="checkbox"
            checked={deployAfterUpload}
            onChange={(event) => setDeployAfterUpload(event.target.checked)}
          />
          Deploy after upload
        </label>
        <div className="ops-form__actions">
          <button
            type="button"
            className="btn-primary"
            disabled={!active.path || busy}
            onClick={() => void runAct("upload")}
          >
            Upload
          </button>
          <button
            type="button"
            disabled={!active.path || busy}
            onClick={() => void runAct("onboard")}
          >
            Onboard
          </button>
        </div>
      </form>

      {error ? (
        <p className="page-error" role="alert">
          {error}
        </p>
      ) : null}
      <JobsDrawer job={job} onClose={() => setJob(null)} />
    </div>
  );
}
