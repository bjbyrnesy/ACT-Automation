import { useState, type FormEvent } from "react";
import { attachTopology, loadSavedTopology } from "../api/client";
import { useActiveTopology } from "../state/activeTopology";
import "./OpsPage.css";

export function AttachPage() {
  const { active, setActive } = useActiveTopology();
  const [host, setHost] = useState("");
  const [to, setTo] = useState("");
  const [mlagPair, setMlagPair] = useState("");
  const [mleaf, setMleaf] = useState("");
  const [et, setEt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!active.path || busy) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const targets = to.split(",").map((value) => value.trim()).filter(Boolean);
      const result = await attachTopology({
        path: active.path,
        host: host.trim(),
        ...(targets.length ? { to: targets } : {}),
        ...(mlagPair ? { mlag_pair: Number(mlagPair) } : {}),
        ...(mleaf ? { mleaf: Number(mleaf) } : {}),
        ...(et ? { et: Number(et) } : {}),
      });
      setActive(await loadSavedTopology(result));
      setStatus(`Attached ${host.trim()} to ${result.name}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ops-page">
      <h1>Attach</h1>
      <p>Attach a host to fabric edges.</p>
      <p>Active topology: {active.name ?? "none"}</p>
      {!active.path ? <p className="page-status">Open or write a topology in Labs before attaching a host.</p> : null}
      <form className="ops-form" onSubmit={(event) => void submit(event)}>
        <label>Host name<input required value={host} onChange={(event) => setHost(event.target.value)} /></label>
        <label>Target nodes (comma separated, optional)<input value={to} onChange={(event) => setTo(event.target.value)} /></label>
        <label>MLAG pair (optional)<input type="number" min="1" value={mlagPair} onChange={(event) => setMlagPair(event.target.value)} /></label>
        <label>Member leaf (optional)<input type="number" min="1" value={mleaf} onChange={(event) => setMleaf(event.target.value)} /></label>
        <label>Ethernet port (optional)<input type="number" min="1" value={et} onChange={(event) => setEt(event.target.value)} /></label>
        <div className="ops-form__actions"><button type="submit" disabled={!active.path || busy}>{busy ? "Attaching…" : "Attach"}</button></div>
      </form>
      {error ? <p className="page-error" role="alert">{error}</p> : null}
      {status ? <p className="page-status" role="status">{status}</p> : null}
    </div>
  );
}
