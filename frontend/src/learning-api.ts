export type Mode = 'source' | 'target' | 'bilingual' | 'off';
export type Progress = { time: number; rate: number; mode: Mode; overlay: Mode; font: number };
export type Cue = { id: string; start: number; end: number; text: string; translation: string };
export type Citation = { id: string; start: number; end: number; text: string };
export type WebSource = { id: string; url: string; title: string; content: string; level: string; retrieved: string };
export type Video = { id: string; title: string; duration: number; width?: number; height?: number; path: string; progress: Progress; media_url: string;
  cues: Cue[]; has_source: boolean; has_target: boolean; browser_ready: boolean; preview?: string; source_url: string;
  subtitle_version: string; tracks: Record<string, { language: string }>; project_root?: string;
  available_tracks: Array<{ key: string; name: string; language: string; role: string }> };
export type Message = { id: string; role: 'user' | 'assistant'; text: string; time: number; status: string;
  citations?: Citation[]; sources?: WebSource[]; searched_sources?: WebSource[]; warnings?: string[];
  usage?: { total_tokens?: number }; subtitle_version: string; provider?: string; model?: string };
export type Chapter = { title: string; summary: string; start: number; end: number; cue_ids: string[] };
export type Job = { id: string; video_id: string; kind: string; status: string; progress: number; message: string; text: string;
  outline?: Chapter[]; warnings?: string[]; result?: { outline?: Chapter[]; answer?: Message }; coverage?: { completed: number; total: number } };
export type Note = { id: string; text: string; start: number; end: number; created: string; updated: string;
  version: number; subtitle_version: string; citations: Citation[]; sources: WebSource[]; tags: string[] };
export type Study = { messages: Message[]; notes: Note[]; outline: Chapter[]; active_job: Job | null };
export type Providers = Record<string, { configured: boolean; model: string; input_budget: number; error?: string }>;
let token = '';
export const setToken = (value: string) => { token = value; };
export async function api<T>(path: string, method = 'GET', data?: unknown): Promise<T> {
  const response = await fetch('/api/learning' + path, { method, headers: { 'Content-Type': 'application/json',
    'X-Learning-Token': token }, body: data === undefined ? undefined : JSON.stringify(data),
    keepalive: method === 'PUT' && path.endsWith('/progress') });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '操作失败');
  return result;
}
export const time = (s: number) => {
  const n = Math.max(0, Math.floor(s));
  return [Math.floor(n / 3600), Math.floor(n / 60) % 60, n % 60].map(v => String(v).padStart(2, '0')).join(':');
};
export const activeJob = (job: Job | null) => !!job && ['queued', 'running', 'cancelling'].includes(job.status);
