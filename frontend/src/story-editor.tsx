import React, { PointerEvent as ReactPointerEvent, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  ChevronLeft,
  ChevronRight,
  Clapperboard,
  Check,
  Film,
  FolderOpen,
  KeyRound,
  Pause,
  Play,
  Redo2,
  RefreshCw,
  Save,
  Scissors,
  Split,
  Trash2,
  Undo2,
  Upload,
  Volume2,
} from 'lucide-react';
import './story-editor.css';

type ProjectSummary = {
  id: string;
  name: string;
  jobId: string;
  clipCount: number;
  durationSec: number;
};

type Clip = {
  id: string;
  base_segment_id: string;
  source_id: string;
  label: string;
  source_start_sec: number;
  source_end_sec: number;
  output_start_sec: number;
  output_end_sec: number;
  duration_sec: number;
  playback_rate: number;
  kind: string;
  story_role: string;
  audio_mode: string;
  transition: string;
  transition_duration_sec: number;
  fade_in_sec: number;
  fade_out_sec: number;
  volume_keyframes: Array<{ id: string; time_sec: number; volume: number }>;
  story_reason: string;
  analysis_refs: string[];
  source_subtitle_ids: string[];
  source_scene_ids: string[];
  source_text: string;
  target_text: string;
  speaker: string;
  thumbnail_url: string;
};

type TrackItem = {
  id: string;
  segment_id: string;
  local_start_sec: number;
  local_end_sec: number;
  text?: string;
  subtitle_text?: string;
  purpose?: string;
  kind?: string;
  audio_url?: string;
  [key: string]: unknown;
};

type Timeline = {
  schema_version: string;
  projectId: string;
  projectName: string;
  jobId: string;
  revisionId: string | null;
  source: {
    filename: string;
    duration_sec: number;
    width: number;
    height: number;
    fps: number;
    language: string;
    media_url: string;
  };
  sources: Array<{
    id: string;
    filename: string;
    duration_sec: number;
    width: number;
    height: number;
    fps: number;
    audio_present: boolean;
    media_url: string;
  }>;
  settings: {
    snap_sec: number;
    burn_subtitles: 'none' | 'source' | 'translated' | 'bilingual';
    original_audio_volume: number;
    source_audio_volume: number;
  };
  clips: Clip[];
  tracks: {
    original_audio: TrackItem[];
    narration: TrackItem[];
    source_audio: TrackItem[];
    subtitles: TrackItem[];
  };
  assets: { narration_ready: boolean; narration_manifest: string };
  revisions: string[];
};

type RenderJob = {
  id: string;
  status: 'queued' | 'running' | 'finished' | 'failed';
  progress: number;
  message: string;
  outputUrl?: string;
  logs?: string[];
};

type EditableTrackName = 'narration' | 'source_audio' | 'subtitles';
type SelectedTrackItem = { track: EditableTrackName; id: string } | null;

const LABEL_WIDTH = 148;
const MIN_CLIP_DURATION = 0.25;

function cloneTimeline(value: Timeline): Timeline {
  return structuredClone(value);
}

function clipDuration(clip: Clip): number {
  return (clip.source_end_sec - clip.source_start_sec) / Math.max(0.01, clip.playback_rate || 1);
}

function timelineLayout(clips: Clip[]) {
  const starts: Record<string, number> = {};
  let cursor = 0;
  let previousDuration = 0;
  clips.forEach((clip, index) => {
    const duration = clipDuration(clip);
    if (index > 0 && clip.transition === 'crossfade') {
      const requested = Math.max(0, clip.transition_duration_sec ?? 0.5);
      cursor -= Math.min(requested, previousDuration / 2, duration / 2);
    }
    starts[clip.id] = cursor;
    cursor += duration;
    previousDuration = duration;
  });
  return { starts, duration: cursor };
}

function formatTime(value: number, milliseconds = true): string {
  const safe = Math.max(0, value || 0);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = Math.floor(safe % 60);
  const millis = Math.floor((safe - Math.floor(safe)) * 1000);
  const base = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  return milliseconds ? `${base}.${String(millis).padStart(3, '0')}` : base;
}

function snap(value: number, interval: number): number {
  return Math.round(value / interval) * interval;
}

function itemAbsoluteStart(item: TrackItem, starts: Record<string, number>): number {
  return (starts[item.segment_id] ?? 0) + item.local_start_sec;
}

function itemAbsoluteEnd(item: TrackItem, starts: Record<string, number>): number {
  return (starts[item.segment_id] ?? 0) + item.local_end_sec;
}

function activeClipAt(clips: Clip[], starts: Record<string, number>, time: number): Clip | undefined {
  return clips.find((clip) => {
    const start = starts[clip.id];
    return time >= start && time < start + clipDuration(clip);
  }) ?? clips[clips.length - 1];
}

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `请求失败 (${response.status})`);
  }
  return payload as T;
}

