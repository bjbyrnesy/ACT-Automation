import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ThemePicker } from "../theme/ThemePicker";

type Settings = {
  CLAB_HOST: string;
  CLAB_IMAGE: string;
  CLAB_NAME: string;
  ACT_TENANT: string;
  ACT_USER: string;
  ACT_API_KEY: string | null;
  CVAAS_HOST: string;
  CVAAS_USER: string;
  CVAAS_TOKEN: string | null;
  GENERIC_VERSION: string;
  GENERIC_USERNAME: string;
  GENERIC_PASSWORD: string | null;
  preview_auto: boolean;
  preview_debounce_ms: number;
};

const EMPTY: Settings = {
  CLAB_HOST: "",
  CLAB_IMAGE: "",
  CLAB_NAME: "",
  ACT_TENANT: "",
  ACT_USER: "",
  ACT_API_KEY: null,
  CVAAS_HOST: "",
  CVAAS_USER: "",
  CVAAS_TOKEN: null,
  GENERIC_VERSION: "",
  GENERIC_USERNAME: "",
  GENERIC_PASSWORD: null,
  preview_auto: false,
  preview_debounce_ms: 400,
};

function asSettings(raw: Record<string, unknown>): Settings {
  return {
    ...EMPTY,
    CLAB_HOST: String(raw.CLAB_HOST ?? ""),
    CLAB_IMAGE: String(raw.CLAB_IMAGE ?? ""),
    CLAB_NAME: String(raw.CLAB_NAME ?? ""),
    ACT_TENANT: String(raw.ACT_TENANT ?? ""),
    ACT_USER: String(raw.ACT_USER ?? ""),
    ACT_API_KEY:
      raw.ACT_API_KEY === null || raw.ACT_API_KEY === undefined
        ? null
        : String(raw.ACT_API_KEY),
    CVAAS_HOST: String(raw.CVAAS_HOST ?? ""),
    CVAAS_USER: String(raw.CVAAS_USER ?? ""),
    CVAAS_TOKEN:
      raw.CVAAS_TOKEN === null || raw.CVAAS_TOKEN === undefined
        ? null
        : String(raw.CVAAS_TOKEN),
    GENERIC_VERSION: String(raw.GENERIC_VERSION ?? ""),
    GENERIC_USERNAME: String(raw.GENERIC_USERNAME ?? ""),
    GENERIC_PASSWORD:
      raw.GENERIC_PASSWORD === null || raw.GENERIC_PASSWORD === undefined
        ? null
        : String(raw.GENERIC_PASSWORD),
    preview_auto: Boolean(raw.preview_auto),
    preview_debounce_ms: Number(raw.preview_debounce_ms ?? 400),
  };
}

