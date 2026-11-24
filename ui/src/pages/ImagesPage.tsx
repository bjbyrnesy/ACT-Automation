import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  IMAGE_UPLOAD_MAX_BYTES,
  listImages,
  loadImageArchive,
  pullImage,
  pushImage,
  type HostImage,
  type Job,
} from "../api/client";
import { JobsDrawer } from "../components/JobsDrawer";
import "./OpsPage.css";
import "./ImagesPage.css";

type SettingKey = "CLAB_IMAGE" | "CLAB_HOST_IMAGE";

/** Longest first so `.tar.gz` wins over `.tar`. Bare `.gz` is not allowed. */
const ARCHIVE_SUFFIXES = [".tar.gz", ".tgz", ".tar", ".xz"] as const;

function allowedArchiveSuffix(filename: string): string {
  const lowered = filename.toLowerCase();
  return ARCHIVE_SUFFIXES.find((suffix) => lowered.endsWith(suffix)) ?? "";
}

function imageRef(row: HostImage): string {
  const unnamed = !row.repository || row.repository === "<none>";
  // `<none>` is not a tag; `repo` alone would mean `:latest`. Use the id.
  if (unnamed || row.tag === "<none>") return row.id;
  if (!row.tag) return row.repository;
  return `${row.repository}:${row.tag}`;
}

