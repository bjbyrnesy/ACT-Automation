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

export type TopologyVersion = {
  name: string;
  path: string;
  lab_id: string;
  mtime: number;
  has_clab_sibling: boolean;
};

export type LabSummary = {
  id: string;
  version_count: number;
  latest: TopologyVersion;
  versions: TopologyVersion[];
};

export type SavedTopology = {
  path: string;
  name: string;
  lab_id?: string;
  yaml_text?: string;
};

export type AttachMlagPair = {
  index: number;
  leaf_a: string;
  leaf_b: string;
  site: string | null;
  label: string;
};

export type AttachMleaf = {
  index: number;
  name: string;
  site: string | null;
  mlag_pair: number | null;
  leaf_a: string | null;
  leaf_b: string | null;
  label: string;
};

export type AttachTargets = {
  mlag_pairs: AttachMlagPair[];
  mleafs: AttachMleaf[];
};

export function extendTopology(body: Record<string, unknown>) {
  return postJson<SavedTopology>("/api/extend", body);
}

export function attachTopology(body: Record<string, unknown>) {
  return postJson<SavedTopology>("/api/attach", body);
}

export function listLabs() {
  return getJson<LabSummary[]>("/api/labs");
}

export function getLab(labId: string) {
  return getJson<LabSummary>(`/api/labs/${encodeURIComponent(labId)}`);
}

export function getTopology(name: string) {
  return getJson<SavedTopology>(`/api/topologies/${encodeURIComponent(name)}`);
}

export function deleteTopology(name: string) {
  return fetch(`/api/topologies/${encodeURIComponent(name)}`, {
    method: "DELETE",
  }).then(async (response) => {
    if (!response.ok) {
      const payload: unknown = await response.json().catch(() => null);
      const detail =
        payload && typeof payload === "object" && "detail" in payload
          ? (payload as { detail?: unknown }).detail
          : null;
      throw new ApiError(
        typeof detail === "string"
          ? detail
          : `Request failed (${response.status})`,
        response.status,
      );
    }
    return response.json() as Promise<{ deleted: string }>;
  });
}

export function getAttachTargets(name: string) {
  return getJson<AttachTargets>(
    `/api/topologies/${encodeURIComponent(name)}/attach-targets`,
  );
}

export function previewSavedTopology(yamlText: string) {
  return postJson<{ png_base64: string | null }>("/api/preview-from-yaml", {
    yaml_text: yamlText,
  });
}

export async function loadSavedTopology(result: SavedTopology) {
  const saved = result.yaml_text ? result : await getTopology(result.name);
  if (!saved.yaml_text) throw new Error("Saved topology has no YAML");
  const name = result.name || saved.name;
  return {
    path: result.path || saved.path || null,
    name,
    labId: result.lab_id || saved.lab_id || labIdFromFilename(name),
    yamlText: saved.yaml_text,
    // SPA renders CvDiagram from YAML; Graphviz PNG is unused in the pane.
    pngBase64: null,
    isDraft: false,
  };
}

export function labIdFromFilename(name: string): string {
  const stem = name.replace(/\.(ya?ml)$/i, "");
  const match = /^(.*)-(\d{4}-\d{2}-\d{2})(?:-(\d+))?$/.exec(stem);
  return match ? match[1] : stem;
}

export function previewTopology(body: PreviewBody, signal?: AbortSignal) {
  return postJson<PreviewResult>("/api/preview", body, signal);
}

export function writeTopology(body: WriteTopologyBody, signal?: AbortSignal) {
  return postJson<WriteTopologyResult>("/api/topologies", body, signal);
}
