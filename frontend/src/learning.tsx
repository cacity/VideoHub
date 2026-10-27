import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BookOpen, FolderPlus, Play, Search, Subtitles, X, Repeat, Crosshair } from 'lucide-react';
import './learning.css';
import { api, setToken, time, Mode, Progress, Cue, Video, Providers } from './learning-api';
import { LearningPanel } from './learning-panel';

function App() {
  const [library, setLibrary] = useState<Video[]>([]);
  const [video, setVideo] = useState<Video | null>(null);
  const [error, setError] = useState('');
  const [importing, setImporting] = useState(false);
  const [importMode, setImportMode] = useState('project');
  const [needsSelection, setNeedsSelection] = useState(false);
  const [path, setPath] = useState('');
  const [folder, setFolder] = useState('');
  const [importChoices, setImportChoices] = useState<Array<{ path: string; title: string; source_url?: string }>>([]);
  const [subtitleChoices, setSubtitleChoices] = useState<Array<{ path: string; name: string; role: string; language: string }>>([]);
  const [showChoices, setShowChoices] = useState(false);
  const [sourceLanguage, setSourceLanguage] = useState('en');
  const [libraryQuery, setLibraryQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState<Providers>({});
  const [position, setPosition] = useState(0);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const [follow, setFollow] = useState(true);
  const [selected, setSelected] = useState<Cue | null>(null);
  const [loop, setLoop] = useState<Cue | null>(null);
  const activeRow = useRef<HTMLDivElement>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const player = useRef<HTMLVideoElement>(null);
  const currentVideo = useRef<Video | null>(null);
  const lastSaved = useRef(0);
  currentVideo.current = video;
  const execute = async (work: () => Promise<void>) => {
    setError(''); setBusy(true);
    try { await work(); } catch (e) { setError(String((e as Error).message)); } finally { setBusy(false); }
  };
  const refresh = async () => setLibrary((await api<{ videos: Video[] }>('/videos')).videos);
  const open = async (id: string) => {
    const item = await api<Video>('/videos/' + id);
    const params = new URLSearchParams(location.search);
    const linked = params.get('video') === id && params.has('t') ? Number(params.get('t')) : NaN;
    if (Number.isFinite(linked)) item.progress.time = Math.max(0, Math.min(item.duration, linked));
    history.replaceState(null, '', '/learn?video=' + id);
    setVideo(item); setPosition(item.progress.time); setSelected(null); setLoop(null); setFollow(true); setQuery('');
  };
  useEffect(() => { void execute(async () => {
    const session = await api<{ token: string; providers: Providers }>('/session');
    setToken(session.token); setProviders(session.providers);
    await refresh();
    const id = new URLSearchParams(location.search).get('video') || localStorage.getItem('videohub.learning.last');
    if (id) await open(id);
  }); }, []);
  useEffect(() => { if (video) localStorage.setItem('videohub.learning.last', video.id); }, [video?.id]);
  useEffect(() => { setSourceLanguage(video?.tracks.source?.language || 'en'); }, [video?.id, video?.tracks.source?.language]);
  useEffect(() => { setSelected(null); setLoop(null); setQuery(''); setPage(0); }, [video?.subtitle_version]);
  useEffect(() => { if (importing) void api<{ videos: typeof importChoices }>('/imports/recent').then(v => setImportChoices(v.videos)).catch(e => setError(e.message)); }, [importing]);
  useEffect(() => { setShowChoices(false); setSubtitleChoices([]); if (video) void api<{ tracks: typeof subtitleChoices }>('/videos/' + video.id + '/subtitle-candidates').then(v => setSubtitleChoices(v.tracks)).catch(e => setError(e.message)); }, [video?.id]);
  const save = async () => {
    const item = currentVideo.current; const element = player.current;
    if (item && element) await api('/videos/' + item.id + '/progress', 'PUT',
      { ...item.progress, time: element.currentTime, rate: element.playbackRate });
  };
  useEffect(() => {
    const flush = () => { void save().catch(() => {}); };
    const visibility = () => { if (document.visibilityState === 'hidden') flush(); };
    window.addEventListener('pagehide', flush); document.addEventListener('visibilitychange', visibility);
    return () => { window.removeEventListener('pagehide', flush); document.removeEventListener('visibilitychange', visibility); };
  }, []);
  const seek = (seconds: number) => { if (player.current) player.current.currentTime = seconds; setPosition(seconds); setFollow(true); };
  const current = video?.cues.filter(c => c.start <= position && c.end > position) || [];
  const currentId = current[0]?.id;
  const labels: Record<string, string> = { en: '英文', 'zh-CN': '中文', 'zh': '中文', ja: '日文', ko: '韩文', auto: '原文' };
  const sourceLabel = labels[video?.tracks.source?.language || 'auto'] || '原文';
  const targetLabel = labels[video?.tracks.target?.language || 'zh-CN'] || '译文';
  const filtered = useMemo(() => video?.cues.filter(c => (c.text + c.translation).toLowerCase().includes(query.toLowerCase())) || [], [video?.cues, query]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / 120));
  useEffect(() => { setPage(0); }, [video?.id, query]);
  useEffect(() => { if (follow && !query && currentId) { const index = filtered.findIndex(c => c.id === currentId); if (index >= 0) setPage(Math.floor(index / 120)); } }, [currentId, follow, query, filtered]);
  useEffect(() => {
    if (!follow || query || !activeRow.current || !transcript.current) return;
    const row = activeRow.current.getBoundingClientRect();
    const box = transcript.current.getBoundingClientRect();
    if (row.top < box.top) transcript.current.scrollBy({ top: row.top - box.top - 10, behavior: 'smooth' });
    else if (row.bottom > box.bottom) transcript.current.scrollBy({ top: row.bottom - box.bottom + 10, behavior: 'smooth' });
  }, [currentId, follow, query]);
  const preference = (patch: Partial<Progress>) => {
    if (!video) return;
    const progress = { ...video.progress, time: player.current?.currentTime || position, ...patch };
    setVideo({ ...video, progress });
    if (patch.rate && player.current) player.current.playbackRate = patch.rate;
    void api('/videos/' + video.id + '/progress', 'PUT', progress).catch(e => setError(e.message));
  };
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
      const result = await api<{ video?: Video; warnings?: string[]; needs_selection?: boolean; videos?: typeof importChoices }>(
        '/imports/project', 'POST', { directory: folder, video_path: needsSelection ? path : '' });
      if (result.needs_selection) { setImportChoices(result.videos || []); setNeedsSelection(true); setPath(''); return; }
      if (!result.video) throw new Error('工程导入失败');
      item = result.video;
      if (result.warnings?.length) setError(result.warnings.join('；'));
    } else {
      const chosen = importChoices.find(c => c.path === path);
      item = await api<Video>('/videos', 'POST', { path, source_url: chosen?.source_url });
    }
    await save(); setVideo(item); setPosition(item.progress.time); setSelected(null); setLoop(null);
    history.replaceState(null, '', '/learn?video=' + item.id);
    await refresh(); setImporting(false);
  };
  return <div className="learning-app">
    <header className="topbar"><a className="brand" href="/learn"><BookOpen size={24} />VideoHub <span>学习</span></a>
      <button onClick={() => setImporting(true)}><FolderPlus size={17} />导入视频</button></header>
    {error && <div className="error" role="alert">{error}<button aria-label="关闭错误" onClick={() => setError('')}><X size={16} /></button></div>}
    <main className="workspace"><aside className="library"><div className="eyebrow">我的学习资料</div>
      {!!library.length && <input className="library-search" aria-label="搜索学习资料" placeholder="搜索资料" value={libraryQuery} onChange={e => setLibraryQuery(e.target.value)}/>}
      {library.filter(v => v.title.toLowerCase().includes(libraryQuery.toLowerCase())).map(item => <button key={item.id} className={'library-item ' + (video?.id === item.id ? 'selected' : '')}
        onClick={() => void execute(async () => { await save(); await open(item.id); await refresh(); })}><Play size={14} /><span>{item.title}<small>{time(item.progress.time)} / {time(item.duration)}</small><progress aria-label="学习进度" max={item.duration} value={item.progress.time}/></span></button>)}
      {!library.length && <p className="muted">导入一个视频，开始学习。</p>}</aside>
      <section className="lesson">{video ? <>
        <div className="lesson-heading"><div><div className="eyebrow">{video.project_root ? '视频学习工程' : '正在学习'}</div><h1>{video.title}</h1></div><span className="time-pill">{time(position)}</span></div>
        {video.project_root && <p className="project-location" title={video.project_root}>工程目录：{video.project_root}</p>}
        <div className="player-wrap" style={{ '--video-ratio': (video.width && video.height ? video.width / video.height : 16 / 9) } as React.CSSProperties}><video key={video.id} ref={player} controls src={video.media_url}
          onLoadedMetadata={() => { if (player.current) { const p = player.current; p.currentTime = video.progress.time; p.playbackRate = video.progress.rate; if (p.videoWidth && p.videoHeight) p.parentElement?.style.setProperty('--video-ratio', String(p.videoWidth / p.videoHeight)); } }}
          onTimeUpdate={() => { let p = player.current?.currentTime || 0; if (loop && p >= loop.end && player.current) { player.current.currentTime = loop.start; p = loop.start; } setPosition(p); if (Date.now() - lastSaved.current > 5000) { lastSaved.current = Date.now(); void save().catch(e => setError(e.message)); } }}
          onPause={() => void save().catch(e => setError(e.message))}
          onSeeked={() => { if (loop && player.current && (player.current.currentTime < loop.start || player.current.currentTime > loop.end)) setLoop(null); }}
          onError={() => setError('浏览器无法播放此编码，或原文件已移动。请检查视频，必要时生成浏览器预览。')} />
          <div className="subtitle-overlay" style={{ fontSize: video.progress.font }}>{video.progress.overlay !== 'off' && current.map(c => <div key={c.id}>{caption(c, video.progress.overlay)}</div>)}</div></div>
        <div className="playback-options"><label>倍速 <select aria-label="播放倍速" value={video.progress.rate} onChange={e => preference({ rate: Number(e.target.value) })}>{[.5,.75,1,1.25,1.5,1.75,2,2.5,3].map(n => <option key={n} value={n}>{n}×</option>)}</select></label>
          <label>画面字幕 <select aria-label="画面字幕" value={video.progress.overlay} onChange={e => preference({ overlay: e.target.value as Mode })}><option value="source">{sourceLabel}</option><option value="target">{targetLabel}</option><option value="bilingual">双语</option><option value="off">关闭</option></select></label>
          <label>字号 <input aria-label="字幕字号" type="range" min="14" max="36" value={video.progress.font} onChange={e => preference({ font: Number(e.target.value) })}/></label>
          {loop && <button className="loop-active" onClick={() => setLoop(null)}><Repeat size={14}/>循环 {time(loop.start)}—{time(loop.end)} · 关闭</button>}</div>
        <div className="transcript-toolbar"><h2><Subtitles size={18} />字幕文稿</h2><label className="search"><Search size={16}/><input aria-label="搜索字幕" placeholder="搜索视频内容" value={query} onChange={e => setQuery(e.target.value)}/></label>
          <select aria-label="原文语言" title="导入原文字幕的语言" value={sourceLanguage} onChange={e => setSourceLanguage(e.target.value)}><option value="en">英文</option><option value="zh-CN">中文</option><option value="ja">日文</option><option value="ko">韩文</option><option value="auto">其他原文</option></select>
          <label className="button">原文<input aria-label="导入原文字幕" type="file" accept=".srt,.vtt,.ass,.ssa" hidden onChange={e => { const f = e.target.files?.[0]; if (f) void execute(() => importTrack(f, 'source')); e.target.value = ''; }} /></label>
          <label className="button">中文<input aria-label="导入中文字幕" type="file" accept=".srt,.vtt,.ass,.ssa" hidden onChange={e => { const f = e.target.files?.[0]; if (f) void execute(() => importTrack(f, 'target')); e.target.value = ''; }} /></label></div>
        {!!subtitleChoices.length && <div className="existing-subtitles"><button onClick={() => setShowChoices(!showChoices)}>发现 {subtitleChoices.length} 份已有字幕 · {showChoices ? '收起' : '选择复用'}</button>{showChoices && <div>{subtitleChoices.map(track => <button disabled={busy} title={track.path} key={track.path} onClick={() => void execute(async () => { await save(); setVideo(await api<Video>('/videos/' + video.id + '/subtitles', 'POST', track)); })}>{track.role === 'target' ? '中文' : '原文'} · {track.name}</button>)}</div>}</div>}
        {video.available_tracks.length > 2 && <div className="track-choices">{(['source','target'] as const).map(role => <label key={role}>{role === 'source' ? '原文轨道' : '译文轨道'}<select aria-label={role === 'source' ? '选择原文轨道' : '选择译文轨道'} value={role} onChange={e => void execute(async () => { await save(); setVideo(await api<Video>('/videos/' + video.id + '/select-track', 'POST', { role, key: e.target.value })); })}>{video.available_tracks.filter(t => t.key === role || t.key.startsWith('available-')).map(t => <option value={t.key} key={t.key}>{t.language} · {t.name}</option>)}</select></label>)}</div>}
        <div className="transcript-options"><div className="segmented">{(['source','target','bilingual','off'] as Mode[]).map((mode, i) => <button key={mode} className={video.progress.mode === mode ? 'chosen' : ''} onClick={() => preference({ mode })}>{[sourceLabel,targetLabel,'双语','隐藏'][i]}</button>)}</div><button className={follow ? 'following' : ''} onClick={() => { setFollow(true); setQuery(''); }}><Crosshair size={14}/>{follow ? '正在跟随' : '回到当前'}</button></div>
        <div ref={transcript} className="transcript" onWheel={() => setFollow(false)} onTouchStart={() => setFollow(false)} onPointerDown={() => setFollow(false)} onKeyDown={e => { if (['ArrowDown','ArrowUp','PageDown','PageUp'].includes(e.key)) setFollow(false); }}>
          {video.progress.mode !== 'off' && filtered.slice(page * 120, (page + 1) * 120).map(c => <div ref={c.id === currentId ? activeRow : undefined} key={c.id} className={'cue ' + (current.some(a => a.id === c.id) ? 'active ' : '') + (selected?.id === c.id ? 'cue-selected' : '')}>
            <button className="cue-time" onClick={() => { setLoop(null); seek(c.start); }}><time>{time(c.start)}</time></button><button className="cue-content" onClick={() => setSelected(c)}>{caption(c, video.progress.mode)}</button><button aria-label={'循环 ' + time(c.start)} className="cue-loop" onClick={() => { setLoop(c); seek(c.start); void player.current?.play().catch(() => {}); }}><Repeat size={14}/></button></div>)}
          {!video.cues.length && <div className="empty"><Subtitles size={26}/><h3>准备好字幕，理解更多内容</h3><p>导入 SRT、VTT 或 ASS 文件。视频和笔记保存在本机。</p></div>}</div>
        {pageCount > 1 && <div className="transcript-pages"><button disabled={page === 0} onClick={() => { setFollow(false); setPage(p => Math.max(0, p - 1)); }}>上一页</button><span>{page + 1} / {pageCount} · {filtered.length} 条字幕</span><button disabled={page >= pageCount - 1} onClick={() => { setFollow(false); setPage(p => Math.min(pageCount - 1, p + 1)); }}>下一页</button></div>}
        {selected && <div className="selection-bar"><span>已选择 {time(selected.start)} · {selected.text.slice(0, 60)}</span><button onClick={() => seek(selected.start)}>定位原片</button><button aria-label="取消选句" onClick={() => setSelected(null)}><X size={15}/></button></div>}
      </> : <div className="welcome"><div className="welcome-icon"><BookOpen size={42}/></div><div className="eyebrow">看懂每一段，留下每一个收获</div><h1>把视频变成你的学习资料</h1><p>双语字幕、随时提问、时间戳笔记。<br/>从一个已经下载好的视频开始。</p><button className="primary" onClick={() => setImporting(true)}><FolderPlus size={18}/>导入第一个视频</button></div>}</section>
      {video && <LearningPanel key={video.id} video={video} position={position} selected={selected} providers={providers} seek={seek}
        refresh={async () => { await save(); const updated = await api<Video>('/videos/' + video.id); setVideo(updated); await refresh(); }} report={setError}/>}
    </main>
    {importing && <div className="modal-backdrop"><form className="modal import-modal" onSubmit={e => { e.preventDefault(); void execute(importChosen); }}><div className="modal-title"><h2>导入学习资料</h2><button type="button" aria-label="关闭导入" onClick={() => setImporting(false)}><X size={20}/></button></div><div className="segmented import-mode"><button type="button" className={importMode === 'project' ? 'chosen' : ''} onClick={() => { setImportMode('project'); setNeedsSelection(false); }}>视频工程（目录）</button><button type="button" className={importMode === 'file' ? 'chosen' : ''} onClick={() => { setImportMode('file'); setNeedsSelection(false); }}>单个视频 / 下载记录</button></div>
      {error && <p className="warning" role="alert">{error}</p>}
      {importMode === 'project' ? <><p>把一个视频和几份字幕放在同一个文件夹，或把字幕放进 subtitles 子文件夹。导入时自动识别语言并加载全部字幕。</p><label>工程目录<input aria-label="工程目录" autoFocus value={folder} placeholder="F:\学习\一节课程" required onChange={e => { setFolder(e.target.value); setNeedsSelection(false); }}/></label>{needsSelection && <p className="warning">目录中有多个视频，请先选择本次学习的视频；只关联同名字幕。</p>}</> : <><p>本地视频直接引用；下载记录会自动整理为工程并加载对应字幕，保留原文件。</p><label>视频路径<input aria-label="视频路径" autoFocus value={path} placeholder="F:\videos\课程.mp4" required onChange={e => setPath(e.target.value)} /></label><details><summary>从视频目录或剧集目录选择</summary><div className="folder-scan"><input aria-label="视频目录" value={folder} placeholder="目录完整路径" onChange={e => setFolder(e.target.value)}/><button type="button" disabled={busy || !folder} onClick={() => void execute(async () => setImportChoices((await api<{ videos: typeof importChoices }>('/imports/directory', 'POST', { path: folder })).videos))}>扫描目录</button></div></details></>}
      {(importMode === 'file' || needsSelection) && !!importChoices.length && <div className="import-choices">{importChoices.map(choice => <button type="button" className={path === choice.path ? 'chosen' : ''} key={choice.path} title={choice.path} onClick={() => setPath(choice.path)}><Play size={13}/>{choice.title}</button>)}</div>}
      <button className="primary" disabled={busy || (needsSelection && !path)}>{busy ? '正在读取…' : importMode === 'project' ? '打开工程并自动加载字幕' : '加入学习资料'}</button></form></div>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<App />);
