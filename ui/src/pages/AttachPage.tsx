import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  attachTopology,
  detachTopology,
  getAttachTargets,
  loadSavedTopology,
  type AttachTargets,
} from "../api/client";
import { useActiveTopology } from "../state/activeTopology";
import "./OpsPage.css";

type TargetKind = "mlag" | "mleaf" | "spine" | "spine_mlag";

type TargetOption = {
  key: string;
  kind: TargetKind;
  index: number;
  name?: string;
  site: string | null;
  label: string;
};

type PairHoming = "dual" | "a" | "b";

const DEFAULT_HOST_NET_SUBNET = "192.168.2.0/24";
const DEFAULT_HOST_NET_GATEWAY = "192.168.2.1";

export function AttachPage() {
  const { active, setActive } = useActiveTopology();
  const [host, setHost] = useState("");
  const [detachHost, setDetachHost] = useState("");
  const [siteFilter, setSiteFilter] = useState("");
  const [targetKey, setTargetKey] = useState("");
  const [pairHoming, setPairHoming] = useState<PairHoming>("dual");
  const [et, setEt] = useState("");
  const [targets, setTargets] = useState<AttachTargets | null>(null);
  const [targetsError, setTargetsError] = useState("");
  const [hostNet, setHostNet] = useState(false);
  const [hostIp, setHostIp] = useState("");
  const [hostSubnet, setHostSubnet] = useState("");
  const [hostGateway, setHostGateway] = useState("");
  const [netDefaults, setNetDefaults] = useState({
    subnet: DEFAULT_HOST_NET_SUBNET,
    gateway: DEFAULT_HOST_NET_GATEWAY,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    let cancelled = false;
    void fetch("/api/settings")
      .then(async (response) => {
        if (!response.ok) return;
        const body = (await response.json()) as Record<string, unknown>;
        if (cancelled) return;
        setNetDefaults({
          subnet:
            String(body.HOST_NET_SUBNET ?? "").trim() ||
            DEFAULT_HOST_NET_SUBNET,
          gateway:
            String(body.HOST_NET_GATEWAY ?? "").trim() ||
            DEFAULT_HOST_NET_GATEWAY,
        });
      })
      .catch(() => {
        /* Placeholders fall back to static defaults. */
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
    for (const pair of targets?.spine_pairs ?? []) {
      next.push({
        key: `spine_mlag:${pair.index}`,
        kind: "spine_mlag",
        index: pair.index,
        site: pair.site,
        label: `Spine MLAG · ${pair.label}`,
      });
    }
    for (const spine of targets?.spines ?? []) {
      next.push({
        key: `spine:${spine.name}`,
        kind: "spine",
        index: 0,
        name: spine.name,
        site: spine.site,
        label: `Spine · ${spine.label}`,
      });
    }
    for (const pair of targets?.mlag_pairs ?? []) {
      next.push({
        key: `mlag:${pair.index}`,
        kind: "mlag",
        index: pair.index,
        site: pair.site,
        label: `Leaf MLAG · ${pair.label}`,
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

  const attached = targets?.hosts ?? [];

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

  useEffect(() => {
    if (detachHost && !attached.includes(detachHost)) {
      setDetachHost("");
    }
  }, [attached, detachHost]);

  const selectedOption = options.find((option) => option.key === targetKey);
  const selectedLeafPair =
    selectedOption?.kind === "mlag"
      ? (targets?.mlag_pairs.find(
          (pair) => pair.index === selectedOption.index,
        ) ?? null)
      : null;
  const selectedSpinePair =
    selectedOption?.kind === "spine_mlag"
      ? (targets?.spine_pairs.find(
          (pair) => pair.index === selectedOption.index,
        ) ?? null)
      : null;
  const selectedPair = selectedLeafPair ?? selectedSpinePair;
  const pairPeerA = selectedLeafPair?.leaf_a ?? selectedSpinePair?.spine_a;
  const pairPeerB = selectedLeafPair?.leaf_b ?? selectedSpinePair?.spine_b;

  useEffect(() => {
    if (!selectedPair) setPairHoming("dual");
  }, [selectedPair]);

  async function submitAttach(event: FormEvent) {
    event.preventDefault();
    if (!active.path || busy) return;
    const selected = options.find((option) => option.key === targetKey);
    if (!selected) {
      setError("Choose a fabric target.");
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const body: Record<string, unknown> = {
        path: active.path,
        host: host.trim(),
        ...(et ? { et: Number(et) } : {}),
      };
      if (selected.kind === "mlag") {
        body.mlag_pair = selected.index;
        body.dual_homed = pairHoming === "dual";
        if (pairHoming !== "dual") body.mlag_side = pairHoming;
      } else if (selected.kind === "mleaf") {
        body.mleaf = selected.index;
      } else if (selected.kind === "spine" && selected.name) {
        body.to = [selected.name];
      } else if (selected.kind === "spine_mlag" && selectedSpinePair) {
        if (pairHoming === "dual") {
          body.to = [selectedSpinePair.spine_a, selectedSpinePair.spine_b];
        } else {
          body.to = [
            pairHoming === "a"
              ? selectedSpinePair.spine_a
              : selectedSpinePair.spine_b,
          ];
        }
      }

      if (hostNet) {
        body.host_net = true;
        if (hostIp.trim()) body.host_ip = hostIp.trim();
        if (hostSubnet.trim()) body.host_subnet = hostSubnet.trim();
        if (hostGateway.trim()) body.host_gateway = hostGateway.trim();
      }

      const result = await attachTopology(body);
      setActive(await loadSavedTopology(result));
      let homeBit = selected.label;
      if (selected.kind === "mlag" || selected.kind === "spine_mlag") {
        homeBit =
          pairHoming === "dual"
            ? "dual-homed"
            : `single-homed (${pairHoming === "a" ? pairPeerA : pairPeerB})`;
      }
      setStatus(`Attached ${host.trim()} → ${homeBit} → ${result.name}.`);
      setHost("");
      setTargetKey("");
      setPairHoming("dual");
      setHostIp("");
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

  async function submitDetach(event: FormEvent) {
    event.preventDefault();
    if (!active.path || busy || !detachHost) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const result = await detachTopology({
        path: active.path,
        host: detachHost,
      });
      setActive(await loadSavedTopology(result));
      setStatus(`Detached ${detachHost} → ${result.name}.`);
      setDetachHost("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  const campusSpines = (targets?.spines.length ?? 0) > 0;
  const siteHasMleaf = filtered.some((option) => option.kind === "mleaf");
  const siteHasPair = filtered.some((option) => option.kind === "mlag");

  return (
    <div className="ops-page">
      <p>
        Attach or detach hosts on fabric edges
        {campusSpines
          ? " (leaf MLAG, member leaf, or campus spine)."
          : " (leaf MLAG or member leaf)."}
      </p>
      {!active.path ? (
        <p className="page-status">Open a lab version before managing hosts.</p>
      ) : null}
      {targetsError ? (
        <p className="page-error" role="alert">
          Could not load attach targets: {targetsError}
        </p>
      ) : null}

      <h2 className="ops-form__section">Attach</h2>
      <form className="ops-form" onSubmit={(event) => void submitAttach(event)}>
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
            onChange={(event) => {
              setTargetKey(event.target.value);
              setPairHoming("dual");
            }}
          >
            <option value="">— select where to attach —</option>
            {filtered.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        {selectedPair && pairPeerA && pairPeerB ? (
          <fieldset className="ops-form__fieldset">
            <legend>
              {selectedOption?.kind === "spine_mlag"
                ? "Spine MLAG homing"
                : "Leaf MLAG homing"}
            </legend>
            <label className="ops-form__check">
              <input
                type="radio"
                name="pair-homing"
                checked={pairHoming === "dual"}
                onChange={() => setPairHoming("dual")}
              />
              Dual-homed (both {pairPeerA} and {pairPeerB})
            </label>
            <label className="ops-form__check">
              <input
                type="radio"
                name="pair-homing"
                checked={pairHoming === "a"}
                onChange={() => setPairHoming("a")}
              />
              Single-homed to {pairPeerA}
            </label>
            <label className="ops-form__check">
              <input
                type="radio"
                name="pair-homing"
                checked={pairHoming === "b"}
                onChange={() => setPairHoming("b")}
              />
              Single-homed to {pairPeerB}
            </label>
          </fieldset>
        ) : null}
        <label>
          Ethernet port on switch (optional)
          <input
            type="number"
            min="1"
            value={et}
            onChange={(event) => setEt(event.target.value)}
          />
        </label>
        <label className="ops-form__check">
          <input
            type="checkbox"
            checked={hostNet}
            onChange={(event) => setHostNet(event.target.checked)}
          />
          Data-plane IP
        </label>
        {hostNet ? (
          <>
            <label>
              Host IP (optional)
              <input
                value={hostIp}
                onChange={(event) => setHostIp(event.target.value)}
                placeholder="auto (next free)"
              />
            </label>
            <label>
              Subnet (optional)
              <input
                value={hostSubnet}
                onChange={(event) => setHostSubnet(event.target.value)}
                placeholder={netDefaults.subnet}
              />
            </label>
            <label>
              Gateway (optional)
              <input
                value={hostGateway}
                onChange={(event) => setHostGateway(event.target.value)}
                placeholder={netDefaults.gateway}
              />
            </label>
            <p className="ops-form__hint">
              Needs a sibling .clab.yml. Blank fields use Settings
              (HOST_NET_SUBNET / HOST_NET_GATEWAY) or the built-in defaults.
            </p>
          </>
        ) : null}
        {campusSpines ? (
          <p className="ops-form__hint">
            Campus use case: spines are valid attach targets (common when
            access port count is tight). Dual-home to the spine MLAG pair or
            pick a single spine.
          </p>
        ) : siteFilter && siteHasPair && !siteHasMleaf ? (
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
            {busy ? "Working…" : "Attach"}
          </button>
        </div>
      </form>

      <h2 className="ops-form__section">Detach</h2>
      <form className="ops-form" onSubmit={(event) => void submitDetach(event)}>
        <label>
          Attached host
          <select
            required
            value={detachHost}
            onChange={(event) => setDetachHost(event.target.value)}
          >
            <option value="">
              {attached.length ? "— select host —" : "— no attached hosts —"}
            </option>
            {attached.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <p className="ops-form__hint">
          Removes the generic host and its uplinks from the ACT topology (and
          sibling .clab.yml when present). Redeploy the lab afterward.
        </p>
        <div className="ops-form__actions">
          <button
            type="submit"
            className="btn-primary"
            disabled={!active.path || busy || !detachHost}
          >
            {busy ? "Working…" : "Detach"}
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
