import type {
  PreviewBody,
  PreviewResult,
  WriteTopologyBody,
  WriteTopologyResult,
} from "./types";

type ValidationIssue = { loc?: (string | number)[]; msg?: string };

export class ApiError extends Error {
  readonly status: number;
  readonly fields: Record<string, string>;

  constructor(message: string, status: number, fields: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fields = fields;
  }
}

async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const errorBody = payload && typeof payload === "object" ? payload as {
      detail?: string | ValidationIssue[];
      fields?: Record<string, string>;
    } : {};
    const fields = { ...errorBody.fields };
    let message = `Request failed (${response.status})`;
    if (typeof errorBody.detail === "string") {
      message = errorBody.detail;
    } else if (Array.isArray(errorBody.detail)) {
      message = errorBody.detail.map((issue) => {
        const field = issue.loc?.filter((part) => part !== "body").join(".") || "form";
        fields[field] = issue.msg || "Invalid value";
        return `${field}: ${fields[field]}`;
      }).join("; ");
    }
    throw new ApiError(message, response.status, fields);
  }
  return payload as T;
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload === "object" && "detail" in payload
      ? payload.detail : null;
    throw new ApiError(typeof detail === "string" ? detail : `Request failed (${response.status})`, response.status);
  }
  return payload as T;
}

export type Job = {
  id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed";
  log?: string;
};

export function submitClabJob(
  action: "generate" | "deploy" | "destroy" | "redeploy" | "onboard",
  body: { path: string; [key: string]: unknown },
) {
  return postJson<Job>(`/api/jobs/clab/${action}`, body);
}

export function submitActJob(
  action: "upload" | "onboard",
  body: { path: string; [key: string]: unknown },
) {
  return postJson<Job>(`/api/jobs/act/${action}`, body);
}

export function getJob(id: string, signal?: AbortSignal) {
  return getJson<Job>(`/api/jobs/${encodeURIComponent(id)}`, signal);
}

export type SavedTopology = { path: string; name: string; yaml_text?: string };

export function extendTopology(body: Record<string, unknown>) {
  return postJson<SavedTopology>("/api/extend", body);
}

export function attachTopology(body: Record<string, unknown>) {
  return postJson<SavedTopology>("/api/attach", body);
}

export function getTopology(name: string) {
  return getJson<SavedTopology>(`/api/topologies/${encodeURIComponent(name)}`);
}

export function previewSavedTopology(yamlText: string) {
  return postJson<{ png_base64: string | null }>("/api/preview-from-yaml", { yaml_text: yamlText });
}

export async function loadSavedTopology(result: SavedTopology) {
  const saved = result.yaml_text ? result : await getTopology(result.name);
  if (!saved.yaml_text) throw new Error("Saved topology has no YAML");
  let pngBase64: string | null = null;
  try {
    pngBase64 = (await previewSavedTopology(saved.yaml_text)).png_base64;
  } catch {
    // The written YAML is still usable if diagram generation fails.
  }
  return {
    path: result.path || saved.path,
    name: result.name || saved.name,
    yamlText: saved.yaml_text,
    pngBase64,
    isDraft: false,
  };
}

export function previewTopology(body: PreviewBody, signal?: AbortSignal) {
  return postJson<PreviewResult>("/api/preview", body, signal);
}

export function writeTopology(body: WriteTopologyBody, signal?: AbortSignal) {
  return postJson<WriteTopologyResult>("/api/topologies", body, signal);
}
