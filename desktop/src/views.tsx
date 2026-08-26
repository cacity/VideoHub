import { open } from "@tauri-apps/plugin-dialog";
import {
  Activity,
  CheckCircle2,
  Clock3,
  FileAudio,
  FileVideo2,
  FolderCog,
  KeyRound,
  ListVideo,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Scissors,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { Field, PathField, SubmitButton, Toggle } from "./components/Controls";
import type {
  CredentialStatus,
  DesktopSettings,
  HealthStatus,
  IdleQueueSnapshot,
  JobRecord,
  OperationSpec,
} from "./types";

export type SubmitTask = (
  operation: string,
  parameters: Record<string, unknown>,
) => Promise<void>;

interface ViewProps {
  submit: SubmitTask;
  busy: boolean;
}

function extractUrl(value: string): string {
  return value.match(/https?:\/\/[^\s<>"']+/i)?.[0]?.replace(/[),.;，。；]+$/, "") || value.trim();
}

export function DashboardView({
  health,
  operations,
  jobs,
  submit,
  busy,
}: ViewProps & {
  health: HealthStatus | null;
  operations: OperationSpec[];
  jobs: JobRecord[];
}) {
  const completed = jobs.filter((job) => job.status === "succeeded").length;
  const failed = jobs.filter((job) => job.status === "failed").length;
  return (
    <div className="view-stack">
      <header className="view-header">
        <div>
          <span className="eyebrow">本地工作台</span>
          <h1>处理概览</h1>
        </div>
        <button
          className="secondary-button"
          type="button"
          disabled={busy}
          onClick={() => void submit("system.preflight", {})}
        >
          <RefreshCw size={16} /> 环境检查
        </button>
      </header>
      <section className="metric-band">
        <div><Activity size={18} /><span>Sidecar</span><strong>{health?.status || "连接中"}</strong></div>
        <div><ListVideo size={18} /><span>可用操作</span><strong>{operations.length}</strong></div>
        <div><CheckCircle2 size={18} /><span>已完成</span><strong>{completed}</strong></div>
        <div><ShieldCheck size={18} /><span>失败</span><strong>{failed}</strong></div>
      </section>
      <section className="section-block">
        <div className="section-title"><h2>最近任务</h2></div>
        <div className="table-list">
          {jobs.slice(0, 8).map((job) => (
            <div className="table-row" key={job.id}>
              <span className={`status-dot ${job.status}`} />
              <strong>{job.operation}</strong>
              <span>{job.message}</span>
              <span>{job.progress}%</span>
            </div>
          ))}
          {jobs.length === 0 ? <div className="empty-state">暂无任务</div> : null}
        </div>
      </section>
    </div>
  );
}

export function DownloadView({ submit, busy }: ViewProps) {
  const [url, setUrl] = useState("");
  const [source, setSource] = useState("auto");
  const [output, setOutput] = useState("");
  const [cookies, setCookies] = useState("");
  const [playlist, setPlaylist] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const cleanUrl = extractUrl(url);
    let operation = "platform.download";
    if (source === "douyin" || (source === "auto" && /douyin\.com|v\.douyin\.com/i.test(cleanUrl))) {
      operation = "douyin.download";
    } else if (source === "koushare" || (source === "auto" && /koushare\.com/i.test(cleanUrl))) {
      operation = "koushare.download";
    }
    await submit(operation, {
      url: cleanUrl,
      platform: source === "auto" ? undefined : source,
      output_dir: output || undefined,
      cookies_file: cookies || undefined,
      playlist,
    });
  }

  return (
    <form className="view-stack" onSubmit={(event) => void handleSubmit(event)}>
      <header className="view-header"><div><span className="eyebrow">媒体获取</span><h1>视频下载</h1></div></header>
      <section className="section-block form-grid">
        <Field label="视频链接">
          <textarea
            rows={3}
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            onPaste={(event) => {
              const value = extractUrl(event.clipboardData.getData("text"));
              if (value.startsWith("http")) {
                event.preventDefault();
                setUrl(value);
              }
            }}
            placeholder="粘贴 YouTube、抖音、Instagram、Bilibili、Twitter/X 或其他 yt-dlp 链接"
            required
          />
        </Field>
        <Field label="来源">
          <select value={source} onChange={(event) => setSource(event.target.value)}>
            <option value="auto">自动识别</option>
            <option value="youtube">YouTube / 通用</option>
            <option value="douyin">抖音</option>
            <option value="instagram">Instagram</option>
            <option value="twitter">Twitter / X</option>
            <option value="bilibili">Bilibili</option>
            <option value="koushare">蔻享</option>
          </select>
        </Field>
        <PathField label="输出目录" value={output} onChange={setOutput} directory placeholder="使用平台默认目录" />
        <PathField
          label="Cookies 文件"
          value={cookies}
          onChange={setCookies}
          filters={[{ name: "Cookies", extensions: ["txt"] }]}
          placeholder="可选"
        />
        <Toggle label="下载播放列表" checked={playlist} onChange={setPlaylist} />
      </section>
      <div className="form-footer"><SubmitButton busy={busy} label="开始下载" /></div>
    </form>
  );
}

export function LocalMediaView({ submit, busy }: ViewProps) {
  const [mode, setMode] = useState("local.video");
  const [path, setPath] = useState("");
  const [output, setOutput] = useState("");
  const [subtitles, setSubtitles] = useState(true);
  const [translate, setTranslate] = useState(true);
  const [article, setArticle] = useState(true);
  const [polish, setPolish] = useState(false);
  const directory = mode === "local.video_batch" || mode === "audio.extract";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await submit(mode, {
      path,
      output_dir: output || undefined,
      generate_subtitles: subtitles,
      translate_to_chinese: translate,
      generate_article: article,
      enable_translation_polish: polish,
      series_project: mode === "local.video_batch",
    });
  }

  return (
    <form className="view-stack" onSubmit={(event) => void handleSubmit(event)}>
      <header className="view-header"><div><span className="eyebrow">本地素材</span><h1>导入与处理</h1></div></header>
      <div className="segmented-control" role="tablist">
        {[
          ["local.video", "单个视频", FileVideo2],
          ["local.audio", "单个音频", FileAudio],
          ["local.video_batch", "剧集目录", ListVideo],
          ["audio.extract", "提取音频", Scissors],
        ].map(([value, label, Icon]) => (
          <button className={mode === value ? "active" : ""} type="button" key={String(value)} onClick={() => setMode(String(value))}>
            <Icon size={16} /> {String(label)}
          </button>
        ))}
      </div>
      <section className="section-block form-grid">
        <PathField label={directory ? "素材目录" : "素材文件"} value={path} onChange={setPath} directory={directory} placeholder="选择本地素材" />
        <PathField label="输出目录" value={output} onChange={setOutput} directory placeholder="使用默认目录" />
        {mode !== "audio.extract" ? (
          <div className="toggle-grid">
            <Toggle label="生成字幕" checked={subtitles} onChange={setSubtitles} />
            <Toggle label="翻译为中文" checked={translate} onChange={setTranslate} />
            <Toggle label="生成摘要" checked={article} onChange={setArticle} />
            <Toggle label="DeepSeek 润色" checked={polish} onChange={setPolish} />
          </div>
        ) : null}
      </section>
      <div className="form-footer"><SubmitButton busy={busy} /></div>
    </form>
  );
}

export function SubtitleView({ submit, busy }: ViewProps) {
  const [mode, setMode] = useState("subtitle.translate");
  const [subtitle, setSubtitle] = useState("");
  const [video, setVideo] = useState("");
  const [output, setOutput] = useState("");
  const [language, setLanguage] = useState("zh-CN");
  const [polish, setPolish] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await submit(mode, {
      path: subtitle,
      subtitle_path: subtitle,
      video_path: video,
      output_dir: output || undefined,
      target_language: language,
      enable_translation_polish: polish,
    });
  }

  return (
    <form className="view-stack" onSubmit={(event) => void handleSubmit(event)}>
      <header className="view-header"><div><span className="eyebrow">字幕工作流</span><h1>翻译与烧录</h1></div></header>
      <div className="segmented-control">
        <button type="button" className={mode === "subtitle.translate" ? "active" : ""} onClick={() => setMode("subtitle.translate")}>字幕翻译</button>
        <button type="button" className={mode === "subtitle.embed" ? "active" : ""} onClick={() => setMode("subtitle.embed")}>烧录字幕</button>
      </div>
      <section className="section-block form-grid">
        {mode === "subtitle.embed" ? <PathField label="视频文件" value={video} onChange={setVideo} filters={[{ name: "Video", extensions: ["mp4", "mkv", "mov", "webm"] }]} /> : null}
        <PathField label="字幕文件" value={subtitle} onChange={setSubtitle} filters={[{ name: "Subtitle", extensions: ["srt", "ass", "vtt"] }]} />
        <PathField label="输出目录" value={output} onChange={setOutput} directory placeholder="使用默认目录" />
        {mode === "subtitle.translate" ? (
          <>
            <Field label="目标语言"><select value={language} onChange={(event) => setLanguage(event.target.value)}><option value="zh-CN">简体中文</option><option value="en">English</option><option value="ja">日本語</option></select></Field>
            <Toggle label="DeepSeek 整体润色" checked={polish} onChange={setPolish} />
          </>
        ) : null}
      </section>
      <div className="form-footer"><SubmitButton busy={busy} /></div>
    </form>
  );
}

