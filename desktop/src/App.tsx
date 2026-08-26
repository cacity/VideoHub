import {
  Captions,
  Clapperboard,
  Clock3,
  Download,
  History,
  LayoutDashboard,
  ListChecks,
  Mic2,
  MonitorPlay,
  Radio,
  Settings,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { desktopApi } from "./api";
import { JobPanel } from "./components/JobPanel";
import type {
  CredentialStatus,
  DesktopSettings,
  HealthStatus,
  IdleQueueSnapshot,
  JobRecord,
  OperationSpec,
} from "./types";
import {
  BatchView,
  CleanupView,
  DashboardView,
  DownloadView,
  DubbingView,
  IdleQueueView,
  JobsView,
  LiveView,
  LocalMediaView,
  SettingsView,
  StudioView,
  SubtitleView,
} from "./views";

type PageId =
  | "dashboard"
  | "download"
  | "local"
  | "subtitle"
  | "dubbing"
  | "batch"
  | "studio"
  | "idle"
  | "queue"
  | "history"
  | "live"
  | "cleanup"
  | "settings";

const navigation: { id: PageId; label: string; icon: typeof Download }[] = [
  { id: "dashboard", label: "概览", icon: LayoutDashboard },
  { id: "download", label: "视频下载", icon: Download },
  { id: "local", label: "本地媒体", icon: MonitorPlay },
  { id: "subtitle", label: "字幕处理", icon: Captions },
  { id: "dubbing", label: "AI 配音", icon: Mic2 },
  { id: "batch", label: "批量处理", icon: Sparkles },
  { id: "studio", label: "故事时间线", icon: Clapperboard },
  { id: "idle", label: "闲时队列", icon: Clock3 },
  { id: "queue", label: "运行任务", icon: ListChecks },
  { id: "history", label: "处理历史", icon: History },
  { id: "live", label: "直播录制", icon: Radio },
  { id: "cleanup", label: "清理工具", icon: Trash2 },
  { id: "settings", label: "设置", icon: Settings },
];

function wait(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

export default function App() {
  const [page, setPage] = useState<PageId>("dashboard");
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [operations, setOperations] = useState<OperationSpec[]>([]);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [settings, setSettings] = useState<DesktopSettings | null>(null);
  const [credentials, setCredentials] = useState<CredentialStatus>({});
  const [idleQueue, setIdleQueue] = useState<IdleQueueSnapshot | null>(null);
  const [storyUrl, setStoryUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refreshJobs = useCallback(async () => {
    const nextJobs = await desktopApi.jobs();
    setJobs(nextJobs);
    setSelectedJobId((current) => current || nextJobs[0]?.id || null);
  }, []);

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      let lastError: unknown = null;
      for (let attempt = 0; attempt < 120 && active; attempt += 1) {
        try {
          const currentHealth = await desktopApi.health();
          const [currentOperations, currentJobs, currentSettings, currentCredentials, currentQueue, currentStoryUrl] =
            await Promise.all([
              desktopApi.capabilities(),
              desktopApi.jobs(),
              desktopApi.settings(),
              desktopApi.credentials(),
              desktopApi.idleQueue(),
              desktopApi.storyEditorUrl(),
            ]);
          if (!active) return;
          setHealth(currentHealth);
          setOperations(currentOperations);
          setJobs(currentJobs);
          setSelectedJobId(currentJobs[0]?.id || null);
          setSettings(currentSettings);
          setCredentials(currentCredentials);
          setIdleQueue(currentQueue);
          setStoryUrl(currentStoryUrl);
          return;
        } catch (caught) {
          lastError = caught;
          await wait(250);
        }
      }
      if (active) setError(lastError instanceof Error ? lastError.message : "无法连接本地服务");
    }
    void bootstrap();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!health) return;
      void Promise.all([desktopApi.health(), desktopApi.jobs(), desktopApi.idleQueue()])
        .then(([nextHealth, nextJobs, nextQueue]) => {
          setHealth(nextHealth);
          setJobs(nextJobs);
          setIdleQueue(nextQueue);
        })
        .catch((caught: unknown) => {
          setError(caught instanceof Error ? caught.message : "任务状态刷新失败");
        });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [health]);

  const submit = useCallback(
    async (operation: string, parameters: Record<string, unknown>) => {
      setBusy(true);
      setError("");
      try {
        const job = await desktopApi.createJob(operation, parameters);
        setSelectedJobId(job.id);
        await refreshJobs();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "任务创建失败");
      } finally {
        setBusy(false);
      }
    },
    [refreshJobs],
  );

  async function cancelJob(id: string) {
    try {
      await desktopApi.cancelJob(id);
      await refreshJobs();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "取消任务失败");
    }
  }

  async function saveSettings(values: Partial<DesktopSettings>) {
    setBusy(true);
    try {
      setSettings(await desktopApi.updateSettings(values));
      setIdleQueue(await desktopApi.idleQueue());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存设置失败");
    } finally {
      setBusy(false);
    }
  }

  async function saveCredentials(values: Record<string, string>) {
    setBusy(true);
    try {
      setCredentials(await desktopApi.updateCredentials(values));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存凭据失败");
    } finally {
      setBusy(false);
    }
  }

  const addIdleTask = useCallback(async (values: Record<string, unknown>) => {
    setBusy(true);
    setError("");
    try {
      setIdleQueue(await desktopApi.addIdleTask(values));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "加入闲时队列失败");
    } finally {
      setBusy(false);
    }
  }, []);

  const pauseIdleQueue = useCallback(async (paused: boolean) => {
    setBusy(true);
    try {
      setIdleQueue(await desktopApi.pauseIdleQueue(paused));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "更新闲时队列失败");
    } finally {
      setBusy(false);
    }
  }, []);

  const removeIdleTask = useCallback(async (id: string) => {
    try {
      setIdleQueue(await desktopApi.removeIdleTask(id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "移除闲时任务失败");
    }
  }, []);

  const clearIdleQueue = useCallback(async () => {
    try {
      setIdleQueue(await desktopApi.clearIdleQueue());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "清空闲时队列失败");
    }
  }, []);

  const runIdleTask = useCallback(async (id: string) => {
    try {
      const result = await desktopApi.runIdleTask(id);
      setIdleQueue(result.queue);
      setSelectedJobId(result.job.id);
      await refreshJobs();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "执行闲时任务失败");
    }
  }, [refreshJobs]);

  const content = useMemo<ReactNode>(() => {
    const props = { submit, busy };
    switch (page) {
      case "download":
        return <DownloadView {...props} />;
      case "local":
        return <LocalMediaView {...props} />;
      case "subtitle":
        return <SubtitleView {...props} />;
      case "dubbing":
        return <DubbingView {...props} />;
      case "batch":
        return <BatchView {...props} />;
      case "studio":
        return <StudioView source={storyUrl} />;
      case "idle":
        return (
          <IdleQueueView
            queue={idleQueue}
            operations={operations}
            busy={busy}
            onAdd={addIdleTask}
            onPause={pauseIdleQueue}
            onRemove={removeIdleTask}
            onClear={clearIdleQueue}
            onRun={runIdleTask}
          />
        );
      case "queue":
        return <JobsView jobs={jobs} />;
      case "history":
        return <JobsView jobs={jobs} history />;
      case "live":
        return <LiveView {...props} />;
      case "cleanup":
        return <CleanupView {...props} />;
      case "settings":
        return (
          <SettingsView
            settings={settings}
            credentials={credentials}
            onSave={saveSettings}
            onSaveCredentials={saveCredentials}
            busy={busy}
          />
        );
      default:
        return (
          <DashboardView
            {...props}
            health={health}
            operations={operations}
            jobs={jobs}
          />
        );
    }
  }, [addIdleTask, busy, clearIdleQueue, credentials, health, idleQueue, jobs, operations, page, pauseIdleQueue, removeIdleTask, runIdleTask, settings, storyUrl, submit]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark"><MonitorPlay size={21} /></span>
          <div><strong>VideoHub</strong><span>Desktop</span></div>
        </div>
        <nav>
          {navigation.map(({ id, label, icon: Icon }) => (
            <button
              className={page === id ? "active" : ""}
              key={id}
              type="button"
              onClick={() => setPage(id)}
              title={label}
            >
              <Icon size={18} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className={`connection-state ${health ? "online" : "offline"}`}>
          <span />
          <div><strong>{health ? "本地服务在线" : "正在连接"}</strong><small>{health ? `PID ${health.pid}` : "Sidecar"}</small></div>
        </div>
      </aside>

      <main className="workspace-pane">
        {error ? (
          <div className="error-banner">
            <span>{error}</span>
            <button className="icon-button" type="button" title="关闭" onClick={() => setError("")}><X size={15} /></button>
          </div>
        ) : null}
        <div className="workspace-scroll">{content}</div>
      </main>

      <JobPanel
        jobs={jobs}
        selectedId={selectedJobId}
        onSelect={setSelectedJobId}
        onCancel={cancelJob}
      />
    </div>
  );
}
