/**
 * Smoke checks for job log line tones (run: npx tsx scripts/job-log-tone-smoke.ts).
 */
import { jobLogTone } from "../src/components/jobLogTone.ts";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

assert(jobLogTone("Deployment failed: boom") === "error", "failed → error");
assert(jobLogTone('20:42:19 ERRO Failed to pull image') === "error", "ERRO → error");
assert(
  jobLogTone("Error response from daemon: pull access denied") === "error",
  "denied → error",
);
assert(jobLogTone("20:42:19 WARN something odd") === "warn", "WARN → warn");
assert(
  jobLogTone("Using container runtime: docker (explicit)") === "ok",
  "runtime → ok",
);
assert(jobLogTone("Wrote /home/acta/labs/foo.clab.yml") === "ok", "Wrote → ok");
assert(jobLogTone("Deployed mylabv1.") === "ok", "Deployed → ok");
assert(
  jobLogTone("20:42:19 INFO Parsing & checking topology") === "plain",
  "INFO → plain",
);

console.log("job-log-tone-smoke: ok");
