const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const ts = require('typescript');
const { JSDOM, VirtualConsole } = require('jsdom');

let dom, root, act, media;
let sessionGeneration = 0;
let blockLaterKeyHandlers = false;
let subtitleCandidates = [];
const subtitleSelections = [];
const savedProgress = [];
let importedLessons = [];
let projectImportFailures = [];
const projectRequests = [];
const savedByVideo = [];
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
  dom = new JSDOM(readFileSync(resolve(__dirname, '../learning.html'), 'utf8'), {
    url: 'https://unit.test/learn?video=fixture', runScripts: 'dangerously',
  });
  // Reproduce a handler added after the native bootstrap but before the App.
  dom.window.addEventListener('keydown', event => {
    if (blockLaterKeyHandlers) event.stopImmediatePropagation();
  }, true);
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
    if (route === '/session') data = { token: 'synthetic-token-' + sessionGeneration, providers: {} };
    else if (route === '/videos') data = { videos: [detail, ...importedLessons] };
    else if (route === '/imports/recent') data = { videos: [] };
    else if (route === '/imports/project') {
      const request = JSON.parse(options.body);
      projectRequests.push(request);
      const lessons = ['one', 'two'].map((name, index) => ({
        ...structuredClone(detail), id: name, title: 'Lesson ' + name, path: '/course/' + name + '.mp4',
        progress: { ...detail.progress, time: 10 + index * 20 },
        cues: [{ id: name + '-cue', start: 0, end: 60, text: 'English ' + name, translation: '中文 ' + name }],
      }));
      if (!request.video_paths) data = { needs_selection: true, videos: lessons };
      else {
        assert.deepEqual(request.video_paths, lessons.map(v => v.path));
        importedLessons = lessons.filter(v => !projectImportFailures.some(e => e.path === v.path));
        data = { video: importedLessons[0] || null, imported: importedLessons, errors: projectImportFailures };
      }
    }
    else if (importedLessons.some(v => route === '/videos/' + v.id)) data = structuredClone(importedLessons.find(v => route === '/videos/' + v.id));
    else if (route === '/videos/fixture') data = structuredClone(detail);
    else if (route.endsWith('/subtitle-candidates')) data = { tracks: subtitleCandidates };
    else if (route.endsWith('/select-track') || route.endsWith('/subtitles')) {
      const request = JSON.parse(options.body);
      subtitleSelections.push({ route, ...request });
      if (request.key) {
        const chosen = detail.available_tracks.find(t => t.key === request.key);
        detail.tracks[request.role] = { ...chosen };
        detail.available_tracks = detail.available_tracks.map(t => t.key === request.role ? { ...chosen, key: request.role } : t);
      }
      detail.subtitle_version += '-updated';
      data = structuredClone(detail);
    }
    else if (route.endsWith('/study')) data = { messages: [], notes: [], outline: [], active_job: null };
    else if (route.endsWith('/progress')) {
      assert.equal(options.headers['X-Learning-Token'], 'synthetic-token-' + sessionGeneration);
      data = JSON.parse(options.body); savedProgress.push(data);
      const id = route.split('/')[2];
      savedByVideo.push({ id, ...data });
      const lesson = [detail, ...importedLessons].find(v => v.id === id);
      lesson.progress = structuredClone(data);
    }
    else throw new Error('Unexpected isolated request: ' + route);
    return { ok: true, json: async () => data };
  };
  const markdownModule = await import('react-markdown');
  const gfmModule = await import('remark-gfm');
  for (const suffix of ['.ts', '.tsx']) require.extensions[suffix] = (module, filename) => {
    const original = module.require.bind(module);
    module.require = name => name === 'react-markdown' ? { __esModule: true, ...markdownModule } : name === 'remark-gfm' ? { __esModule: true, ...gfmModule } : original(name);
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

async function scanProject() {
  const open = [...document.querySelectorAll('button')].find(b => b.textContent.includes('导入视频'));
  await act(async () => open.click());
  const folder = document.querySelector('[aria-label="工程目录"]');
  await act(async () => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(folder, '/course');
    folder.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => document.querySelector('.import-modal').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
}

async function press(target, key, code = '', extra = {}) {
  const event = new KeyboardEvent('keydown', { key, code, bubbles: true, cancelable: true, ...extra });
  if (extra.timeStamp !== undefined) Object.defineProperty(event, 'timeStamp', { value: extra.timeStamp });
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
  assert.ok(savedProgress.some(p => p.rate === 1), 'subsequent preference changes include the latest speed');
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

test('mounted App applies held speed keys and rapid presses immediately, saving only the final burst value', async () => {
  const previousWrites = savedProgress.length;
  media.playbackRate = 1;
  await press(media, 'c', 'KeyC', { timeStamp: 100 });
  await press(media, 'c', 'KeyC', { repeat: true, timeStamp: 600 });
  const skipped = await press(media, 'c', 'KeyC', { repeat: true, timeStamp: 630 });
  assert.equal(skipped.defaultPrevented, true);
  await press(media, 'c', 'KeyC', { repeat: true, timeStamp: 780 });
  assert.equal(media.playbackRate, 1.3, 'holding C continues to raise the speed');
  await act(async () => {
    for (const timeStamp of [790, 800, 810]) {
      const event = new KeyboardEvent('keydown', { key: 'c', code: 'KeyC', bubbles: true, cancelable: true });
      Object.defineProperty(event, 'timeStamp', { value: timeStamp });
      media.dispatchEvent(event);
    }
  });
  assert.equal(media.playbackRate, 1.6, 'all distinct presses work even in one React batch');
  assert.equal(document.querySelector('[aria-label="播放倍速"]').value, '1.6');
  assert.equal(savedProgress.length, previousWrites, 'UI and media do not wait for network writes');
  await act(async () => new Promise(resolve => setTimeout(resolve, 300)));
  assert.equal(savedProgress.length, previousWrites + 1);
  assert.equal(savedProgress.at(-1).rate, 1.6);
});

test('held speed/seek work fullscreen; held toggles do not flicker and remain protected while editing', async () => {
  await press(media, 'f', 'KeyF', { timeStamp: 1000 });
  assert.equal(document.fullscreenElement?.id, 'learning-player');
  await press(media, 'f', 'KeyF', { repeat: true, timeStamp: 1500 });
  assert.equal(document.fullscreenElement?.id, 'learning-player', 'holding F must not exit immediately');
  await press(media, 'Process', 'KeyX', { timeStamp: 1600, keyCode: 229, isComposing: true });
  await press(media, 'Process', 'KeyX', { repeat: true, timeStamp: 2100, keyCode: 229, isComposing: true });
  assert.equal(media.playbackRate, 1.4);
  const beforeSeek = media.currentTime;
  await press(media, 'ArrowRight', 'ArrowRight', { timeStamp: 2200 });
  await press(media, 'ArrowRight', 'ArrowRight', { repeat: true, timeStamp: 2700 });
  assert.equal(media.currentTime, beforeSeek + 10);
  const oldMode = document.querySelector('[aria-label="画面字幕"]').value;
  await press(media, 's', 'KeyS', { timeStamp: 2800 });
  const newMode = document.querySelector('[aria-label="画面字幕"]').value;
  assert.notEqual(newMode, oldMode);
  await press(media, 's', 'KeyS', { repeat: true, timeStamp: 3300 });
  assert.equal(document.querySelector('[aria-label="画面字幕"]').value, newMode);
  await press(media, 's', 'KeyS', { timeStamp: 3310 });
  assert.equal(document.querySelector('[aria-label="画面字幕"]').value, oldMode);
  const textarea = document.querySelector('[aria-label="向视频提问"]');
  textarea.focus();
  const typing = await press(textarea, 'c', 'KeyC', { repeat: true, timeStamp: 4000 });
  assert.equal(typing.defaultPrevented, false);
  assert.equal(media.playbackRate, 1.4);
  await press(media, 'f', 'KeyF', { timeStamp: 4100 });
  assert.equal(document.fullscreenElement, null);
});

test('pending burst speed is flushed on pagehide and cannot be lost before the debounce finishes', async () => {
  const previousWrites = savedProgress.length;
  await press(media, 'x', 'KeyX', { timeStamp: 5000 });
  await press(media, 'x', 'KeyX', { repeat: true, timeStamp: 5500 });
  assert.equal(media.playbackRate, 1.2);
  assert.equal(savedProgress.length, previousWrites);
  await act(async () => window.dispatchEvent(new Event('pagehide')));
  assert.equal(savedProgress.at(-1).rate, 1.2);
  assert.equal(savedProgress.length, previousWrites + 1);
  await act(async () => new Promise(resolve => setTimeout(resolve, 300)));
  assert.equal(savedProgress.length, previousWrites + 1, 'flush cancels the delayed duplicate write');
});

test('reopening the App after service restarts binds keys once and renews the session without enabling shortcuts manually', async () => {
  const entry = resolve(__dirname, '../src/learning.tsx');
  for (let restart = 0; restart < 3; restart++) {
    await act(async () => root.unmount());
    sessionGeneration++;
    delete require.cache[entry];
    await act(async () => require(entry));
    media = document.querySelector('video');
    await act(async () => media.dispatchEvent(new Event('loadedmetadata')));
    const startingRate = media.playbackRate;
    const mode = document.querySelector('[aria-label="画面字幕"]').value;
    await press(media, 'c', 'KeyC');
    assert.equal(media.playbackRate, Math.round((startingRate + .1) * 100) / 100, 'one press must execute exactly once after reopening');
    await press(media, 'x', 'KeyX');
    assert.equal(media.playbackRate, startingRate);
    await press(media, 's', 'KeyS');
    assert.notEqual(document.querySelector('[aria-label="画面字幕"]').value, mode);
    await press(media, 's', 'KeyS');
    assert.equal(document.querySelector('[aria-label="画面字幕"]').value, mode);
    await press(media, 'f', 'KeyF');
    assert.equal(document.fullscreenElement?.id, 'learning-player');
    await press(media, 'f', 'KeyF');
    assert.equal(document.fullscreenElement, null);
    await act(async () => window.dispatchEvent(new Event('pagehide')));
    assert.equal(savedProgress.at(-1).rate, startingRate);
  }
});

test('the native entry still executes player commands when a later listener stops further dispatch', async () => {
  const rate = media.playbackRate;
  const panel = document.getElementById('learning-self-check');
  panel.open = true;
  blockLaterKeyHandlers = true;
  try {
    await press(media, 'c', 'KeyC');
    assert.equal(media.playbackRate, Math.round((rate + .1) * 100) / 100);
    await press(media, 'x', 'KeyX');
    assert.equal(media.playbackRate, rate);
    await press(media, 's', 'KeyS');
    assert.equal(document.querySelector('[aria-label="画面字幕"]').value, 'off');
    await press(media, 's', 'KeyS');
    assert.equal(document.querySelector('[aria-label="画面字幕"]').value, 'bilingual');
    await press(media, 'f', 'KeyF');
    assert.equal(document.fullscreenElement?.id, 'learning-player');
    await press(media, 'f', 'KeyF');
    assert.equal(document.fullscreenElement, null);
    const textarea = document.querySelector('[aria-label="向视频提问"]');
    await press(textarea, 'c', 'KeyC');
    assert.equal(media.playbackRate, rate, 'early entry must still preserve typing');
  } finally { blockLaterKeyHandlers = false; panel.open = false; }
});

test('native self-check remains usable without React and reports bootstrap, keys, and redacted errors', async () => {
  const html = readFileSync(resolve(__dirname, '../learning.html'), 'utf8');
  const scriptErrors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', error => scriptErrors.push(error));
  const isolated = new JSDOM(html, { url: 'https://unit.test/learn?video=private-id', runScripts: 'dangerously', virtualConsole });
  const win = isolated.window;
  try {
    const panel = win.document.getElementById('learning-self-check');
    const report = win.document.getElementById('learning-self-report');
    assert.match(report.textContent, /等待学习页启动/);
    panel.open = true;
    win.document.dispatchEvent(new win.CustomEvent('videohub:learning-runtime', {
      detail: { app: '已启动', listener: '已绑定', player: '已挂载' },
    }));
    win.document.body.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'c', code: 'KeyC', bubbles: true }));
    win.document.body.dispatchEvent(new win.KeyboardEvent('keyup', { key: 'c', code: 'KeyC', bubbles: true }));
    await new Promise(resolve => win.setTimeout(resolve, 0));
    assert.match(report.textContent, /按下：KeyC/);
    assert.match(report.textContent, /松开：KeyC/);
    assert.match(report.textContent, /快捷键监听：已绑定/);
    assert.ok(!report.textContent.includes('private-id'), 'video IDs and query strings must not enter the report');
    const input = win.document.createElement('textarea');
    win.document.body.append(input);
    input.dispatchEvent(new win.KeyboardEvent('keydown', { key: 'secret', code: 'KeyC', bubbles: true }));
    await new Promise(resolve => win.setTimeout(resolve, 0));
    assert.match(report.textContent, /输入区（已省略内容）/);
    assert.ok(!report.textContent.includes('secret'));
    win.dispatchEvent(new win.ErrorEvent('error', { message: 'private question', error: new win.TypeError('private question') }));
    assert.match(report.textContent, /脚本错误：TypeError/);
    assert.ok(!report.textContent.includes('private question'));
    let copied = '';
    Object.defineProperty(win.navigator, 'clipboard', { value: { writeText: async value => { copied = value; } } });
    win.document.getElementById('learning-copy-report').click();
    await new Promise(resolve => win.queueMicrotask(resolve));
    assert.equal(copied, report.textContent);
    await new Promise(resolve => win.setTimeout(resolve, 0));
    assert.deepEqual(scriptErrors, []);
  } finally { win.close(); }
});

