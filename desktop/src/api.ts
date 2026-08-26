import { invoke } from "@tauri-apps/api/core";

import type {
  ApiConfig,
  CredentialStatus,
  DesktopSettings,
  HealthStatus,
  JobRecord,
  IdleQueueSnapshot,
  OperationSpec,
} from "./types";

let configPromise: Promise<ApiConfig> | null = null;

async function loadConfig(): Promise<ApiConfig> {
  if (window.__TAURI_INTERNALS__) {
    return invoke<ApiConfig>("get_api_config");
  }
  return {
    port: Number(import.meta.env.VITE_VIDEOHUB_API_PORT || 8765),
    token: String(import.meta.env.VITE_VIDEOHUB_API_TOKEN || ""),
  };
}

function apiConfig(): Promise<ApiConfig> {
  configPromise ||= loadConfig();
  return configPromise;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const config = await apiConfig();
  const headers = new Headers(init.headers);
  if (config.token) headers.set("Authorization", `Bearer ${config.token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`http://127.0.0.1:${config.port}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      message = payload.detail || message;
    } catch {
      // Keep the HTTP status when the sidecar returns no JSON body.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const desktopApi = {
  health: () => request<HealthStatus>("/v1/health"),
  capabilities: async () =>
    (await request<{ operations: OperationSpec[] }>("/v1/capabilities")).operations,
  jobs: async () => (await request<{ items: JobRecord[] }>("/v1/jobs")).items,
  job: (id: string) => request<JobRecord>(`/v1/jobs/${id}`),
  createJob: (operation: string, parameters: Record<string, unknown>) =>
    request<JobRecord>("/v1/jobs", {
      method: "POST",
      body: JSON.stringify({ operation, parameters }),
    }),
  cancelJob: (id: string) =>
    request<JobRecord>(`/v1/jobs/${id}/cancel`, { method: "POST" }),
  idleQueue: () => request<IdleQueueSnapshot>("/v1/idle-queue"),
  addIdleTask: async (values: Record<string, unknown>) =>
    (
      await request<{ queue: IdleQueueSnapshot }>("/v1/idle-queue", {
        method: "POST",
        body: JSON.stringify(values),
      })
    ).queue,
  pauseIdleQueue: (paused: boolean) =>
    request<IdleQueueSnapshot>("/v1/idle-queue/state", {
      method: "PUT",
      body: JSON.stringify({ paused }),
    }),
  removeIdleTask: (id: string) =>
    request<IdleQueueSnapshot>(`/v1/idle-queue/${id}`, { method: "DELETE" }),
  clearIdleQueue: () =>
    request<IdleQueueSnapshot>("/v1/idle-queue", { method: "DELETE" }),
  runIdleTask: async (id: string) =>
    request<{ queue: IdleQueueSnapshot; job: JobRecord }>(`/v1/idle-queue/${id}/run`, {
      method: "POST",
    }),
  storyEditorUrl: async () => {
    const config = await apiConfig();
    return `http://127.0.0.1:${config.port}/story-editor?token=${encodeURIComponent(config.token)}`;
  },
  settings: async () =>
    (await request<{ values: DesktopSettings }>("/v1/settings")).values,
  updateSettings: async (values: Partial<DesktopSettings>) =>
    (
      await request<{ values: DesktopSettings }>("/v1/settings", {
        method: "PUT",
        body: JSON.stringify({ values }),
      })
    ).values,
  credentials: async () =>
    (await request<{ configured: CredentialStatus }>("/v1/credentials")).configured,
  updateCredentials: async (values: Record<string, string>) =>
    (
      await request<{ configured: CredentialStatus }>("/v1/credentials", {
        method: "PUT",
        body: JSON.stringify({ values }),
      })
    ).configured,
};
