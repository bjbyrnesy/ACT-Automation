import { useState, type FormEvent } from "react";
import { extendTopology, loadSavedTopology } from "../api/client";
import { useActiveTopology } from "../state/activeTopology";
import "./OpsPage.css";

type Add = "spine" | "leaf" | "pair" | "mleaf" | "site";

export function ExtendPage() {
  const { active, setActive } = useActiveTopology();
  const [add, setAdd] = useState<Add>("leaf");
  const [site, setSite] = useState("");
  const [pair, setPair] = useState("");
  const [count, setCount] = useState(1);
  const [name, setName] = useState("");
  const [firstSite, setFirstSite] = useState("");
  const [rekeyIdentity, setRekeyIdentity] = useState(false);
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
      const body: Record<string, unknown> = { path: active.path, add };
      if (add === "site") {
        body.name = name.trim();
        if (firstSite.trim()) body.first_site = firstSite.trim();
        if (rekeyIdentity) body.rekey_identity = true;
      } else {
        body.count = count;
        if (site.trim()) body.site = site.trim();
        if (add === "mleaf" && pair.trim()) body.pair = Number(pair);
      }
      const result = await extendTopology(body);
      setActive(await loadSavedTopology(result));
      setStatus(`Extended topology saved as ${result.name}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ops-page">
      <h1>Extend</h1>
      <p>Grow an existing topology without renumbering links.</p>
      <p>Active topology: {active.name ?? "none"}</p>
      {!active.path ? <p className="page-status">Open or write a topology in Labs before extending it.</p> : null}
      <form className="ops-form" onSubmit={(event) => void submit(event)}>
        <label>Add<select value={add} onChange={(event) => setAdd(event.target.value as Add)}><option value="spine">Spine</option><option value="leaf">Leaf</option><option value="pair">Leaf pair</option><option value="mleaf">Member leaf</option><option value="site">Site</option></select></label>
        {add === "site" ? (
          <>
            <label>New site name<input required value={name} onChange={(event) => setName(event.target.value)} /></label>
            <label>First site (optional)<input value={firstSite} onChange={(event) => setFirstSite(event.target.value)} /></label>
            <label className="ops-form__check"><input type="checkbox" checked={rekeyIdentity} onChange={(event) => setRekeyIdentity(event.target.checked)} />Rekey identity</label>
          </>
        ) : (
          <>
            <label>Count<input type="number" min="1" required value={count} onChange={(event) => setCount(event.target.valueAsNumber)} /></label>
            <label>Site (optional)<input value={site} onChange={(event) => setSite(event.target.value)} /></label>
            {add === "mleaf" ? <label>Leaf pair number<input type="number" min="1" value={pair} onChange={(event) => setPair(event.target.value)} /></label> : null}
          </>
        )}
        <div className="ops-form__actions"><button type="submit" disabled={!active.path || busy}>{busy ? "Extending…" : "Extend"}</button></div>
      </form>
      {error ? <p className="page-error" role="alert">{error}</p> : null}
      {status ? <p className="page-status" role="status">{status}</p> : null}
    </div>
  );
}
