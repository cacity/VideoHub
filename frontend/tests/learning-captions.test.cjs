const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const ts = require('typescript');

// Use the production selector with the project's existing TypeScript compiler.
const output = ts.transpileModule(readFileSync(resolve(__dirname, '../src/learning-api.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const api = {};
new Function('exports', output)(api);
const { currentCue } = api;

test('library groups by full project directory, normalizes Windows paths, and searches folders and lessons', () => {
  const videos = [
    { id: 'a1', path: 'F:\\课程\\剧名\\01.mp4', title: '第一集' },
    { id: 'a2', path: 'f:/课程/剧名/02.mp4', title: '第二集' },
    { id: 'b', path: 'G:/课程/剧名/01.mp4', title: '另一版' },
    { id: 'c', path: '/course/season/01.mp4', project_root: '/course', title: '第三集' },
    { id: 'd', path: '/single.mp4', title: '单独视频' },
  ];
  const groups = api.groupLibrary(videos);
  assert.deepEqual(groups.map(g => [g.title, g.videos.map(v => v.id)]), [
    ['剧名', ['a1', 'a2']], ['剧名', ['b']], ['course', ['c']], ['', ['d']],
  ]);
  assert.equal(api.groupLibrary(videos, '剧名').flatMap(g => g.videos).length, 3);
  assert.deepEqual(api.groupLibrary(videos, '第二集')[0].videos.map(v => v.id), ['a2']);
  assert.deepEqual(api.groupLibrary(videos, '找不到'), []);
});

const source = [
  { id: 's1', start: 30.24, end: 36.32, text: 'exterior, interior' },
  { id: 's2', start: 32.88, end: 38.399, text: 'details? Some stories' },
];
const target = [
  { id: 't1', start: 25.919, end: 33.28, text: '外观、内饰有哪些细节？' },
  { id: 't2', start: 33.839, end: 39.239, text: '有些内容只在这里呈现。' },
];

test('rolling originals display one latest cue; translation follows its own clock', () => {
  assert.equal(currentCue(source, 33).id, 's2');
  assert.equal(currentCue(target, 33).id, 't1');
  assert.equal(currentCue(target, 33.5), undefined);
  assert.equal(currentCue(target, 34).id, 't2');
});

test('caption intervals include their start and exclude their end', () => {
  assert.equal(currentCue([], 33), undefined);
  assert.equal(currentCue(target, 0), undefined);
  assert.equal(currentCue(target, 25.919).id, 't1');
  assert.equal(currentCue(target, 33.28), undefined);
  assert.equal(currentCue(target, 33.839).id, 't2');
  assert.equal(currentCue(target, 39.239), undefined);
});

test('seeking backwards clears later captions without changing transcript cues', () => {
  const original = JSON.stringify(source);
  assert.equal(currentCue(source, 37).id, 's2');
  assert.equal(currentCue(source, 31).id, 's1');
  assert.equal(currentCue(source, 0), undefined);
  assert.equal(JSON.stringify(source), original);
});
