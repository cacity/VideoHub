import React, { useEffect, useState } from 'react';
import { Download, Scissors, X } from 'lucide-react';
import { activeJob, api, Job, time } from './learning-api';

function timestamp(seconds: number): string {
  const [whole, decimal] = seconds.toFixed(6).split('.');
  const fraction = decimal.replace(/0+$/, '');
  return time(Number(whole)) + (fraction ? '.' + fraction : '');
}

function parseTimestamp(value: string): number {
  const text = value.trim();
  if (/^\d+(?:\.\d{1,6})?$/.test(text)) return Number(text);
  const parts = /^(?:(\d+):)?([0-5]?\d):([0-5]?\d(?:\.\d{1,6})?)$/.exec(text);
  return parts ? Number(parts[1] || 0) * 3600 + Number(parts[2]) * 60 + Number(parts[3]) : NaN;
}

type Props = { videoId: string; duration: number; position: () => number; close: () => void };

export function LearningClip({ videoId, duration, position, close }: Props) {
  const [start, setStart] = useState('00:00:00');
  const [end, setEnd] = useState(() => timestamp(duration));
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const base = '/videos/' + videoId + '/clips';
  const working = activeJob(job);
  const from = parseTimestamp(start);
  const to = parseTimestamp(end);
  const valid = 0 <= from && from < to && to <= duration;
  const clip = job?.status === 'finished' ? job.result?.clip : undefined;

  useEffect(() => {
    let disposed = false;
    void api<{ job: Job | null }>(base).then(data => {
      if (!disposed) setJob(data.job);
    }).catch(e => { if (!disposed) setError(e.message); })
      .finally(() => { if (!disposed) setBusy(false); });
    return () => { disposed = true; };
  }, [base]);

  const jobId = job?.id;
  useEffect(() => {
    if (!working || !jobId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<Job>('/jobs/' + jobId);
        if (disposed) return;
        setJob(next);
        if (!activeJob(next)) return;
      } catch (e) {
        if (disposed) return;
        setError((e as Error).message);
      }
      timer = setTimeout(() => void poll(), 900);
    };
    timer = setTimeout(() => void poll(), 300);
    return () => { disposed = true; clearTimeout(timer); };
  }, [working, jobId]);

  const action = async (work: () => Promise<Job>) => {
    setBusy(true); setError('');
    try { setJob(await work()); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return <form className="clip-editor" id="learning-clip" aria-labelledby="learning-clip-title" onSubmit={e => {
    e.preventDefault();
    if (valid && !working && !busy) void action(() => api<Job>(base, 'POST', { start: from, end: to }));
  }}>
    <div className="clip-header"><h2 id="learning-clip-title"><Scissors size={16}/>截取片段</h2>
      <button type="button" onClick={close} aria-label="收起截取工具"><X size={16}/></button></div>
    <p className="muted">拖动播放器到切点，或输入时:分:秒（可带小数）。原视频会保留。</p>
    <div className="clip-points">
      <div><label>开始时间<input value={start} disabled={busy || working} onChange={e => setStart(e.target.value)}/></label>
        <button type="button" disabled={busy || working} onClick={() => setStart(timestamp(position()))}>设为起点</button></div>
      <div><label>结束时间<input value={end} disabled={busy || working} onChange={e => setEnd(e.target.value)}/></label>
        <button type="button" disabled={busy || working} onClick={() => setEnd(timestamp(position()))}>设为终点</button></div>
    </div>
    {!valid && <p className="warning">请选择视频时长内的起止点，结束时间须晚于开始时间。</p>}
    <div className="clip-actions">
      <button className="primary" disabled={busy || working || !valid}>导出 MP4</button>
      {working && job && <button type="button" disabled={busy || job.status === 'cancelling'} onClick={() => void action(() => api<Job>('/jobs/' + job.id + '/cancel', 'POST', {}))}>停止截取</button>}
    </div>
    {working && job && <div className="clip-status" role="status"><progress max={100} value={job.progress} aria-label="视频截取进度"/>{job.message} {job.progress}%</div>}
    {job && ['failed', 'cancelled', 'interrupted'].includes(job.status) && <p className="warning" role="alert">{job.status === 'cancelled' ? '截取已停止。' : job.message}</p>}
    {error && <p className="warning" role="alert">{error}</p>}
    {clip && <div className="clip-result"><a className="button" href={'/api/learning/jobs/' + job?.id + '/clip'} download><Download size={15}/>下载片段</a>
      <span title={clip.name}>{timestamp(clip.start)} – {timestamp(clip.end)}</span></div>}
  </form>;
}