export function DubbingView({ submit, busy }: ViewProps) {
  const [video, setVideo] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [output, setOutput] = useState("");
  const [backend, setBackend] = useState("minimax");
  const [voice, setVoice] = useState("Chinese (Mandarin)_Male_Announcer");
  const [speed, setSpeed] = useState(1.2);
  const [burnMode, setBurnMode] = useState("none");
  const [background, setBackground] = useState(true);
  const [backgroundVolume, setBackgroundVolume] = useState(0.2);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await submit("dubbing.run", {
      video_path: video,
      subtitle_path: subtitle || undefined,
      output_path: output || undefined,
      tts_backend: backend,
      voice,
      minimax_voice_id: voice,
      speed,
      subtitle_burn_mode: burnMode,
      keep_background_audio: background,
      background_volume: backgroundVolume,
    });
  }

  return (
    <form className="view-stack" onSubmit={(event) => void handleSubmit(event)}>
      <header className="view-header"><div><span className="eyebrow">AI 音频</span><h1>视频配音</h1></div></header>
      <section className="section-block form-grid two-column">
        <PathField label="视频文件" value={video} onChange={setVideo} filters={[{ name: "Video", extensions: ["mp4", "mkv", "mov", "webm"] }]} />
        <PathField label="字幕文件" value={subtitle} onChange={setSubtitle} filters={[{ name: "Subtitle", extensions: ["srt", "ass", "vtt"] }]} placeholder="可自动转录" />
        <PathField label="输出文件" value={output} onChange={setOutput} placeholder="自动命名" />
        <Field label="TTS 引擎"><select value={backend} onChange={(event) => setBackend(event.target.value)}><option value="minimax">MiniMax</option><option value="cosyvoice">CosyVoice</option><option value="kokoro">Kokoro</option></select></Field>
        <Field label="音色 ID"><input value={voice} onChange={(event) => setVoice(event.target.value)} /></Field>
        <Field label={`语速 ${speed.toFixed(1)}x`}><input type="range" min="0.7" max="1.5" step="0.1" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} /></Field>
        <Field label="字幕烧录"><select value={burnMode} onChange={(event) => setBurnMode(event.target.value)}><option value="none">不烧录</option><option value="single">单语字幕</option><option value="bilingual">双语字幕</option></select></Field>
        <Toggle label="保留背景原声" checked={background} onChange={setBackground} />
        {background ? <Field label={`原声音量 ${backgroundVolume.toFixed(1)}x`}><input type="range" min="0" max="1" step="0.1" value={backgroundVolume} onChange={(event) => setBackgroundVolume(Number(event.target.value))} /></Field> : null}
      </section>
      <div className="form-footer"><SubmitButton busy={busy} label="开始配音" /></div>
    </form>
  );
}

