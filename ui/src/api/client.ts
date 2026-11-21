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

export function previewTopology(body: PreviewBody, signal?: AbortSignal) {
  return postJson<PreviewResult>("/api/preview", body, signal);
}

export function writeTopology(body: WriteTopologyBody, signal?: AbortSignal) {
  return postJson<WriteTopologyResult>("/api/topologies", body, signal);
}
