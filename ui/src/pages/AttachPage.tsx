import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  attachTopology,
  getAttachTargets,
  loadSavedTopology,
  type AttachTargets,
} from "../api/client";
import { useActiveTopology } from "../state/activeTopology";
import "./OpsPage.css";

type TargetKind = "mlag" | "mleaf";

type TargetOption = {
  key: string;
  kind: TargetKind;
  index: number;
  site: string | null;
  label: string;
};

export function AttachPage() {
  const { active, setActive } = useActiveTopology();
  const [host, setHost] = useState("");
  const [siteFilter, setSiteFilter] = useState("");
  const [targetKey, setTargetKey] = useState("");
  const [et, setEt] = useState("");
  const [targets, setTargets] = useState<AttachTargets | null>(null);
  const [targetsError, setTargetsError] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    let cancelled = false;
    if (!active.name || active.isDraft) {
      setTargets(null);
      setTargetsError("");
      return;
    }
    setTargetsError("");
    void getAttachTargets(active.name)
      .then((next) => {
        if (!cancelled) setTargets(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setTargets(null);
          setTargetsError(
            caught instanceof Error ? caught.message : String(caught),
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [active.name, active.path, active.yamlText, active.isDraft]);

  const options = useMemo(() => {
    const next: TargetOption[] = [];
    for (const pair of targets?.mlag_pairs ?? []) {
      next.push({
        key: `mlag:${pair.index}`,
        kind: "mlag",
        index: pair.index,
        site: pair.site,
        label: `MLAG · ${pair.label}`,
      });
    }
    for (const item of targets?.mleafs ?? []) {
      next.push({
        key: `mleaf:${item.index}`,
        kind: "mleaf",
        index: item.index,
        site: item.site,
        label: `Member leaf · ${item.label}`,
      });
    }
    return next;
  }, [targets]);

  const sites = useMemo(() => {
    const values = new Set<string>();
    for (const option of options) {
      if (option.site) values.add(option.site);
    }
    return [...values].sort((a, b) => a.localeCompare(b));
  }, [options]);

  const filtered = useMemo(() => {
    if (!siteFilter) return options;
    return options.filter((option) => option.site === siteFilter);
  }, [options, siteFilter]);

  useEffect(() => {
    if (targetKey && !filtered.some((option) => option.key === targetKey)) {
      setTargetKey("");
    }
  }, [filtered, targetKey]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!active.path || busy) return;
    const selected = options.find((option) => option.key === targetKey);
    if (!selected) {
      setError("Choose a fabric target (MLAG pair or member leaf).");
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const result = await attachTopology({
        path: active.path,
        host: host.trim(),
        ...(selected.kind === "mlag" ? { mlag_pair: selected.index } : {}),
        ...(selected.kind === "mleaf" ? { mleaf: selected.index } : {}),
        ...(et ? { et: Number(et) } : {}),
      });
      setActive(await loadSavedTopology(result));
      setStatus(
        `Attached ${host.trim()} to ${selected.label} → ${result.name}.`,
      );
      setHost("");
      setTargetKey("");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught);
      if (/already exists/i.test(message)) {
        setError(
          `${message} Pick a new host name — each attach creates a distinct node.`,
        );
      } else {
        setError(message);
      }
    } finally {
      setBusy(false);
    }
  }

  const siteHasMleaf = filtered.some((option) => option.kind === "mleaf");
  const siteHasPair = filtered.some((option) => option.kind === "mlag");

  return (
    <div className="ops-page">
      <p>Attach a host to a site fabric edge (MLAG pair or member leaf).</p>
      {!active.path ? (
        <p className="page-status">Open a lab version before attaching hosts.</p>
      ) : null}
      {targetsError ? (
        <p className="page-error" role="alert">
          Could not load attach targets: {targetsError}
        </p>
      ) : null}
      <form className="ops-form" onSubmit={(event) => void submit(event)}>
        <label>
          Host name
          <input
            required
            value={host}
            onChange={(event) => setHost(event.target.value)}
            placeholder="e.g. jumphost-e1"
          />
        </label>
        <label>
          Site
          <select
            value={siteFilter}
            onChange={(event) => setSiteFilter(event.target.value)}
          >
            <option value="">All sites</option>
            {sites.map((site) => (
              <option key={site} value={site}>
                Site {site}
              </option>
            ))}
          </select>
        </label>
        <label>
          Fabric target
          <select
            required
            value={targetKey}
            onChange={(event) => setTargetKey(event.target.value)}
          >
            <option value="">— select where to attach —</option>
            {filtered.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Ethernet port on switch (optional)
          <input
            type="number"
            min="1"
            value={et}
            onChange={(event) => setEt(event.target.value)}
          />
        </label>
        {siteFilter && siteHasPair && !siteHasMleaf ? (
          <p className="ops-form__hint">
            Site {siteFilter} has MLAG leaf pairs but no member leaf — pick an
            MLAG target for this site.
          </p>
        ) : (
          <p className="ops-form__hint">
            Filter by site first. Member leaves exist only where the fabric was
            built with them (often older sites); new sites may only expose MLAG
            pairs.
          </p>
        )}
        <div className="ops-form__actions">
          <button
            type="submit"
            className="btn-primary"
            disabled={!active.path || busy}
          >
            {busy ? "Attaching…" : "Attach"}
          </button>
        </div>
      </form>
      {error ? (
        <p className="page-error" role="alert">
          {error}
        </p>
      ) : null}
      {status ? (
        <p className="page-status" role="status">
          {status}
        </p>
      ) : null}
    </div>
  );
}