test('a focused player recovers a delivered keyup when keydown is absent, without doubling normal presses or intercepting typing', async () => {
  const wrap = document.getElementById('learning-player');
  const release = async (target, key, code, extra = {}) => {
    const event = new KeyboardEvent('keyup', { key, code, bubbles: true, cancelable: true, ...extra });
    await act(async () => target.dispatchEvent(event));
    return event;
  };
  await act(async () => { window.dispatchEvent(new Event('blur')); wrap.focus(); });
  const rate = media.playbackRate;
  await release(wrap, 'c', 'KeyC');
  assert.equal(media.playbackRate, Math.round((rate + .1) * 100) / 100);
  await release(wrap, 'x', 'KeyX');
  assert.equal(media.playbackRate, rate);
  await release(wrap, 'Process', 'KeyC', { keyCode: 229, isComposing: true });
  assert.equal(media.playbackRate, Math.round((rate + .1) * 100) / 100);
  await release(wrap, 'X', '');
  assert.equal(media.playbackRate, rate, 'keyup fallback also handles missing physical codes and case');
  const original = document.querySelector('[aria-label="画面字幕"]').value;
  await release(wrap, 's', 'KeyS');
  assert.notEqual(document.querySelector('[aria-label="画面字幕"]').value, original);
  await release(wrap, 's', 'KeyS');
  assert.equal(document.querySelector('[aria-label="画面字幕"]').value, original);
  await release(wrap, 'f', 'KeyF');
  assert.equal(document.fullscreenElement?.id, 'learning-player');
  await release(wrap, 'f', 'KeyF');
  assert.equal(document.fullscreenElement, null);
  const position = media.currentTime;
  await release(wrap, 'ArrowRight', '');
  assert.equal(media.currentTime, Math.min(60, position + 5));
  await release(wrap, 'ArrowLeft', '');
  assert.equal(media.currentTime, position);
  await press(wrap, 'c', 'KeyC');
  const afterDown = media.playbackRate;
  await release(wrap, 'c', 'KeyC');
  assert.equal(media.playbackRate, afterDown, 'normal down/up pair must execute only once');
  const textarea = document.querySelector('[aria-label="向视频提问"]');
  await act(async () => textarea.focus());
  const typing = await release(textarea, 'c', 'KeyC');
  assert.equal(typing.defaultPrevented, false);
  assert.equal(media.playbackRate, afterDown);
  await act(async () => wrap.focus());
  await release(wrap, 'c', 'KeyC', { ctrlKey: true });
  assert.equal(media.playbackRate, afterDown, 'modifier shortcuts remain protected');
  await press(textarea, 'x', 'KeyX');
  await release(wrap, 'x', 'KeyX');
  assert.equal(media.playbackRate, afterDown, 'rejected typing must not be retried on keyup after a focus change');
  await act(async () => window.dispatchEvent(new Event('blur')));
  await release(wrap, 'x', 'KeyX');
  assert.equal(media.playbackRate, afterDown, 'losing the window focus disables release recovery until reactivation');
});

