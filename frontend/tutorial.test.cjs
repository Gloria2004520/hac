const test = require('node:test');
const assert = require('node:assert/strict');
const { generateTutorial, normalizeTutorial, MODEL } = require('./tutorial.cjs');
const raw = { title: '换盆', tools: [{ name: '新盆', required: true }], steps: [{ title: '放入新盆', actions: ['放稳'], done: '已放稳', cue_id: 2, timestamp: 999, wait_minutes: -1 }] };
const segments = [{ id: 2, start: 12.5, end: 14, text: '接下来放到新盆里' }];
const provider = content => ({ ok: true, json: async () => ({ choices: [{ message: { content } }] }) });

test('timestamps can only come from supplied subtitle cues, not AI fields', () => {
  const tutorial = normalizeTutorial(raw, { source: 'subtitle', segments });
  assert.equal(tutorial.steps[0].timestamp, 12.5);
  assert.equal(tutorial.steps[0].origin, 'subtitle');
  assert.equal(tutorial.steps[0].evidence, segments[0].text);
  assert.equal(tutorial.steps[0].wait_minutes, 0);
  const manual = normalizeTutorial(raw, { source: 'manual', segments: [] });
  assert.equal(manual.steps[0].timestamp, null);
  assert.equal(manual.steps[0].origin, 'ai');
});
test('rejects incomplete structured responses without replacing them with a demo', () => {
  assert.throws(() => normalizeTutorial({ steps: [] }, {}));
  assert.throws(() => normalizeTutorial({ steps: [{ title: '动作' }] }, {}));
});
test('manual generation calls only the free model', async () => {
  let count = 0;
  const tutorial = await generateTutorial({ text: '先准备新盆和盆土，取出旧盆中的植物，检查根系，再放入新盆中。' }, {
    key: 'test-key', fetchImpl: async (url, options) => {
      count++; assert.equal(url, 'https://openrouter.ai/api/v1/chat/completions');
      assert.equal(JSON.parse(options.body).model, MODEL);
      return provider(JSON.stringify(raw));
    },
  });
  assert.equal(count, 1); assert.equal(tutorial.source, 'manual');
});
test('subtitle generation retrieves evidence from backend before model call', async () => {
  let calls = 0;
  const tutorial = await generateTutorial({ videoId: 'abc' }, {
    key: 'test-key', backendUrl: 'http://backend', fetchImpl: async url => {
      calls++; return url.startsWith('http://backend') ? { ok: true, json: async () => ({ segments }) } : provider(JSON.stringify(raw));
    },
  });
  assert.equal(calls, 2); assert.equal(tutorial.steps[0].timestamp, 12.5);
});
test('no model call after missing subtitles or invalid input', async () => {
  let calls = 0;
  const options = { key: 'test', backendUrl: 'http://backend', fetchImpl: async () => { calls++; return { ok: false, status: 422, json: async () => ({ detail: '没有字幕' }) }; } };
  await assert.rejects(generateTutorial({ videoId: 'abc' }, options), /没有字幕/);
  await assert.rejects(generateTutorial({ text: '标题' }, options), /教程文字/);
  await assert.rejects(generateTutorial({ videoId: '../bad' }, options), /ID/);
  assert.equal(calls, 1);
});
test('rate limiting has no paid fallback or automatic retries', async () => {
  let count = 0;
  await assert.rejects(generateTutorial({ text: '先准备新盆和盆土，取出旧盆中的植物，检查根系，再放入新盆中。' }, { key: 'test', fetchImpl: async () => { count++; return { ok: false, status: 429 }; } }), /限流/);
  assert.equal(count, 1);
});
