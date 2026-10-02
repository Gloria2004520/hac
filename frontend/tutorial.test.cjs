const test = require('node:test');
const assert = require('node:assert/strict');
const { generateTutorial, normalizeTutorial, MODEL, parseTimedTranscript } = require('./tutorial.cjs');
const F = require('./dist/tutorial-frames.js');
const raw = { title: '换盆', tools: [{ name: '新盆', required: true }], steps: [{ title: '放入新盆', actions: ['放稳'], done: '已放稳', cue_id: 2, timestamp: 999, wait_minutes: -1 }] };
const segments = [{ id: 2, start: 12.5, end: 14, text: '接下来放到新盆里' }];
const provider = content => ({ ok: true, json: async () => ({ choices: [{ message: { content } }] }) });

test('timestamps can only come from supplied subtitle cues, not AI fields', () => {
  const tutorial = normalizeTutorial(raw, { source: 'subtitle', segments });
  assert.equal(tutorial.steps[0].timestamp, 12.5);
  assert.equal(tutorial.steps[0].clip_end, 14);
  assert.equal(tutorial.steps[0].origin, 'subtitle');
  assert.equal(tutorial.steps[0].evidence, segments[0].text);
  assert.equal(tutorial.steps[0].wait_minutes, 0);
  const manual = normalizeTutorial(raw, { source: 'manual', segments: [] });
  assert.equal(manual.steps[0].timestamp, null);
  assert.equal(manual.steps[0].origin, 'ai');
});
test('step range is grounded in all matched cues and ignores model range fields', () => {
  const draft = structuredClone(raw); draft.steps[0].cue_ids = [2, 3, 999]; draft.steps[0].clip_end = 300;
  const tutorial = normalizeTutorial(draft, { source: 'subtitle', segments: [...segments, { id: 3, start: 14, end: 20, text: '然后填土' }] });
  assert.equal(tutorial.steps[0].timestamp, 12.5); assert.equal(tutorial.steps[0].clip_end, 20);
  assert.equal(tutorial.steps[0].evidence, '接下来放到新盆里 然后填土');
});
test('SRT and VTT imports preserve real caption timestamps', () => {
  const captions = '\uFEFF1\n00:00:01,200 --> 00:00:04,000\n穿针\n打结\n\n2\n00:00:04,000 --> 00:00:08,000\n缝合';
  assert.deepEqual(parseTimedTranscript(captions), [{ id: 1, start: 1.2, end: 4, text: '穿针 打结' }, { id: 2, start: 4, end: 8, text: '缝合' }]);
  assert.equal(parseTimedTranscript('WEBVTT\n\n00:01.200 --> 00:02.200 align:start\n<c>动作</c>')[0].start, 1.2);
  assert.deepEqual(parseTimedTranscript('只有文字，没有时间点'), []);
});
test('single-frame drafts migrate without losing their image', () => {
  const image = { time: 12.5, url: 'data:image/jpeg;base64,AA==' };
  const step = { frame: image }; F.migrate(step);
  assert.deepEqual(step.frames, [image]); assert.equal(step.frame, undefined);
  F.add(step, { time: 5, url: image.url }); assert.equal(step.frames[0].time, 5);
  assert.throws(() => F.add(step, { time: 5.01, url: image.url }), /已经有画面/);
});
test('frame limits and sampling do not overwrite existing frames or exceed the video', () => {
  const step = { frames: [] };
  for (let i = 0; i < 8; i++) F.add(step, { time: i, url: 'image' });
  assert.throws(() => F.add(step, { time: 9, url: 'image' }), /最多保存/); assert.equal(step.frames.length, 8);
  const points = F.sample(2, 8, 10); assert.equal(points.length, 3); assert(points.every(t => t >= 2 && t < 8));
  assert.throws(() => F.sample(8, 12, 10), /超出视频/); assert.throws(() => F.sample(3, 2, 10), /起止时间/);
  assert(F.sample(0, .01, 1).every(t => t >= 0));
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
test('local subtitle generation supplies timed evidence without backend video requests', async () => {
  const text = '1\n00:00:01,000 --> 00:00:05,000\n取出旧盆中的植物，检查根系，然后放入新盆。';
  const response = structuredClone(raw); response.steps[0].cue_ids = [1];
  const tutorial = await generateTutorial({ text }, { key: 'test', fetchImpl: async (url, options) => {
    assert.equal(url, 'https://openrouter.ai/api/v1/chat/completions');
    const evidence = JSON.parse(JSON.parse(options.body).messages[1].content);
    assert.equal(evidence.source, 'manual_subtitle'); assert.equal(evidence.segments[0].end, 5);
    return provider(JSON.stringify(response));
  } });
  assert.equal(tutorial.steps[0].timestamp, 1); assert.equal(tutorial.steps[0].clip_end, 5);
  assert.equal(tutorial.source, 'manual_subtitle');
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
