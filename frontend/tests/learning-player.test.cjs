const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const ts = require('typescript');
const { JSDOM } = require('jsdom');

let dom, root, act, media;
const savedProgress = [];
const detail = {
  id: 'fixture', title: 'Synthetic lesson', duration: 60, width: 1280, height: 720,
  path: '/synthetic.mp4', source_url: '', media_url: '/synthetic.mp4', browser_ready: true,
  progress: { time: 10, rate: 1, mode: 'bilingual', overlay: 'bilingual', font: 20 },
  has_source: true, has_target: true, subtitle_version: 'v1', subtitle_warnings: [],
  tracks: { source: { language: 'en' }, target: { language: 'zh-CN' } }, available_tracks: [],
  cues: [{ id: 's1', start: 0, end: 60, text: 'Hello.', translation: '你好。' }],
  playback_cues: { source: [{ id: 's1', start: 0, end: 60, text: 'Hello.' }], target: [{ id: 't1', start: 0, end: 60, text: '你好。' }] },
};

before(async () => {
  // Local DOM emulation only: never navigate or fetch an actual application page.
  dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'https://unit.test/learn?video=fixture' });
  for (const name of ['window', 'document', 'HTMLElement', 'Event', 'KeyboardEvent', 'localStorage', 'location', 'history']) globalThis[name] = dom.window[name];
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: dom.window.navigator });
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.getComputedStyle = () => ({ paddingLeft: '24px', paddingRight: '24px' });
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  Object.defineProperty(dom.window.HTMLElement.prototype, 'clientWidth', { get: () => 1100 });
  dom.window.HTMLElement.prototype.scrollBy = () => {};
  dom.window.HTMLElement.prototype.requestFullscreen = async function () {
    Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: this });
    document.dispatchEvent(new Event('fullscreenchange'));
  };
  document.exitFullscreen = async () => {
    Object.defineProperty(document, 'fullscreenElement', { configurable: true, value: null });
    document.dispatchEvent(new Event('fullscreenchange'));
  };
  const state = new WeakMap();
  Object.defineProperty(dom.window.HTMLMediaElement.prototype, 'paused', { get() { return state.get(this) !== 'playing'; } });
  dom.window.HTMLMediaElement.prototype.play = async function () { state.set(this, 'playing'); };
  dom.window.HTMLMediaElement.prototype.pause = function () { state.set(this, 'paused'); };
  globalThis.fetch = async (url, options = {}) => {
    const route = String(url).replace('/api/learning', '');
    let data;
    if (route === '/session') data = { token: 'synthetic-token', providers: {} };
    else if (route === '/videos') data = { videos: [detail] };
    else if (route === '/videos/fixture') data = structuredClone(detail);
    else if (route.endsWith('/subtitle-candidates')) data = { tracks: [] };
    else if (route.endsWith('/study')) data = { messages: [], notes: [], outline: [], active_job: null };
    else if (route.endsWith('/progress')) { data = JSON.parse(options.body); savedProgress.push(data); }
    else throw new Error('Unexpected isolated request: ' + route);
    return { ok: true, json: async () => data };
  };
  for (const suffix of ['.ts', '.tsx']) require.extensions[suffix] = (module, filename) => {
    const result = ts.transpileModule(readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React, esModuleInterop: true },
    });
    module._compile(result.outputText, filename);
  };
  require.extensions['.css'] = () => {};
  act = require('react').act;
  const client = require('react-dom/client');
  const create = client.createRoot;
  client.createRoot = (...args) => { root = create(...args); return root; };
  await act(async () => require(resolve(__dirname, '../src/learning.tsx')));
  media = document.querySelector('video');
  assert.ok(media, 'Actual learning App mounted a video');
  await act(async () => media.dispatchEvent(new Event('loadedmetadata')));
});

after(async () => {
  if (root) await act(async () => root.unmount());
  dom?.window.close();
});

async function press(target, key, code = '', extra = {}) {
  const event = new KeyboardEvent('keydown', { key, code, bubbles: true, cancelable: true, ...extra });
  await act(async () => target.dispatchEvent(event));
  return event;
}

test('mounted App executes speed and subtitle keys after explicitly focusing the player', async () => {
  const enable = [...document.querySelectorAll('button')].find(b => b.textContent.includes('点击这里启用快捷键'));
  await act(async () => enable.click());
  assert.equal(document.activeElement.id, 'learning-player');
  assert.match(document.querySelector('[role="status"]').textContent, /已启用/);
  await press(document.activeElement, 'c', 'KeyC');
  assert.equal(media.playbackRate, 1.1);
  assert.equal(document.querySelector('[aria-label="播放倍速"]').value, '1.1');
  await press(document.activeElement, 'x', 'KeyX');
  assert.equal(media.playbackRate, 1);
  await press(document.activeElement, 's', 'KeyS');
  assert.equal(document.querySelector('[aria-label="画面字幕"]').value, 'off');
  await press(document.activeElement, 's', 'KeyS');
  assert.equal(document.querySelector('[aria-label="画面字幕"]').value, 'bilingual');
  assert.ok(savedProgress.some(p => p.rate === 1.1));
});

test('mounted App invokes fullscreen and handles IME keys while fullscreen', async () => {
  await press(media, 'f', 'KeyF');
  assert.equal(document.fullscreenElement?.id, 'learning-player');
  await press(media, 'Process', 'KeyC', { keyCode: 229, isComposing: true });
  assert.equal(media.playbackRate, 1.1);
  await press(media, 'f', 'KeyF');
  assert.equal(document.fullscreenElement, null);
});

test('mounted App preserves textarea typing and resumes shortcuts after import dialog closes', async () => {
  const textarea = document.querySelector('[aria-label="向视频提问"]');
  textarea.focus();
  const typed = await press(textarea, 'c', 'KeyC');
  assert.equal(typed.defaultPrevented, false);
  assert.equal(media.playbackRate, 1.1);
  const open = [...document.querySelectorAll('button')].find(b => b.textContent.includes('导入视频'));
  await act(async () => open.click());
  await press(document.body, 'c', 'KeyC');
  assert.equal(media.playbackRate, 1.1);
  await act(async () => document.querySelector('[aria-label="关闭导入"]').click());
  await press(media, 'c', 'KeyC');
  assert.equal(media.playbackRate, 1.2);
});

test('mounted diagnostics distinguish prevented events and redact editor keystrokes', async () => {
  const detect = [...document.querySelectorAll('button')].find(b => b.textContent.includes('检测按键是否收到'));
  await act(async () => detect.click());
  assert.match(document.querySelector('.shortcut-diagnostic').textContent, /等待按键/);
  const event = new KeyboardEvent('keydown', { key: 'c', code: 'KeyC', bubbles: true, cancelable: true });
  event.preventDefault();
  await act(async () => media.dispatchEvent(event));
  assert.match(document.querySelector('.shortcut-diagnostic').textContent, /已被其他处理器阻止/);
  assert.equal(media.playbackRate, 1.2);
  const textarea = document.querySelector('[aria-label="向视频提问"]');
  textarea.focus();
  await press(textarea, 'c', 'KeyC');
  const text = document.querySelector('.shortcut-diagnostic').textContent;
  assert.match(text, /文字输入（不记录内容）/);
  assert.ok(!text.includes('KeyC'));
  assert.equal(media.playbackRate, 1.2);
});
