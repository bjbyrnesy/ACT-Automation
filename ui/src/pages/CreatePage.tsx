import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, previewTopology, writeTopology } from "../api/client";
import type { CapacityBody, PreviewBody, PreviewResult } from "../api/types";
import { useActiveTopology } from "../state/activeTopology";
import "./CreatePage.css";

const initial: PreviewBody = {
  hostname_prefix: "demo", serial_prefix: "DEMO", eos_version: "4.35.4M",
  capacity: {
    fabric_mode: "l3ls", max_spines: 2, max_leaves: 4, max_mleafs_per_pair: 0,
    spines: 2, leaves: 4, use_case: null, bb_redundancy: "mlag-peer",
    border_redundancy: "mlag-peer", bb_count: 2, border_count: 2, backbone_mode: "hub",
  },
  mlag_pairs: true, spine_mlag: false, member_leaf_pairs: [],
  member_leaves_per_pair: 0, dc_count: 1, sites: [],
};

type CapacityNumber = "spines" | "leaves" | "max_spines" | "max_leaves" | "max_mleafs_per_pair" | "bb_count" | "border_count";
const capacityNumbers: { key: CapacityNumber; label: string; min: number }[] = [
  { key: "spines", label: "Spines", min: 1 },
  { key: "leaves", label: "Leaves", min: 1 },
  { key: "max_spines", label: "Reserved spines", min: 1 },
  { key: "max_leaves", label: "Reserved leaves", min: 1 },
  { key: "max_mleafs_per_pair", label: "Reserved member leaves per pair", min: 0 },
  { key: "bb_count", label: "Backbone count", min: 1 },
  { key: "border_count", label: "Border count", min: 1 },
];

