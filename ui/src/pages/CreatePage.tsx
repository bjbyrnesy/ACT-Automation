import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, previewTopology, writeTopology } from "../api/client";
import type { CapacityBody, PreviewBody, PreviewResult } from "../api/types";
import { useActiveTopology } from "../state/activeTopology";
import { useCreateWizard, type WizardFact } from "../state/createWizard";
import "./CreatePage.css";

const SITE_LETTERS = "ABCDEFGH";

const initial: PreviewBody = {
  hostname_prefix: "",
  serial_prefix: "",
  eos_version: "4.37.0F",
  capacity: {
    fabric_mode: "l3ls",
    max_spines: 4,
    max_leaves: 8,
    max_mleafs_per_pair: 2,
    spines: 2,
    leaves: 4,
    use_case: "datacenter",
    bb_redundancy: "mlag-peer",
    border_redundancy: "mlag-peer",
    bb_count: 2,
    border_count: 2,
    backbone_mode: "hub",
  },
  mlag_pairs: true,
  spine_mlag: false,
  member_leaf_pairs: [],
  member_leaves_per_pair: 0,
  dc_count: 1,
  sites: [],
};

type StepId =
  | "identity"
  | "sites"
  | "role"
  | "size"
  | "capacity"
  | "pairing"
  | "review";

/** Steps whose Next commit changes fabric shape enough to warrant one preview. */
const PREVIEW_AFTER: ReadonlySet<StepId> = new Set([
  "sites",
  "role",
  "size",
  "capacity",
  "pairing",
]);

type StepDef = {
  id: StepId;
  title: string;
  blurb: string;
};

const STEPS: StepDef[] = [
  {
    id: "identity",
    title: "Identity",
    blurb: "Prefixes and EOS version for the new lab.",
  },
  {
    id: "sites",
    title: "Sites",
    blurb: "How many sites, and their names.",
  },
  {
    id: "role",
    title: "Fabric role",
    blurb: "Use case and leaf-spine mode.",
  },
  {
    id: "size",
    title: "Size",
    blurb: "Spines and leaves to deploy now.",
  },
  {
    id: "capacity",
    title: "Capacity",
    blurb: "Reserved growth limits and multi-site backbone.",
  },
  {
    id: "pairing",
    title: "Pairing",
    blurb: "Leaf MLAG pairs and optional member leaves.",
  },
  {
    id: "review",
    title: "Review",
    blurb: "Preview the fabric, then finish to the library.",
  },
];

function defaultSiteName(index: number): string {
  return index < SITE_LETTERS.length
    ? SITE_LETTERS[index]
    : `site${index + 1}`;
}

function identityReady(body: PreviewBody): boolean {
  const serial = body.serial_prefix.trim();
  const host = body.hostname_prefix.trim();
  const eos = body.eos_version.trim();
  return (
    Boolean(serial) &&
    /^[A-Za-z0-9]+$/.test(serial) &&
    Boolean(host) &&
    /^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$/.test(host) &&
    Boolean(eos)
  );
}

