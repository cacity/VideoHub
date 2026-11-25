import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BookOpen, FolderPlus, Folder, ChevronRight, ChevronDown, ChevronUp, Play, Search, Subtitles, X, Repeat, Crosshair, Maximize, Minimize, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Scissors, Trash2 } from 'lucide-react';
import './learning.css';
import { api, setToken, time, currentCue, groupLibrary, defaultSubtitleStyle, SubtitleStyle, Mode, Progress, Cue, Video, Providers } from './learning-api';
import { LearningPanel } from './learning-panel';
import { LearningClip } from './learning-clip';
import { ResizeHandle, useLearningSizes } from './learning-resize';
import { bindPlaybackShortcuts, handlePlaybackShortcut, inspectPlaybackShortcut, stepPlaybackRate, playbackRates, toggleSubtitleMode, ShortcutRepeatState } from './learning-shortcuts';

function savedLayout(): { library: boolean; assistant: boolean; tools: boolean; transcriptSide: boolean } {
  try {
    const value = JSON.parse(localStorage.getItem('videohub.learning.layout') || '{}');
    return { library: value?.library === true, assistant: value?.assistant === true, tools: value?.tools === true, transcriptSide: value?.transcriptSide === true };
  } catch { return { library: false, assistant: false, tools: false, transcriptSide: false }; }
}

function reportRuntime(detail: Record<string, string>) {
  document.dispatchEvent(new window.CustomEvent('videohub:learning-runtime', { detail }));
}

function savedLibraryGroups(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem('videohub.learning.collapsed-groups') || '[]');
    return Array.isArray(value) ? value.filter(key => typeof key === 'string') : [];
  } catch { return []; }
}