export function CreatePage() {
  const navigate = useNavigate();
  const { setActiveTopology } = useActiveTopology();
  const [body, setBody] = useState<PreviewBody>(initial);
  const [sitesText, setSitesText] = useState("");
  const [pairsText, setPairsText] = useState("");
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [previewing, setPreviewing] = useState(false);
  const [writing, setWriting] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const autoPreview = localStorage.getItem("acta.preview_auto") === "1";

  function change(next: PreviewBody) {
    sequence.current++;
    controller.current?.abort();
    setBody(next);
    setPreview(null);
    setActiveTopology(null);
    setPreviewing(false);
    setError("");
    setFieldErrors({});
  }

  function capacity<K extends keyof CapacityBody>(key: K, value: CapacityBody[K]) {
    change({ ...body, capacity: { ...body.capacity, [key]: value } });
  }

  const runPreview = useCallback(async () => {
    controller.current?.abort();
    const currentController = new AbortController();
    controller.current = currentController;
    const id = ++sequence.current;
    setPreviewing(true);
    setError("");
    setFieldErrors({});
    try {
      const result = await previewTopology(body, currentController.signal);
      if (id !== sequence.current) return;
      setPreview(result);
      setActiveTopology({ yamlText: result.yaml_text, pngBase64: result.png_base64 ?? undefined, isDraft: true });
    } catch (caught) {
      if (id !== sequence.current || currentController.signal.aborted) return;
      setPreview(null);
      setActiveTopology(null);
      setError(caught instanceof Error ? caught.message : "Preview failed");
      setFieldErrors(caught instanceof ApiError ? caught.fields : {});
    } finally {
      if (id === sequence.current) setPreviewing(false);
    }
  }, [body, setActiveTopology]);

  useEffect(() => {
    if (!autoPreview) return;
    const timer = window.setTimeout(() => { void runPreview(); }, 400);
    return () => window.clearTimeout(timer);
  }, [autoPreview, runPreview]);
  useEffect(() => () => controller.current?.abort(), []);

  async function write() {
    if (!preview || writing) return;
    setWriting(true);
    setError("");
    setFieldErrors({});
    try {
      const result = await writeTopology({ yaml_text: preview.yaml_text, stem: body.hostname_prefix });
      setActiveTopology({ path: result.path, name: result.name, yamlText: preview.yaml_text,
        pngBase64: preview.png_base64 ?? undefined, isDraft: false });
      navigate("/show");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Write failed");
      setFieldErrors(caught instanceof ApiError ? caught.fields : {});
    } finally {
      setWriting(false);
    }
  }

  const fieldError = (name: string) => fieldErrors[name] && <small className="create-form__field-error">{fieldErrors[name]}</small>;
  return (
    <div className="create-page">
      <h1>Create</h1>
      <p>Configure a fabric, preview its ACT YAML and diagram, then write it to Labs.</p>
      <form className="create-form" onSubmit={(event: FormEvent) => { event.preventDefault(); void runPreview(); }}>
        <fieldset disabled={writing}>
          <legend>Identity</legend>
          <label>Hostname prefix<input required value={body.hostname_prefix} onChange={(event) => change({ ...body, hostname_prefix: event.target.value })} />{fieldError("hostname_prefix")}</label>
          <label>Serial prefix<input required value={body.serial_prefix} onChange={(event) => change({ ...body, serial_prefix: event.target.value })} />{fieldError("serial_prefix")}</label>
          <label>EOS version<input required value={body.eos_version} onChange={(event) => change({ ...body, eos_version: event.target.value })} />{fieldError("eos_version")}</label>
        </fieldset>
        <fieldset disabled={writing}>
          <legend>Capacity</legend>
          <label>Fabric mode<select value={body.capacity.fabric_mode} onChange={(event) => capacity("fabric_mode", event.target.value as CapacityBody["fabric_mode"])}><option value="l3ls">L3 leaf-spine</option><option value="l2ls">L2 leaf-spine</option></select>{fieldError("capacity.fabric_mode")}</label>
          <label>Use case<select value={body.capacity.use_case ?? ""} onChange={(event) => capacity("use_case", (event.target.value || null) as CapacityBody["use_case"])}><option value="">Default</option><option value="datacenter">Datacenter</option><option value="campus">Campus</option></select>{fieldError("capacity.use_case")}</label>
          {capacityNumbers.map(({ key, label, min }) => <label key={key}>{label}<input type="number" min={min} required value={body.capacity[key]} onChange={(event) => capacity(key, event.target.valueAsNumber)} />{fieldError(`capacity.${key}`)}</label>)}
          <label>Backbone redundancy<select value={body.capacity.bb_redundancy} onChange={(event) => capacity("bb_redundancy", event.target.value as CapacityBody["bb_redundancy"])}><option value="mlag-peer">MLAG peer</option><option value="evpn-aa">EVPN all-active</option></select>{fieldError("capacity.bb_redundancy")}</label>
          <label>Border redundancy<select value={body.capacity.border_redundancy} onChange={(event) => capacity("border_redundancy", event.target.value as CapacityBody["border_redundancy"])}><option value="mlag-peer">MLAG peer</option><option value="evpn-aa">EVPN all-active</option></select>{fieldError("capacity.border_redundancy")}</label>
          <label>Backbone mode<select value={body.capacity.backbone_mode} onChange={(event) => capacity("backbone_mode", event.target.value as CapacityBody["backbone_mode"])}><option value="hub">Hub</option></select>{fieldError("capacity.backbone_mode")}</label>
        </fieldset>
        <fieldset disabled={writing}>
          <legend>Topology</legend>
          <label className="create-form__check"><input type="checkbox" checked={body.mlag_pairs} onChange={(event) => change({ ...body, mlag_pairs: event.target.checked })} />Leaf MLAG pairs</label>{fieldError("mlag_pairs")}
          <label className="create-form__check"><input type="checkbox" checked={body.spine_mlag} onChange={(event) => change({ ...body, spine_mlag: event.target.checked })} />Spine MLAG</label>{fieldError("spine_mlag")}
          <label>Member leaf pairs (comma-separated numbers)<input value={pairsText} onChange={(event) => { const text = event.target.value; setPairsText(text); change({ ...body, member_leaf_pairs: text.split(",").map((part) => part.trim()).filter(Boolean).map(Number) }); }} />{fieldError("member_leaf_pairs")}</label>
          <label>Member leaves per pair<input type="number" min="0" required value={body.member_leaves_per_pair} onChange={(event) => change({ ...body, member_leaves_per_pair: event.target.valueAsNumber })} />{fieldError("member_leaves_per_pair")}</label>
          <label>Data center count<input type="number" min="1" required value={body.dc_count} onChange={(event) => change({ ...body, dc_count: event.target.valueAsNumber })} />{fieldError("dc_count")}</label>
          <label>Sites (comma-separated, optional)<input value={sitesText} onChange={(event) => { const text = event.target.value; setSitesText(text); change({ ...body, sites: text.split(",").map((site) => site.trim()).filter(Boolean) }); }} />{fieldError("sites")}</label>
        </fieldset>
        {error && <div className="create-form__error" role="alert">{error}</div>}
        {preview && <p className="create-form__summary" role="status">{preview.summary.node_count} nodes · {preview.summary.fabric_mode} · {preview.summary.sites.length || 1} site(s)</p>}
        <div className="create-form__actions"><button type="submit" disabled={previewing || writing}>{previewing ? "Previewing…" : "Preview"}</button><button type="button" disabled={!preview || previewing || writing} onClick={() => { void write(); }}>{writing ? "Writing…" : "Write"}</button></div>
      </form>
    </div>
  );
}
