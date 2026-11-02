import type { Mode } from './learning-api';

export type PlaybackShortcut = 'fullscreen' | 'faster' | 'slower' | 'subtitles' | 'play' | 'back' | 'forward' | 'mute';
type ShortcutEvent = Pick<KeyboardEvent, 'key' | 'code' | 'ctrlKey' | 'altKey' | 'metaKey' | 'repeat' | 'isComposing' | 'keyCode' | 'timeStamp' | 'defaultPrevented' | 'target' | 'preventDefault' | 'stopPropagation'>;
export type ShortcutCheck = { action?: PlaybackShortcut; reason: string; suppressed?: boolean };
export type ShortcutRepeatState = { action?: PlaybackShortcut; at?: number };
const repeatable = new Set<PlaybackShortcut>(['faster', 'slower', 'back', 'forward']);
const repeatInterval = 180;

// The HTML bootstrap owns the earliest page listener. Hand the current App
// callback to it instead of installing a second, later keyboard listener.
export function bindPlaybackShortcuts(handler: (event: KeyboardEvent) => void, host: Window = window): () => void {
  const binding = { handler, connected: false };
  const dispatch = (name: string) => {
    const event = host.document.createEvent('CustomEvent');
    event.initCustomEvent(name, false, false, binding);
    host.document.dispatchEvent(event);
  };
  dispatch('videohub:shortcut-bind');
  if (!binding.connected) host.addEventListener('keydown', handler, { capture: true, passive: false });
  return () => {
    if (binding.connected) dispatch('videohub:shortcut-unbind');
    else host.removeEventListener('keydown', handler, true);
  };
}

export function inspectPlaybackShortcut(event: ShortcutEvent, blocked = false): ShortcutCheck {
  if (blocked) return { reason: '导入窗口打开中' };
  if (event.defaultPrevented) return { reason: '按键已被其他处理器阻止' };
  if (event.ctrlKey || event.altKey || event.metaKey) return { reason: '正在使用组合键' };
  const target = event.target as HTMLElement | null;
  if (target?.isContentEditable || target?.closest?.('textarea,[contenteditable]:not([contenteditable="false"]),[role="textbox"],[role="combobox"],[role="spinbutton"],[role="dialog"],[aria-modal="true"],dialog[open]')) return { reason: '焦点在文字输入区或弹窗' };
  const input = target?.closest?.('input') as HTMLInputElement | null;
  if (input && !['range', 'checkbox', 'radio', 'button', 'submit', 'reset'].includes(input.type)) return { reason: '焦点在文字或数值输入框' };
  // Keep Space activation and arrow navigation available to focused controls.
  if ([' ', 'ArrowLeft', 'ArrowRight'].includes(event.key) && target?.closest?.('input,select,button,a,summary,[role="button"],[role="tab"],[role="separator"],[role="slider"],[data-playback-navigation="local"]')) return { reason: '保留控件自身的空格或方向键' };
  // On non-editable surfaces Windows IMEs may report Process/229 instead of
  // a letter. Physical key codes still identify the intended player command.
  const physicalLetters: Record<string, PlaybackShortcut> = {
    KeyF: 'fullscreen', KeyC: 'faster', KeyX: 'slower', KeyS: 'subtitles', KeyM: 'mute',
  };
  const actions: Record<string, PlaybackShortcut> = {
    f: 'fullscreen', c: 'faster', x: 'slower', s: 'subtitles',
    ' ': 'play', ArrowLeft: 'back', ArrowRight: 'forward', m: 'mute',
  };
  const physical = physicalLetters[event.code];
  const action = event.isComposing || event.keyCode === 229
    ? physical
    : physical || actions[event.key.length === 1 ? event.key.toLowerCase() : event.key];
  if (!action) return { reason: '未识别为视频快捷键' };
  if (event.repeat && !repeatable.has(action)) return { action, reason: '按住时不重复切换；松开后可再次按下', suppressed: true };
  return { action, reason: event.repeat ? '已识别长按连续调节' : '已识别快捷键' };
}

export function handlePlaybackShortcut(event: ShortcutEvent, run: (action: PlaybackShortcut) => void, blocked = false, repeatState?: ShortcutRepeatState): boolean {
  const { action, suppressed } = inspectPlaybackShortcut(event, blocked);
  if (!action) return false;
  event.preventDefault();
  event.stopPropagation();
  // Consume skipped repeats too, so the native video controls cannot apply
  // their own faster repeat or toggle playback/fullscreen a second time.
  if (suppressed) return true;
  if (event.repeat && repeatState?.action === action && repeatState.at !== undefined
    && event.timeStamp >= repeatState.at && event.timeStamp - repeatState.at < repeatInterval) return true;
  if (repeatState) { repeatState.action = action; repeatState.at = event.timeStamp; }
  run(action);
  return true;
}

export const stepPlaybackRate = (rate: number, delta: number) => Math.min(3, Math.max(.25, Math.round((rate + delta) * 100) / 100));
export const playbackRates = (current: number) => [...new Set([.25, .5, .75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3, current])].sort((a, b) => a - b);

export function toggleSubtitleMode(current: Mode, previous: Mode | undefined, hasSource: boolean, hasTarget: boolean): Mode {
  if (current !== 'off') return 'off';
  if (previous && previous !== 'off') return previous;
  return hasSource && hasTarget ? 'bilingual' : hasTarget ? 'target' : 'source';
}
