/** Classify job-log lines for JobsDrawer coloring. */

export type JobLogTone = "error" | "warn" | "ok" | "plain";

const ERROR_RE =
  /\b(?:ERRO|ERROR|FATAL|failed|failure|denied|refused|traceback)\b|^\s*%?\s*error\b/i;
const WARN_RE = /\b(?:WARN(?:ING)?|WRN)\b/i;
const OK_RE =
  /\b(?:Deployed|Wrote|Preserving|succeeded|complete[d]?)\b|Using container runtime:|pinned in per-node/i;

/** Return tone for a single log line (no ANSI; plain text from job capture). */
export function jobLogTone(line: string): JobLogTone {
  const text = line.trim();
  if (!text) return "plain";
  if (ERROR_RE.test(text)) return "error";
  if (WARN_RE.test(text)) return "warn";
  if (OK_RE.test(text)) return "ok";
  return "plain";
}