test('subtitle versions in the actual App select one track per role, reuse bilingual files and open translation even with the assistant collapsed', async () => {
  await act(async () => root.unmount());
  detail.tracks = { source: { language: 'en', path: '/source.srt', hash: 'source-v1' }, target: { language: 'zh-CN', path: '/target.srt' } };
  detail.available_tracks = [
    { key: 'source', name: 'lesson.en.srt', role: 'source', language: 'en', path: '/source.srt' },
    { key: 'available-v2', name: 'lesson.en.vtt', role: 'source', language: 'en', path: '/source.vtt', hash: 'source-v2' },
    { key: 'target', name: 'lesson.google.srt', role: 'target', language: 'zh-CN', path: '/target.srt' },
  ];
  subtitleCandidates = [
    { name: 'lesson.bilingual.ass', path: '/mixed.ass', role: 'source', language: 'en', format: 'ASS', bilingual: true },
    { name: 'lesson.bilingual.ass', path: '/mixed.ass', role: 'target', language: 'zh-CN', format: 'ASS', bilingual: true },
  ];
  localStorage.setItem('videohub.learning.layout', JSON.stringify({ assistant: true }));
  const entry = resolve(__dirname, '../src/learning.tsx');
  delete require.cache[entry];
  await act(async () => require(entry));
  assert.equal(document.getElementById('learning-assistant').hidden, true);
  const translate = [...document.querySelectorAll('.transcript-toolbar button')].find(b => b.textContent === '翻译已有字幕');
  await act(async () => translate.click());
  assert.equal(document.getElementById('learning-assistant').hidden, false);
  assert.ok(document.querySelector('.translation-setup'));
  const versions = document.querySelector('.subtitle-versions');
  versions.open = true;
  const sourceSelect = document.querySelector('[aria-label="选择原文轨道"]');
  assert.equal(sourceSelect.options.length, 2);
  assert.ok(!sourceSelect.textContent.includes('google'), 'Chinese versions never appear as source options');
  await act(async () => { sourceSelect.value = 'available-v2'; sourceSelect.dispatchEvent(new Event('change', { bubbles: true })); });
  assert.equal(subtitleSelections.at(-1).key, 'available-v2');
  assert.match(document.querySelector('.translation-setup').textContent, /lesson.en.vtt/);
  const files = [...document.querySelectorAll('.subtitle-file-list button')];
  assert.equal(files.length, 2, 'one bilingual file exposes two distinct language actions');
  await act(async () => files.find(b => b.textContent.startsWith('用作译文')).click());
  assert.equal(subtitleSelections.at(-1).path, '/mixed.ass');
  assert.equal(subtitleSelections.at(-1).role, 'target');
  assert.equal(document.querySelectorAll('video').length, 1, 'switching subtitles does not remount the player');
});

