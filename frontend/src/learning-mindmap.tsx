import React, { useEffect, useRef, useState } from 'react';
import { Download, Maximize, Minus, Plus } from 'lucide-react';
import { Mindmap, MindmapNode, time } from './learning-api';

export const LearningMindmap = React.memo(function LearningMindmap({ value, videoId, seek }: { value: Mindmap; videoId: string; seek: (t: number) => void }) {
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [zoom, setZoom] = useState(1);
  const [expanded, setExpanded] = useState(false);
  const dialog = useRef<HTMLElement>(null);
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => { setClosed(new Set()); setZoom(1); }, [value.created]);
  useEffect(() => {
    if (!expanded) return;
    dialog.current?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setExpanded(false); }
      if (event.key === 'Tab') {
        const items = [...(dialog.current?.querySelectorAll<HTMLElement>('button,a[href],[tabindex="0"]') || [])];
        const first = items[0], last = items[items.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    window.addEventListener('keydown', escape);
    return () => {
      window.removeEventListener('keydown', escape);
      container.current?.querySelector<HTMLElement>('[aria-label="展开脑图大图"]')?.focus();
    };
  }, [expanded]);
  const toggle = (id: string) => setClosed(before => {
    const next = new Set(before); if (next.has(id)) next.delete(id); else next.add(id); return next;
  });
  const branch = (node: MindmapNode, depth: number): React.ReactNode => <li key={node.id}>
    <div className={'mindmap-node depth-' + Math.min(depth, 2)}>
      <div className="mindmap-node-head">{!!node.children.length && <button type="button" aria-label={(closed.has(node.id) ? '展开' : '折叠') + node.label} aria-expanded={!closed.has(node.id)} onClick={() => toggle(node.id)}>{closed.has(node.id) ? '+' : '−'}</button>}<strong>{node.label}</strong></div>
      {node.summary && <p>{node.summary}</p>}
      <button className="mindmap-time" title="回到对应字幕段落" onClick={() => seek(node.start)}>{time(node.start)}—{time(node.end)} ↗</button>
    </div>
    {!!node.children.length && !closed.has(node.id) && <ul>{node.children.map(child => branch(child, depth + 1))}</ul>}
  </li>;
  const figure = <>
    <div className="mindmap-tools"><button aria-label="缩小脑图" onClick={() => setZoom(z => Math.max(.5, +(z - .1).toFixed(1)))}><Minus size={13}/></button><button onClick={() => setZoom(1)} title="恢复100%">{Math.round(zoom * 100)}%</button><button aria-label="放大脑图" onClick={() => setZoom(z => Math.min(1.8, +(z + .1).toFixed(1)))}><Plus size={13}/></button><button onClick={() => setClosed(new Set())}>展开全部</button><button onClick={() => setClosed(new Set([value.root.id]))}>折叠全部</button><button aria-label={expanded ? '关闭脑图大图' : '展开脑图大图'} onClick={() => setExpanded(v => !v)}><Maximize size={13}/>{expanded ? '关闭大图' : '查看大图'}</button></div>
    <div className="mindmap-scroll" tabIndex={0} role="region" data-playback-navigation="local" aria-label="视频脑图，可横向滚动">
      <ul className="mindmap-tree" style={{ zoom } as React.CSSProperties}>{branch(value.root, 0)}</ul>
    </div>
  </>;
  return <div ref={container}>
    <p className="mindmap-explanation"><strong>{value.organization === 'logical' ? '逻辑脑图' : '主题图'}</strong> · {value.explanation}</p>
    <p className="muted">{value.basis} 已处理 {value.coverage.parts} 段 / {value.coverage.cues} 条字幕。</p>
    <div className="mindmap-exports"><a className="button" href={'/api/learning/videos/' + videoId + '/mindmap/export?format=markdown'} download><Download size={12}/>Markdown</a><a className="button" href={'/api/learning/videos/' + videoId + '/mindmap/export?format=json'} download><Download size={12}/>JSON</a></div>
    {!expanded && figure}
    {expanded && <div className="mindmap-dialog-backdrop"><section ref={dialog} tabIndex={-1} className="mindmap-dialog" role="dialog" aria-modal="true" aria-label="视频脑图大图"><h3>{value.root.label}</h3>{figure}</section></div>}
  </div>;
});
