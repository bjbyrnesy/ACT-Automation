import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useActiveTopology } from "../state/activeTopology";

type TopologyListItem = {
  name: string;
  path: string;
  mtime: number;
  has_clab_sibling: boolean;
};

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function LabsPage() {
  const navigate = useNavigate();
  const { setActive } = useActiveTopology();
  const [items, setItems] = useState<TopologyListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const listed = await fetchJson<TopologyListItem[]>("/api/topologies");
      setItems(listed);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function openTopology(item: TopologyListItem) {
    setBusy(item.name);
    setError(null);
    try {
      const topo = await fetchJson<{ yaml_text: string; path: string }>(
        `/api/topologies/${encodeURIComponent(item.name)}`,
      );
      let pngBase64: string | null = null;
      try {
        const preview = await fetchJson<{ png_base64: string | null }>(
          "/api/preview-from-yaml",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ yaml_text: topo.yaml_text }),
          },
        );
        pngBase64 = preview.png_base64;
      } catch {
        pngBase64 = null;
      }
      setActive({
        path: topo.path,
        name: item.name,
        yamlText: topo.yaml_text,
        pngBase64,
        isDraft: false,
      });
      navigate("/show");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <h1>Labs</h1>
      <p>Browse and open topology files under the labs root.</p>
      {error ? <p className="page-error">{error}</p> : null}
      <div className="labs-toolbar">
        <button type="button" onClick={() => void load()}>
          Refresh list
        </button>
      </div>
      <table className="labs-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Modified</th>
            <th>Clab</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={4}>No topologies found.</td>
            </tr>
          ) : (
            items.map((item) => (
              <tr key={item.name}>
                <td>{item.name}</td>
                <td>{new Date(item.mtime * 1000).toLocaleString()}</td>
                <td>{item.has_clab_sibling ? "yes" : "—"}</td>
                <td>
                  <button
                    type="button"
                    disabled={busy === item.name}
                    onClick={() => void openTopology(item)}
                  >
                    {busy === item.name ? "Opening…" : "Open"}
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </>
  );
}