export function SettingsPage() {
  const [form, setForm] = useState<Settings>(EMPTY);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    const response = await fetch("/api/settings");
    if (!response.ok) {
      throw new Error(`Failed to load settings (${response.status})`);
    }
    const body = (await response.json()) as Record<string, unknown>;
    setForm(asSettings(body));
  }, []);

  useEffect(() => {
    void load().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : String(err));
    });
  }, [load]);

  function update<K extends keyof Settings>(key: K, value: Settings[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setStatus(null);
    setError(null);
    try {
      const response = await fetch("/api/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          CLAB_HOST: form.CLAB_HOST,
          CLAB_IMAGE: form.CLAB_IMAGE,
          CLAB_NAME: form.CLAB_NAME,
          ACT_TENANT: form.ACT_TENANT,
          ACT_USER: form.ACT_USER,
          ACT_API_KEY: form.ACT_API_KEY,
          CVAAS_HOST: form.CVAAS_HOST,
          CVAAS_USER: form.CVAAS_USER,
          CVAAS_TOKEN: form.CVAAS_TOKEN,
          GENERIC_VERSION: form.GENERIC_VERSION,
          GENERIC_USERNAME: form.GENERIC_USERNAME,
          GENERIC_PASSWORD: form.GENERIC_PASSWORD,
          preview_auto: form.preview_auto,
          preview_debounce_ms: form.preview_debounce_ms,
        }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as {
          detail?: string;
        } | null;
        throw new Error(body?.detail ?? `Save failed (${response.status})`);
      }
      setForm(asSettings((await response.json()) as Record<string, unknown>));
      setStatus("Saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  const hostLabel = form.CLAB_HOST.trim() ? form.CLAB_HOST.trim() : "local";

  return (
    <>
      <h1>Settings</h1>
      <p>
        Clab host badge: <strong>{hostLabel}</strong> (empty host means local).
      </p>
      {error ? <p className="page-error">{error}</p> : null}
      {status ? <p className="page-status">{status}</p> : null}
      <form className="settings-form" onSubmit={(event) => void onSubmit(event)}>
        <fieldset>
          <legend>containerlab</legend>
          <label>
            CLAB_HOST
            <input
              value={form.CLAB_HOST}
              placeholder="empty = local"
              onChange={(event) => update("CLAB_HOST", event.target.value)}
            />
          </label>
          <label>
            CLAB_IMAGE
            <input
              value={form.CLAB_IMAGE}
              onChange={(event) => update("CLAB_IMAGE", event.target.value)}
            />
          </label>
          <label>
            CLAB_NAME
            <input
              value={form.CLAB_NAME}
              onChange={(event) => update("CLAB_NAME", event.target.value)}
            />
          </label>
        </fieldset>
        <fieldset>
          <legend>ACT / CVaaS</legend>
          <label>
            ACT_TENANT
            <input
              value={form.ACT_TENANT}
              onChange={(event) => update("ACT_TENANT", event.target.value)}
            />
          </label>
          <label>
            ACT_USER
            <input
              value={form.ACT_USER}
              onChange={(event) => update("ACT_USER", event.target.value)}
            />
          </label>
          <label>
            ACT_API_KEY
            <input
              value={form.ACT_API_KEY ?? ""}
              onChange={(event) =>
                update("ACT_API_KEY", event.target.value || null)
              }
            />
          </label>
          <label>
            CVAAS_HOST
            <input
              value={form.CVAAS_HOST}
              onChange={(event) => update("CVAAS_HOST", event.target.value)}
            />
          </label>
          <label>
            CVAAS_USER
            <input
              value={form.CVAAS_USER}
              onChange={(event) => update("CVAAS_USER", event.target.value)}
            />
          </label>
          <label>
            CVAAS_TOKEN
            <input
              value={form.CVAAS_TOKEN ?? ""}
              onChange={(event) =>
                update("CVAAS_TOKEN", event.target.value || null)
              }
            />
          </label>
        </fieldset>
        <fieldset>
          <legend>Attach defaults</legend>
          <label>
            GENERIC_VERSION
            <input
              value={form.GENERIC_VERSION}
              onChange={(event) =>
                update("GENERIC_VERSION", event.target.value)
              }
            />
          </label>
          <label>
            GENERIC_USERNAME
            <input
              value={form.GENERIC_USERNAME}
              onChange={(event) =>
                update("GENERIC_USERNAME", event.target.value)
              }
            />
          </label>
          <label>
            GENERIC_PASSWORD
            <input
              value={form.GENERIC_PASSWORD ?? ""}
              onChange={(event) =>
                update("GENERIC_PASSWORD", event.target.value || null)
              }
            />
          </label>
        </fieldset>
        <ThemePicker />
        <fieldset>
          <legend>Preview</legend>
          <label className="settings-form__check">
            <input
              type="checkbox"
              checked={form.preview_auto}
              onChange={(event) => update("preview_auto", event.target.checked)}
            />
            Auto-preview
          </label>
          <label>
            Debounce (ms)
            <input
              type="number"
              min={0}
              value={form.preview_debounce_ms}
              onChange={(event) =>
                update("preview_debounce_ms", Number(event.target.value) || 0)
              }
            />
          </label>
        </fieldset>
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? "Saving…" : "Save settings"}
        </button>
      </form>
    </>
  );
}
