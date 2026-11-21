import { useState } from "react";
import { useActiveTopology } from "../state/activeTopology";

async function previewFromYaml(yamlText: string): Promise<string | null> {
  const response = await fetch("/api/preview-from-yaml", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ yaml_text: yamlText }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(body?.detail ?? `Preview failed (${response.status})`);
  }
  const data = (await response.json()) as { png_base64: string | null };
  return data.png_base64;
}

export function ShowPage() {
  const { active, setActive } = useActiveTopology();
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  async function refreshDiagram() {
    if (!active.yamlText) {
      setError("No active topology YAML to refresh.");
      return;
    }
    setRefreshing(true);
    setError(null);
    try {
      const pngBase64 = await previewFromYaml(active.yamlText);
      setActive({ ...active, pngBase64 });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRefreshing(false);
    }
  }

  if (!active.yamlText) {
    return (
      <>
        <h1>Show</h1>
        <p>No active topology. Open one from Labs.</p>
      </>
    );
  }

  return (
    <>
      <h1>Show</h1>
      <p>
        Active: {active.name ?? "unnamed"}
        {active.path ? ` (${active.path})` : ""}
      </p>
      <div className="show-actions">
        <button
          type="button"
          disabled={refreshing}
          onClick={() => void refreshDiagram()}
        >
          {refreshing ? "Refreshing…" : "Refresh diagram"}
        </button>
      </div>
      {error ? <p className="page-error">{error}</p> : null}
      <div className="show-panes">
        <section aria-label="Active YAML">
          <div className="show-panes__label">YAML</div>
          <pre className="show-panes__mono">{active.yamlText}</pre>
        </section>
        <section aria-label="Active diagram">
          <div className="show-panes__label">Diagram</div>
          <div className="show-panes__diagram">
            {active.pngBase64 ? (
              <img
                alt="Topology diagram"
                src={`data:image/png;base64,${active.pngBase64}`}
              />
            ) : (
              <span>No diagram yet. Use Refresh diagram.</span>
            )}
          </div>
        </section>
      </div>
    </>
  );
}
