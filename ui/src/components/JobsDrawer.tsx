import { useEffect, useState } from "react";
import { getJob, type Job } from "../api/client";
import { jobLogTone } from "./jobLogTone";
import "./JobsDrawer.css";

function statusTone(status: string): "error" | "warn" | "ok" | "plain" {
  if (status === "failed") return "error";
  if (status === "succeeded") return "ok";
  if (status === "queued" || status === "running") return "warn";
  return "plain";
}

function CopyIcon() {
  return (
    <svg
      className="jobs-drawer__icon"
      viewBox="0 0 16 16"
      width="14"
      height="14"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M6 2a2 2 0 0 0-2 2v7a1 1 0 0 0 1 1h5a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H6Zm0 1h4a1 1 0 0 1 1 1v7H5V4a1 1 0 0 1 1-1Z"
      />
      <path
        fill="currentColor"
        d="M4 5a1 1 0 0 0-1 1v7a2 2 0 0 0 2 2h5a1 1 0 1 0 0-2H5V6a1 1 0 0 0-1-1Z"
      />
    </svg>
  );
}

async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.select();
  try {
    if (!document.execCommand("copy")) {
      throw new Error("Copy command failed");
    }
  } finally {
    document.body.removeChild(area);
  }
}

function JobLog({ log }: { log: string }) {
  const lines = log.length ? log.split("\n") : ["No log output yet."];
  return (
    <pre className="jobs-drawer__log" aria-label="Job log">
      {lines.map((line, index) => {
        const tone = log.length ? jobLogTone(line) : "plain";
        const key = `${index}:${line.slice(0, 24)}`;
        return (
          <span key={key} className={`jobs-drawer__line jobs-drawer__line--${tone}`}>
            {line}
            {index < lines.length - 1 ? "\n" : null}
          </span>
        );
      })}
    </pre>
  );
}

export function JobsDrawer({ job, onClose }: { job: Job | null; onClose: () => void }) {
  const [current, setCurrent] = useState<Job | null>(job);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

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

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1500);
    return () => window.clearTimeout(timer);
  }, [copied]);

  if (!job) return null;
  const shown = current?.id === job.id ? current : job;
  const tone = statusTone(shown.status);
  const logText = shown.log || "";

  const onCopyLog = () => {
    void (async () => {
      try {
        await copyText(logText.length ? logText : "No log output yet.");
        setCopied(true);
        setError("");
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
      }
    })();
  };

  return (
    <aside className="jobs-drawer" aria-label="Job status">
      <div className="jobs-drawer__head">
        <strong>{shown.kind}</strong>
        <div className="jobs-drawer__actions">
          <button
            type="button"
            className="jobs-drawer__icon-btn"
            onClick={onCopyLog}
            aria-label={copied ? "Log copied" : "Copy job log"}
            title={copied ? "Copied" : "Copy log"}
          >
            <CopyIcon />
            <span aria-live="polite">{copied ? "Copied" : "Copy"}</span>
          </button>
          <button type="button" onClick={onClose} aria-label="Close job status">
            Close
          </button>
        </div>
      </div>
      <p role="status">
        Status:{" "}
        <span className={`jobs-drawer__status jobs-drawer__status--${tone}`}>{shown.status}</span>
      </p>
      {error ? (
        <p className="page-error" role="alert">
          {error}
        </p>
      ) : null}
      {shown.status === "failed" && !shown.log ? <p className="page-error">Job failed.</p> : null}
      <JobLog log={logText} />
    </aside>
  );
}