test('assistant dragging can use most of the viewport, releases library space, and survives reopening', async () => {
  const previousWidth = window.innerWidth;
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1920 });
  await act(async () => window.dispatchEvent(new Event('resize')));
  let handle = document.querySelector('[aria-label="调整学习助手宽度"]');
  handle.setPointerCapture = () => {};
  handle.hasPointerCapture = () => false;
  const pointer = (name, x) => Object.assign(new Event(name, { bubbles: true, cancelable: true }), { pointerId: 42, button: 0, clientX: x });
  await act(async () => handle.dispatchEvent(pointer('pointerdown', 1200)));
  await act(async () => handle.dispatchEvent(pointer('pointermove', -10000)));
  await act(async () => handle.dispatchEvent(pointer('pointerup', -10000)));
  assert.ok(Number(handle.getAttribute('aria-valuenow')) > 1000, 'drag beyond the previous 560px limit');
  const widthWithLibrary = Number(handle.getAttribute('aria-valuemax'));
  await act(async () => document.querySelector('[aria-label="折叠资料库"]').click());
  assert.equal(Number(handle.getAttribute('aria-valuemax')), 1536, 'collapsed library permits 80% at 1920px');
  assert.ok(Number(handle.getAttribute('aria-valuemax')) > widthWithLibrary);
  await press(handle, 'End');
  assert.equal(document.querySelector('.workspace').style.getPropertyValue('--preferred-assistant-width'), '1536px');
  await act(async () => root.unmount());
  const entry = resolve(__dirname, '../src/learning.tsx');
  delete require.cache[entry];
  await act(async () => require(entry));
  media = document.querySelector('video');
  handle = document.querySelector('[aria-label="调整学习助手宽度"]');
  assert.equal(Number(handle.getAttribute('aria-valuenow')), 1536, 'saved wide preference is not clamped to the old 560px cap');
  await act(async () => document.querySelector('[aria-label="展开资料库"]').click());
  const libraryWidth = Number(document.querySelector('[aria-label="调整资料库宽度"]').getAttribute('aria-valuenow'));
  assert.ok(1920 - libraryWidth - Number(handle.getAttribute('aria-valuenow')) >= 320);
  await press(handle, 'Enter');
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: previousWidth });
  await act(async () => window.dispatchEvent(new Event('resize')));
});

