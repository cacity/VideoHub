const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const ts = require('typescript');
const { JSDOM } = require('jsdom');
let dom, root, act, React, LearningMarkdown, LearningPanel;
let study, job, submitted = [];
const seeked = [];
const map = {
  organization: 'topics', explanation: '多话题，按主题归纳。', basis: '由全片字幕归纳',
  created: '2026-11-02', subtitle_version: 'v1', coverage: { parts: 2, cues: 4 },
  root: { id: 'n1', label: '整片主题', summary: '总览', start: 0, end: 60, chapter_indices: [0, 1], children: [
    { id: 'n2', label: '学习步骤', summary: '先理解后练习', start: 12, end: 30, chapter_indices: [0], children: [] },
    { id: 'n3', label: '复习方法', summary: '间隔重复', start: 30, end: 60, chapter_indices: [1], children: [] },
  ] },
};
const video = { id: 'fixture', title: '合成视频', subtitle_version: 'v1', has_source: true,
  has_target: true, duration: 60, progress: {}, cues: [], tracks: {}, browser_ready: true };

before(async () => {
  dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'https://unit.test' });
  for (const name of ['window', 'document', 'HTMLElement', 'Event', 'localStorage']) globalThis[name] = dom.window[name];
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: dom.window.navigator });
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const markdownModule = await import('react-markdown');
  const gfmModule = await import('remark-gfm');
  for (const suffix of ['.ts', '.tsx']) require.extensions[suffix] = (module, filename) => {
    const original = module.require.bind(module);
    module.require = name => name === 'react-markdown' ? { __esModule: true, ...markdownModule } : name === 'remark-gfm' ? { __esModule: true, ...gfmModule } : original(name);
    module._compile(ts.transpileModule(readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React, esModuleInterop: true },
    }).outputText, filename);
  };
  React = require('react'); act = React.act;
  root = require('react-dom/client').createRoot(document.getElementById('root'));
  LearningMarkdown = require(resolve(__dirname, '../src/learning-markdown.tsx')).LearningMarkdown;
  LearningPanel = require(resolve(__dirname, '../src/learning-panel.tsx')).LearningPanel;
  globalThis.fetch = async (url, options = {}) => {
    if (url.endsWith('/study')) return { ok: true, json: async () => structuredClone(study) };
    if (url.endsWith('/prepare')) {
      submitted.push(JSON.parse(options.body));
      study.mindmap = structuredClone(map);
      return { ok: true, json: async () => ({ id: 'job', kind: 'mindmap', status: 'finished', message: '完成', progress: 100 }) };
    }
    throw new Error('Unexpected isolated request: ' + url);
  };
  globalThis.EventSource = class {
    constructor() { queueMicrotask(() => this.onmessage?.({ data: JSON.stringify(job) })); }
    close() {}
  };
});
after(async () => { await act(async () => root.unmount()); dom.window.close(); });
const render = async props => act(async () => root.render(React.createElement(LearningMarkdown, props)));
const button = text => [...document.querySelectorAll('button')].find(b => b.textContent.trim() === text);
const click = async element => { assert.ok(element); await act(async () => element.click()); };

test('Markdown renders headings, lists, emphasis, tables, quotes, and fenced code; references keep video seeking', async () => {
  await render({
    text: '## 核心概念\n\n1. **理解** 与 *练习* [cue:c1]\n2. `术语`\n\n> 引用\n\n| 概念 | 例子 |\n| --- | --- |\n| A | B |\n\n```python\nprint("[cue:c1]")\n```\n\n[web:W1]',
    citations: [{ id: 'c1', start: 12, end: 14, text: '真实字幕' }],
    sources: [{ id: 'W1', url: 'https://example.com/reference', title: '资料' }], seek: t => seeked.push(t),
  });
  assert.equal(document.querySelector('h2').textContent, '核心概念');
  assert.equal(document.querySelectorAll('ol li').length, 2);
  assert.equal(document.querySelector('strong').textContent, '理解');
  assert.ok(document.querySelector('em') && document.querySelector('table') && document.querySelector('blockquote'));
  assert.match(document.querySelector('pre code').textContent, /\[cue:c1\]/, 'tokens inside code must stay code');
  assert.equal(document.querySelectorAll('.inline-citation').length, 1);
  await click(document.querySelector('.inline-citation'));
  assert.equal(seeked.at(-1), 12);
  assert.equal(document.querySelector('a').getAttribute('href'), 'https://example.com/reference');
});