function App() {
  const [collapsed, setCollapsed] = useState(savedLayout);
  const [fullscreen, setFullscreen] = useState(false);
  const [library, setLibrary] = useState<Video[]>([]);
  const [managing, setManaging] = useState(false);
  const [video, setVideo] = useState<Video | null>(null);
  const [clipVideoId, setClipVideoId] = useState('');
  const [error, setError] = useState('');
  const [importing, setImporting] = useState(false);
  const [importMode, setImportMode] = useState('project');
  const [needsSelection, setNeedsSelection] = useState(false);
  const [importPaths, setImportPaths] = useState<string[]>([]);
  const [importNotice, setImportNotice] = useState('');
  const [path, setPath] = useState('');
  const [folder, setFolder] = useState('');
  const [importChoices, setImportChoices] = useState<Array<{ path: string; title: string; source_url?: string }>>([]);
  const [subtitleChoices, setSubtitleChoices] = useState<Array<{ path: string; name: string; role: string; language: string; format?: string; bilingual?: boolean; modified?: number }>>([]);
  const [translationRequest, setTranslationRequest] = useState({ videoId: '', count: 0 });
  const [sourceLanguage, setSourceLanguage] = useState('en');
  const [libraryQuery, setLibraryQuery] = useState('');
  const [collapsedGroups, setCollapsedGroups] = useState(savedLibraryGroups);
  const libraryGroups = useMemo(() => groupLibrary(library, libraryQuery), [library, libraryQuery]);
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState<Providers>({});
  const [mindmapAvailable, setMindmapAvailable] = useState(false);
  const [position, setPosition] = useState(0);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const [follow, setFollow] = useState(true);
  const [selected, setSelected] = useState<Cue | null>(null);
  const [loop, setLoop] = useState<Cue | null>(null);
  const [shortcutNotice, setShortcutNotice] = useState('');
  const [shortcutDiagnostic, setShortcutDiagnostic] = useState('');
  const diagnoseKeys = useRef(false);
  const shortcutRepeat = useRef<ShortcutRepeatState>({});
  const pendingRateSave = useRef<{ timer: number; id: string; progress: Progress } | null>(null);
  const visibleOverlay = useRef<Record<string, Mode>>({});
  const activeRow = useRef<HTMLDivElement>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const player = useRef<HTMLVideoElement>(null);
  const playerWrap = useRef<HTMLDivElement>(null);
  const subtitleOverlay = useRef<HTMLDivElement>(null);
  const lesson = useRef<HTMLElement>(null);
  const [videoRatio, setVideoRatio] = useState(16 / 9);
  const sizes = useLearningSizes(lesson, collapsed.assistant, videoRatio, collapsed.library, collapsed.transcriptSide);
  const currentVideo = useRef<Video | null>(null);
  const lastSaved = useRef(0);
  currentVideo.current = video;
  useEffect(() => {
    try { localStorage.setItem('videohub.learning.layout', JSON.stringify(collapsed)); } catch { /* Optional preference storage. */ }
  }, [collapsed]);
  useEffect(() => {
    try { localStorage.setItem('videohub.learning.collapsed-groups', JSON.stringify(collapsedGroups)); } catch { /* Optional preference storage. */ }
  }, [collapsedGroups]);
  useEffect(() => {
    const overlay = subtitleOverlay.current;
    if (!overlay) return;
    const measure = () => overlay.style.setProperty('--subtitle-block-height', overlay.getBoundingClientRect().height + 'px');
    const observer = new ResizeObserver(measure);
    observer.observe(overlay); measure();
    return () => observer.disconnect();
  }, [video?.id]);
  useEffect(() => {
    const sync = () => setFullscreen(document.fullscreenElement === playerWrap.current && !!playerWrap.current);
    document.addEventListener('fullscreenchange', sync);
    return () => document.removeEventListener('fullscreenchange', sync);
  }, []);
  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement === playerWrap.current) await document.exitFullscreen();
      else if (playerWrap.current?.requestFullscreen) await playerWrap.current.requestFullscreen();
      else throw new Error('当前浏览器不支持播放器全屏，请使用浏览器窗口最大化观看');
    } catch (e) { const message = '无法切换全屏：' + (e as Error).message; setError(message); setShortcutNotice(message); }
  };
  const execute = async (work: () => Promise<void>) => {
    setError(''); setBusy(true);
    try { await work(); } catch (e) { setError(String((e as Error).message)); } finally { setBusy(false); }
  };
  const refresh = async () => {
    const { videos } = await api<{ videos: Video[] }>('/videos');
    setLibrary(videos);
    return videos;
  };
  const open = async (id: string) => {
    const item = await api<Video>('/videos/' + id);
    const params = new URLSearchParams(location.search);
    const linked = params.get('video') === id && params.has('t') ? Number(params.get('t')) : NaN;
    if (Number.isFinite(linked)) item.progress.time = Math.max(0, Math.min(item.duration, linked));
    history.replaceState(null, '', '/learn?video=' + id);
    setVideo(item); setPosition(item.progress.time); setSelected(null); setLoop(null); setFollow(true); setQuery('');
  };
  useEffect(() => { void execute(async () => {
    const session = await api<{ token: string; providers: Providers; features?: { mindmap?: boolean } }>('/session');
    setToken(session.token); setProviders(session.providers);
    setMindmapAvailable(session.features?.mindmap === true);
    const videos = await refresh();
    const params = new URLSearchParams(location.search);
    const directory = params.get('directory');
    const linkedId = params.get('video');
    const lastId = localStorage.getItem('videohub.learning.last');
    const id = linkedId || videos.find(item => item.id === lastId)?.id;
    if (directory) { setFolder(directory); setImporting(true); }
    else if (id) {
      await open(id);
      if (params.get('trim') === '1') setClipVideoId(id);
    }
  }); }, []);
  useEffect(() => { if (video) localStorage.setItem('videohub.learning.last', video.id); }, [video?.id]);
  useEffect(() => { setSourceLanguage(video?.tracks.source?.language || 'en'); }, [video?.id, video?.tracks.source?.language]);
  useEffect(() => { setVideoRatio(video?.width && video.height ? video.width / video.height : 16 / 9); }, [video?.id, video?.width, video?.height]);
  useEffect(() => { setSelected(null); setLoop(null); setQuery(''); setPage(0); }, [video?.subtitle_version]);
  useEffect(() => {
    let disposed = false;
    if (importing && !needsSelection) void api<{ videos: typeof importChoices }>('/imports/recent')
      .then(v => { if (!disposed) setImportChoices(v.videos); }).catch(e => { if (!disposed) setError(e.message); });
    return () => { disposed = true; };
  }, [importing, needsSelection]);
  useEffect(() => {
    let disposed = false;
    setSubtitleChoices([]);
    if (video) void api<{ tracks: typeof subtitleChoices }>('/videos/' + video.id + '/subtitle-candidates')
      .then(v => { if (!disposed) setSubtitleChoices(v.tracks); }).catch(e => { if (!disposed) setError(e.message); });
    return () => { disposed = true; };
  }, [video?.id, video?.subtitle_version]);
  const save = async () => {
    if (pendingRateSave.current) {
      window.clearTimeout(pendingRateSave.current.timer);
      pendingRateSave.current = null;
    }
    const item = currentVideo.current; const element = player.current;
    if (item && element) await api('/videos/' + item.id + '/progress', 'PUT',
      { ...item.progress, time: element.currentTime, rate: element.playbackRate });
  };
  const removeFromLibrary = (item: Video) => {
    if (busy || !window.confirm(`将「${item.title}」移出资料库？原视频、字幕和学习记录会保留，重新导入即可恢复。`)) return;
    void execute(async () => {
      if (currentVideo.current?.id === item.id) await save();
      await api('/videos/' + item.id, 'DELETE');
      if (currentVideo.current?.id === item.id) {
        currentVideo.current = null;
        setVideo(null); setPosition(0); setSelected(null); setLoop(null); setClipVideoId('');
        localStorage.removeItem('videohub.learning.last');
        history.replaceState(null, '', '/learn');
      }
      setLibrary(items => items.filter(entry => entry.id !== item.id));
      setImportNotice(`已将「${item.title}」移出资料库。`);
    });
  };
  useEffect(() => {
    const flush = () => { void save().catch(() => {}); };
    const visibility = () => { if (document.visibilityState === 'hidden') flush(); };
    window.addEventListener('pagehide', flush); document.addEventListener('visibilitychange', visibility);
    return () => { window.removeEventListener('pagehide', flush); document.removeEventListener('visibilitychange', visibility); };
  }, []);
  useEffect(() => () => {
    const pending = pendingRateSave.current;
    if (!pending) return;
    window.clearTimeout(pending.timer); pendingRateSave.current = null;
    void api('/videos/' + pending.id + '/progress', 'PUT', pending.progress).catch(() => {});
  }, []);
  const seek = useCallback((seconds: number) => { if (player.current) player.current.currentTime = seconds; setPosition(seconds); setFollow(true); }, []);
  const current = video?.cues.filter(c => c.start <= position && c.end > position) || [];
  const sourceCaption = currentCue(video?.playback_cues?.source || [], position);
  const targetCaption = currentCue(video?.playback_cues?.target || [], position);
  const currentId = sourceCaption?.id || current[current.length - 1]?.id;
  const subtitleStyle = { ...defaultSubtitleStyle, ...video?.progress.style };
  const stylePreference = (patch: Partial<SubtitleStyle>) => preference({ style: { ...subtitleStyle, ...patch } });
  const subtitleFonts = { sans: 'Arial, "Microsoft YaHei", sans-serif', serif: 'Georgia, SimSun, serif', mono: 'Consolas, "Microsoft YaHei", monospace' };
  const isEnglishCaption = (role: 'source' | 'target', text: string) => {
    const language = video?.tracks[role]?.language?.toLowerCase() || 'auto';
    return /^en(?:[-_]|$)/.test(language) || (['auto', 'und'].includes(language) && /[a-z]/i.test(text) && !/[\u3400-\u9fff]/.test(text));
  };
  const labels: Record<string, string> = { en: '英文', 'zh-CN': '中文', 'zh': '中文', ja: '日文', ko: '韩文', auto: '原文' };
  const sourceLabel = labels[video?.tracks.source?.language || 'auto'] || '原文';
  const targetLabel = labels[video?.tracks.target?.language || 'zh-CN'] || '译文';
  const filtered = useMemo(() => video?.cues.filter(c => (c.text + c.translation).toLowerCase().includes(query.toLowerCase())) || [], [video?.cues, query]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / 120));
  useEffect(() => { setPage(0); }, [video?.id, query]);
  useEffect(() => { if (follow && !query && currentId) { const index = filtered.findIndex(c => c.id === currentId); if (index >= 0) setPage(Math.floor(index / 120)); } }, [currentId, follow, query, filtered]);
  useLayoutEffect(() => {
    if (!follow || query || !activeRow.current || !transcript.current) return;
    const row = activeRow.current;
    const box = transcript.current;
    const align = () => {
      // Leave room after the last cue so even the final sentence can reach the top.
      box.style.setProperty('--transcript-tail-space', box.clientHeight + 'px');
      const padding = parseFloat(getComputedStyle(box).paddingTop) || 0;
      const delta = row.getBoundingClientRect().top - box.getBoundingClientRect().top - box.clientTop - padding;
      if (Math.abs(delta) > 0.5) box.scrollTop = Math.max(0, box.scrollTop + delta);
    };
    align();
    const observer = new ResizeObserver(align);
    observer.observe(box); observer.observe(row);
    return () => observer.disconnect();
  }, [video?.id, currentId, page, follow, query, video?.progress.mode, subtitleStyle.transcript_font, subtitleStyle.transcript_gap, collapsed.transcriptSide, collapsed.tools]);
  const preference = (patch: Partial<Progress>) => {
    const item = currentVideo.current;
    if (!item) return;
    const progress = { ...item.progress, time: player.current?.currentTime ?? position, ...patch };
    currentVideo.current = { ...item, progress };
    setVideo(currentVideo.current);
    if (progress.overlay !== 'off') visibleOverlay.current[item.id] = progress.overlay;
    if (patch.rate && player.current) player.current.playbackRate = patch.rate;
    if (pendingRateSave.current) {
      window.clearTimeout(pendingRateSave.current.timer);
      pendingRateSave.current = null;
    }
    // Apply every key to the media immediately, but persist a burst as its
    // final value instead of queuing overlapping requests for each repeat.
    if (patch.rate !== undefined) {
      const timer = window.setTimeout(() => {
        pendingRateSave.current = null;
        void api('/videos/' + item.id + '/progress', 'PUT', progress).catch(e => setError(e.message));
      }, 250);
      pendingRateSave.current = { timer, id: item.id, progress };
    } else void api('/videos/' + item.id + '/progress', 'PUT', progress).catch(e => setError(e.message));
  };
  useEffect(() => {
    if (video?.progress.overlay && video.progress.overlay !== 'off') visibleOverlay.current[video.id] = video.progress.overlay;
    setShortcutNotice('');
  }, [video?.id]);
  useEffect(() => {
    if (!shortcutNotice) return;
    const timer = window.setTimeout(() => setShortcutNotice(''), 1600);
    return () => window.clearTimeout(timer);
  }, [shortcutNotice]);
  useEffect(() => {
    shortcutRepeat.current = {};
    const onKeyDown = (event: KeyboardEvent) => {
      const item = currentVideo.current;
      const element = player.current;
      const decision = inspectPlaybackShortcut(event, importing);
      reportRuntime({ decision: !item || !element ? '播放器尚未准备好' : decision.reason, execution: '未执行' });
      if (diagnoseKeys.current && !event.ctrlKey && !event.altKey && !event.metaKey) {
        const check = inspectPlaybackShortcut(event, importing);
        const editing = check.reason.includes('输入');
        const safeKey = editing ? '文字输入（不记录内容）' : /^(?:[fcxsmFCXSM]|Process|Unidentified| |ArrowLeft|ArrowRight)$/.test(event.key) ? event.key : '其他按键';
        const safeCode = editing ? '省略' : /^(?:Key[FCXSM]|Space|ArrowLeft|ArrowRight)$/.test(event.code) ? event.code : event.code ? '其他键码' : '空';
        const state = !item || !element ? '播放器尚未准备好' : check.reason;
        setShortcutDiagnostic(`按键：${safeKey}；物理码：${safeCode}；数字码：${editing ? '省略' : event.keyCode}\n状态：${state}${check.action ? ' / ' + check.action : ''}\n焦点：${document.activeElement?.tagName || '无'}；输入法组合：${event.isComposing ? '是' : '否'}；此前已阻止：${event.defaultPrevented ? '是' : '否'}\n播放器：${element ? '已挂载' : '未挂载'}；当前倍速：${element?.playbackRate ?? '未知'}`);
      }
      if (!item || !element) return;
      handlePlaybackShortcut(event, action => {
        reportRuntime({ execution: '已执行 ' + action });
        if (action === 'fullscreen') { void toggleFullscreen(); return; }
        if (action === 'faster' || action === 'slower') {
          const rate = stepPlaybackRate(element.playbackRate, action === 'faster' ? .1 : -.1);
          preference({ rate }); setShortcutNotice(`播放速度 ${rate}×`);
        } else if (action === 'subtitles') {
          if (item.progress.overlay !== 'off') visibleOverlay.current[item.id] = item.progress.overlay;
          const overlay = toggleSubtitleMode(item.progress.overlay, visibleOverlay.current[item.id], item.has_source, item.has_target);
          preference({ overlay }); setShortcutNotice(overlay === 'off' ? '画面字幕已隐藏' : '画面字幕已显示');
        } else if (action === 'play') {
          if (element.paused) void element.play().catch(e => setError('无法播放：' + e.message));
          else element.pause();
        } else if (action === 'back' || action === 'forward') {
          setLoop(null);
          const next = Math.max(0, Math.min(item.duration, element.currentTime + (action === 'back' ? -5 : 5)));
          seek(next); setShortcutNotice(`${action === 'back' ? '后退' : '前进'} 5 秒`);
        } else if (action === 'mute') {
          element.muted = !element.muted; setShortcutNotice(element.muted ? '已静音' : '已取消静音');
        }
      }, importing, shortcutRepeat.current);
    };
    const unbind = bindPlaybackShortcuts(onKeyDown);
    reportRuntime({ app: '已启动', listener: '已绑定', player: player.current ? '已挂载' : '尚未打开视频' });
    return () => {
      unbind();
      reportRuntime({ listener: '已移除' });
    };
  }, [video?.id, importing]);
  const caption = (cue: Cue, mode: Mode) => <>
    {(mode === 'source' || mode === 'bilingual') && <span className="source-text">{cue.text}</span>}
    {(mode === 'target' || mode === 'bilingual') && <span className="target-text">{cue.translation || (video?.has_target ? '此句暂无对应译文' : '尚未导入译文')}</span>}
  </>;
  const importTrack = async (file: File, role: string) => {
    if (!video) return;
    const suffix = '.' + file.name.split('.').pop();
    await save();
    setVideo(await api<Video>('/videos/' + video.id + '/subtitles', 'POST',
      { role, language: role === 'source' ? sourceLanguage : 'zh-CN', suffix, content: await file.text() }));
  };
  const importChosen = async () => {
    let item: Video;
    if (importMode === 'project') {
      const result = await api<{ video?: Video; imported?: Video[]; errors?: Array<{ path: string; error: string }>; warnings?: string[]; needs_selection?: boolean; videos?: typeof importChoices }>(
        '/imports/project', 'POST', { directory: folder, ...(needsSelection ? { video_paths: importPaths } : {}) });
      if (result.needs_selection) {
        const choices = result.videos || [];
        setImportChoices(choices); setImportPaths(choices.map(c => c.path)); setNeedsSelection(true); return;
      }
      const messages = [...(result.warnings || []), ...(result.errors || []).map(e => e.path.split(/[\\/]/).pop() + '：' + e.error)];
      if (messages.length) setError(messages.join('；'));
      if (result.imported) {
        await refresh();
        setImportNotice(`已导入 ${result.imported.length} 个视频${result.errors?.length ? `，${result.errors.length} 个失败` : ''}，可在左侧资料库切换。`);
      }
      if (!result.video && messages.length) return;
      if (!result.video) throw new Error('工程导入失败');
      item = result.video;
    } else {
      const chosen = importChoices.find(c => c.path === path);
      item = await api<Video>('/videos', 'POST', { path, source_url: chosen?.source_url });
    }
    await save(); setVideo(item); setPosition(item.progress.time); setSelected(null); setLoop(null);
    history.replaceState(null, '', '/learn?video=' + item.id);
    await refresh(); setImporting(false);
    setLibraryQuery(''); setCollapsed(value => ({ ...value, library: false }));
  };
  return <div className="learning-app">
    <header className="topbar"><a className="brand" href="/learn"><BookOpen size={24} />VideoHub <span>学习</span></a>
      <div className="topbar-actions">
        <button className="layout-toggle" aria-label={collapsed.library ? '展开资料库' : '折叠资料库'} title={collapsed.library ? '展开左侧资料库' : '折叠左侧资料库'} aria-expanded={!collapsed.library} aria-controls="learning-library" onClick={() => setCollapsed(value => ({ ...value, library: !value.library }))}>{collapsed.library ? <PanelLeftOpen size={17}/> : <PanelLeftClose size={17}/>}<span>资料库</span></button>
        {video && <button className="layout-toggle" aria-label={collapsed.assistant ? '展开学习助手' : '折叠学习助手'} title={collapsed.assistant ? '展开右侧学习助手' : '折叠右侧学习助手'} aria-expanded={!collapsed.assistant} aria-controls="learning-assistant" onClick={() => setCollapsed(value => ({ ...value, assistant: !value.assistant }))}>{collapsed.assistant ? <PanelRightOpen size={17}/> : <PanelRightClose size={17}/>}<span>学习助手</span></button>}
        <button onClick={() => setImporting(true)}><FolderPlus size={17} />导入视频</button>
      </div></header>
    {error && <div className="error" role="alert">{error}<button aria-label="关闭错误" onClick={() => setError('')}><X size={16} /></button></div>}
    {importNotice && !importing && <div className="import-notice" role="status">{importNotice}<button aria-label="关闭提示" onClick={() => setImportNotice('')}><X size={16}/></button></div>}
    <main style={{ '--preferred-library-width': sizes.library + 'px', '--preferred-assistant-width': sizes.assistant + 'px' } as React.CSSProperties} className={'workspace' + (collapsed.library ? ' library-collapsed' : '') + (collapsed.assistant ? ' assistant-collapsed' : '')}><aside className="library" id="learning-library" hidden={collapsed.library}>
      <div className="library-heading"><div className="eyebrow">我的学习资料</div>
        {!!library.length && <button type="button" aria-label="管理学习资料" aria-pressed={managing} onClick={() => setManaging(value => !value)}>{managing ? '完成' : '管理'}</button>}</div>
      {!!library.length && <input className="library-search" aria-label="搜索学习资料" placeholder="搜索资料" value={libraryQuery} onChange={e => setLibraryQuery(e.target.value)}/>}
      {libraryGroups.map(group => <section className="library-group" key={group.key}>
        {group.title && <button className={'library-group-toggle' + (group.videos.some(item => item.id === video?.id) ? ' contains-selected' : '')}
          title={group.path} aria-label={'目录：' + group.title} aria-expanded={!!libraryQuery.trim() || !collapsedGroups.includes(group.key)}
          onClick={() => setCollapsedGroups(keys => keys.includes(group.key) ? keys.filter(key => key !== group.key) : [...keys, group.key])}>
          {(libraryQuery.trim() || !collapsedGroups.includes(group.key)) ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}<Folder size={15}/><span>{group.title}</span><small>{group.videos.length}</small>
        </button>}
        {(!group.title || libraryQuery.trim() || !collapsedGroups.includes(group.key)) && <div className="library-group-items">{group.videos.map(item => <div key={item.id} className="library-row">
        <button disabled={busy} className={'library-item ' + (video?.id === item.id ? 'selected' : '')} title={item.title + '\n' + time(item.progress.time) + ' / ' + time(item.duration)} aria-label={item.title + '，' + time(item.progress.time) + ' / ' + time(item.duration)}
          onClick={() => void execute(async () => { await save(); await open(item.id); await refresh(); })}><Play size={14} /><span className="library-title">{item.title}</span><progress aria-label="学习进度" max={item.duration} value={item.progress.time}/></button>
        {managing && <button className="library-remove" disabled={busy} title="移出资料库" aria-label={'移出资料库：' + item.title} onClick={() => removeFromLibrary(item)}><Trash2 size={15}/></button>}
      </div>)}</div>}
      </section>)}
      {!!library.length && !libraryGroups.length && <p className="muted">没有找到匹配的资料或目录。</p>}
      {!library.length && <p className="muted">导入一个视频，开始学习。</p>}
      <ResizeHandle label="调整资料库宽度" controls="learning-library" className="library-width-resizer" axis="x" value={sizes.library} min={160} max={sizes.libraryMax} change={value => sizes.change('library', value)} reset={() => sizes.reset('library')}/></aside>
      <section className={'lesson' + (collapsed.tools ? ' tools-collapsed' : '') + (collapsed.transcriptSide ? ' transcript-side' : '')} style={{ '--video-column-width': sizes.videoWidth + 'px' } as React.CSSProperties} ref={lesson}><div className="lesson-content">{video ? <><div className="watch-pane" id="learning-watch-pane">
        <div className="lesson-heading"><div><div className="eyebrow">{video.project_root ? '视频学习工程' : '正在学习'}</div><h1 title={video.title}>{video.title}</h1></div><span className="time-pill">{time(position)}</span></div>
        {video.project_root && <p className="project-location" title={video.project_root}>工程目录：{video.project_root}</p>}
        {!!video.subtitle_warnings?.length && <details className="warning"><summary>字幕片尾时间已校正（{video.subtitle_warnings.length} 项）</summary>{video.subtitle_warnings.map(warning => <p key={warning}>{warning}</p>)}</details>}
        <div className="player-wrap" id="learning-player" ref={playerWrap} tabIndex={0} aria-label="视频播放器" aria-keyshortcuts="F C X S Space ArrowLeft ArrowRight M" onPointerDownCapture={() => playerWrap.current?.focus({ preventScroll: true })} style={{ '--video-ratio': videoRatio, '--player-height': sizes.player + 'px' } as React.CSSProperties}><video key={video.id} ref={player} controls controlsList="nofullscreen" playsInline src={video.media_url}
          onDoubleClick={e => { e.preventDefault(); void toggleFullscreen(); }}
          onLoadedMetadata={() => { if (player.current) { const p = player.current; p.currentTime = video.progress.time; p.playbackRate = video.progress.rate; if (p.videoWidth && p.videoHeight) setVideoRatio(p.videoWidth / p.videoHeight); } }}
          onTimeUpdate={() => { let p = player.current?.currentTime || 0; if (loop && p >= loop.end && player.current) { player.current.currentTime = loop.start; p = loop.start; } setPosition(p); if (Date.now() - lastSaved.current > 5000) { lastSaved.current = Date.now(); void save().catch(e => setError(e.message)); } }}
          onPause={() => void save().catch(e => setError(e.message))}
          onSeeked={() => { if (loop && player.current && (player.current.currentTime < loop.start || player.current.currentTime > loop.end)) setLoop(null); }}
          onError={() => setError('浏览器无法播放此编码，或原文件已移动。请检查视频，必要时生成浏览器预览。')} />
          <div ref={subtitleOverlay} className="subtitle-overlay" data-position={subtitleStyle.position} data-mode={video.progress.overlay} style={{ '--subtitle-size': video.progress.font + 'px', '--subtitle-offset': subtitleStyle.offset + '%', '--subtitle-english-gap': subtitleStyle.english_size_delta + 'px',
            '--subtitle-source-color': subtitleStyle.source_color, '--subtitle-target-color': subtitleStyle.target_color,
            '--subtitle-background': `rgba(0,0,0,${subtitleStyle.background})`, fontFamily: subtitleFonts[subtitleStyle.font_family],
            fontWeight: subtitleStyle.bold ? 700 : 400, lineHeight: subtitleStyle.line_height,
            textShadow: subtitleStyle.outline ? '0 2px 4px #000, 1px 0 2px #000, -1px 0 2px #000' : 'none' } as React.CSSProperties}>{video.progress.overlay !== 'off' && <div>
            {(video.progress.overlay === 'source' || video.progress.overlay === 'bilingual') && sourceCaption && <span className="source-text" data-english={isEnglishCaption('source', sourceCaption.text) || undefined}>{sourceCaption.text}</span>}
            {(video.progress.overlay === 'target' || video.progress.overlay === 'bilingual') && targetCaption && (video.progress.overlay !== 'bilingual' || targetCaption.text !== sourceCaption?.text) && <span className="target-text" data-english={isEnglishCaption('target', targetCaption.text) || undefined}>{targetCaption.text}</span>}
            {(video.progress.overlay === 'target' || video.progress.overlay === 'bilingual') && !video.has_target && sourceCaption && <span className="target-text">尚未导入译文</span>}
          </div>}</div>
          {shortcutNotice && <div className="shortcut-notice" role="status">{shortcutNotice}</div>}
          <button className="player-fullscreen" aria-label={fullscreen ? '退出全屏' : '全屏观看（含字幕）'} title={fullscreen ? '退出全屏（Esc / F）' : '全屏观看，保留字幕（F / 双击画面）'} onClick={() => void toggleFullscreen()}>{fullscreen ? <Minimize size={17}/> : <Maximize size={17}/>}<span>{fullscreen ? '退出全屏' : '全屏'}</span></button>
        </div>
        <ResizeHandle label="调整播放器高度" controls="learning-player" className="player-height-resizer" axis="y" value={sizes.player} min={sizes.playerMin} max={sizes.playerMax} change={value => sizes.change('player', value)} reset={() => sizes.reset('player')}/>
        <div className="learning-tools" id="learning-playback-tools" hidden={collapsed.tools}>
        <div className="playback-options"><label>倍速 <select aria-label="播放倍速" title="C 加速 0.1×，X 减速 0.1×（0.25–3×）" value={video.progress.rate} onChange={e => preference({ rate: Number(e.target.value) })}>{playbackRates(video.progress.rate).map(n => <option key={n} value={n}>{n}×</option>)}</select></label>
          <label>画面字幕 <select aria-label="画面字幕" value={video.progress.overlay} onChange={e => preference({ overlay: e.target.value as Mode })}><option value="source">{sourceLabel}</option><option value="target">{targetLabel}</option><option value="bilingual">双语</option><option value="off">关闭</option></select></label>
          <label>画面字号 <input aria-label="字幕字号" type="range" min="14" max="96" value={video.progress.font} onChange={e => preference({ font: Number(e.target.value) })}/><output>{video.progress.font}px</output></label>
          <label title="双语画面中，正数让英文更小，0为同样大小，负数让英文更大；英文最小10px">中英字号差 <input aria-label="中英字幕字号差" type="range" min="-12" max="12" step="1" value={subtitleStyle.english_size_delta} onChange={e => stylePreference({ english_size_delta: Number(e.target.value) })}/><output>{subtitleStyle.english_size_delta}px</output></label>
          <label>字幕上下 <input aria-label="画面字幕上下位置" title="从底部向上移动；选择顶部位置时从顶部向下移动" type="range" min="0" max="60" value={subtitleStyle.offset} onChange={e => stylePreference({ offset: Number(e.target.value) })}/><output>{subtitleStyle.offset}%</output></label>
          {loop && <button className="loop-active" onClick={() => setLoop(null)}><Repeat size={14}/>循环 {time(loop.start)}—{time(loop.end)} · 关闭</button>}
          <button className="clip-toggle" aria-expanded={clipVideoId === video.id} aria-controls="learning-clip" onClick={() => setClipVideoId(clipVideoId === video.id ? '' : video.id)}><Scissors size={14}/>截取片段</button></div>
        {clipVideoId === video.id && <LearningClip key={video.id} videoId={video.id} duration={video.duration}
          position={() => Math.min(video.duration, player.current?.currentTime ?? position)} close={() => setClipVideoId('')}/>}
        <details className="shortcut-help"><summary>快捷键 · F 全屏 · C / X 倍速 · S 字幕</summary>
          <button type="button" onClick={() => { playerWrap.current?.focus({ preventScroll: true }); setShortcutNotice('快捷键已启用：F 全屏 · C / X 倍速 · S 字幕'); }}>点击这里启用快捷键</button>
          <button type="button" onClick={() => { diagnoseKeys.current = true; setShortcutDiagnostic('检测已开启，等待按键。请点击画面后按一次 C。'); playerWrap.current?.focus({ preventScroll: true }); }}>检测按键是否收到</button>
          {shortcutDiagnostic && <pre className="shortcut-diagnostic" role="status">{shortcutDiagnostic}</pre>}
          <div><span><kbd>F</kbd> 全屏 / 退出</span><span><kbd>C</kbd> 加速 0.1×</span><span><kbd>X</kbd> 减速 0.1×</span><span><kbd>S</kbd> 显示 / 隐藏画面字幕</span><span><kbd>空格</kbd> 播放 / 暂停</span><span><kbd>←</kbd> / <kbd>→</kbd> 后退 / 前进 5 秒</span><span><kbd>M</kbd> 静音 / 取消</span></div>
          <p>学习页与全屏均可使用，中文输入法下也支持字母快捷键；输入问题、笔记、搜索文字或打开导入窗口时停用。C / X 和左右方向键支持长按连续调节；F / S / M / 空格按住只切换一次，松开后可再次按下。下拉框、滑块保留空格和方向键，F / C / X / S 仍可控制视频。倍速范围 0.25–3×，字幕恢复本页中该视频上次显示的语言，不改变下方文稿。</p>
        </details>
        <details className="subtitle-settings"><summary>字幕文件与样式</summary>
          <p className="muted">原文和译文分别保存为纯文本 SRT；画面字幕与下方文稿可分别调整，按当前视频记忆。双语画面中英文默认比中文小2px，可用“中英字号差”调节；单语画面使用统一的画面字号。上下滑块从所选边缘向画面内移动。</p>
          <div className="subtitle-downloads">{(['source','target'] as const).map(role => video.subtitle_urls?.[role] && <a key={role} href={video.subtitle_urls[role]} download title={video.tracks[role]?.path}>下载{role === 'source' ? sourceLabel : targetLabel}字幕（SRT）</a>)}</div>
          <div className="subtitle-style-grid">
            <label>字体<select aria-label="字幕字体" value={subtitleStyle.font_family} onChange={e => stylePreference({ font_family: e.target.value as SubtitleStyle['font_family'] })}><option value="sans">无衬线 / 微软雅黑</option><option value="serif">衬线 / 宋体</option><option value="mono">等宽字体</option></select></label>
            <label>位置<select aria-label="字幕位置" value={subtitleStyle.position} onChange={e => stylePreference({ position: e.target.value as SubtitleStyle['position'] })}><option value="bottom">底部</option><option value="top">顶部</option></select></label>
            <label>原文颜色<input aria-label="原文字幕颜色" type="color" value={subtitleStyle.source_color} onChange={e => stylePreference({ source_color: e.target.value })}/></label>
            <label>译文颜色<input aria-label="译文字幕颜色" type="color" value={subtitleStyle.target_color} onChange={e => stylePreference({ target_color: e.target.value })}/></label>
            <label>背景深度<input aria-label="字幕背景深度" type="range" min="0" max="0.9" step="0.05" value={subtitleStyle.background} onChange={e => stylePreference({ background: Number(e.target.value) })}/></label>
            <label>行距<input aria-label="字幕行距" type="range" min="1.1" max="2" step="0.1" value={subtitleStyle.line_height} onChange={e => stylePreference({ line_height: Number(e.target.value) })}/></label>
            <label><input aria-label="字幕粗体" type="checkbox" checked={subtitleStyle.bold} onChange={e => stylePreference({ bold: e.target.checked })}/>粗体</label>
            <label><input aria-label="字幕描边阴影" type="checkbox" checked={subtitleStyle.outline} onChange={e => stylePreference({ outline: e.target.checked })}/>描边阴影</label>
          </div><button onClick={() => preference({ font: 20, style: { ...defaultSubtitleStyle } })}>恢复默认字幕样式</button>
        </details>
        </div>
        </div>
        <ResizeHandle label="调整视频和字幕宽度" controls="learning-watch-pane learning-transcript-pane" className="transcript-width-resizer" axis="x" value={sizes.videoWidth} min={sizes.videoMin} max={sizes.videoMax} change={value => sizes.change('videoShare', value / sizes.splitAvailable)} reset={() => sizes.reset('videoShare')}/>
        <section className="transcript-pane" id="learning-transcript-pane" aria-label="字幕文稿">
        <div className="transcript-heading"><h2><Subtitles size={18} />字幕文稿</h2><div className="transcript-actions">
          <button className="transcript-position-toggle" aria-pressed={collapsed.transcriptSide} onClick={() => setCollapsed(value => ({ ...value, transcriptSide: !value.transcriptSide }))}>{collapsed.transcriptSide ? '字幕放下方' : '字幕放右侧'}</button>
          <button className="tools-toggle" aria-expanded={!collapsed.tools} aria-controls="learning-playback-tools learning-transcript-tools" onClick={() => setCollapsed(value => ({ ...value, tools: !value.tools }))}>
            {collapsed.tools ? <ChevronDown size={15}/> : <ChevronUp size={15}/>}{collapsed.tools ? '展开工具栏' : '隐藏工具栏'}
          </button></div></div>
        <div className="learning-tools" id="learning-transcript-tools" hidden={collapsed.tools}>
        <div className="transcript-toolbar"><label className="search"><Search size={16}/><input aria-label="搜索字幕" placeholder="搜索视频内容" value={query} onChange={e => setQuery(e.target.value)}/></label>
          <select aria-label="原文语言" title="导入原文字幕的语言" value={sourceLanguage} onChange={e => setSourceLanguage(e.target.value)}><option value="en">英文</option><option value="zh-CN">中文</option><option value="ja">日文</option><option value="ko">韩文</option><option value="auto">其他原文</option></select>
          <label className="button">原文<input aria-label="导入原文字幕" type="file" accept=".srt,.vtt,.ass,.ssa" hidden onChange={e => { const f = e.target.files?.[0]; if (f) void execute(() => importTrack(f, 'source')); e.target.value = ''; }} /></label>
          <label className="button">中文<input aria-label="导入中文字幕" type="file" accept=".srt,.vtt,.ass,.ssa" hidden onChange={e => { const f = e.target.files?.[0]; if (f) void execute(() => importTrack(f, 'target')); e.target.value = ''; }} /></label>
          <button onClick={() => { setCollapsed(value => ({ ...value, assistant: false })); setTranslationRequest(value => ({ videoId: video.id, count: value.count + 1 })); }}>翻译已有字幕</button></div>
        <details className="subtitle-versions"><summary>字幕版本 · 原文 / 译文 / 双语文件</summary>
          <p className="muted">分别选择一份原文和一份译文用于学习。可先选原文，再点“翻译已有字幕”；重新翻译后可切回旧版本。</p>
          <button disabled={busy} onClick={() => void execute(async () => { const value = await api<{ tracks: typeof subtitleChoices }>('/videos/' + video.id + '/subtitle-candidates'); setSubtitleChoices(value.tracks); })}>重新查找字幕</button>
          <div className="track-choices">{(['source','target'] as const).filter(role => video.available_tracks.some(t => t.role === role)).map(role => <label key={role}>{role === 'source' ? '原文版本' : '译文版本'}<select disabled={busy} title={video.tracks[role]?.path} aria-label={role === 'source' ? '选择原文轨道' : '选择译文轨道'} value={role} onChange={e => { const key = e.target.value; void execute(async () => { await save(); setVideo(await api<Video>('/videos/' + video.id + '/select-track', 'POST', { role, key })); }); }}>{video.available_tracks.filter(t => t.role === role && (t.key === role || t.path !== video.tracks[role]?.path)).map(t => <option value={t.key} key={t.key}>{t.key === role ? '当前 · ' : ''}{labels[t.language] || t.language} · {t.label || t.name}{t.updated ? ' · ' + new Date(t.updated).toLocaleString() : ''}{t.key !== role ? ' · ' + t.key.slice(-6) : ''}</option>)}</select></label>)}</div>
          <div className="subtitle-file-list">{subtitleChoices.filter(t => !video.available_tracks.some(a => a.role === t.role && a.path === t.path)).map(track => <button disabled={busy} title={track.path} key={track.path + track.role} onClick={() => void execute(async () => { await save(); setVideo(await api<Video>('/videos/' + video.id + '/subtitles', 'POST', track)); })}>
            <strong>{track.role === 'target' ? '用作译文' : '用作原文'} · {labels[track.language] || track.language} · {track.format || track.name.split('.').pop()?.toUpperCase()}{track.bilingual ? ' · 双语文件（提取单语言）' : ''}</strong><span>{track.name}</span><small>{track.modified ? new Date(track.modified * 1000).toLocaleString() + ' · ' : ''}{track.path}</small>
          </button>)}</div>
          {!subtitleChoices.length && <p className="muted">未发现其他字幕文件。可用上方“原文 / 中文”导入其他目录中的字幕。</p>}
        </details>
        <div className="transcript-appearance"><label>文稿字号 <input aria-label="文稿字号" type="range" min="12" max="36" value={subtitleStyle.transcript_font} onChange={e => stylePreference({ transcript_font: Number(e.target.value) })}/><output>{subtitleStyle.transcript_font}px</output></label>
          <label>句组间距 <input aria-label="文稿句组间距" type="range" min="0" max="24" value={subtitleStyle.transcript_gap} onChange={e => stylePreference({ transcript_gap: Number(e.target.value) })}/><output>{subtitleStyle.transcript_gap}px</output></label></div>
        </div>
        <div className="transcript-options"><div className="segmented">{(['source','target','bilingual','off'] as Mode[]).map((mode, i) => <button key={mode} className={video.progress.mode === mode ? 'chosen' : ''} onClick={() => preference({ mode })}>{[sourceLabel,targetLabel,'双语','隐藏'][i]}</button>)}</div><button className={follow ? 'following' : ''} onClick={() => { setFollow(true); setQuery(''); }}><Crosshair size={14}/>{follow ? '正在跟随' : '回到当前'}</button></div>
        <div ref={transcript} className="transcript" style={{ '--transcript-font': subtitleStyle.transcript_font + 'px', '--transcript-gap': subtitleStyle.transcript_gap + 'px' } as React.CSSProperties} onWheel={() => setFollow(false)} onTouchStart={() => setFollow(false)} onPointerDown={() => setFollow(false)} onKeyDown={e => { if (['ArrowDown','ArrowUp','PageDown','PageUp'].includes(e.key)) setFollow(false); }}>
          {video.progress.mode !== 'off' && filtered.slice(page * 120, (page + 1) * 120).map(c => <div ref={c.id === currentId ? activeRow : undefined} aria-current={c.id === currentId ? 'true' : undefined} key={c.id} className={'cue ' + (current.some(a => a.id === c.id) ? 'active ' : '') + (selected?.id === c.id ? 'cue-selected' : '')}>
            <button className="cue-time" onClick={() => { setLoop(null); seek(c.start); }}><time>{time(c.start)}</time></button><button className="cue-content" onClick={() => setSelected(c)}>{caption(c, video.progress.mode)}</button><button aria-label={'循环 ' + time(c.start)} className="cue-loop" onClick={() => { setLoop(c); seek(c.start); void player.current?.play().catch(() => {}); }}><Repeat size={14}/></button></div>)}
          {!video.cues.length && <div className="empty"><Subtitles size={26}/><h3>准备好字幕，理解更多内容</h3><p>导入 SRT、VTT 或 ASS 文件。视频和笔记保存在本机。</p></div>}</div>
        {pageCount > 1 && <div className="transcript-pages"><button disabled={page === 0} onClick={() => { setFollow(false); setPage(p => Math.max(0, p - 1)); }}>上一页</button><span>{page + 1} / {pageCount} · {filtered.length} 条字幕</span><button disabled={page >= pageCount - 1} onClick={() => { setFollow(false); setPage(p => Math.min(pageCount - 1, p + 1)); }}>下一页</button></div>}
        {selected && <div className="selection-bar"><span>已选择 {time(selected.start)} · {selected.text.slice(0, 60)}</span><button onClick={() => seek(selected.start)}>定位原片</button><button aria-label="取消选句" onClick={() => setSelected(null)}><X size={15}/></button></div>}
      </section></> : <div className="welcome"><div className="welcome-icon"><BookOpen size={42}/></div><div className="eyebrow">看懂每一段，留下每一个收获</div><h1>把视频变成你的学习资料</h1><p>双语字幕、随时提问、时间戳笔记。<br/>从一个已经下载好的视频开始。</p><button className="primary" onClick={() => setImporting(true)}><FolderPlus size={18}/>导入第一个视频</button></div>}</div></section>
      {video && <LearningPanel key={video.id} video={video} position={position} selected={selected} providers={providers} mindmapAvailable={mindmapAvailable} translationRequest={translationRequest.videoId === video.id ? translationRequest.count : 0} seek={seek} collapsed={collapsed.assistant}
        resizeHandle={<ResizeHandle label="调整学习助手宽度" controls="learning-assistant" className="assistant-width-resizer" axis="x" direction={-1} value={sizes.assistant} min={260} max={sizes.assistantMax} change={value => sizes.change('assistant', value)} reset={() => sizes.reset('assistant')}/>}
        refresh={async () => {
          if (currentVideo.current?.id !== video.id) return;
          await save();
          const updated = await api<Video>('/videos/' + video.id);
          if (currentVideo.current?.id !== video.id) return;
          setVideo(updated);
          await refresh();
        }} report={setError}/>}
    </main>
    {importing && <div className="modal-backdrop"><form className="modal import-modal" onSubmit={e => { e.preventDefault(); void execute(importChosen); }}><div className="modal-title"><h2>导入学习资料</h2><button type="button" disabled={busy} aria-label="关闭导入" onClick={() => setImporting(false)}><X size={20}/></button></div><div className="segmented import-mode"><button type="button" disabled={busy} className={importMode === 'project' ? 'chosen' : ''} onClick={() => { setImportMode('project'); setNeedsSelection(false); }}>视频工程（目录）</button><button type="button" disabled={busy} className={importMode === 'file' ? 'chosen' : ''} onClick={() => { setImportMode('file'); setNeedsSelection(false); }}>单个视频 / 下载记录</button></div>
      {error && <p className="warning" role="alert">{error}</p>}
      {importMode === 'project' ? <><p>一个目录可放多个视频；字幕放在同目录或 subtitles 子目录。多个视频请使用对应名称，例如 lesson1.mp4、lesson1.en.srt、lesson1.zh-CN.srt。</p><label>工程目录<input disabled={busy} aria-label="工程目录" autoFocus value={folder} placeholder="F:\学习\课程目录" required onChange={e => { setFolder(e.target.value); setNeedsSelection(false); setImportPaths([]); }}/></label>{needsSelection && <><p className="warning">找到 {importChoices.length} 个视频，已选 {importPaths.length} 个。可全部导入或选择部分；每个视频只关联自己的同名字幕，进度和笔记分别保存。</p><div className="import-selection-actions"><button type="button" disabled={busy} onClick={() => setImportPaths(importChoices.map(c => c.path))}>全选</button><button type="button" disabled={busy} onClick={() => setImportPaths([])}>清空选择</button></div></>}</> : <><p>本地视频直接引用；下载记录会自动整理为工程并加载对应字幕，保留原文件。</p><label>视频路径<input aria-label="视频路径" autoFocus value={path} placeholder="F:\videos\课程.mp4" required onChange={e => setPath(e.target.value)} /></label><details><summary>从视频目录或剧集目录选择</summary><div className="folder-scan"><input aria-label="视频目录" value={folder} placeholder="目录完整路径" onChange={e => setFolder(e.target.value)}/><button type="button" disabled={busy || !folder} onClick={() => void execute(async () => setImportChoices((await api<{ videos: typeof importChoices }>('/imports/directory', 'POST', { path: folder })).videos))}>扫描目录</button></div></details></>}
      {importMode === 'project' && needsSelection && <div className="import-choices">{importChoices.map(choice => <label className="import-video-choice" key={choice.path} title={choice.path}><input type="checkbox" disabled={busy} checked={importPaths.includes(choice.path)} onChange={e => { const checked = e.target.checked; setImportPaths(previous => checked ? [...previous, choice.path] : previous.filter(p => p !== choice.path)); }}/><span>{choice.title}</span></label>)}</div>}
      {importMode === 'file' && !!importChoices.length && <div className="import-choices">{importChoices.map(choice => <button type="button" className={path === choice.path ? 'chosen' : ''} key={choice.path} title={choice.path} onClick={() => setPath(choice.path)}><Play size={13}/>{choice.title}</button>)}</div>}
      <button className="primary" disabled={busy || (needsSelection && !importPaths.length)}>{busy ? '正在读取并导入…' : importMode === 'project' ? needsSelection ? `导入所选 ${importPaths.length} 个视频及字幕` : '打开工程并扫描视频' : '加入学习资料'}</button></form></div>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<App />);