export function BatchView({ submit, busy }: ViewProps) {
  const [mode, setMode] = useState("youtube.batch");
  const [urls, setUrls] = useState("");
  const [path, setPath] = useState("");
  const [polish, setPolish] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const parameters = mode === "youtube.batch"
      ? { urls: urls.split(/\r?\n/).map(extractUrl).filter(Boolean), enable_translation_polish: polish, generate_subtitles: true }
      : { path, series_project: true, enable_translation_polish: polish, generate_subtitles: true };
    await submit(mode, parameters);
  }

  return (
    <form className="view-stack" onSubmit={(event) => void handleSubmit(event)}>
      <header className="view-header"><div><span className="eyebrow">批量生产</span><h1>批处理</h1></div></header>
      <div className="segmented-control">
        <button type="button" className={mode === "youtube.batch" ? "active" : ""} onClick={() => setMode("youtube.batch")}>链接列表</button>
        <button type="button" className={mode === "local.video_batch" ? "active" : ""} onClick={() => setMode("local.video_batch")}>剧集目录</button>
      </div>
      <section className="section-block form-grid">
        {mode === "youtube.batch" ? <Field label="视频链接（每行一个）"><textarea rows={10} value={urls} onChange={(event) => setUrls(event.target.value)} required /></Field> : <PathField label="项目目录" value={path} onChange={setPath} directory />}
        <Toggle label="DeepSeek 润色" checked={polish} onChange={setPolish} />
      </section>
      <div className="form-footer"><SubmitButton busy={busy} label="创建批量任务" /></div>
    </form>
  );
}