test('model Markdown cannot execute HTML, open unsafe schemes, or load remote images', async () => {
  await render({ text: '<script>evil()</script>\n\n<img src=x onerror="evil()">\n\n[危险](javascript:evil()) [正常](https://example.com) ![外链图](https://example.com/private.png)\n\n[cue:invented]' });
  assert.equal(document.querySelectorAll('script,img,iframe').length, 0);
  assert.equal(document.querySelectorAll('a').length, 1);
  assert.equal(document.querySelector('a').rel, 'noopener noreferrer');
  assert.ok(!document.querySelector('.inline-citation'));
});

async function panel(key, extra = {}) {
  await act(async () => root.render(React.createElement(LearningPanel, { key, video, position: 0, selected: null,
    providers: { deepseek: { configured: true, model: 'test' } }, seek: t => seeked.push(t), refresh: async () => {}, report: () => {},
    collapsed: false, resizeHandle: null, ...extra })));
}

test('brain-map tab follows outline, generates through prepare even on fast completion, and supports collapse, zoom, seeking and exports', async () => {
  submitted = [];
  study = { messages: [], notes: [], outline: [], mindmap: null, active_job: null };
  await panel('map-generation');
  assert.deepEqual([...document.querySelectorAll('.panel-tabs button')].map(b => b.textContent), ['AI 对话', '笔记', '大纲', '脑图']);
  await click(button('脑图'));
  await click(button('生成脑图'));
  assert.equal(submitted[0].kind, 'mindmap');
  assert.equal(submitted[0].force, false);
  assert.match(document.querySelector('.mindmap-panel').textContent, /主题图/);
  assert.equal(document.querySelectorAll('.mindmap-node').length, 3);
  await click(document.querySelector('[aria-label="折叠整片主题"]'));
  assert.equal(document.querySelectorAll('.mindmap-node').length, 1);
  await click(button('展开全部'));
  assert.equal(document.querySelectorAll('.mindmap-node').length, 3);
  await click(document.querySelectorAll('.mindmap-time')[1]);
  assert.equal(seeked.at(-1), 12);
  await click(document.querySelector('[aria-label="放大脑图"]'));
  assert.ok(button('110%'));
  assert.match(document.querySelector('.mindmap-exports a').href, /format=markdown/);
  await click(document.querySelector('[aria-label="展开脑图大图"]'));
  assert.ok(document.querySelector('[role="dialog"]'));
  assert.equal(document.activeElement.getAttribute('role'), 'dialog');
  await act(async () => document.activeElement.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.equal(document.activeElement.getAttribute('aria-label'), '展开脑图大图');
  await click(document.querySelector('[aria-label="展开脑图大图"]'));
  await click(document.querySelector('[aria-label="关闭脑图大图"]'));
  assert.equal(document.querySelector('[role="dialog"]'), null);
  await click(button('重新生成脑图'));
  assert.equal(submitted.at(-1).force, true);
});

test('an older running service shows a restart hint instead of submitting an unsupported mindmap job', async () => {
  study = { messages: [], notes: [], outline: [], active_job: null };
  await panel('old-backend', { mindmapAvailable: false });
  await click(button('脑图'));
  assert.ok(button('生成脑图').disabled);
  assert.match(document.querySelector('.mindmap-panel').textContent, /重启VideoHub/);
});

test('existing assistant answers and saved notes both render Markdown without changing original text', async () => {
  const text = '### 已有回答\n\n- **一项**\n- 二项';
  study = { messages: [{ id: 'm1', role: 'assistant', text, status: 'finished', time: 0, subtitle_version: 'v1' }],
    notes: [{ id: 'note1', text, start: 0, end: 0, tags: [], citations: [], sources: [], subtitle_version: 'v1', created: '2026-11-02', version: 1 }],
    outline: [], mindmap: null, active_job: null };
  await panel('markdown-history');
  assert.equal(document.querySelector('.message h3').textContent, '已有回答');
  assert.equal(document.querySelectorAll('.message li').length, 2);
  await click(button('笔记'));
  assert.equal(document.querySelector('.note h3').textContent, '已有回答');
  assert.equal(study.messages[0].text, text);
});

test('streaming answer snapshots render Markdown without unverified citation buttons', async () => {
  job = { id: 'stream', kind: 'chat', status: 'running', text: '## 正在解释\n\n- **重点** [cue:unknown]', progress: 75, message: '回答中' };
  study = { messages: [], notes: [], outline: [], active_job: job };
  await panel('streaming');
  assert.equal(document.querySelector('.streaming h2').textContent, '正在解释');
  assert.ok(document.querySelector('.streaming strong'));
  assert.equal(document.querySelector('.streaming .inline-citation'), null);
  assert.ok(!document.querySelector('.streaming').textContent.includes('[cue:'));
});

test('existing subtitles can be translated from any learning tab, only after confirmation, using the chosen source and provider', async () => {
  submitted = [];
  study = { messages: [], notes: [], outline: [], active_job: null };
  let refreshed = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    if (url.endsWith('/prepare')) {
      submitted.push(JSON.parse(options.body));
      return { ok: true, json: async () => ({ id: 'translated', kind: 'translation', status: 'finished', progress: 100, message: '字幕翻译完成' }) };
    }
    return originalFetch(url, options);
  };
  try {
    await panel('existing-translation', { translationRequest: 1,
      video: { ...video, has_target: false, tracks: { source: { language: 'en', hash: 'chosen-english-version' } },
        available_tracks: [{ key: 'source', name: 'lesson.en.vtt', role: 'source' }] },
      providers: { deepseek: { configured: true, model: 'test' }, kimi: { configured: true, model: 'kimi-test' } },
      refresh: async () => { refreshed++; } });
    assert.equal(submitted.length, 0, 'opening the translation form must not call a model');
    assert.match(document.querySelector('.translation-setup').textContent, /lesson.en.vtt/);
    assert.ok(document.querySelector('.messages'), 'chat remains available while translation is open');
    const provider = document.querySelector('[aria-label="AI 服务"]');
    await act(async () => { provider.value = 'kimi'; provider.dispatchEvent(new Event('change', { bubbles: true })); });
    await click(button('开始翻译为中文'));
    assert.equal(submitted.length, 1);
    assert.equal(submitted[0].kind, 'translation');
    assert.equal(submitted[0].source_hash, 'chosen-english-version');
    assert.equal(submitted[0].provider, 'kimi');
    assert.equal(refreshed, 1, 'fast completion refreshes subtitle versions as well');
    assert.match(document.querySelector('.job-card').textContent, /字幕翻译完成/);
    await click(button('收起'));
    assert.equal(document.querySelector('.translation-setup'), null);
  } finally { globalThis.fetch = originalFetch; localStorage.removeItem('videohub.learning.provider'); }
});

test('translation requires an existing source and configured provider, and reports submission errors beside the translation form', async () => {
  study = { messages: [], notes: [], outline: [], active_job: null };
  await panel('no-source', { translationRequest: 1, video: { ...video, has_source: false } });
  assert.ok(button('开始翻译为中文').disabled);
  assert.match(document.querySelector('.translation-setup').textContent, /先从“字幕版本”选择原文/);
  await panel('unconfigured-translation', { translationRequest: 1, providers: {} });
  assert.ok(button('开始翻译为中文').disabled);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => url.endsWith('/prepare')
    ? { ok: false, json: async () => ({ error: '原文字幕已改变，请重新确认翻译版本' }) } : originalFetch(url, options);
  try {
    await panel('translation-error', { translationRequest: 1 });
    await click(button('开始翻译为中文'));
    assert.match(document.querySelector('.translation-setup [role="alert"]').textContent, /原文字幕已改变/);
    assert.ok(!button('开始翻译为中文').disabled, 'a failed request can be retried');
  } finally { globalThis.fetch = originalFetch; }
});