export function ImagesPage() {
  const [rows, setRows] = useState<HostImage[]>([]);
  const [runtime, setRuntime] = useState("");
  const [host, setHost] = useState("");
  const [loading, setLoading] = useState(true);
  const [registry, setRegistry] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [tag, setTag] = useState("");
  const [pushRef, setPushRef] = useState("");
  const [pullRef, setPullRef] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [warning, setWarning] = useState("");
  const [job, setJob] = useState<Job | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await listImages();
      setRows(result.images);
      setRuntime(result.runtime);
      setHost(result.host);
      setWarning(result.warning ?? "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    let cancelled = false;
    void fetch("/api/settings")
      .then(async (response) => {
        if (!response.ok) return;
        const body = (await response.json()) as Record<string, unknown>;
        if (!cancelled) setRegistry(String(body.CLAB_REGISTRY ?? "").trim());
      })
      .catch(() => {
        /* Registry actions stay hidden if settings cannot be read. */
      });
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  async function setImageSetting(key: SettingKey, row: HostImage) {
    const value = imageRef(row);
    setError("");
    setStatus("");
    try {
      const response = await fetch("/api/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: value }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as {
          detail?: string;
        } | null;
        throw new Error(body?.detail ?? `Save failed (${response.status})`);
      }
      setStatus(`${key} set to ${value}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  function onFileChange(selected: File | null, input?: HTMLInputElement) {
    setError("");
    if (!selected) {
      setFile(null);
      return;
    }
    if (!allowedArchiveSuffix(selected.name)) {
      setFile(null);
      if (input) input.value = "";
      setError("Archive must be .tar, .tar.gz, .tgz, or .xz.");
      return;
    }
    if (selected.size > IMAGE_UPLOAD_MAX_BYTES) {
      setFile(null);
      if (input) input.value = "";
      setError("Archive exceeds the 10 GB limit.");
      return;
    }
    setFile(selected);
  }

  async function submit(run: () => Promise<Job>) {
    if (busy) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      setJob(await run());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function onLoad(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    if (!allowedArchiveSuffix(file.name)) {
      setFile(null);
      setError("Archive must be .tar, .tar.gz, .tgz, or .xz.");
      return;
    }
    const trimmedName = name.trim();
    const trimmedTag = tag.trim();
    if (Boolean(trimmedName) !== Boolean(trimmedTag)) {
      setError("Name and tag must both be set, or both left empty.");
      return;
    }
    void submit(() =>
      loadImageArchive(file, {
        name: trimmedName || undefined,
        tag: trimmedTag || undefined,
      }),
    );
  }

  function closeJob() {
    setJob(null);
    void refresh();
  }

  const target = host ? `${host} (${runtime || "runtime"})` : `local (${runtime || "runtime"})`;

  return (
    <div className="ops-page images-page">
      <div className="images-page__head">
        <div>
          <h1>Images</h1>
          <p>
            Container images on the lab host: <strong>{target}</strong>.
          </p>
        </div>
        <button type="button" disabled={loading} onClick={() => void refresh()}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error ? (
        <p className="page-error" role="alert">
          {error}
        </p>
      ) : null}
      {warning ? <p className="page-status">{warning}</p> : null}
      {status ? <p className="page-status">{status}</p> : null}

      <table className="labs-table images-page__table">
        <thead>
          <tr>
            <th>Repository</th>
            <th>Tag</th>
            <th>ID</th>
            <th>Size</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={6}>{loading ? "Loading…" : "No images found."}</td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={`${row.id}-${row.repository}-${row.tag}`}>
                <td>{row.repository}</td>
                <td>{row.tag}</td>
                <td className="images-page__mono">{row.id}</td>
                <td>{row.size}</td>
                <td>{row.created}</td>
                <td className="images-page__row-actions">
                  <button type="button" onClick={() => void setImageSetting("CLAB_IMAGE", row)}>
                    Use as CLAB_IMAGE
                  </button>
                  <button
                    type="button"
                    onClick={() => void setImageSetting("CLAB_HOST_IMAGE", row)}
                  >
                    Use as CLAB_HOST_IMAGE
                  </button>
                  {registry ? (
                    <button type="button" onClick={() => setPushRef(imageRef(row))}>
                      Select for push
                    </button>
                  ) : null}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <form className="ops-form" onSubmit={onLoad}>
        <h2 className="ops-form__section">Upload &amp; load archive</h2>
        <label>
          Image archive (.tar, .tar.gz, .tgz, .xz, .tar.xz; max 10 GB)
          <input
            type="file"
            accept=".tar,.tar.gz,.tgz,.xz,.tar.xz"
            onChange={(event) =>
              onFileChange(event.target.files?.[0] ?? null, event.currentTarget)
            }
          />
        </label>
        <label>
          Name (optional)
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. ceos"
          />
        </label>
        <label>
          Tag (optional)
          <input
            value={tag}
            onChange={(event) => setTag(event.target.value)}
            placeholder="e.g. 4.33.1F"
          />
        </label>
        <p className="ops-form__hint">
          The archive is uploaded to ACTA, copied to the lab host, and loaded
          with the host runtime. Set both name and tag to retag the loaded
          image, or leave both empty.
        </p>
        <div className="ops-form__actions">
          <button type="submit" className="btn-primary" disabled={!file || busy}>
            Upload &amp; load
          </button>
        </div>
      </form>

      {registry ? (
        <form className="ops-form" onSubmit={(event) => event.preventDefault()}>
          <h2 className="ops-form__section">Registry</h2>
          <p className="ops-form__hint">
            Configured registry: <code>{registry}</code>
          </p>
          <label>
            Push local image
            <input
              value={pushRef}
              onChange={(event) => setPushRef(event.target.value)}
              placeholder="name:tag"
            />
          </label>
          <div className="ops-form__actions">
            <button
              type="button"
              disabled={!pushRef.trim() || busy}
              onClick={() => void submit(() => pushImage(pushRef.trim()))}
            >
              Push
            </button>
          </div>
          <label>
            Pull image
            <input
              value={pullRef}
              onChange={(event) => setPullRef(event.target.value)}
              placeholder="name:tag"
            />
          </label>
          <div className="ops-form__actions">
            <button
              type="button"
              disabled={!pullRef.trim() || busy}
              onClick={() => void submit(() => pullImage(pullRef.trim()))}
            >
              Pull
            </button>
          </div>
        </form>
      ) : (
        <p className="ops-form__hint">
          Set CLAB_REGISTRY in Settings to enable registry push and pull.
        </p>
      )}

      <JobsDrawer job={job} onClose={closeJob} />
    </div>
  );
}