export function IdleQueueView({
  queue,
  operations,
  busy,
  onAdd,
  onPause,
  onRemove,
  onClear,
  onRun,
}: {
  queue: IdleQueueSnapshot | null;
  operations: OperationSpec[];
  busy: boolean;
  onAdd: (values: Record<string, unknown>) => Promise<void>;
  onPause: (paused: boolean) => Promise<void>;
  onRemove: (id: string) => Promise<void>;
  onClear: () => Promise<void>;
  onRun: (id: string) => Promise<void>;
}) {
  const [operation, setOperation] = useState("platform.download");
  const [title, setTitle] = useState("");
  const [input, setInput] = useState("");
  const queueOperations = operations.filter((item) =>
    [
      "platform.download",
      "douyin.download",
      "koushare.download",
      "youtube.process",
      "local.audio",
      "local.video",
      "local.video_batch",
      "local.text",
      "audio.extract",
      "live.record",
    ].includes(item.id),
  );
  const usesPath = operation.startsWith("local.") || operation === "audio.extract";

  async function addTask(event: FormEvent) {
    event.preventDefault();
    await onAdd({
      title: title.trim() || input.trim(),
      operation,
      parameters: { [usesPath ? "path" : "url"]: usesPath ? input.trim() : extractUrl(input) },
    });
    setTitle("");
    setInput("");
  }

  return (
    <div className="view-stack">
      <header className="view-header">
        <div><span className="eyebrow">定时执行</span><h1>闲时队列</h1></div>
        <div className="header-actions">
          <button className="secondary-button" type="button" disabled={busy || !queue} onClick={() => void onPause(!queue?.idle_paused)}>
            {queue?.idle_paused ? <Play size={16} /> : <Pause size={16} />}
            {queue?.idle_paused ? "继续" : "暂停"}
          </button>
          <button className="danger-button" type="button" disabled={busy || !queue?.tasks.length} onClick={() => void onClear()}><Trash2 size={16} /> 清空</button>
        </div>
      </header>
      <section className="queue-band">
        <div><Clock3 size={17} /><span>执行时段</span><strong>{queue ? `${queue.idle_start_time} - ${queue.idle_end_time}` : "读取中"}</strong></div>
        <div><Activity size={17} /><span>当前状态</span><strong>{queue?.idle_paused ? "已暂停" : queue?.in_idle_window ? "闲时执行中" : "等待时段"}</strong></div>
        <div><ListVideo size={17} /><span>待执行</span><strong>{queue?.tasks.length || 0}</strong></div>
      </section>
      <form className="section-block form-grid two-column" onSubmit={(event) => void addTask(event)}>
        <div className="section-title full-span"><h2>添加任务</h2></div>
        <Field label="操作">
          <select value={operation} onChange={(event) => setOperation(event.target.value)}>
            {queueOperations.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}
          </select>
        </Field>
        <Field label="任务名称"><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="可选" /></Field>
        <Field label={usesPath ? "本地路径" : "视频或直播链接"}>
          <input value={input} onChange={(event) => setInput(event.target.value)} required />
        </Field>
        <div className="form-footer queue-submit"><SubmitButton busy={busy} label="加入队列" /></div>
      </form>
      <section className="section-block table-list queue-list">
        {queue?.tasks.map((task) => (
          <div className="queue-row" key={task.id}>
            <span className="status-dot" />
            <div><strong>{task.title}</strong><span>{task.operation}</span></div>
            <time>{new Date(task.created_at).toLocaleString()}</time>
            <button className="icon-button" type="button" title="立即执行" onClick={() => void onRun(task.id)}><Play size={15} /></button>
            <button className="icon-button danger" type="button" title="移除" onClick={() => void onRemove(task.id)}><Trash2 size={15} /></button>
          </div>
        ))}
        {!queue?.tasks.length ? <div className="empty-state">暂无闲时任务</div> : null}
      </section>
    </div>
  );
}

