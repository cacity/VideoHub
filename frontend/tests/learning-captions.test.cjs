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
