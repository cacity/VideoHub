import { Ban, CheckCircle2, Clock3, LoaderCircle, XCircle } from "lucide-react";

import type { JobRecord, JobStatus } from "../types";

interface JobPanelProps {
  jobs: JobRecord[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCancel: (id: string) => Promise<void>;
}

const terminal = new Set<JobStatus>(["succeeded", "failed", "cancelled", "interrupted"]);

function StatusIcon({ status }: { status: JobStatus }) {
  if (status === "succeeded") return <CheckCircle2 size={15} />;
  if (status === "failed" || status === "interrupted") return <XCircle size={15} />;
  if (status === "cancelled") return <Ban size={15} />;
  if (status === "running") return <LoaderCircle className="spin" size={15} />;
  return <Clock3 size={15} />;
}

function timeLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function JobPanel({ jobs, selectedId, onSelect, onCancel }: JobPanelProps) {
  const selected = jobs.find((job) => job.id === selectedId) || jobs[0];
  return (
    <aside className="job-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">任务中心</span>
          <h2>{jobs.filter((job) => !terminal.has(job.status)).length} 个进行中</h2>
        </div>
      </div>

      <div className="job-list">
        {jobs.length === 0 ? <div className="empty-state">暂无任务</div> : null}
        {jobs.slice(0, 20).map((job) => (
          <button
            className={`job-row ${selected?.id === job.id ? "selected" : ""}`}
            key={job.id}
            type="button"
            onClick={() => onSelect(job.id)}
          >
            <span className={`job-status ${job.status}`}>
              <StatusIcon status={job.status} />
            </span>
            <span className="job-copy">
              <strong>{job.operation}</strong>
              <span>{job.message || job.status}</span>
            </span>
            <time>{timeLabel(job.created_at)}</time>
          </button>
        ))}
      </div>

      {selected ? (
        <div className="job-detail">
          <div className="job-detail-title">
            <div>
              <span className="eyebrow">当前任务</span>
              <h3>{selected.operation}</h3>
            </div>
            {!terminal.has(selected.status) ? (
              <button
                className="icon-button danger"
                type="button"
                title="取消任务"
                onClick={() => void onCancel(selected.id)}
              >
                <Ban size={16} />
              </button>
            ) : null}
          </div>
          <div className="progress-track">
            <span style={{ width: `${selected.progress}%` }} />
          </div>
          <div className="progress-copy">
            <span>{selected.message}</span>
            <strong>{selected.progress}%</strong>
          </div>
          <pre className="job-log">
            {selected.logs.length ? selected.logs.slice(-80).join("\n") : "等待日志..."}
          </pre>
          {selected.error ? <div className="error-box">{selected.error}</div> : null}
        </div>
      ) : null}
    </aside>
  );
}