function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectId, setProjectId] = useState('');
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<SelectedTrackItem>(null);
  const [draftText, setDraftText] = useState('');
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [zoom, setZoom] = useState(8);
  const [status, setStatus] = useState('正在查找解说项目…');
  const [statusKind, setStatusKind] = useState<'normal' | 'error' | 'success'>('normal');
  const [renderJob, setRenderJob] = useState<RenderJob | null>(null);
  const [saving, setSaving] = useState(false);
  const [dragPreview, setDragPreview] = useState<{ clipId: string; start: number; end: number } | null>(null);
  const [trackDragPreview, setTrackDragPreview] = useState<{
    track: EditableTrackName;
    itemId: string;
    start: number;
    end: number;
  } | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [rewriting, setRewriting] = useState(false);
  const [rewriteInstruction, setRewriteInstruction] = useState('让这段解说更自然、紧凑，并与上下文顺畅衔接');
  const [sourcePath, setSourcePath] = useState('');
  const [addingSource, setAddingSource] = useState(false);
  const [previewSourceId, setPreviewSourceId] = useState('source-main');
  const undoStack = useRef<Timeline[]>([]);
  const redoStack = useRef<Timeline[]>([]);
  const videoRef = useRef<HTMLVideoElement>(null);
  const narrationRef = useRef<HTMLAudioElement>(new Audio());
  const activeNarrationId = useRef<string | null>(null);
  const activeClipId = useRef<string | null>(null);
  const rafRef = useRef<number | null>(null);
  const pendingSeek = useRef<{ sourceTime: number; shouldPlay: boolean; clipId: string } | null>(null);

  const layout = useMemo(() => timelineLayout(timeline?.clips ?? []), [timeline?.clips]);
  const selectedClip = timeline?.clips.find((clip) => clip.id === selectedClipId) ?? null;
  const selectedTrackItem = selectedItem && timeline
    ? timeline.tracks[selectedItem.track].find((item) => item.id === selectedItem.id) ?? null
    : null;

  useEffect(() => {
    if (!selectedTrackItem) {
      setDraftText('');
      return;
    }
    setDraftText(String(selectedTrackItem.text ?? selectedTrackItem.purpose ?? ''));
  }, [selectedItem?.track, selectedItem?.id, selectedTrackItem?.text, selectedTrackItem?.purpose]);

  const setMessage = (message: string, kind: 'normal' | 'error' | 'success' = 'normal') => {
    setStatus(message);
    setStatusKind(kind);
  };

  useEffect(() => {
    api<{ projects: ProjectSummary[] }>('/api/story-editor/projects')
      .then(({ projects: found }) => {
        setProjects(found);
        if (found.length) {
          const preferred = found.find((item) => item.name.includes('project011')) ?? found[0];
          setProjectId(preferred.id);
        } else {
          setMessage('没有找到包含 story_plan.json 的解说项目', 'error');
        }
      })
      .catch((error: Error) => setMessage(error.message, 'error'));
  }, []);

  useEffect(() => {
    if (!projectId) return;
    setTimeline(null);
    setMessage('正在打开项目…');
    api<Timeline>(`/api/story-editor/projects/${projectId}`)
      .then((value) => {
        setTimeline(value);
        setSelectedClipId(value.clips[0]?.id ?? null);
        setSelectedItem(null);
        activeClipId.current = value.clips[0]?.id ?? null;
        setPlayhead(0);
        setPreviewSourceId(value.clips[0]?.source_id ?? 'source-main');
        undoStack.current = [];
        redoStack.current = [];
        setMessage(`已打开 ${value.projectName}`, 'success');
      })
      .catch((error: Error) => setMessage(error.message, 'error'));
  }, [projectId]);

  const commit = (next: Timeline, message?: string) => {
    if (!timeline) return;
    undoStack.current.push(cloneTimeline(timeline));
    if (undoStack.current.length > 80) undoStack.current.shift();
    redoStack.current = [];
    setTimeline(next);
    if (message) setMessage(message);
  };

  const undo = () => {
    if (!timeline || !undoStack.current.length) return;
    redoStack.current.push(cloneTimeline(timeline));
    const previous = undoStack.current.pop()!;
    setTimeline(previous);
    setSelectedClipId((current) => previous.clips.some((clip) => clip.id === current) ? current : previous.clips[0]?.id ?? null);
    setMessage('已撤销上一步');
  };

  const redo = () => {
    if (!timeline || !redoStack.current.length) return;
    undoStack.current.push(cloneTimeline(timeline));
    const next = redoStack.current.pop()!;
    setTimeline(next);
    setMessage('已恢复下一步');
  };

  const seekComposition = (time: number, shouldPlay = playing) => {
    if (!timeline || !videoRef.current) return;
    const bounded = Math.min(Math.max(0, time), Math.max(0, layout.duration - 0.001));
    const clip = activeClipAt(timeline.clips, layout.starts, bounded);
    if (!clip) return;
    const local = bounded - layout.starts[clip.id];
    const sourceTime = clip.source_start_sec + local * clip.playback_rate;
    const video = videoRef.current;
    const sourceId = clip.source_id || 'source-main';
    if (sourceId !== previewSourceId) {
      pendingSeek.current = { sourceTime, shouldPlay, clipId: clip.id };
      activeClipId.current = clip.id;
      setPreviewSourceId(sourceId);
      setPlayhead(bounded);
      return;
    }
    if (Math.abs(video.currentTime - sourceTime) > 0.08) video.currentTime = sourceTime;
    video.playbackRate = clip.playback_rate;
    activeClipId.current = clip.id;
    setPlayhead(bounded);
    if (shouldPlay) void video.play();
  };

  const syncNarration = (time: number, shouldPlay: boolean) => {
    if (!timeline) return;
    const item = timeline.tracks.narration.find(
      (entry) => time >= itemAbsoluteStart(entry, layout.starts) && time < itemAbsoluteEnd(entry, layout.starts),
    );
    const audio = narrationRef.current;
    if (!item?.audio_url) {
      if (!audio.paused) audio.pause();
      activeNarrationId.current = null;
      return;
    }
    const offset = time - itemAbsoluteStart(item, layout.starts);
    if (activeNarrationId.current !== item.id) {
      activeNarrationId.current = item.id;
      audio.src = item.audio_url;
      audio.currentTime = Math.max(0, offset);
    } else if (Math.abs(audio.currentTime - offset) > 0.25) {
      audio.currentTime = Math.max(0, offset);
    }
    if (shouldPlay && audio.paused) void audio.play().catch(() => undefined);
    if (!shouldPlay && !audio.paused) audio.pause();
  };

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !timeline) return;
    const tick = () => {
      if (video.paused || video.ended) return;
      const clip = timeline.clips.find((item) => item.id === activeClipId.current)
        ?? activeClipAt(timeline.clips, layout.starts, playhead);
      if (!clip) return;
      let composition = layout.starts[clip.id] + (video.currentTime - clip.source_start_sec) / clip.playback_rate;
      if (video.currentTime >= clip.source_end_sec - 0.035) {
        const index = timeline.clips.findIndex((entry) => entry.id === clip.id);
        const next = timeline.clips[index + 1];
        if (!next) {
          video.pause();
          setPlaying(false);
          composition = layout.duration;
        } else {
          composition = layout.starts[next.id];
          activeClipId.current = next.id;
          if ((next.source_id || 'source-main') !== previewSourceId) {
            pendingSeek.current = {
              sourceTime: next.source_start_sec,
              shouldPlay: true,
              clipId: next.id,
            };
            setPreviewSourceId(next.source_id || 'source-main');
            return;
          }
          video.currentTime = next.source_start_sec;
          video.playbackRate = next.playback_rate;
        }
      }
      const anchorActive = timeline.tracks.source_audio.some(
        (item) => composition >= itemAbsoluteStart(item, layout.starts) && composition < itemAbsoluteEnd(item, layout.starts),
      );
      video.volume = Math.min(1, Math.max(0, anchorActive ? timeline.settings.source_audio_volume : timeline.settings.original_audio_volume));
      setPlayhead(composition);
      syncNarration(composition, true);
      rafRef.current = requestAnimationFrame(tick);
    };
    if (playing) rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, timeline, layout.starts, layout.duration, previewSourceId]);

  const togglePlayback = () => {
    const video = videoRef.current;
    if (!video || !timeline) return;
    if (playing) {
      video.pause();
      narrationRef.current.pause();
      setPlaying(false);
    } else {
      seekComposition(playhead, true);
      setPlaying(true);
    }
  };

  const normalizeLinkedItems = (
    next: Timeline,
    clipId: string,
    newDuration: number,
    sourceShiftSec: number,
  ) => {
    (['narration', 'source_audio', 'subtitles'] as const).forEach((trackName) => {
      next.tracks[trackName] = next.tracks[trackName].flatMap((item) => {
        if (item.segment_id !== clipId) return [item];
        const sourceBound = trackName === 'source_audio' || (trackName === 'subtitles' && item.kind === 'source_dialogue');
        const start = item.local_start_sec - (sourceBound ? sourceShiftSec : 0);
        const end = item.local_end_sec - (sourceBound ? sourceShiftSec : 0);
        if (end <= 0 || start >= newDuration) return [];
        return [{ ...item, local_start_sec: Math.max(0, start), local_end_sec: Math.min(newDuration, end) }];
      });
    });
    const original = next.tracks.original_audio.find((item) => item.segment_id === clipId);
    if (original) original.local_end_sec = newDuration;
  };

  const applyTrim = (clipId: string, newStart: number, newEnd: number) => {
    if (!timeline) return;
    const next = cloneTimeline(timeline);
    const clip = next.clips.find((item) => item.id === clipId);
    if (!clip) return;
    const oldStart = clip.source_start_sec;
    clip.source_start_sec = newStart;
    clip.source_end_sec = newEnd;
    const duration = clipDuration(clip);
    clip.duration_sec = duration;
    const sourceShift = (newStart - oldStart) / clip.playback_rate;
    normalizeLinkedItems(next, clipId, duration, sourceShift);
    commit(next, `已调整 ${clipId} 切点`);
  };

  const commitTrackPosition = (
    trackName: EditableTrackName,
    itemId: string,
    absoluteStart: number,
    absoluteEnd: number,
    mode: 'move' | 'left' | 'right',
  ) => {
    if (!timeline) return;
    const next = cloneTimeline(timeline);
    const item = next.tracks[trackName].find((entry) => entry.id === itemId);
    if (!item) return;
    let targetClip = next.clips.find((clip) => clip.id === item.segment_id);
    if (mode === 'move') {
      targetClip = activeClipAt(next.clips, layout.starts, (absoluteStart + absoluteEnd) / 2);
    }
    if (!targetClip) return;
    const clipStart = layout.starts[targetClip.id];
    const duration = clipDuration(targetClip);
    let localStart = absoluteStart - clipStart;
    let localEnd = absoluteEnd - clipStart;
    const itemDuration = localEnd - localStart;
    if (mode === 'move') {
      localStart = Math.min(Math.max(0, localStart), Math.max(0, duration - itemDuration));
      localEnd = localStart + Math.min(itemDuration, duration);
    } else {
      localStart = Math.max(0, localStart);
      localEnd = Math.min(duration, localEnd);
    }
    if (localEnd - localStart < 0.05) {
      setMessage('轨道块至少保留 0.05 秒', 'error');
      return;
    }
    item.segment_id = targetClip.id;
    item.local_start_sec = Number(localStart.toFixed(3));
    item.local_end_sec = Number(localEnd.toFixed(3));
    commit(next, `已调整 ${itemId}`);
    setSelectedClipId(targetClip.id);
  };

  const beginTrackDrag = (
    event: ReactPointerEvent,
    trackName: EditableTrackName,
    item: TrackItem,
    mode: 'move' | 'left' | 'right',
  ) => {
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    const pointerStart = event.clientX;
    const initialStart = itemAbsoluteStart(item, layout.starts);
    const initialEnd = itemAbsoluteEnd(item, layout.starts);
    const duration = initialEnd - initialStart;
    let finalStart = initialStart;
    let finalEnd = initialEnd;
    const onMove = (moveEvent: PointerEvent) => {
      const delta = snap((moveEvent.clientX - pointerStart) / zoom, timeline?.settings.snap_sec ?? 0.1);
      if (mode === 'move') {
        finalStart = Math.min(Math.max(0, initialStart + delta), Math.max(0, layout.duration - duration));
        finalEnd = finalStart + duration;
      } else if (mode === 'left') {
        finalStart = Math.min(initialEnd - 0.05, Math.max(0, initialStart + delta));
      } else {
        finalEnd = Math.max(initialStart + 0.05, Math.min(layout.duration, initialEnd + delta));
      }
      setTrackDragPreview({ track: trackName, itemId: item.id, start: finalStart, end: finalEnd });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      setTrackDragPreview(null);
      if (finalStart !== initialStart || finalEnd !== initialEnd) {
        commitTrackPosition(trackName, item.id, finalStart, finalEnd, mode);
      }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
  };

  const applySelectedText = () => {
    if (!timeline || !selectedItem || !selectedTrackItem) return;
    const clean = draftText.trim();
    if (!clean) {
      setMessage('文本不能为空', 'error');
      return;
    }
    const next = cloneTimeline(timeline);
    const item = next.tracks[selectedItem.track].find((entry) => entry.id === selectedItem.id);
    if (!item) return;
    if (selectedItem.track === 'source_audio') {
      item.purpose = clean;
    } else {
      item.text = clean;
    }
    if (selectedItem.track === 'narration') {
      item.subtitle_text = clean;
      item.audio_stale = clean !== String(item.generated_text ?? item.original_text ?? '');
      const subtitle = next.tracks.subtitles.find((entry) => entry.id === `subtitle-${item.id}`);
      if (subtitle) {
        item.audio_stale = Boolean(item.audio_stale);
        subtitle.text = clean;
      }
    }
    commit(next, `已更新 ${selectedTrackItem.id} 文本`);
  };

  const regenerateSelectedNarration = async () => {
    if (!timeline || !selectedItem || selectedItem.track !== 'narration' || !selectedTrackItem) return;
    const clean = draftText.trim();
    if (!clean) {
      setMessage('旁白文本不能为空', 'error');
      return;
    }
    setRegenerating(true);
    setMessage(`正在重新生成 ${selectedTrackItem.id}…`);
    try {
      const result = await api<{
        assetId: string;
        audioUrl: string;
        durationSec: number;
        cacheHit: boolean;
      }>(`/api/story-editor/projects/${timeline.projectId}/tts/minimax`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: clean,
          slotDurationSec: selectedTrackItem.local_end_sec - selectedTrackItem.local_start_sec,
        }),
      });
      const next = cloneTimeline(timeline);
      const item = next.tracks.narration.find((entry) => entry.id === selectedTrackItem.id)!;
      item.text = clean;
      item.subtitle_text = clean;
      item.generated_text = clean;
      item.asset_id = result.assetId;
      item.audio_url = result.audioUrl;
      item.audio_stale = false;
      const subtitle = next.tracks.subtitles.find((entry) => entry.id === `subtitle-${item.id}`);
      if (subtitle) subtitle.text = clean;
      commit(next, `${selectedTrackItem.id} 已${result.cacheHit ? '复用缓存' : '重新生成'} MiniMax 语音`);
      narrationRef.current.src = result.audioUrl;
      void narrationRef.current.play().catch(() => undefined);
    } catch (error) {
      setMessage((error as Error).message, 'error');
    } finally {
      setRegenerating(false);
    }
  };

  const rewriteSelectedText = async () => {
    if (!selectedTrackItem || !draftText.trim()) return;
    setRewriting(true);
    setMessage(`正在局部改写 ${selectedTrackItem.id}…`);
    try {
      const result = await api<{ text: string; provider: string }>('/api/story-editor/rewrite', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: draftText,
          instruction: rewriteInstruction,
          context: String(selectedTrackItem.purpose ?? ''),
        }),
      });
      setDraftText(result.text);
      setMessage(`${selectedTrackItem.id} 已由 DeepSeek 局部改写，请确认后应用`, 'success');
    } catch (error) {
      setMessage((error as Error).message, 'error');
    } finally {
      setRewriting(false);
    }
  };

  const updateClipSettings = (updates: Partial<Clip>, message: string) => {
    if (!timeline || !selectedClip) return;
    const next = cloneTimeline(timeline);
    const clip = next.clips.find((item) => item.id === selectedClip.id)!;
    Object.assign(clip, updates);
    commit(next, message);
  };

  const switchClipSource = (sourceId: string) => {
    if (!timeline || !selectedClip) return;
    const source = timeline.sources.find((item) => item.id === sourceId);
    if (!source) return;
    const duration = Math.min(10, source.duration_sec);
    updateClipSettings(
      {
        source_id: sourceId,
        source_start_sec: 0,
        source_end_sec: duration,
        duration_sec: duration,
        kind: 'visual',
        source_subtitle_ids: [],
        source_scene_ids: [],
        source_text: '',
        target_text: '',
        thumbnail_url: `/api/story-editor/projects/${timeline.projectId}/thumbnail?source=${sourceId}&time=${Math.min(source.duration_sec / 2, 5).toFixed(3)}`,
      },
      `已将 ${selectedClip.id} 切换到素材 ${source.filename}`,
    );
    setPreviewSourceId(sourceId);
  };

  const addLocalSource = async () => {
    if (!timeline || !sourcePath.trim()) return;
    setAddingSource(true);
    setMessage('正在读取本地视频素材…');
    try {
      const source = await api<Timeline['sources'][number]>(
        `/api/story-editor/projects/${timeline.projectId}/sources`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: sourcePath }),
        },
      );
      const next = cloneTimeline(timeline);
      next.sources = [...next.sources.filter((item) => item.id !== source.id), source];
      commit(next, `已加入素材 ${source.filename}`);
      setSourcePath('');
      setMessage(`素材 ${source.filename} 已加入，可在片段参数中切换`, 'success');
    } catch (error) {
      setMessage((error as Error).message, 'error');
    } finally {
      setAddingSource(false);
    }
  };

  const addVolumeKeyframe = () => {
    if (!timeline || !selectedClip) return;
    const localTime = Math.min(
      clipDuration(selectedClip),
      Math.max(0, playhead - layout.starts[selectedClip.id]),
    );
    const keyframe = {
      id: `volume-${Date.now()}`,
      time_sec: Number(localTime.toFixed(3)),
      volume: 1,
    };
    updateClipSettings(
      { volume_keyframes: [...(selectedClip.volume_keyframes ?? []), keyframe].sort((a, b) => a.time_sec - b.time_sec) },
      `已在 ${localTime.toFixed(2)} 秒添加音量关键帧`,
    );
  };

  const updateVolumeKeyframe = (id: string, volume: number) => {
    if (!selectedClip) return;
    updateClipSettings(
      {
        volume_keyframes: (selectedClip.volume_keyframes ?? []).map((item) => item.id === id ? { ...item, volume } : item),
      },
      '已更新音量关键帧',
    );
  };

  const deleteVolumeKeyframe = (id: string) => {
    if (!selectedClip) return;
    updateClipSettings(
      { volume_keyframes: (selectedClip.volume_keyframes ?? []).filter((item) => item.id !== id) },
      '已删除音量关键帧',
    );
  };

  const beginTrim = (event: ReactPointerEvent, clip: Clip, side: 'left' | 'right') => {
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    const startX = event.clientX;
    const initialStart = clip.source_start_sec;
    const initialEnd = clip.source_end_sec;
    const maxSource = timeline?.source.duration_sec ?? initialEnd;
    let finalStart = initialStart;
    let finalEnd = initialEnd;
    const onMove = (moveEvent: PointerEvent) => {
      const deltaOutput = (moveEvent.clientX - startX) / zoom;
      const deltaSource = deltaOutput * clip.playback_rate;
      if (side === 'left') {
        finalStart = Math.min(initialEnd - MIN_CLIP_DURATION, Math.max(0, snap(initialStart + deltaSource, timeline?.settings.snap_sec ?? 0.1)));
      } else {
        finalEnd = Math.max(initialStart + MIN_CLIP_DURATION, Math.min(maxSource, snap(initialEnd + deltaSource, timeline?.settings.snap_sec ?? 0.1)));
      }
      setDragPreview({ clipId: clip.id, start: finalStart, end: finalEnd });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      setDragPreview(null);
      if (finalStart !== initialStart || finalEnd !== initialEnd) applyTrim(clip.id, finalStart, finalEnd);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
  };

  const splitSelected = () => {
    if (!timeline || !selectedClip) return;
    const clipStart = layout.starts[selectedClip.id];
    const localSplit = playhead - clipStart;
    const duration = clipDuration(selectedClip);
    if (localSplit < MIN_CLIP_DURATION || duration - localSplit < MIN_CLIP_DURATION) {
      setMessage('播放头需要位于所选片段内部，并与边界至少相距 0.25 秒', 'error');
      return;
    }
    const crossingNarration = timeline.tracks.narration.find(
      (item) => item.segment_id === selectedClip.id && item.local_start_sec < localSplit && item.local_end_sec > localSplit,
    );
    if (crossingNarration) {
      setMessage(`切点穿过旁白 ${crossingNarration.id}，请移到旁白块间隙后再拆分`, 'error');
      return;
    }
    const next = cloneTimeline(timeline);
    const index = next.clips.findIndex((clip) => clip.id === selectedClip.id);
    const used = new Set(next.clips.map((clip) => clip.id));
    const unique = (base: string) => {
      let value = base;
      let suffix = 2;
      while (used.has(value)) value = `${base}-${suffix++}`;
      used.add(value);
      return value;
    };
    const leftId = unique(`${selectedClip.id}-a`);
    const rightId = unique(`${selectedClip.id}-b`);
    const sourceSplit = selectedClip.source_start_sec + localSplit * selectedClip.playback_rate;
    const left: Clip = { ...selectedClip, id: leftId, source_end_sec: sourceSplit, duration_sec: localSplit };
    const right: Clip = { ...selectedClip, id: rightId, source_start_sec: sourceSplit, duration_sec: duration - localSplit };
    next.clips.splice(index, 1, left, right);
    (['original_audio', 'narration', 'source_audio', 'subtitles'] as const).forEach((trackName) => {
      next.tracks[trackName] = next.tracks[trackName].flatMap((item) => {
        if (item.segment_id !== selectedClip.id) return [item];
        if (item.local_end_sec <= localSplit) return [{ ...item, segment_id: leftId }];
        if (item.local_start_sec >= localSplit) {
          return [{
            ...item,
            segment_id: rightId,
            local_start_sec: item.local_start_sec - localSplit,
            local_end_sec: item.local_end_sec - localSplit,
          }];
        }
        if (trackName === 'original_audio') {
          return [
            { ...item, id: `${item.id}-a`, segment_id: leftId, local_end_sec: localSplit },
            { ...item, id: `${item.id}-b`, segment_id: rightId, local_start_sec: 0, local_end_sec: item.local_end_sec - localSplit },
          ];
        }
        const midpoint = (item.local_start_sec + item.local_end_sec) / 2;
        return midpoint < localSplit
          ? [{ ...item, segment_id: leftId, local_end_sec: localSplit }]
          : [{ ...item, segment_id: rightId, local_start_sec: 0, local_end_sec: item.local_end_sec - localSplit }];
      });
    });
    commit(next, `已在 ${formatTime(playhead)} 拆分片段`);
    setSelectedClipId(rightId);
  };

  const deleteSelected = () => {
    if (!timeline || !selectedClip || timeline.clips.length <= 1) return;
    const next = cloneTimeline(timeline);
    next.clips = next.clips.filter((clip) => clip.id !== selectedClip.id);
    (Object.keys(next.tracks) as Array<keyof Timeline['tracks']>).forEach((trackName) => {
      next.tracks[trackName] = next.tracks[trackName].filter((item) => item.segment_id !== selectedClip.id);
    });
    commit(next, `已删除 ${selectedClip.id}`);
    setSelectedClipId(next.clips[Math.min(timeline.clips.indexOf(selectedClip), next.clips.length - 1)]?.id ?? null);
  };

  const moveSelected = (direction: -1 | 1) => {
    if (!timeline || !selectedClip) return;
    const index = timeline.clips.findIndex((clip) => clip.id === selectedClip.id);
    const target = index + direction;
    if (target < 0 || target >= timeline.clips.length) return;
    const next = cloneTimeline(timeline);
    [next.clips[index], next.clips[target]] = [next.clips[target], next.clips[index]];
    commit(next, `已重排 ${selectedClip.id}`);
  };

  const dropClip = (targetId: string, sourceId: string) => {
    if (!timeline || sourceId === targetId) return;
    const next = cloneTimeline(timeline);
    const from = next.clips.findIndex((clip) => clip.id === sourceId);
    const to = next.clips.findIndex((clip) => clip.id === targetId);
    if (from < 0 || to < 0) return;
    const [moved] = next.clips.splice(from, 1);
    next.clips.splice(to, 0, moved);
    commit(next, `已拖动重排 ${sourceId}`);
  };

  const updateSelectedNumber = (field: 'source_start_sec' | 'source_end_sec', value: number) => {
    if (!selectedClip || !timeline || Number.isNaN(value)) return;
    const start = field === 'source_start_sec' ? value : selectedClip.source_start_sec;
    const end = field === 'source_end_sec' ? value : selectedClip.source_end_sec;
    if (start < 0 || end > timeline.source.duration_sec || end - start < MIN_CLIP_DURATION) {
      setMessage('切点超出源视频范围或片段不足 0.25 秒', 'error');
      return;
    }
    applyTrim(selectedClip.id, start, end);
  };

  const saveRevision = async (): Promise<string | null> => {
    if (!timeline || saving) return null;
    setSaving(true);
    setMessage('正在保存修订…');
    try {
      const saved = await api<{ revisionId: string; savedAt: string }>(
        `/api/story-editor/projects/${timeline.projectId}/revisions`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ timeline, note: 'visual timeline revision' }),
        },
      );
      setTimeline({ ...timeline, revisionId: saved.revisionId, revisions: [saved.revisionId, ...timeline.revisions] });
      setMessage(`修订 ${saved.revisionId} 已保存`, 'success');
      return saved.revisionId;
    } catch (error) {
      setMessage((error as Error).message, 'error');
      return null;
    } finally {
      setSaving(false);
    }
  };

  const startRender = async () => {
    if (!timeline) return;
    const revisionId = await saveRevision();
    if (!revisionId) return;
    try {
      const job = await api<RenderJob>(`/api/story-editor/projects/${timeline.projectId}/render`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revisionId }),
      });
      setRenderJob(job);
      setMessage(job.message);
    } catch (error) {
      setMessage((error as Error).message, 'error');
    }
  };

  useEffect(() => {
    if (!renderJob || !['queued', 'running'].includes(renderJob.status)) return;
    const timer = window.setInterval(() => {
      api<RenderJob>(`/api/story-editor/jobs/${renderJob.id}`)
        .then((job) => {
          setRenderJob(job);
          setMessage(job.message, job.status === 'failed' ? 'error' : job.status === 'finished' ? 'success' : 'normal');
        })
        .catch((error: Error) => setMessage(error.message, 'error'));
    }, 1200);
    return () => window.clearInterval(timer);
  }, [renderJob?.id, renderJob?.status]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.matches('input,select,textarea')) return;
      if (event.code === 'Space') {
        event.preventDefault();
        togglePlayback();
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault();
        event.shiftKey ? redo() : undo();
      } else if (event.key === 'Delete') {
        deleteSelected();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  });

  if (!timeline) {
    return <div className="loading-screen">{status}</div>;
  }

  const activeSubtitle = timeline.tracks.subtitles.find(
    (item) => playhead >= itemAbsoluteStart(item, layout.starts) && playhead < itemAbsoluteEnd(item, layout.starts),
  );
  const previewSource = timeline.sources.find((item) => item.id === previewSourceId)
    ?? timeline.sources[0];
  const contentWidth = Math.max(920, layout.duration * zoom);
  const previewClip = dragPreview && selectedClip?.id === dragPreview.clipId
    ? { ...selectedClip, source_start_sec: dragPreview.start, source_end_sec: dragPreview.end }
    : selectedClip;
  const playheadLeft = LABEL_WIDTH + playhead * zoom;

  const trackItems = (
    items: TrackItem[],
    className: string,
    label: (item: TrackItem) => string,
    trackName: EditableTrackName,
  ) => items.map((item) => {
    const preview = trackDragPreview?.track === trackName && trackDragPreview.itemId === item.id
      ? trackDragPreview
      : null;
    const start = preview?.start ?? itemAbsoluteStart(item, layout.starts);
    const end = preview?.end ?? itemAbsoluteEnd(item, layout.starts);
    const selected = selectedItem?.track === trackName && selectedItem.id === item.id;
    const movable = trackName === 'source_audio' || trackName === 'subtitles';
    return (
      <div
        className={`track-item ${className} ${selected ? 'selected' : ''} ${item.audio_stale ? 'stale' : ''}`}
        key={item.id}
        style={{ left: start * zoom, width: Math.max(5, (end - start) * zoom) }}
        title={`${item.id}\n${label(item)}\n${formatTime(start)} - ${formatTime(end)}`}
        onClick={(event) => {
          event.stopPropagation();
          setSelectedClipId(item.segment_id);
          setSelectedItem({ track: trackName, id: item.id });
          seekComposition(start, false);
        }}
        onPointerDown={movable ? (event) => beginTrackDrag(event, trackName, item, 'move') : undefined}
      >
        {movable && <span className="track-trim left" onPointerDown={(event) => beginTrackDrag(event, trackName, item, 'left')} />}
        <span className="track-item-text">{label(item)}</span>
        {movable && <span className="track-trim right" onPointerDown={(event) => beginTrackDrag(event, trackName, item, 'right')} />}
      </div>
    );
  });

  return (
    <main className="editor-app">
      <header className="toolbar">
        <div className="brand"><span className="brand-mark"><Film size={17} /></span>故事时间线</div>
        <FolderOpen size={16} aria-hidden="true" />
        <select className="project-select" value={projectId} onChange={(event) => setProjectId(event.target.value)} aria-label="选择解说项目">
          {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
        <div className="toolbar-divider" />
        <button className="icon-button" onClick={undo} disabled={!undoStack.current.length} title="撤销"><Undo2 size={16} /></button>
        <button className="icon-button" onClick={redo} disabled={!redoStack.current.length} title="重做"><Redo2 size={16} /></button>
        <button className="icon-button" onClick={splitSelected} disabled={!selectedClip} title="在播放头拆分"><Split size={16} /></button>
        <button className="icon-button" onClick={deleteSelected} disabled={!selectedClip || timeline.clips.length <= 1} title="删除片段"><Trash2 size={16} /></button>
        <button className="icon-button" onClick={() => moveSelected(-1)} disabled={!selectedClip} title="向前移动"><ChevronLeft size={17} /></button>
        <button className="icon-button" onClick={() => moveSelected(1)} disabled={!selectedClip} title="向后移动"><ChevronRight size={17} /></button>
        <div className="toolbar-spacer" />
        <button className="command-button primary" onClick={() => void saveRevision()} disabled={saving}><Save size={15} />保存修订</button>
        <button className="command-button render" onClick={() => void startRender()} disabled={saving || renderJob?.status === 'running'}><Clapperboard size={15} />完整渲染</button>
      </header>

      <section className="preview-area">
        <div className="preview-stage">
          <video
            ref={videoRef}
            src={previewSource?.media_url ?? timeline.source.media_url}
            preload="metadata"
            onLoadedMetadata={() => {
              const pending = pendingSeek.current;
              if (pending && videoRef.current) {
                pendingSeek.current = null;
                videoRef.current.currentTime = pending.sourceTime;
                const clip = timeline.clips.find((item) => item.id === pending.clipId);
                if (clip) videoRef.current.playbackRate = clip.playback_rate;
                if (pending.shouldPlay) void videoRef.current.play();
              } else {
                seekComposition(playhead, false);
              }
            }}
            onClick={togglePlayback}
            onPause={() => {
              narrationRef.current.pause();
            }}
          />
          {activeSubtitle?.text && <div className="subtitle-overlay">{String(activeSubtitle.text)}</div>}
        </div>
        <aside className="inspector">
          <div className="inspector-title">{selectedTrackItem ? '轨道块参数' : '片段参数'}</div>
          <div className="inspector-body">
            {selectedTrackItem && selectedItem ? (
              <>
                <div className="selection-summary">
                  <strong>{selectedTrackItem.id}</strong><br />
                  {selectedItem.track === 'narration' ? 'MiniMax 旁白' : selectedItem.track === 'source_audio' ? '影视原声窗口' : '最终字幕'}
                  {Boolean(selectedTrackItem.audio_stale) && <><br /><span className="stale-text">文本已修改，语音需要重新生成</span></>}
                </div>
                <div className="field-row">
                  <div className="field"><label>片段内开始</label><input value={`${selectedTrackItem.local_start_sec.toFixed(3)} 秒`} readOnly /></div>
                  <div className="field"><label>片段内结束</label><input value={`${selectedTrackItem.local_end_sec.toFixed(3)} 秒`} readOnly /></div>
                </div>
                <div className="field">
                  <label>{selectedItem.track === 'source_audio' ? '窗口用途' : '文本'}</label>
                  <textarea value={draftText} onChange={(event) => setDraftText(event.target.value)} />
                </div>
                {selectedItem.track === 'narration' && (
                  <div className="field">
                    <label>局部 AI 改写要求</label>
                    <input value={rewriteInstruction} onChange={(event) => setRewriteInstruction(event.target.value)} />
                  </div>
                )}
                <div className="inspector-actions">
                  <button className="command-button" onClick={applySelectedText}><Check size={14} />应用文本</button>
                  {selectedItem.track === 'narration' && (
                    <button className="command-button" onClick={() => void rewriteSelectedText()} disabled={rewriting}>
                      <KeyRound size={14} />{rewriting ? '改写中…' : 'AI 局部改写'}
                    </button>
                  )}
                  {selectedItem.track === 'narration' && (
                    <button className="command-button primary" onClick={() => void regenerateSelectedNarration()} disabled={regenerating}>
                      <RefreshCw size={14} />{regenerating ? '生成中…' : '重生本段'}
                    </button>
                  )}
                </div>
                {selectedItem.track === 'narration' && selectedTrackItem.audio_url && (
                  <button
                    className="command-button"
                    onClick={() => {
                      narrationRef.current.src = String(selectedTrackItem.audio_url);
                      narrationRef.current.currentTime = 0;
                      void narrationRef.current.play().catch(() => undefined);
                    }}
                  >
                    <Volume2 size={14} />试听当前语音
                  </button>
                )}
              </>
            ) : previewClip ? (
              <>
                <div className="selection-summary">
                  <strong>{previewClip.id}</strong><br />
                  {previewClip.story_reason || previewClip.label}
                </div>
                <div className="field-row">
                  <div className="field">
                    <label>源入点（秒）</label>
                    <input
                      key={`${previewClip.id}-start-${previewClip.source_start_sec}`}
                      type="number"
                      step={timeline.settings.snap_sec}
                      defaultValue={previewClip.source_start_sec.toFixed(3)}
                      onBlur={(event) => updateSelectedNumber('source_start_sec', Number(event.target.value))}
                      onKeyDown={(event) => { if (event.key === 'Enter') event.currentTarget.blur(); }}
                    />
                  </div>
                  <div className="field">
                    <label>源出点（秒）</label>
                    <input
                      key={`${previewClip.id}-end-${previewClip.source_end_sec}`}
                      type="number"
                      step={timeline.settings.snap_sec}
                      defaultValue={previewClip.source_end_sec.toFixed(3)}
                      onBlur={(event) => updateSelectedNumber('source_end_sec', Number(event.target.value))}
                      onKeyDown={(event) => { if (event.key === 'Enter') event.currentTarget.blur(); }}
                    />
                  </div>
                </div>
                <div className="field">
                  <label>视频素材源</label>
                  <select value={previewClip.source_id || 'source-main'} onChange={(event) => switchClipSource(event.target.value)}>
                    {timeline.sources.map((source) => <option key={source.id} value={source.id}>{source.filename}</option>)}
                  </select>
                </div>
                <div className="source-add-row">
                  <input
                    value={sourcePath}
                    onChange={(event) => setSourcePath(event.target.value)}
                    placeholder="输入本地视频绝对路径"
                  />
                  <button className="icon-button" onClick={() => void addLocalSource()} disabled={addingSource || !sourcePath.trim()} title="加入本地素材"><Upload size={15} /></button>
                </div>
                <div className="field-row">
                  <div className="field"><label>片段时长</label><input value={`${clipDuration(previewClip).toFixed(3)} 秒`} readOnly /></div>
                  <div className="field"><label>播放速度</label><input value={`${previewClip.playback_rate.toFixed(2)}x`} readOnly /></div>
                </div>
                <div className="field"><label>叙事作用</label><input value={previewClip.story_role} readOnly /></div>
                <div className="field-row">
                  <div className="field">
                    <label>入场转场</label>
                    <select value={previewClip.transition} onChange={(event) => updateClipSettings({ transition: event.target.value }, '已更新片段转场')}>
                      <option value="cut">直接切换</option>
                      <option value="crossfade">交叉淡化</option>
                    </select>
                  </div>
                  <div className="field">
                    <label>转场时长</label>
                    <input
                      type="number"
                      min="0.1"
                      max="3"
                      step="0.1"
                      defaultValue={(previewClip.transition_duration_sec ?? 0.5).toFixed(1)}
                      onBlur={(event) => updateClipSettings({ transition_duration_sec: Number(event.target.value) }, '已更新转场时长')}
                    />
                  </div>
                </div>
                <div className="field-row">
                  <div className="field">
                    <label>淡入（秒）</label>
                    <input type="number" min="0" max="5" step="0.1" defaultValue={(previewClip.fade_in_sec ?? 0).toFixed(1)} onBlur={(event) => updateClipSettings({ fade_in_sec: Number(event.target.value) }, '已更新淡入')} />
                  </div>
                  <div className="field">
                    <label>淡出（秒）</label>
                    <input type="number" min="0" max="5" step="0.1" defaultValue={(previewClip.fade_out_sec ?? 0).toFixed(1)} onBlur={(event) => updateClipSettings({ fade_out_sec: Number(event.target.value) }, '已更新淡出')} />
                  </div>
                </div>
                <div className="keyframe-section">
                  <div className="keyframe-heading">
                    <span>音量关键帧</span>
                    <button className="command-button" onClick={addVolumeKeyframe}>在播放头添加</button>
                  </div>
                  {(previewClip.volume_keyframes ?? []).map((keyframe) => (
                    <div className="keyframe-row" key={keyframe.id}>
                      <span>{keyframe.time_sec.toFixed(2)}s</span>
                      <input type="range" min="0" max="2" step="0.05" value={keyframe.volume} onChange={(event) => updateVolumeKeyframe(keyframe.id, Number(event.target.value))} />
                      <span>{Math.round(keyframe.volume * 100)}%</span>
                      <button className="icon-button" onClick={() => deleteVolumeKeyframe(keyframe.id)} title="删除关键帧"><Trash2 size={13} /></button>
                    </div>
                  ))}
                  {!(previewClip.volume_keyframes ?? []).length && <span className="empty-inline">暂无关键帧，使用片段默认音量</span>}
                </div>
                <div className="field">
                  <label>渲染字幕</label>
                  <select
                    value={timeline.settings.burn_subtitles}
                    onChange={(event) => {
                      const next = cloneTimeline(timeline);
                      next.settings.burn_subtitles = event.target.value as Timeline['settings']['burn_subtitles'];
                      commit(next, '已更新字幕烧录方式');
                    }}
                  >
                    <option value="none">不烧录字幕</option>
                    <option value="source">原文字幕</option>
                    <option value="translated">中文字幕</option>
                    <option value="bilingual">双语字幕</option>
                  </select>
                </div>
              </>
            ) : <div className="empty-preview">在时间线上选择一个视频片段</div>}
          </div>
        </aside>
      </section>

      <section className="timeline-panel">
        <div className="timeline-tools">
          <button className="icon-button" onClick={togglePlayback} title={playing ? '暂停' : '播放'}>{playing ? <Pause size={16} /> : <Play size={16} />}</button>
          <span className="timecode">{formatTime(playhead)} / {formatTime(layout.duration)}</span>
          <button className="command-button" onClick={splitSelected}><Scissors size={14} />拆分</button>
          <div className="zoom-control">缩放<input type="range" min="3" max="22" step="1" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} />{zoom}px/s</div>
        </div>
        <div className="timeline-scroll">
          <div className="timeline-content" style={{ width: LABEL_WIDTH + contentWidth }}>
            <div className="ruler-row">
              <div className="track-label">时间</div>
              <div
                className="ruler-lane"
                style={{ width: contentWidth, backgroundSize: `${zoom * 5}px 100%` }}
                onClick={(event) => {
                  const rect = event.currentTarget.getBoundingClientRect();
                  seekComposition((event.clientX - rect.left) / zoom, false);
                }}
              >
                {Array.from({ length: Math.ceil(layout.duration / 30) + 1 }, (_, index) => index * 30).map((second) => (
                  <div className="ruler-mark" key={second} style={{ left: second * zoom }}><span>{formatTime(second, false)}</span></div>
                ))}
              </div>
            </div>

            <div className="track-row video-track">
              <div className="track-label"><Film size={14} />视频<small>{timeline.clips.length}</small></div>
              <div className="track-lane" style={{ width: contentWidth, backgroundSize: `${zoom * 5}px 100%` }}>
                {timeline.clips.map((clip) => {
                  const display = dragPreview?.clipId === clip.id ? { ...clip, source_start_sec: dragPreview.start, source_end_sec: dragPreview.end } : clip;
                  return (
                    <div
                      className={`clip ${selectedClipId === clip.id ? 'selected' : ''}`}
                      key={clip.id}
                      draggable
                      onDragStart={(event) => event.dataTransfer.setData('text/plain', clip.id)}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event) => dropClip(clip.id, event.dataTransfer.getData('text/plain'))}
                      onClick={(event) => {
                        event.stopPropagation();
                        setSelectedClipId(clip.id);
                        setSelectedItem(null);
                        seekComposition(layout.starts[clip.id], false);
                      }}
                      style={{
                        left: layout.starts[clip.id] * zoom,
                        width: Math.max(9, clipDuration(display) * zoom),
                        backgroundImage: `url(${clip.thumbnail_url})`,
                      }}
                      title={`${clip.id}\n${clip.story_reason}\n源 ${formatTime(display.source_start_sec)} - ${formatTime(display.source_end_sec)}`}
                    >
                      <span className="trim-handle left" onPointerDown={(event) => beginTrim(event, clip, 'left')} />
                      <span className="clip-name">{clip.id} · {clip.story_reason}</span>
                      <span className="trim-handle right" onPointerDown={(event) => beginTrim(event, clip, 'right')} />
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="track-row">
              <div className="track-label"><Volume2 size={14} />原声音轨<small>{timeline.clips.length}</small></div>
              <div className="track-lane" style={{ width: contentWidth, backgroundSize: `${zoom * 5}px 100%` }}>
                {timeline.clips.map((clip) => (
                  <div className="track-item original-item" key={`original-${clip.id}`} style={{ left: layout.starts[clip.id] * zoom, width: Math.max(5, clipDuration(clip) * zoom) }} title={`${clip.id} 原声`}>
                    {(clip.volume_keyframes ?? []).map((keyframe) => (
                      <span
                        className="keyframe-dot"
                        key={keyframe.id}
                        style={{ left: keyframe.time_sec * zoom, bottom: `${Math.min(30, 3 + keyframe.volume * 13)}px` }}
                        title={`${keyframe.time_sec.toFixed(2)}s · ${Math.round(keyframe.volume * 100)}%`}
                      />
                    ))}
                  </div>
                ))}
              </div>
            </div>

            <div className="track-row">
              <div className="track-label">旁白音轨<small>{timeline.tracks.narration.length}</small></div>
              <div className="track-lane" style={{ width: contentWidth, backgroundSize: `${zoom * 5}px 100%` }}>
                {trackItems(timeline.tracks.narration, 'narration-item', (item) => item.text ?? item.id, 'narration')}
              </div>
            </div>

            <div className="track-row">
              <div className="track-label">原声窗口<small>{timeline.tracks.source_audio.length}</small></div>
              <div className="track-lane" style={{ width: contentWidth, backgroundSize: `${zoom * 5}px 100%` }}>
                {trackItems(timeline.tracks.source_audio, 'source-item', (item) => item.purpose ?? item.id, 'source_audio')}
              </div>
            </div>

            <div className="track-row">
              <div className="track-label">字幕轨<small>{timeline.tracks.subtitles.length}</small></div>
              <div className="track-lane" style={{ width: contentWidth, backgroundSize: `${zoom * 5}px 100%` }}>
                {trackItems(timeline.tracks.subtitles, 'subtitle-item', (item) => item.text ?? item.id, 'subtitles')}
              </div>
            </div>
            <div className="playhead" style={{ left: playheadLeft }} />
          </div>
        </div>
      </section>

      <footer className="statusbar">
        <span className={statusKind === 'normal' ? '' : statusKind}>{status}</span>
        <span>{timeline.source.width}×{timeline.source.height} · {timeline.source.fps.toFixed(3)} fps</span>
        <span>{timeline.assets.narration_ready ? '旁白缓存可用' : '旁白缓存缺失'}</span>
        {timeline.revisionId && <span>当前修订：{timeline.revisionId}</span>}
        {renderJob && <><div className="render-progress"><span style={{ width: `${renderJob.progress}%` }} /></div><span>{renderJob.progress}%</span></>}
        {renderJob?.status === 'finished' && renderJob.outputUrl && <a href={renderJob.outputUrl} target="_blank" rel="noreferrer">打开成片</a>}
      </footer>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
