const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const ts = require('typescript');

const compiled = ts.transpileModule(readFileSync(resolve(__dirname, '../src/learning-shortcuts.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const shortcuts = {};
new Function('exports', compiled)(shortcuts);
const { handlePlaybackShortcut, stepPlaybackRate, playbackRates, toggleSubtitleMode } = shortcuts;

function key(key, options = {}) {
  return {
    key, code: '', ctrlKey: false, altKey: false, metaKey: false, repeat: false,
    isComposing: false, keyCode: 0, defaultPrevented: false, target: null,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() { this.stopped = true; },
    ...options,
  };
}

test('page and fullscreen keys dispatch once and consume the native video action', () => {
  for (const [value, expected] of Object.entries({ f: 'fullscreen', F: 'fullscreen', c: 'faster', X: 'slower', s: 'subtitles', ' ': 'play', ArrowLeft: 'back', ArrowRight: 'forward', m: 'mute' })) {
    const actions = [];
    const event = key(value);
    assert.equal(handlePlaybackShortcut(event, action => actions.push(action)), true);
    assert.deepEqual(actions, [expected]);
    assert.equal(event.defaultPrevented, true);
    assert.equal(event.stopped, true);
  }
});

test('typing, IME, held keys, browser combinations, and import dialogs retain their keys', () => {
  for (const options of [{ ctrlKey: true }, { altKey: true }, { metaKey: true }, { repeat: true }, { isComposing: true }, { keyCode: 229 }, { defaultPrevented: true }]) {
    assert.equal(handlePlaybackShortcut(key('c', options), () => assert.fail('unwanted playback action')), false);
  }
  assert.equal(handlePlaybackShortcut(key('f'), () => assert.fail('modal shortcut'), true), false);
  assert.equal(handlePlaybackShortcut(key('Escape'), () => assert.fail('native Esc exit must remain available')), false);
  for (const selector of ['input', 'textarea', '[contenteditable]', '[role="textbox"]', '[role="combobox"]', '[role="spinbutton"]', '[role="dialog"]', '[aria-modal="true"]']) {
    const target = { closest: query => query.includes(selector) ? target : null };
    const event = key('x', { target });
    assert.equal(handlePlaybackShortcut(event, () => assert.fail(selector)), false);
    assert.equal(event.defaultPrevented, false);
  }
  assert.equal(handlePlaybackShortcut(key('s', { target: { isContentEditable: true } }), () => assert.fail('editable ancestor')), false);
});

test('physical letter keys work with a Chinese IME outside text editors', () => {
  for (const [code, expected] of Object.entries({ KeyF: 'fullscreen', KeyC: 'faster', KeyX: 'slower', KeyS: 'subtitles', KeyM: 'mute' })) {
    const actions = [];
    const event = key('Process', { code, keyCode: 229, isComposing: true });
    assert.equal(handlePlaybackShortcut(event, action => actions.push(action)), true);
    assert.deepEqual(actions, [expected]);
    assert.equal(event.defaultPrevented, true);
    const editor = { isContentEditable: true };
    assert.equal(handlePlaybackShortcut(key('Process', { code, target: editor, keyCode: 229, isComposing: true }), () => assert.fail('IME text was intercepted')), false);
  }
});

test('letter shortcuts work after selecting a speed or changing a non-text input', () => {
  const targetFor = (selector, type) => ({
    type,
    closest(query) { return query.split(',').includes(selector) ? this : null; },
  });
  for (const target of [targetFor('select'), targetFor('input', 'range'), targetFor('input', 'checkbox'), targetFor('[role="slider"]')]) {
    for (const value of ['f', 'c', 'x', 's']) {
      const actions = [];
      assert.equal(handlePlaybackShortcut(key(value, { target }), action => actions.push(action)), true);
      assert.equal(actions.length, 1);
    }
    for (const value of [' ', 'ArrowLeft', 'ArrowRight']) {
      assert.equal(handlePlaybackShortcut(key(value, { target }), () => assert.fail('form control key intercepted')), false);
    }
  }
  for (const type of ['text', 'search', 'number', 'password', 'email']) {
    assert.equal(handlePlaybackShortcut(key('c', { target: targetFor('input', type) }), () => assert.fail('typing interrupted')), false);
  }
});

test('focused controls keep Space activation and arrow navigation', () => {
  for (const selector of ['button', 'a', 'summary', '[role="separator"]', '[role="tab"]']) {
    const target = { closest: query => query.split(',').includes(selector) ? target : null };
    for (const value of [' ', 'ArrowLeft', 'ArrowRight']) {
      assert.equal(handlePlaybackShortcut(key(value, { target }), () => assert.fail('control key intercepted')), false);
    }
    const actions = [];
    handlePlaybackShortcut(key('f', { target }), action => actions.push(action));
    assert.deepEqual(actions, ['fullscreen']);
  }
});

test('repeated speed presses stay precise, visible in the menu, and within playback limits', () => {
  let rate = 1;
  const change = action => { rate = stepPlaybackRate(rate, action === 'faster' ? .1 : -.1); };
  for (let i = 0; i < 3; i++) handlePlaybackShortcut(key('c'), change);
  assert.equal(rate, 1.3);
  handlePlaybackShortcut(key('x'), change);
  assert.equal(rate, 1.2);
  assert.ok(playbackRates(rate).includes(1.2));
  assert.equal(new Set(playbackRates(1)).size, playbackRates(1).length);
  for (let i = 0; i < 40; i++) handlePlaybackShortcut(key('c'), change);
  assert.equal(rate, 3);
  for (let i = 0; i < 40; i++) handlePlaybackShortcut(key('x'), change);
  assert.equal(rate, .25);
  assert.equal(stepPlaybackRate(.75, .1), .85);
});

test('subtitle toggle restores the prior language for each video and handles a reload while hidden', () => {
  for (const mode of ['source', 'target', 'bilingual']) {
    assert.equal(toggleSubtitleMode(mode, undefined, true, true), 'off');
    assert.equal(toggleSubtitleMode('off', mode, true, true), mode);
  }
  assert.equal(toggleSubtitleMode('off', undefined, true, false), 'source');
  assert.equal(toggleSubtitleMode('off', undefined, false, true), 'target');
  assert.equal(toggleSubtitleMode('off', undefined, true, true), 'bilingual');
});