export function StudioView({ source }: { source: string }) {
  return (
    <div className="view-stack studio-view">
      <header className="view-header"><div><span className="eyebrow">五轨精修</span><h1>故事时间线</h1></div></header>
      {source ? <iframe title="VideoHub 故事时间线" src={source} /> : <div className="empty-state">正在连接故事时间线</div>}
    </div>
  );
}

export function LiveView({ submit, busy }: ViewProps) {
  const [url, setUrl] = useState("");
  const [output, setOutput] = useState("");
  const [cookies, setCookies] = useState("");
  const [duration, setDuration] = useState(0);
  const [container, setContainer] = useState("ts");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await submit("live.record", {
      url: extractUrl(url),
      output_dir: output || undefined,
      cookies_file: cookies || undefined,
      duration_seconds: duration > 0 ? Math.round(duration * 60) : 0,
      container,
    });
  }

  return (
    <form className="view-stack" onSubmit={(event) => void handleSubmit(event)}>
      <header className="view-header"><div><span className="eyebrow">直播流</span><h1>直播录制</h1></div><Radio size={22} /></header>
      <section className="section-block form-grid two-column">
        <div className="full-span"><Field label="直播间或直播流链接"><textarea rows={3} value={url} onChange={(event) => setUrl(event.target.value)} required /></Field></div>
        <PathField label="输出目录" value={output} onChange={setOutput} directory placeholder="使用直播默认目录" />
        <PathField label="Cookies 文件" value={cookies} onChange={setCookies} filters={[{ name: "Cookies", extensions: ["txt"] }]} placeholder="可选" />
        <Field label="录制时长（分钟）" hint="0 表示持续录制，手动取消任务即可停止"><input type="number" min="0" step="1" value={duration} onChange={(event) => setDuration(Number(event.target.value))} /></Field>
        <Field label="容器"><select value={container} onChange={(event) => setContainer(event.target.value)}><option value="ts">TS</option><option value="mp4">MP4</option><option value="mkv">MKV</option></select></Field>
      </section>
      <div className="form-footer"><SubmitButton busy={busy} label="开始录制" /></div>
    </form>
  );
}

export function CleanupView({ submit, busy }: ViewProps) {
  const [directories, setDirectories] = useState<string[]>([]);
  async function addDirectory() {
    const selected = await open({ directory: true, multiple: true });
    if (Array.isArray(selected)) setDirectories(Array.from(new Set([...directories, ...selected])));
    else if (typeof selected === "string") setDirectories(Array.from(new Set([...directories, selected])));
  }
  return (
    <div className="view-stack">
      <header className="view-header"><div><span className="eyebrow">存储管理</span><h1>清理工具</h1></div></header>
      <section className="section-block">
        <div className="section-title"><h2>清理目录</h2><button className="secondary-button" type="button" onClick={() => void addDirectory()}><FolderCog size={16} /> 添加目录</button></div>
        <div className="directory-list">
          {directories.map((path) => <div key={path}><span>{path}</span><button className="icon-button" type="button" title="移除" onClick={() => setDirectories(directories.filter((item) => item !== path))}><Trash2 size={15} /></button></div>)}
          {directories.length === 0 ? <div className="empty-state">尚未选择目录</div> : null}
        </div>
      </section>
      <div className="form-footer split-actions">
        <button className="secondary-button" type="button" disabled={busy} onClick={() => void submit("cleanup.preview", { directories })}>预览</button>
        <button className="danger-button" type="button" disabled={busy || directories.length === 0} onClick={() => void submit("cleanup.execute", { directories, confirmed: true })}><Trash2 size={16} /> 执行清理</button>
      </div>
    </div>
  );
}