function buildFacts(
  body: PreviewBody,
  siteNames: string[],
  pairsText: string,
  stepIndex: number,
): WizardFact[] {
  const facts: WizardFact[] = [];
  const serial = body.serial_prefix.trim();
  const host = body.hostname_prefix.trim();

  if (host || serial) {
    facts.push({ step: "identity", label: "Lab", value: host || serial });
  } else if (stepIndex === 0) {
    facts.push({ step: "identity", label: "Lab", value: "not set yet" });
  }
  if (body.eos_version.trim() && (host || serial)) {
    facts.push({
      step: "identity",
      label: "EOS",
      value: body.eos_version.trim(),
    });
  }

  if (stepIndex >= 1) {
    const sites =
      body.dc_count > 1
        ? siteNames.map((name) => name.trim()).filter(Boolean).join(", ")
        : "single-site";
    facts.push({
      step: "sites",
      label: "Sites",
      value: body.dc_count > 1 ? `${body.dc_count}: ${sites}` : sites,
    });
  }

  if (stepIndex >= 2) {
    facts.push({
      step: "role",
      label: "Fabric",
      value: `${body.capacity.fabric_mode} · ${body.capacity.use_case ?? "default"}`,
    });
  }

  if (stepIndex >= 3) {
    facts.push({
      step: "size",
      label: "Size",
      value: `${body.capacity.spines}S / ${body.capacity.leaves}L`,
    });
  }

  if (stepIndex >= 4) {
    facts.push({
      step: "capacity",
      label: "Reserved",
      value: `max ${body.capacity.max_spines}S / ${body.capacity.max_leaves}L · mleaf ${body.capacity.max_mleafs_per_pair}`,
    });
    if (body.dc_count > 1) {
      facts.push({
        step: "capacity",
        label: "Backbone",
        value: `${body.capacity.bb_count} · ${body.capacity.bb_redundancy}`,
      });
      if (body.capacity.fabric_mode !== "l2ls") {
        facts.push({
          step: "capacity",
          label: "Border",
          value: `${body.capacity.border_count} · ${body.capacity.border_redundancy}`,
        });
      }
    }
  }

  if (stepIndex >= 5) {
    const spineMlag =
      body.capacity.fabric_mode === "l2ls" && body.capacity.spines === 2;
    const parts = [
      body.mlag_pairs ? "leaf MLAG" : "no leaf MLAG",
      spineMlag ? "spine MLAG" : null,
      pairsText.trim() ? `mleaf pairs ${pairsText.trim()}` : null,
    ].filter(Boolean);
    facts.push({
      step: "pairing",
      label: "Pairing",
      value: parts.join(" · "),
    });
  }

  return facts;
}

