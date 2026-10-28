export type Mode = 'source' | 'target' | 'bilingual' | 'off';
export type SubtitleStyle = { font_family: 'sans' | 'serif' | 'mono'; source_color: string; target_color: string;
  background: number; position: 'bottom' | 'top'; bold: boolean; outline: boolean; line_height: number };
export const defaultSubtitleStyle: SubtitleStyle = { font_family: 'sans', source_color: '#ffffff', target_color: '#f3f1cd',
  background: 0, position: 'bottom', bold: false, outline: true, line_height: 1.5 };
export type Progress = { time: number; rate: number; mode: Mode; overlay: Mode; font: number; style?: SubtitleStyle };
export type TimedCue = { id: string; start: number; end: number; text: string };
export type Cue = TimedCue & { translation: string };
export type Citation = { id: string; start: number; end: number; text: string };
export type WebSource = { id: string; url: string; title: string; content: string; level: string; retrieved: string };
export type Video = { id: string; title: string; duration: number; width?: number; height?: number; path: string; progress: Progress; media_url: string;
  cues: Cue[]; playback_cues: { source: TimedCue[]; target: TimedCue[] }; has_source: boolean; has_target: boolean; browser_ready: boolean; preview?: string; source_url: string;
  subtitle_version: string; subtitle_warnings?: string[]; tracks: Record<string, { language: string; path?: string }>; project_root?: string;
  subtitle_urls?: Partial<Record<'source' | 'target', string>>;
  available_tracks: Array<{ key: string; name: string; path?: string; language: string; role: string }> };
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
export type ChatRequest = {
  provider: string; model: string; question: string; time: number; scope: string; cue_ids: string[];
  search: boolean; search_provider: string; search_query: string;
};
export function resolveSearchQuery(question: string, explicit: string): string {
  const query = explicit.trim();
  if (Array.from(query).length > 128) throw new Error('联网检索词不能超过128字');
  return query || Array.from(question.trim().replace(/\s+/g, ' ')).slice(0, 128).join('');
}
export async function sendChat(videoId: string, options: ChatRequest): Promise<Job> {
  const question = options.question.trim();
  if (!question) throw new Error('请输入问题后再发送');
  const search_query = options.search ? resolveSearchQuery(question, options.search_query) : '';
  // Send a bounded, visible query to search; never derive it from video text or notes.
  return api<Job>('/videos/' + videoId + '/chat', 'POST', {
    provider: options.provider, model: options.model, question, time: options.time, scope: options.scope,
    cue_ids: options.cue_ids, search: options.search, search_provider: options.search_provider, search_query,
  });
}
export const time = (s: number) => {
  const n = Math.max(0, Math.floor(s));
  return [Math.floor(n / 3600), Math.floor(n / 60) % 60, n % 60].map(v => String(v).padStart(2, '0')).join(':');
};
export const activeJob = (job: Job | null) => !!job && ['queued', 'running', 'cancelling'].includes(job.status);

// Parsed tracks are sorted by start time. Rolling platform captions can
// overlap: display the latest active cue without stacking earlier ones.
export function currentCue(cues: TimedCue[], position: number): TimedCue | undefined {
  for (let i = cues.length - 1; i >= 0; i--) {
    if (cues[i].start <= position && position < cues[i].end) return cues[i];
  }
}