export function JobsView({ jobs, history = false }: { jobs: JobRecord[]; history?: boolean }) {
  const terminal = new Set(["succeeded", "failed", "cancelled", "interrupted"]);
  const filtered = jobs.filter((job) => (history ? terminal.has(job.status) : !terminal.has(job.status)));
  return (
    <div className="view-stack">
      <header className="view-header"><div><span className="eyebrow">任务记录</span><h1>{history ? "处理历史" : "运行队列"}</h1></div></header>
      <section className="section-block table-list">
        {filtered.map((job) => <div className="table-row wide" key={job.id}><span className={`status-dot ${job.status}`} /><strong>{job.operation}</strong><span>{job.message}</span><span>{job.progress}%</span><time>{new Date(job.created_at).toLocaleString()}</time></div>)}
        {filtered.length === 0 ? <div className="empty-state">暂无记录</div> : null}
      </section>
    </div>
  );
}

export function SettingsView({
  settings,
  credentials,
  onSave,
  onSaveCredentials,
  busy,
}: {
  settings: DesktopSettings | null;
  credentials: CredentialStatus;
  onSave: (values: Partial<DesktopSettings>) => Promise<void>;
  onSaveCredentials: (values: Record<string, string>) => Promise<void>;
  busy: boolean;
}) {
  const [draft, setDraft] = useState<DesktopSettings | null>(settings);
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  useEffect(() => {
    if (settings) setDraft(settings);
  }, [settings]);
  if (!draft) return <div className="empty-state">正在读取设置</div>;
  const update = <K extends keyof DesktopSettings>(key: K, value: DesktopSettings[K]) => setDraft({ ...draft, [key]: value });
  return (
    <div className="view-stack">
      <header className="view-header"><div><span className="eyebrow">应用配置</span><h1>设置</h1></div></header>
      <section className="section-block form-grid two-column">
        <div className="section-title full-span"><h2>工作目录与模型</h2></div>
        <PathField label="工作目录" value={draft.workspace_dir} onChange={(value) => update("workspace_dir", value)} directory />
        <Field label="Whisper 模型"><select value={draft.whisper_model} onChange={(event) => update("whisper_model", event.target.value)}><option value="tiny">tiny</option><option value="base">base</option><option value="small">small</option><option value="medium">medium</option><option value="large-v3">large-v3</option></select></Field>
        <Field label="目标语言"><input value={draft.target_language} onChange={(event) => update("target_language", event.target.value)} placeholder="zh-CN" /></Field>
        <Field label="翻译方式"><select value={draft.translation_method} onChange={(event) => update("translation_method", event.target.value)}><option value="google">Google</option><option value="llm">大模型</option></select></Field>
        <Toggle label="默认启用 DeepSeek 润色" checked={draft.translation_polish} onChange={(value) => update("translation_polish", value)} />
        <Field label="OpenAI 模型"><input value={draft.openai_model} onChange={(event) => update("openai_model", event.target.value)} /></Field>
        <Field label="OpenAI Base URL"><input value={draft.openai_base_url} onChange={(event) => update("openai_base_url", event.target.value)} /></Field>
        <Field label="DeepSeek 模型"><input value={draft.deepseek_model} onChange={(event) => update("deepseek_model", event.target.value)} /></Field>
        <Field label="DeepSeek Base URL"><input value={draft.deepseek_base_url} onChange={(event) => update("deepseek_base_url", event.target.value)} /></Field>
        <Field label="代理"><input value={draft.proxy} onChange={(event) => update("proxy", event.target.value)} placeholder="http://127.0.0.1:7890" /></Field>
        <Field label="闲时开始"><input type="time" value={draft.idle_start} onChange={(event) => update("idle_start", event.target.value)} /></Field>
        <Field label="闲时结束"><input type="time" value={draft.idle_end} onChange={(event) => update("idle_end", event.target.value)} /></Field>
        <Field label="yt-dlp 模式"><select value={draft.ytdlp_mode} onChange={(event) => update("ytdlp_mode", event.target.value)}><option value="python">Python 包</option><option value="local">本地可执行文件</option></select></Field>
        <PathField label="yt-dlp 可执行文件" value={draft.ytdlp_exe_path} onChange={(value) => update("ytdlp_exe_path", value)} filters={[{ name: "Executable", extensions: ["exe"] }]} />
        <Field label="中文字幕字体"><input value={draft.subtitle_font_zh} onChange={(event) => update("subtitle_font_zh", event.target.value)} /></Field>
        <Field label="中文字幕字号"><input type="number" min="12" max="160" value={draft.subtitle_font_zh_size} onChange={(event) => update("subtitle_font_zh_size", Number(event.target.value))} /></Field>
        <Field label="英文字幕字体"><input value={draft.subtitle_font_en} onChange={(event) => update("subtitle_font_en", event.target.value)} /></Field>
        <Field label="英文字幕字号"><input type="number" min="12" max="160" value={draft.subtitle_font_en_size} onChange={(event) => update("subtitle_font_en_size", Number(event.target.value))} /></Field>
      </section>
      <section className="section-block form-grid two-column">
        <div className="section-title full-span"><h2>配音引擎</h2></div>
        <Field label="默认 TTS"><select value={draft.tts_backend} onChange={(event) => update("tts_backend", event.target.value)}><option value="minimax">MiniMax</option><option value="cosyvoice">CosyVoice</option><option value="kokoro">Kokoro</option><option value="doubao">豆包</option></select></Field>
        <Field label="MiniMax 模型"><input value={draft.minimax_model} onChange={(event) => update("minimax_model", event.target.value)} /></Field>
        <Field label="MiniMax 音色"><input value={draft.minimax_voice_id} onChange={(event) => update("minimax_voice_id", event.target.value)} /></Field>
        <Field label="MiniMax 语言增强"><input value={draft.minimax_language_boost} onChange={(event) => update("minimax_language_boost", event.target.value)} /></Field>
        <Field label="CosyVoice 服务"><input value={draft.cosyvoice_url} onChange={(event) => update("cosyvoice_url", event.target.value)} /></Field>
        <Field label="CosyVoice 模式"><select value={draft.cosyvoice_mode} onChange={(event) => update("cosyvoice_mode", event.target.value)}><option value="sft">SFT</option><option value="zero_shot">Zero-shot</option><option value="instruct">Instruct</option></select></Field>
        <Field label="CosyVoice 音色"><input value={draft.cosyvoice_speaker} onChange={(event) => update("cosyvoice_speaker", event.target.value)} /></Field>
        <Field label="CosyVoice 指令"><input value={draft.cosyvoice_instruction} onChange={(event) => update("cosyvoice_instruction", event.target.value)} /></Field>
        <div className="full-span form-footer"><button className="primary-button" type="button" disabled={busy} onClick={() => void onSave(draft)}><ShieldCheck size={16} /> 保存设置</button></div>
      </section>
      <section className="section-block form-grid two-column">
        <div className="section-title full-span"><h2>系统凭据</h2><KeyRound size={17} /></div>
        {[
          ["openai_api_key", "OpenAI API Key"],
          ["deepseek_api_key", "DeepSeek API Key"],
          ["claude_api_key", "Claude API Key"],
          ["minimax_api_key", "MiniMax API Key"],
          ["doubao_tts_app_id", "豆包 App ID"],
          ["doubao_tts_access_token", "豆包 Access Token"],
          ["koushare_access_token", "蔻享 Access Token"],
        ].map(([key, label]) => <Field label={`${label}${credentials[key] ? " · 已配置" : ""}`} key={key}><input type="password" value={secrets[key] || ""} onChange={(event) => setSecrets({ ...secrets, [key]: event.target.value })} placeholder={credentials[key] ? "留空保持不变" : "未配置"} /></Field>)}
        <div className="full-span form-footer"><button className="secondary-button" type="button" disabled={busy || !Object.values(secrets).some(Boolean)} onClick={() => void onSaveCredentials(Object.fromEntries(Object.entries(secrets).filter(([, value]) => value)))}><KeyRound size={16} /> 更新凭据</button></div>
      </section>
    </div>
  );
}