export function CreatePage() {
  const navigate = useNavigate();
  const { setActive, clearActive } = useActiveTopology();
  const { setWizard } = useCreateWizard();
  const [stepIndex, setStepIndex] = useState(0);
  const [body, setBody] = useState<PreviewBody>(initial);
  const [siteNames, setSiteNames] = useState<string[]>(["A"]);
  const [pairsText, setPairsText] = useState("");
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [previewing, setPreviewing] = useState(false);
  const [writing, setWriting] = useState(false);
  /** Until the user edits hostname, keep it locked to serial (CLI default). */
  const [hostnameTouched, setHostnameTouched] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const quietTimer = useRef<number | null>(null);
  const lastDiagramSig = useRef<string>("");

  const step = STEPS[stepIndex];
  const multiDc = body.dc_count > 1;
  const isL2 = body.capacity.fabric_mode === "l2ls";
  const pairCount = Math.floor(body.capacity.leaves / 2);
  const stepBlurb =
    step.id === "pairing" && isL2
      ? "Leaf MLAG, spine MLAG (always on for dual-spine L2LS), and member leaves."
      : step.id === "pairing"
        ? "Leaf MLAG pairs and optional member leaves. L3LS spines stay independent."
        : step.blurb;

  const syncSites = useCallback((count: number, names: string[]) => {
    const next = Array.from({ length: count }, (_, index) => {
      const existing = names[index]?.trim();
      return existing || defaultSiteName(index);
    });
    setSiteNames(next);
    return next;
  }, []);

  function patch(next: PreviewBody) {
    // Form edits only — do not abort/rebuild the diagram on every keystroke.
    setBody(next);
    setError("");
    setFieldErrors({});
  }

  function capacity<K extends keyof CapacityBody>(key: K, value: CapacityBody[K]) {
    patch({ ...body, capacity: { ...body.capacity, [key]: value } });
  }

  function validateStep(id: StepId): string | null {
    if (id === "identity") {
      if (!body.serial_prefix.trim()) return "Serial prefix is required.";
      if (!/^[A-Za-z0-9]+$/.test(body.serial_prefix.trim())) {
        return "Serial prefix must be alphanumeric.";
      }
      if (!body.hostname_prefix.trim()) return "Hostname prefix is required.";
      if (!/^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$/.test(body.hostname_prefix.trim())) {
        return "Hostname prefix must be alphanumeric with optional dashes.";
      }
      if (!body.eos_version.trim()) return "EOS version is required.";
    }
    if (id === "sites") {
      if (body.dc_count < 1 || body.dc_count > 8) {
        return "Site count must be between 1 and 8.";
      }
      if (multiDc) {
        const cleaned = siteNames.map((name) => name.trim()).filter(Boolean);
        if (cleaned.length !== body.dc_count) {
          return "Name every site.";
        }
        if (new Set(cleaned).size !== cleaned.length) {
          return "Site names must be unique.";
        }
      }
    }
    if (id === "size") {
      if (body.capacity.spines < 1) return "Need at least one spine.";
      if (body.capacity.leaves < 1) return "Need at least one leaf.";
      if (isL2 && body.capacity.spines > 2) {
        return "L2LS fabrics are capped at 2 spines.";
      }
    }
    if (id === "capacity") {
      if (body.capacity.max_spines < body.capacity.spines) {
        return "Maximum spines must be ≥ current spines.";
      }
      if (body.capacity.max_leaves < body.capacity.leaves) {
        return "Maximum leaves must be ≥ current leaves.";
      }
    }
    if (id === "pairing" && body.mlag_pairs && pairsText.trim()) {
      const parsed = pairsText
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean)
        .map(Number);
      if (parsed.some((value) => !Number.isInteger(value) || value < 1 || value > pairCount)) {
        return `Member leaf pairs must be integers from 1 to ${pairCount}.`;
      }
    }
    return null;
  }

  function buildPayloadFrom(
    base: PreviewBody,
    opts?: { sitesOverride?: string[] },
  ): PreviewBody {
    const siteSource =
      opts?.sitesOverride ??
      (base.dc_count > 1
        ? siteNames.map((name) => name.trim()).filter(Boolean)
        : []);
    const sites = base.dc_count > 1 ? siteSource.filter(Boolean) : [];
    const member_leaf_pairs =
      base.mlag_pairs &&
      base.capacity.max_mleafs_per_pair > 0 &&
      pairsText.trim()
        ? pairsText
            .split(",")
            .map((part) => part.trim())
            .filter(Boolean)
            .map(Number)
        : [];
    const l2 = base.capacity.fabric_mode === "l2ls";
    return {
      ...base,
      serial_prefix: base.serial_prefix.trim(),
      hostname_prefix: base.hostname_prefix.trim(),
      eos_version: base.eos_version.trim(),
      sites,
      dc_count: base.dc_count > 1 ? sites.length || base.dc_count : base.dc_count,
      member_leaf_pairs,
      member_leaves_per_pair: member_leaf_pairs.length
        ? Math.max(1, base.member_leaves_per_pair)
        : 0,
      // L2LS with two spines always peers; L3LS never does.
      spine_mlag: l2 && base.capacity.spines === 2,
    };
  }

  function buildPayload(): PreviewBody {
    return buildPayloadFrom(body);
  }

  const runPreview = useCallback(
    async (opts?: { quiet?: boolean; payload?: PreviewBody }) => {
      const quiet = opts?.quiet ?? false;
      const payload = opts?.payload ?? buildPayload();
      if (!identityReady(payload)) return;
      controller.current?.abort();
      const currentController = new AbortController();
      controller.current = currentController;
      const id = ++sequence.current;
      // Only surface spinner/errors for explicit (non-quiet) refreshes.
      if (!quiet) {
        setPreviewing(true);
        setError("");
        setFieldErrors({});
      }
      try {
        const result = await previewTopology(payload, currentController.signal);
        if (id !== sequence.current) return;
        setPreview(result);
        setActive({
          path: null,
          name: null,
          labId: null,
          yamlText: result.yaml_text,
          mgmtIps: null,
          pngBase64: null,
          isDraft: true,
        });
      } catch (caught) {
        if (id !== sequence.current || currentController.signal.aborted) return;
        // Quiet failures keep the last stable diagram; loud ones report.
        if (!quiet) {
          setPreview(null);
          clearActive();
          setError(caught instanceof Error ? caught.message : "Preview failed");
          setFieldErrors(caught instanceof ApiError ? caught.fields : {});
        }
      } finally {
        if (!quiet && id === sequence.current) setPreviewing(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [body, siteNames, pairsText, isL2, setActive, clearActive],
  );

  const resolvedSites = useMemo(() => {
    if (body.dc_count <= 1) return [] as string[];
    return Array.from({ length: body.dc_count }, (_, index) => {
      const name = siteNames[index]?.trim();
      return name || defaultSiteName(index);
    });
  }, [body.dc_count, siteNames]);

  // Sites step is index 1; committed after Next (≥ role).
  const sitesCommitted = stepIndex >= 2;

  // Topology-shaping fields that warrant a live diagram rebuild (debounced, quiet).
  // Reserved max_* caps are omitted — they do not change the drawn fabric.
  const diagramSig = useMemo(
    () =>
      [
        body.dc_count,
        body.dc_count > 1 ? resolvedSites.join("|") : "single",
        body.capacity.fabric_mode,
        body.capacity.spines,
        body.capacity.leaves,
        body.capacity.bb_redundancy,
        body.capacity.bb_count,
        body.capacity.border_redundancy,
        body.capacity.border_count,
        body.mlag_pairs ? 1 : 0,
        body.spine_mlag ? 1 : 0,
        pairsText.trim(),
        body.member_leaves_per_pair,
      ].join("::"),
    [
      body.dc_count,
      resolvedSites,
      body.capacity.fabric_mode,
      body.capacity.spines,
      body.capacity.leaves,
      body.capacity.bb_redundancy,
      body.capacity.bb_count,
      body.capacity.border_redundancy,
      body.capacity.border_count,
      body.mlag_pairs,
      body.spine_mlag,
      pairsText,
      body.member_leaves_per_pair,
    ],
  );

  useEffect(() => {
    const facts = buildFacts(body, siteNames, pairsText, stepIndex);
    setWizard({
      stepIndex,
      stepId: step.id,
      stepTitle: step.title,
      totalSteps: STEPS.length,
      facts,
      previewing,
      sites: resolvedSites,
      sitesCommitted,
    });
  }, [
    body,
    siteNames,
    pairsText,
    stepIndex,
    step.id,
    step.title,
    resolvedSites,
    sitesCommitted,
    previewing,
    setWizard,
  ]);

  // Quiet background refresh after the user pauses (covers number steppers).
  useEffect(() => {
    if (!identityReady(body)) return;
    if (diagramSig === lastDiagramSig.current) return;
    const first = lastDiagramSig.current === "";
    lastDiagramSig.current = diagramSig;
    if (first) return;

    if (quietTimer.current !== null) {
      window.clearTimeout(quietTimer.current);
    }
    // Long enough that click-hold / multi-click on spines/leaves can settle.
    quietTimer.current = window.setTimeout(() => {
      quietTimer.current = null;
      void runPreview({ quiet: true });
    }, 900);

    return () => {
      if (quietTimer.current !== null) {
        window.clearTimeout(quietTimer.current);
        quietTimer.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diagramSig, runPreview]);

  // One preview when landing on Review — not on every form keystroke.
  useEffect(() => {
    if (step.id !== "review") return;
    if (!identityReady(body)) return;
    void runPreview({ quiet: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step.id]);

  useEffect(
    () => () => {
      if (quietTimer.current !== null) {
        window.clearTimeout(quietTimer.current);
      }
      controller.current?.abort();
      setWizard(null);
    },
    [setWizard],
  );

  async function write() {
    if (!preview || writing) return;
    setWriting(true);
    setError("");
    setFieldErrors({});
    try {
      const payload = buildPayload();
      const result = await writeTopology({
        yaml_text: preview.yaml_text,
        stem: payload.hostname_prefix,
      });
      setActive({
        path: result.path,
        name: result.name,
        labId: result.lab_id,
        yamlText: preview.yaml_text,
        mgmtIps: null,
        pngBase64: null,
        isDraft: false,
      });
      navigate(`/labs/${encodeURIComponent(result.lab_id)}/overview`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Write failed");
      setFieldErrors(caught instanceof ApiError ? caught.fields : {});
    } finally {
      setWriting(false);
    }
  }

  function goNext(event?: FormEvent) {
    event?.preventDefault();
    const problem = validateStep(step.id);
    if (problem) {
      setError(problem);
      return;
    }
    setError("");
    const leaving = step.id;
    let committed = body;
    if (leaving === "sites" && body.dc_count > 1) {
      // Persist resolved names before advancing so the diagram boxes match.
      const names = resolvedSites;
      setSiteNames(names);
      committed = { ...body, sites: names, dc_count: names.length };
      setBody(committed);
    }
    setStepIndex((index) => Math.min(index + 1, STEPS.length - 1));
    // One quiet rebuild after topology-shaping steps — never while typing.
    if (PREVIEW_AFTER.has(leaving) && identityReady(committed)) {
      void runPreview({
        quiet: true,
        payload: buildPayloadFrom(committed, {
          sitesOverride:
            committed.dc_count > 1
              ? committed.sites.length
                ? committed.sites
                : resolvedSites
              : [],
        }),
      });
    }
  }

  function goBack() {
    setError("");
    setStepIndex((index) => Math.max(index - 1, 0));
  }

  function goToStep(index: number) {
    // Only revisit completed steps (or stay on current) before Finish.
    if (index < 0 || index > stepIndex || writing) return;
    if (index === stepIndex) return;
    setError("");
    setFieldErrors({});
    setStepIndex(index);
  }

  const progress = useMemo(
    () => ((stepIndex + 1) / STEPS.length) * 100,
    [stepIndex],
  );

  const fieldError = (name: string) =>
    fieldErrors[name] ? (
      <small className="create-form__field-error">{fieldErrors[name]}</small>
    ) : null;

  return (
    <div className="create-page create-page--wizard">
      <div className="create-wizard__head">
        <div>
          <h1>New lab</h1>
          <p>
            Guided create — step {stepIndex + 1} of {STEPS.length}: {step.title}.{" "}
            {stepBlurb}
          </p>
        </div>
        <ol className="create-wizard__steps" aria-label="Wizard steps">
          {STEPS.map((item, index) => {
            const done = index < stepIndex;
            const current = index === stepIndex;
            const reachable = done || current;
            return (
              <li
                key={item.id}
                className={
                  current ? "is-current" : done ? "is-done" : "is-upcoming"
                }
              >
                {reachable ? (
                  <button
                    type="button"
                    className="create-wizard__step-btn"
                    aria-current={current ? "step" : undefined}
                    disabled={writing || current}
                    title={
                      current
                        ? `Current step: ${item.title}`
                        : `Go back to ${item.title}`
                    }
                    onClick={() => goToStep(index)}
                  >
                    <span className="create-wizard__step-index">
                      {index + 1}
                    </span>
                    <span className="create-wizard__step-label">
                      {item.title}
                    </span>
                  </button>
                ) : (
                  <span className="create-wizard__step-static">
                    <span className="create-wizard__step-index">
                      {index + 1}
                    </span>
                    <span className="create-wizard__step-label">
                      {item.title}
                    </span>
                  </span>
                )}
              </li>
            );
          })}
        </ol>
        <div className="create-wizard__bar" aria-hidden="true">
          <div style={{ width: `${progress}%` }} />
        </div>
      </div>

      <form className="create-form" onSubmit={goNext}>
        {step.id === "identity" ? (
          <fieldset disabled={writing}>
            <legend>Identity</legend>
            <label>
              Serial prefix
              <input
                required
                autoFocus
                value={body.serial_prefix}
                onChange={(event) => {
                  const serial = event.target.value;
                  patch({
                    ...body,
                    serial_prefix: serial,
                    hostname_prefix: hostnameTouched
                      ? body.hostname_prefix
                      : serial,
                  });
                }}
              />
              {fieldError("serial_prefix")}
            </label>
            <label>
              Hostname prefix
              <input
                required
                value={body.hostname_prefix}
                onChange={(event) => {
                  setHostnameTouched(true);
                  patch({ ...body, hostname_prefix: event.target.value });
                }}
              />
              {fieldError("hostname_prefix")}
            </label>
            <label>
              EOS version
              <input
                required
                value={body.eos_version}
                onChange={(event) =>
                  patch({ ...body, eos_version: event.target.value })
                }
              />
              {fieldError("eos_version")}
            </label>
          </fieldset>
        ) : null}

        {step.id === "sites" ? (
          <fieldset disabled={writing}>
            <legend>Sites</legend>
            <label>
              Number of sites (1–8)
              <input
                type="number"
                min={1}
                max={8}
                required
                value={body.dc_count}
                onChange={(event) => {
                  const count = event.target.valueAsNumber || 1;
                  const names = syncSites(count, siteNames);
                  patch({
                    ...body,
                    dc_count: count,
                    sites: count > 1 ? names : [],
                  });
                }}
              />
            </label>
            {multiDc
              ? siteNames.map((name, index) => (
                  <label key={index}>
                    Site {index + 1} name
                    <input
                      required
                      value={name}
                      onChange={(event) => {
                        const next = [...siteNames];
                        next[index] = event.target.value;
                        setSiteNames(next);
                        patch({
                          ...body,
                          sites: next.map((item) => item.trim()).filter(Boolean),
                        });
                      }}
                    />
                  </label>
                ))
              : (
                <p className="create-form__hint">
                  Single-site labs use unscoped hostnames (no site token).
                </p>
              )}
          </fieldset>
        ) : null}

        {step.id === "role" ? (
          <fieldset disabled={writing}>
            <legend>Fabric role</legend>
            <label>
              Use case
              <select
                value={body.capacity.use_case ?? "datacenter"}
                onChange={(event) =>
                  capacity(
                    "use_case",
                    event.target.value as CapacityBody["use_case"],
                  )
                }
              >
                <option value="datacenter">Datacenter</option>
                <option value="campus">Campus</option>
              </select>
            </label>
            <label>
              Fabric mode
              <select
                value={body.capacity.fabric_mode}
                onChange={(event) => {
                  const mode = event.target.value as CapacityBody["fabric_mode"];
                  const spines =
                    mode === "l2ls"
                      ? Math.min(body.capacity.spines, 2)
                      : body.capacity.spines;
                  patch({
                    ...body,
                    spine_mlag: mode === "l2ls" && spines === 2,
                    capacity: {
                      ...body.capacity,
                      fabric_mode: mode,
                      spines,
                      max_spines:
                        mode === "l2ls"
                          ? Math.min(body.capacity.max_spines, 2)
                          : body.capacity.max_spines,
                    },
                  });
                }}
              >
                <option value="l3ls">L3 leaf-spine</option>
                <option value="l2ls">L2 leaf-spine</option>
              </select>
            </label>
            <p className="create-form__hint">
              {isL2
                ? "L2LS: dual spines always peer with MLAG (capped at 2 spines)."
                : "L3LS: routed leaf-spine — spines are never MLAG’d; leaf pairs are optional."}
              {multiDc
                ? " Multi-site labs typically use L3LS with borders and backbone."
                : ""}
            </p>
          </fieldset>
        ) : null}

        {step.id === "size" ? (
          <fieldset disabled={writing}>
            <legend>Size</legend>
            <label>
              {multiDc ? "Spines per site" : "Number of spines"}
              <input
                type="number"
                min={1}
                max={isL2 ? 2 : 32}
                required
                value={body.capacity.spines}
                onChange={(event) => {
                  const spines = event.target.valueAsNumber;
                  patch({
                    ...body,
                    spine_mlag: isL2 && spines === 2,
                    capacity: { ...body.capacity, spines },
                  });
                }}
              />
            </label>
            <label>
              {multiDc ? "Leaves per site" : "Number of leaves"}
              <input
                type="number"
                min={1}
                max={64}
                required
                value={body.capacity.leaves}
                onChange={(event) =>
                  capacity("leaves", event.target.valueAsNumber)
                }
              />
            </label>
          </fieldset>
        ) : null}

        {step.id === "capacity" ? (
          <fieldset disabled={writing}>
            <legend>Reserved capacity</legend>
            <label>
              Maximum spines{multiDc ? " per site" : ""}
              <input
                type="number"
                min={body.capacity.spines}
                required
                value={body.capacity.max_spines}
                onChange={(event) =>
                  capacity("max_spines", event.target.valueAsNumber)
                }
              />
            </label>
            <label>
              Maximum leaves{multiDc ? " per site" : ""}
              <input
                type="number"
                min={body.capacity.leaves}
                required
                value={body.capacity.max_leaves}
                onChange={(event) =>
                  capacity("max_leaves", event.target.valueAsNumber)
                }
              />
            </label>
            <label>
              Maximum member leaves per leaf pair
              <input
                type="number"
                min={0}
                required
                value={body.capacity.max_mleafs_per_pair}
                onChange={(event) =>
                  capacity("max_mleafs_per_pair", event.target.valueAsNumber)
                }
              />
            </label>
            {multiDc ? (
              <>
                <label>
                  Backbone redundancy
                  <select
                    value={body.capacity.bb_redundancy}
                    onChange={(event) =>
                      capacity(
                        "bb_redundancy",
                        event.target.value as CapacityBody["bb_redundancy"],
                      )
                    }
                  >
                    <option value="mlag-peer">MLAG peer</option>
                    <option value="evpn-aa">EVPN all-active</option>
                  </select>
                </label>
                <label>
                  Backbone node count
                  <input
                    type="number"
                    min={body.capacity.bb_redundancy === "evpn-aa" ? 2 : 1}
                    max={4}
                    required
                    value={body.capacity.bb_count}
                    onChange={(event) =>
                      capacity("bb_count", event.target.valueAsNumber)
                    }
                  />
                </label>
                {!isL2 ? (
                  <>
                    <label>
                      Border redundancy
                      <select
                        value={body.capacity.border_redundancy}
                        onChange={(event) =>
                          capacity(
                            "border_redundancy",
                            event.target
                              .value as CapacityBody["border_redundancy"],
                          )
                        }
                      >
                        <option value="mlag-peer">MLAG peer</option>
                        <option value="evpn-aa">EVPN all-active</option>
                      </select>
                    </label>
                    <label>
                      Border leaves per site
                      <input
                        type="number"
                        min={
                          body.capacity.border_redundancy === "evpn-aa" ? 2 : 1
                        }
                        max={4}
                        required
                        value={body.capacity.border_count}
                        onChange={(event) =>
                          capacity("border_count", event.target.valueAsNumber)
                        }
                      />
                    </label>
                  </>
                ) : null}
              </>
            ) : null}
          </fieldset>
        ) : null}

        {step.id === "pairing" ? (
          <fieldset disabled={writing}>
            <legend>Pairing</legend>
            <label className="create-form__check">
              <input
                type="checkbox"
                checked={body.mlag_pairs}
                onChange={(event) =>
                  patch({ ...body, mlag_pairs: event.target.checked })
                }
              />
              Pair leaves into MLAG pairs
            </label>
            {!isL2 ? (
              <p className="create-form__hint">
                L3LS spines stay independent — no spine MLAG. Only leaf pairs
                (and member leaves hung off those pairs) apply here.
              </p>
            ) : body.capacity.spines === 2 ? (
              <p className="create-form__hint">
                Spine MLAG peer-links are always included for dual-spine L2LS.
              </p>
            ) : (
              <p className="create-form__hint">
                L2LS spine MLAG needs two spines (currently {body.capacity.spines}
                ). Add a second spine on the Size step.
              </p>
            )}
            {body.mlag_pairs &&
            body.capacity.leaves >= 2 &&
            body.capacity.max_mleafs_per_pair > 0 ? (
              <>
                <label>
                  Leaf pairs receiving member leaves (1–{pairCount},
                  comma-separated)
                  <input
                    value={pairsText}
                    placeholder="e.g. 1"
                    onChange={(event) => setPairsText(event.target.value)}
                  />
                </label>
                <label>
                  Member leaves per selected pair
                  <input
                    type="number"
                    min={1}
                    max={body.capacity.max_mleafs_per_pair}
                    value={Math.max(1, body.member_leaves_per_pair || 1)}
                    onChange={(event) =>
                      patch({
                        ...body,
                        member_leaves_per_pair: event.target.valueAsNumber,
                      })
                    }
                  />
                </label>
              </>
            ) : (
              <p className="create-form__hint">
                Member leaves need leaf MLAG pairs, at least two leaves, and a
                reserved member-leaf capacity &gt; 0.
              </p>
            )}
          </fieldset>
        ) : null}

        {step.id === "review" ? (
          <fieldset disabled={writing}>
            <legend>Review</legend>
            <p className="create-form__hint">
              Selections and the live diagram are in the pane below. Finish
              writes the lab into Topologies.
            </p>
            {previewing ? (
              <p className="page-status">Building preview…</p>
            ) : preview ? (
              <p className="create-form__summary" role="status">
                {preview.summary.node_count} nodes · {preview.summary.fabric_mode}{" "}
                · {preview.summary.sites.length || 1} site(s).
              </p>
            ) : (
              <p className="page-status">Waiting for a valid preview…</p>
            )}
            <button
              type="button"
              disabled={previewing || writing}
              onClick={() => void runPreview()}
            >
              Refresh preview
            </button>
          </fieldset>
        ) : null}

        {error ? (
          <div className="create-form__error" role="alert">
            {error}
          </div>
        ) : null}

        <div className="create-form__actions create-wizard__nav">
          <button
            type="button"
            disabled={stepIndex === 0 || writing}
            onClick={goBack}
          >
            Back
          </button>
          {step.id !== "review" ? (
            <button type="submit" className="btn-primary" disabled={writing}>
              Next
            </button>
          ) : (
            <button
              type="button"
              className="btn-primary"
              disabled={!preview || previewing || writing}
              onClick={() => void write()}
            >
              {writing ? "Writing…" : "Finish"}
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
