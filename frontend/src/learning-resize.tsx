import React, { useEffect, useRef, useState } from 'react';

type Sizes = { library: number; assistant: number; player: number | null };
type Part = keyof Sizes;
const defaults: Sizes = { library: 220, assistant: 360, player: null };
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

function savedSizes(): Sizes {
  try {
    const value = JSON.parse(localStorage.getItem('videohub.learning.sizes') || '{}');
    const valid = (key: Part, min: number, max: number) => typeof value?.[key] === 'number' && Number.isFinite(value[key])
      ? clamp(value[key], min, max) : defaults[key];
    return { library: valid('library', 160, 420)!, assistant: valid('assistant', 260, 560)!, player: valid('player', 60, 1200) };
  } catch { return { ...defaults }; }
}

export function useLearningSizes(lesson: React.RefObject<HTMLElement>, assistantHidden: boolean, ratio: number) {
  const [sizes, setSizes] = useState(savedSizes);
  const [viewport, setViewport] = useState({ width: window.innerWidth, height: window.innerHeight });
  const [contentWidth, setContentWidth] = useState(640);
  useEffect(() => {
    const resize = () => setViewport({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);
  useEffect(() => {
    const element = lesson.current;
    if (!element) return;
    const measure = () => {
      const style = getComputedStyle(element);
      setContentWidth(Math.max(1, element.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [lesson]);
  useEffect(() => {
    try { localStorage.setItem('videohub.learning.sizes', JSON.stringify(sizes)); } catch { /* Optional preference storage. */ }
  }, [sizes]);
  const libraryMax = Math.max(160, Math.min(420, viewport.width * .28));
  const assistantMax = Math.max(260, Math.min(560, viewport.width * .36));
  const playerMax = Math.max(1, Math.min(1200, viewport.height * .85, contentWidth / ratio));
  const playerMin = Math.min(120, playerMax);
  const change = (part: Part, value: number) => setSizes(previous => ({ ...previous, [part]: Math.round(value) }));
  const reset = (part: Part) => setSizes(previous => ({ ...previous, [part]: defaults[part] }));
  return {
    library: clamp(sizes.library, 160, libraryMax), libraryMax,
    assistant: clamp(sizes.assistant, 260, assistantMax), assistantMax,
    player: clamp(sizes.player ?? viewport.height * (assistantHidden ? .68 : .46), playerMin, playerMax), playerMin, playerMax,
    change, reset,
  };
}

type HandleProps = {
  label: string; controls: string; className: string; axis: 'x' | 'y';
  value: number; min: number; max: number; direction?: 1 | -1;
  change: (value: number) => void; reset: () => void;
};

export function ResizeHandle({ label, controls, className, axis, value, min, max, direction = 1, change, reset }: HandleProps) {
  const drag = useRef<{ pointer: number; start: number; value: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const apply = (next: number) => change(clamp(next, min, max));
  const finish = (event: React.PointerEvent<HTMLDivElement>) => {
    if (drag.current?.pointer !== event.pointerId) return;
    drag.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  return <div role="separator" tabIndex={0} aria-label={label} aria-controls={controls}
    aria-orientation={axis === 'x' ? 'vertical' : 'horizontal'} aria-valuemin={Math.round(min)} aria-valuemax={Math.round(max)}
    aria-valuenow={Math.round(value)} aria-valuetext={Math.round(value) + ' 像素'}
    title={label + '：拖动调节，双击或 Enter 恢复默认，方向键微调'}
    className={'layout-resizer ' + className + (dragging ? ' is-dragging' : '')}
    onDoubleClick={reset}
    onPointerDown={event => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.currentTarget.focus({ preventScroll: true });
      event.currentTarget.setPointerCapture(event.pointerId);
      drag.current = { pointer: event.pointerId, start: axis === 'x' ? event.clientX : event.clientY, value };
      setDragging(true);
    }}
    onPointerMove={event => {
      if (drag.current?.pointer === event.pointerId) apply(drag.current.value + ((axis === 'x' ? event.clientX : event.clientY) - drag.current.start) * direction);
    }}
    onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={() => { drag.current = null; setDragging(false); }}
    onKeyDown={event => {
      const step = event.shiftKey ? 40 : 12;
      let next: number | undefined;
      if (event.key === (axis === 'x' ? 'ArrowLeft' : 'ArrowUp')) next = value - step * direction;
      if (event.key === (axis === 'x' ? 'ArrowRight' : 'ArrowDown')) next = value + step * direction;
      if (event.key === 'Home') next = min;
      if (event.key === 'End') next = max;
      if (event.key === 'Enter') { event.preventDefault(); reset(); }
      if (next !== undefined) { event.preventDefault(); apply(next); }
    }}><span aria-hidden="true"/></div>;
}