test('directory imports select all lessons and switch their own captions and progress in the real App', async () => {
  await scanProject();
  const boxes = [...document.querySelectorAll('.import-video-choice input')];
  assert.equal(boxes.length, 2);
  assert.ok(boxes.every(b => b.checked), 'all videos are selected by default');
  const submit = document.querySelector('.import-modal .primary');
  assert.match(submit.textContent, /2 个视频/);
  await act(async () => [...document.querySelectorAll('.import-selection-actions button')].find(b => b.textContent === '清空选择').click());
  assert.equal(submit.disabled, true);
  await act(async () => [...document.querySelectorAll('.import-selection-actions button')].find(b => b.textContent === '全选').click());
  await act(async () => document.querySelector('.import-modal').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  assert.equal(document.querySelector('.import-modal'), null);
  assert.deepEqual(projectRequests.at(-1).video_paths, ['/course/one.mp4', '/course/two.mp4']);
  assert.match(document.querySelector('.import-notice').textContent, /已导入 2 个视频/);
  assert.match(document.querySelector('.transcript').textContent, /English one/);
  await act(async () => document.querySelector('video').dispatchEvent(new Event('loadedmetadata')));
  assert.equal(document.querySelector('video').currentTime, 10);
  const two = [...document.querySelectorAll('.library-item')].find(b => b.textContent.includes('Lesson two'));
  await act(async () => { document.querySelector('video').currentTime = 17; two.click(); });
  await act(async () => document.querySelector('video').dispatchEvent(new Event('loadedmetadata')));
  assert.match(document.querySelector('.transcript').textContent, /English two/);
  assert.equal(document.querySelector('video').currentTime, 30);
  assert.ok(savedByVideo.some(v => v.id === 'one' && v.time === 17));
  const one = [...document.querySelectorAll('.library-item')].find(b => b.textContent.includes('Lesson one'));
  await act(async () => one.click());
  await act(async () => document.querySelector('video').dispatchEvent(new Event('loadedmetadata')));
  assert.equal(document.querySelector('video').currentTime, 17);
});

test('partial directory imports show the failed video without dropping the successful lesson', async () => {
  projectImportFailures = [{ path: '/course/two.mp4', error: '无法读取视频' }];
  await act(async () => [...document.querySelectorAll('button')].find(b => b.textContent.includes('导入视频')).click());
  await act(async () => document.querySelector('.import-modal').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  assert.equal(document.querySelector('.import-modal'), null);
  assert.match(document.querySelector('.import-notice').textContent, /已导入 1 个视频，1 个失败/);
  assert.match(document.querySelector('[role="alert"]').textContent, /two.mp4：无法读取视频/);
  assert.ok([...document.querySelectorAll('.library-item')].some(b => b.textContent.includes('Lesson one')));
});

test('desktop directory links open the directory form and complete failures remain available for retry', async () => {
  await act(async () => root.unmount());
  history.replaceState(null, '', '/learn?directory=%2Fcourse&launch=example');
  const entry = resolve(__dirname, '../src/learning.tsx');
  delete require.cache[entry];
  await act(async () => require(entry));
  assert.equal(document.querySelector('[aria-label="工程目录"]').value, '/course');
  await act(async () => document.querySelector('.import-modal').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  projectImportFailures = ['one', 'two'].map(name => ({ path: '/course/' + name + '.mp4', error: '模拟导入失败' }));
  await act(async () => document.querySelector('.import-modal').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  assert.ok(document.querySelector('.import-modal'), 'keep selections and errors visible for retry');
  assert.equal(document.querySelectorAll('.import-video-choice input:checked').length, 2);
  assert.match(document.querySelector('.import-modal [role="alert"]').textContent, /模拟导入失败/);
  assert.equal(document.querySelector('.import-modal .primary').disabled, false);
});
