export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "interrupted";

export interface ApiConfig {
  port: number;
  token: string;
  data_dir?: string;
}

export interface OperationSpec {
  id: string;
  title: string;
  category: string;
  description: string;
}

export interface JobRecord {
  id: string;
  operation: string;
  parameters: Record<string, unknown>;
  status: JobStatus;
  progress: number;
  message: string;
  logs: string[];
  result: unknown;
  error: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface DesktopSettings {
  workspace_dir: string;
  openai_model: string;
  openai_base_url: string;
  deepseek_model: string;
  deepseek_base_url: string;
  proxy: string;
  whisper_model: string;
  target_language: string;
  translation_method: string;
  translation_polish: boolean;
  tts_backend: string;
  cosyvoice_url: string;
  cosyvoice_mode: string;
  cosyvoice_speaker: string;
  cosyvoice_instruction: string;
  minimax_api_url: string;
  minimax_model: string;
  minimax_voice_id: string;
  minimax_language_boost: string;
  subtitle_font_zh: string;
  subtitle_font_zh_size: number;
  subtitle_font_en: string;
  subtitle_font_en_size: number;
  ytdlp_mode: string;
  ytdlp_exe_path: string;
  koushare_username: string;
  idle_start: string;
  idle_end: string;
}

export type CredentialStatus = Record<string, boolean>;

export interface IdleQueueTask {
  id: string;
  title: string;
  operation: string;
  parameters: Record<string, unknown>;
  created_at: string;
}

export interface IdleQueueSnapshot {
  tasks: IdleQueueTask[];
  idle_start_time: string;
  idle_end_time: string;
  is_idle_running: boolean;
  idle_paused: boolean;
  in_idle_window: boolean;
}

export interface HealthStatus {
  status: string;
  version: string;
  pid: number;
  data_dir: string;
  workspace_dir: string;
  active_jobs: number;
}
