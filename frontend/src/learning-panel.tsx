import React, { useEffect, useRef, useState } from 'react';
import { ArrowUp, BookmarkPlus, Check, ChevronRight, Download, Globe, ListTree, MessageCircle, NotebookPen, Settings2, Square, Sparkles, Pencil, Trash2 } from 'lucide-react';
import { api, activeJob, time, Video, Cue, Providers, Study, Job, Message, Note, Citation, WebSource } from './learning-api';

type Props = { video: Video; position: number; selected: Cue | null; providers: Providers;
  seek: (value: number) => void; refresh: () => Promise<void>; report: (message: string) => void };

export function LearningPanel({ video, position, selected, providers, seek, refresh, report }: Props) {
  const [tab, setTab] = useState('chat');
  const [study, setStudy] = useState<Study>({ messages: [], notes: [], outline: [], active_job: null });
  const [job, setJob] = useState<Job | null>(null);
  const [question, setQuestion] = useState('');
  const [provider, setProvider] = useState(localStorage.getItem('videohub.learning.provider') === 'kimi' ? 'kimi' : 'deepseek');
  const [models, setModels] = useState<Record<string, string>>(() => { try { const value = JSON.parse(localStorage.getItem('videohub.learning.models') || '{}'); return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; } catch { return {}; } });
  const [scope, setScope] = useState('full');
  const [settings, setSettings] = useState(false);
  const [search, setSearch] = useState(false);
  const [searchProvider, setSearchProvider] = useState('deepseek');
  const [searchQuery, setSearchQuery] = useState('');
  const [starting, setStarting] = useState(false);
  const [noteText, setNoteText] = useState('');
  const [noteTags, setNoteTags] = useState('');
  const [editing, setEditing] = useState<Note | null>(null);
  const [noteBusy, setNoteBusy] = useState(false);
  const [whisperModel, setWhisperModel] = useState('small');
  const tail = useRef<HTMLDivElement>(null);
  const currentId = useRef(video.id); currentId.current = video.id;
  const model = models[provider] || providers[provider]?.model || '';
  const working = activeJob(job) || starting;
  const reload = async () => {
    const id = video.id;
    const value = await api<Study>('/videos/' + id + '/study');
    if (currentId.current === id) { setStudy(value); if (value.active_job) setJob(value.active_job); }
  };
  useEffect(() => { setStudy({ messages: [], notes: [], outline: [], active_job: null }); setJob(null); setQuestion(''); void reload().catch(e => report(e.message)); }, [video.id, video.subtitle_version]);
  useEffect(() => {
    if (!job || !activeJob(job)) return;
    const stream = new EventSource('/api/learning/jobs/' + job.id + '/events');
    let disposed = false;
    let finished = false;
    let fallback: ReturnType<typeof setInterval> | undefined;
    const receive = (next: Job) => {
      if (disposed || finished) return;
      setJob(next);
      if (!activeJob(next)) {
        finished = true;
        stream.close();
        if (fallback) clearInterval(fallback);
        void reload().catch(e => report(e.message));
        if (next.status === 'finished') void refresh().catch(e => report(e.message));
      }
    };
    stream.onmessage = event => receive(JSON.parse(event.data));
    stream.onerror = () => { stream.close(); if (!fallback && !disposed && !finished) fallback = setInterval(() => { void api<Job>('/jobs/' + job.id).then(receive).catch(e => { if (!disposed) report(e.message); }); }, 1500); };
    return () => { disposed = true; stream.close(); if (fallback) clearInterval(fallback); };
  }, [job?.id]);
  useEffect(() => { const box = tail.current?.parentElement; if (box) box.scrollTop = box.scrollHeight; }, [study.messages.length, job?.text]);
  const start = async (kind: string, text = question) => {
    setStarting(true);
    try {
      const data = { provider, model, kind, whisper_model: whisperModel, question: text, time: position, scope,
        cue_ids: selected ? [selected.id] : [], search, search_provider: searchProvider, search_query: searchQuery };
      const value = await api<Job>('/videos/' + video.id + (kind === 'chat' ? '/chat' : '/prepare'), 'POST', data);
      setJob(value); if (kind === 'chat') { setQuestion(''); await reload(); }
    } catch (e) { report((e as Error).message); } finally { setStarting(false); }
  };
  const stop = () => job && api<Job>('/jobs/' + job.id + '/cancel', 'POST', {}).then(setJob).catch(e => report(e.message));
  const noteAction = async (action: () => Promise<unknown>) => {
    setNoteBusy(true);
    try { await action(); await reload(); } catch (e) { report((e as Error).message); } finally { setNoteBusy(false); }
  };
  const saveNote = () => noteAction(async () => {
    const endpoint = '/videos/' + video.id + '/notes' + (editing ? '/' + editing.id : '');
    await api(endpoint, editing ? 'PATCH' : 'POST', { text: noteText,
      start: editing ? editing.start : selected?.start ?? position,
      end: editing ? editing.end : selected?.end ?? position,
      cue_ids: !editing && selected ? [selected.id] : [], version: editing?.version,
      tags: noteTags.split(/[,，]/).map(t => t.trim()).filter(Boolean) });
    setNoteText(''); setNoteTags(''); setEditing(null);
  });
  const answer = (message: Message) => <article key={message.id} className={'message ' + message.role}>
    <div className="message-label">{message.role === 'user' ? '你' : '学习助教'}<small>{time(message.time)}{message.model && ' · ' + message.model}</small></div>
    <div className="message-text"><GroundedText text={message.text} citations={message.citations || []} sources={message.sources || []} seek={seek}/></div>
    {message.status !== 'finished' && <p className="warning">{message.status === 'cancelled' ? '已停止，回复不完整' : '回复未完成'}</p>}
    {message.subtitle_version !== video.subtitle_version && <p className="warning">字幕已更新，此回答基于旧版字幕。</p>}
    <div className="citation-list">{message.citations?.map(c => <button title={c.text} key={c.id} onClick={() => seek(c.start)}><PlayCitation/>{time(c.start)}—{time(c.end)}</button>)}</div>
    {message.sources?.map(s => <a className="web-source" href={s.url} key={s.id} target="_blank" rel="noopener noreferrer"><Globe size={13}/>{s.title}<small>{s.level}</small></a>)}
    {message.warnings?.map((w, i) => <p className="warning" key={i}>{w}</p>)}
    {message.usage?.total_tokens != null && <small className="usage">本次回答 {message.usage.total_tokens} tokens（不含结构分析与搜索）</small>}
    {message.role === 'assistant' && message.status === 'finished' && <button className="save-answer" disabled={noteBusy} onClick={() => void noteAction(async () => { await api('/videos/' + video.id + '/notes', 'POST', { answer_id: message.id }); setTab('notes'); })}><BookmarkPlus size={12}/>存为笔记</button>}
  </article>;
  return <aside className="study-panel">
    <div className="panel-tabs">{[['chat','AI 对话',MessageCircle],['notes','笔记',NotebookPen],['outline','大纲',ListTree]].map(([id,label,Icon]) => {
      const TabIcon = Icon as typeof MessageCircle; return <button key={String(id)} className={tab === id ? 'current-tab' : ''} onClick={() => setTab(String(id))}><TabIcon size={16}/>{String(label)}</button>;
    })}</div>
    <div className="model-bar"><span className={'status-dot ' + (providers[provider]?.configured ? 'ready' : '')}/><select aria-label="AI 服务" value={provider} onChange={e => { setProvider(e.target.value); localStorage.setItem('videohub.learning.provider', e.target.value); }}><option value="deepseek">DeepSeek</option><option value="kimi">Kimi</option></select><button aria-label="模型设置" onClick={() => setSettings(!settings)}><Settings2 size={15}/></button></div>
    {settings && <div className="model-settings"><label>模型名称<input aria-label="模型名称" value={model} onChange={e => { const next = { ...models, [provider]: e.target.value }; setModels(next); localStorage.setItem('videohub.learning.models', JSON.stringify(next)); }}/></label><p>密钥从本机 .env 读取。DeepSeek：DEEPSEEK_API_KEY；Kimi：MOONSHOT_API_KEY。修改后重启服务。</p><p>启用 AI 会向所选服务发送问题和所需字幕；启用联网只向搜索服务发送你填写的检索词。</p></div>}
    {!providers[provider]?.configured && <div className="configuration-hint">{providers[provider]?.error || (provider === 'deepseek' ? 'DeepSeek' : 'Kimi') + ' 尚未配置密钥'}。播放、字幕和手动笔记仍可使用。</div>}
    {job && <div className={'job-card ' + job.status}><div><Sparkles size={14}/><span>{job.message}</span>{activeJob(job) && <button onClick={() => void stop()}><Square size={11}/>停止</button>}</div><progress max="100" value={job.progress}/>{job.warnings?.map(w => <p className="warning" key={w}>{w}</p>)}</div>}
    {tab === 'chat' && <><div className="messages">{!study.messages.length && !job?.text && <div className="chat-welcome"><div className="assistant-symbol"><Sparkles size={22}/></div><h3>不明白的地方，随时问</h3><p>助教会结合当前字幕与视频结构回答，<br/>引用可以直接回到原片。</p><div className="quick-prompts">{['这里是什么意思？','用一个例子解释当前概念','梳理视频的主要观点'].map(q => <button disabled={working} key={q} onClick={() => void start('chat', q)}>{q}<ChevronRight size={14}/></button>)}</div></div>}
      {study.messages.map(answer)}
      {job?.kind === 'chat' && activeJob(job) && job.text && <article className="message assistant streaming"><div className="message-label">学习助教 <span className="streaming-dot"/></div><div className="message-text">{job.text.replace(/\[cue:[^\]]+\]/g, '')}</div></article>}
      <div ref={tail}/></div>
      <form className="chat-composer" onSubmit={e => { e.preventDefault(); void start('chat'); }}>
        <div className="context-label"><span>当前 {time(position)}</span>{selected && <span>已选一句字幕</span>}</div>
        <label className="scope"><input type="checkbox" checked={scope === 'full'} onChange={e => setScope(e.target.checked ? 'full' : 'current')}/>允许引用全片 <small>关闭后仅看至当前进度</small></label>
        <textarea aria-label="向视频提问" rows={3} placeholder={selected ? '围绕选中的这句话提问…' : '提问，或点击左侧字幕选择一句话…'} value={question} onChange={e => setQuestion(e.target.value)} maxLength={1500}/>
        <div className="composer-actions"><label className={'search-toggle ' + (search ? 'enabled' : '')}><input type="checkbox" checked={search} onChange={e => setSearch(e.target.checked)}/><Globe size={14}/>联网补充</label><button className="primary send" aria-label="发送问题" disabled={working || !question.trim()}><ArrowUp size={18}/></button></div>
        {search && <div className="search-config"><select aria-label="搜索服务" value={searchProvider} onChange={e => setSearchProvider(e.target.value)}><option value="deepseek">DeepSeek 搜索</option><option value="kimi">Kimi 搜索</option></select><input aria-label="联网检索词" placeholder="填写要搜索的概念（最多128字）" maxLength={128} value={searchQuery} onChange={e => setSearchQuery(e.target.value)}/></div>}
      </form></>}
    {tab === 'outline' && <div className="outline"><div className="panel-section-head"><h3>视频章节</h3><button disabled={working} onClick={() => void start('analysis')}><Sparkles size={13}/>生成大纲</button></div>
      {(job?.outline || study.outline).map((c, i) => <button className="chapter" key={i} onClick={() => seek(c.start)}><time>{time(c.start)}</time><strong>{c.title}</strong><p>{c.summary}</p></button>)}
      {!study.outline.length && !job?.outline?.length && <p className="muted">生成后可按章节跳转。长视频将逐段分析全部字幕，完成后保留缓存。</p>}
      <button className="translate-button" disabled={working} onClick={() => void start('translation')}><Check size={14}/>{video.has_target ? '重新生成中文字幕' : '生成中文字幕'}</button>
      {!video.has_source && <div className="prepare-transcription"><p className="muted">没有原文字幕？可使用本地 Whisper 生成，已有字幕时无需重复转写。</p><label>Whisper 模型 <select aria-label="Whisper模型" value={whisperModel} onChange={e => setWhisperModel(e.target.value)}>{['tiny','base','small','medium','large'].map(m => <option key={m}>{m}</option>)}</select></label><button disabled={working} onClick={() => void start('transcription')}>生成原文字幕</button></div>}
      {!video.browser_ready && !video.preview && <div className="prepare-transcription"><p className="muted">原视频编码可能不兼容浏览器。生成预览会占用额外磁盘空间，保留原片。</p><button disabled={working} onClick={() => void start('preview')}>生成浏览器预览</button></div>}
    </div>}
    {tab === 'notes' && <div className="notes-panel"><div className="panel-section-head"><h3>我的笔记 <small>{study.notes.length}</small></h3><a className="button" href={'/api/learning/videos/' + video.id + '/export'} download><Download size={13}/>导出 Markdown</a></div>
      <form className="note-editor" onSubmit={e => { e.preventDefault(); void saveNote(); }}><div className="context-label">{editing ? '编辑笔记 · ' + time(editing.start) : selected ? '摘录选中字幕 · ' + time(selected.start) : '记录当前时间 · ' + time(position)}</div>
        {selected && !editing && <blockquote>{selected.text}</blockquote>}
        <textarea aria-label="笔记正文" placeholder="记下理解、疑问或一个新的想法…" rows={4} value={noteText} onChange={e => setNoteText(e.target.value)} maxLength={30000}/>
        <input aria-label="笔记标签" placeholder="标签，用逗号分隔（可选）" value={noteTags} onChange={e => setNoteTags(e.target.value)}/>
        <div className="note-editor-actions">{editing && <button type="button" onClick={() => { setEditing(null); setNoteText(''); setNoteTags(''); }}>取消编辑</button>}<button className="primary" disabled={noteBusy || (!noteText.trim() && !selected)}><Check size={13}/>{editing ? '保存修改' : '保存笔记'}</button></div></form>
      {!study.notes.length && <p className="muted">在这里记录想法，或把助教的回答存为笔记。每一条都能回到视频。</p>}
      {study.notes.map(note => <article className="note" key={note.id}><div className="note-head"><button className="note-time" onClick={() => seek(note.start)}><PlayCitation/>{time(note.start)}</button><button aria-label="编辑笔记" onClick={() => { setEditing(note); setNoteText(note.text); setNoteTags(note.tags.join(', ')); }}><Pencil size={12}/></button><button disabled={noteBusy} aria-label="删除笔记" onClick={() => void noteAction(() => api('/videos/' + video.id + '/notes/' + note.id, 'DELETE'))}><Trash2 size={12}/></button></div>
        <p><GroundedText text={note.text} citations={note.citations} sources={note.sources} seek={seek}/></p>
        {note.citations.map(c => <button className="note-excerpt" key={c.id} onClick={() => seek(c.start)}>{time(c.start)} · {c.text}</button>)}
        {note.sources.map(s => <a className="web-source" key={s.id} href={s.url} target="_blank" rel="noopener noreferrer"><Globe size={12}/>{s.title}</a>)}
        {note.subtitle_version !== video.subtitle_version && <small className="warning">字幕已更新，摘录保留原版本。</small>}
        <div className="note-tags">{note.tags.map(t => <span key={t}>{t}</span>)}</div><small className="usage">{new Date(note.created).toLocaleString()}</small></article>)}
    </div>}
  </aside>;
}
function PlayCitation() { return <span className="citation-triangle">▶</span>; }

function GroundedText({text,citations,sources,seek}:{text:string;citations:Citation[];sources:WebSource[];seek:(t:number)=>void}) {
  return <>{text.split(/(\[cue:[^\]]+\]|\[web:[^\]]+\])/g).map((part,i) => {
    const cueMatch = /^\[cue:([^\]]+)\]$/.exec(part);
    if (cueMatch) { const cue = citations.find(c => c.id === cueMatch[1]); return cue ? <button className="inline-citation" title={cue.text} key={i} onClick={() => seek(cue.start)}>{time(cue.start)}</button> : null; }
    const webMatch = /^\[web:([^\]]+)\]$/.exec(part);
    if (webMatch) { const source = sources.find(s => s.id === webMatch[1]); return source ? <a className="inline-source" title={source.title} key={i} href={source.url} target="_blank" rel="noopener noreferrer">[来源 {source.id.replace('W','')}]</a> : null; }
    return <React.Fragment key={i}>{part.split(/(\*\*[^*]+\*\*)/g).map((text,j) => text.startsWith('**') && text.endsWith('**') ? <strong key={j}>{text.slice(2,-2)}</strong> : <React.Fragment key={j}>{text}</React.Fragment>)}</React.Fragment>;
  })}</>;
}
