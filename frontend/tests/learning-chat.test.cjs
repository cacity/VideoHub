const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const ts = require('typescript');

const compiled = ts.transpileModule(readFileSync(resolve(__dirname, '../src/learning-api.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const learning = {};
new Function('exports', compiled)(learning);
const { sendChat, resolveSearchQuery, setToken } = learning;

const request = {
  provider: 'deepseek', model: 'example-model', question: '  什么是固态电池？  ',
  time: 12, scope: 'current', cue_ids: ['cue-1'],
  search: true, search_provider: 'kimi', search_query: '',
};

test('checking search without a separate query submits a bounded nonempty query and receives a job', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, options, body: JSON.parse(options.body) });
    return { ok: true, json: async () => ({ id: 'job-1', kind: 'chat', status: 'queued' }) };
  });
  setToken('local-session');
  const original = JSON.stringify(request);
  const job = await sendChat('video-1', request);
  assert.equal(job.id, 'job-1');
  assert.equal(calls[0].url, '/api/learning/videos/video-1/chat');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.headers['X-Learning-Token'], 'local-session');
  assert.equal(calls[0].body.search_query, '什么是固态电池？');
  assert.equal(calls[0].body.question, '什么是固态电池？');
  assert.equal(calls[0].body.search_provider, 'kimi');
  assert.equal(JSON.stringify(request), original);
});

test('explicit search terms override the question and exclude subtitle or note bodies', async t => {
  let body;
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    body = JSON.parse(options.body);
    return { ok: true, json: async () => ({ id: 'job-2' }) };
  });
  await sendChat('video-1', { ...request, search_query: '  固态电池 循环寿命  ', subtitles: 'private video text', notes: 'private notes' });
  assert.equal(body.search_query, '固态电池 循环寿命');
  assert.equal(body.time, 12);
  assert.deepEqual(body.cue_ids, ['cue-1']);
  assert.equal(body.scope, 'current');
  assert.ok(!('subtitles' in body) && !('notes' in body));
});

test('automatic search terms collapse whitespace and bound Unicode by characters', () => {
  assert.equal(resolveSearchQuery('  compare\n  concepts \t please ', ''), 'compare concepts please');
  const question = '电池🔋'.repeat(80);
  const query = resolveSearchQuery(question, '   ');
  assert.equal(Array.from(query).length, 128);
  assert.equal(query, Array.from(question).slice(0, 128).join(''));
  assert.throws(() => resolveSearchQuery('valid', '字'.repeat(129)), /128/);
});

test('disabled search sends no query and empty questions fail before any request', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    calls.push(JSON.parse(options.body));
    return { ok: true, json: async () => ({ id: 'job-3' }) };
  });
  await sendChat('video-1', { ...request, search: false, search_query: 'unused'.repeat(40) });
  assert.equal(calls[0].search, false);
  assert.equal(calls[0].search_query, '');
  await assert.rejects(sendChat('video-1', { ...request, question: '  ' }), /请输入问题/);
  await assert.rejects(sendChat('video-1', { ...request, search_query: '字'.repeat(129) }), /128/);
  assert.equal(calls.length, 1);
});

test('request failures preserve the server error and leave the draft available for retry', async t => {
  const original = JSON.stringify(request);
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, json: async () => ({ error: '此视频已有任务运行，请先等待或停止' }) }));
  await assert.rejects(sendChat('video-1', request), /已有任务运行/);
  assert.equal(JSON.stringify(request), original);
});
