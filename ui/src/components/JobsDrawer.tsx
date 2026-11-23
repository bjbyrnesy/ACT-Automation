import { useEffect, useState } from "react";
import { getJob, type Job } from "../api/client";
import "./JobsDrawer.css";

export function JobsDrawer({ job, onClose }: { job: Job | null; onClose: () => void }) {
  const [current, setCurrent] = useState<Job | null>(job);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!job) return;
    const controller = new AbortController();
    let timer: number | undefined;
    const poll = async () => {
      try {
        const next = await getJob(job.id, controller.signal);
        if (controller.signal.aborted) return;
        setCurrent(next);
        setError("");
        if (next.status === "queued" || next.status === "running") {
          timer = window.setTimeout(() => void poll(), 1000);
        }
      } catch (caught) {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : String(caught));
      }
    };
    void poll();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [job]);

  if (!job) return null;
  const shown = current?.id === job.id ? current : job;
  return (
    <aside className="jobs-drawer" aria-label="Job status">
      <div className="jobs-drawer__head">
        <strong>{shown.kind}</strong>
        <button type="button" onClick={onClose} aria-label="Close job status">Close</button>
      </div>
      <p role="status">Status: {shown.status}</p>
      {error ? <p className="page-error" role="alert">{error}</p> : null}
      {shown.status === "failed" && !shown.log ? <p className="page-error">Job failed.</p> : null}
      <pre aria-label="Job log">{shown.log || "No log output yet."}</pre>
    </aside>
  );
}
