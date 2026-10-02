// Optional browser QA with independent browser context; AI and platform requests are mocked.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.DEMO_URL || 'http://127.0.0.1:8777';
const { demo } = require('./dist/tutorial-example.js');

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE || undefined, headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage(), errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*youtube*', route => route.abort());
    await page.goto(base + '/');
    await page.getByRole('link', { name: /体验教程拆解/ }).click();
    await page.getByRole('heading', { name: '把掉下来的纽扣缝回去' }).waitFor();
    assert.equal(await page.getByRole('checkbox').count(), 0);
    assert.equal(await page.getByRole('textbox').count(), 0);
    assert.equal(await page.getByRole('heading', { name: /穿针并打结/ }).count(), 1);
    assert.equal(await page.getByRole('heading', { name: /收好工具/ }).count(), 1);
    assert.equal(await page.getByRole('link', { name: /打开 YouTube/ }).isVisible(), false);
    await page.screenshot({ path: '/private/tmp/slowly-sop-mobile.png', fullPage: true });
    const downloadEvent = page.waitForEvent('download'); await page.getByRole('button', { name: '导出 SOP', exact: true }).click();
    const download = await downloadEvent;
    assert.equal(download.suggestedFilename(), 'slowly-tutorial-sop.json');
    await page.getByRole('button', { name: '编辑 SOP', exact: true }).click();
    await page.getByRole('textbox', { name: '任务名称' }).fill('我的纽扣教程');
    await page.getByRole('button', { name: '保存 SOP', exact: true }).click();
    await page.reload(); await page.getByRole('heading', { name: '我的纽扣教程' }).waitFor();
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.screenshot({ path: '/private/tmp/slowly-sop-desktop.png', fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    const manual = await context.newPage(); manual.on('pageerror', e => errors.push(e.message));
    await manual.goto(base + '/video.html');
    await manual.getByRole('textbox', { name: '教程文字' }).fill('把普通四孔纽扣放到衣服对应扣眼的位置，穿针打结，交叉缝合固定，收线后检查。');
    await manual.route('**/api/tutorial', route => route.fulfill({ status: 429, json: { error: '免费模型正在限流' } }));
    await manual.getByRole('button', { name: '根据文字生成 SOP' }).click();
    await manual.getByRole('alert').filter({ hasText: '免费模型正在限流' }).waitFor();
    assert.match(await manual.getByRole('textbox', { name: '教程文字' }).inputValue(), /普通四孔纽扣/);
    await manual.unroute('**/api/tutorial');
    await manual.route('**/api/tutorial', route => route.fulfill({ json: { tutorial: structuredClone(demo) } }));
    await manual.getByRole('button', { name: '根据文字生成 SOP' }).click();
    await manual.getByRole('heading', { name: '把掉下来的纽扣缝回去' }).waitFor();
    assert.equal(await manual.getByRole('checkbox').count(), 0);
    await manual.locator('input[type=file]').setInputFiles({ name: 'invalid.json', mimeType: 'application/json', buffer: Buffer.from('{}') });
    await manual.getByRole('alert').filter({ hasText: 'SOP 格式不正确' }).waitFor();
    await manual.getByRole('heading', { name: '把掉下来的纽扣缝回去' }).waitFor();

    // A real browser-generated video fixture exercises canvas extraction without downloading videos.
    const data = await page.evaluate(async () => {
      const canvas = document.createElement('canvas'); canvas.width = 320; canvas.height = 180;
      const ctx = canvas.getContext('2d'); ctx.fillStyle = '#f8d65b'; ctx.fillRect(0, 0, 320, 180);
      const stream = canvas.captureStream(10), recorder = new MediaRecorder(stream, { mimeType: 'video/webm' }), chunks = [];
      const recording = new Promise(resolve => { recorder.ondataavailable = e => chunks.push(e.data); recorder.onstop = resolve; });
      recorder.start(); await new Promise(resolve => setTimeout(resolve, 400)); recorder.stop(); await recording; stream.getTracks().forEach(t => t.stop());
      return Array.from(new Uint8Array(await new Blob(chunks).arrayBuffer()));
    });
    const video = await context.newPage(); video.on('pageerror', e => errors.push(e.message));
    await video.route('**/api/videos/fixture', route => route.fulfill({ json: { id: 'fixture', status: 'ready', title: '视频测试', source_url: 'https://youtube.com/watch?v=abc', progress: 100 } }));
    await video.route('**/api/videos/fixture/content', route => route.fulfill({ body: Buffer.from(data), contentType: 'video/webm' }));
    const fixture = structuredClone(demo); fixture.source = 'subtitle'; fixture.steps[0].timestamp = 0; fixture.steps[0].origin = 'subtitle'; fixture.steps[0].evidence = '穿针并打结';
    await video.route('**/api/tutorial', route => route.fulfill({ json: { tutorial: fixture } }));
    await video.route('**/*youtube*', route => route.abort());
    await video.goto(base + '/video.html?id=fixture');
    await video.getByRole('button', { name: '从视频字幕生成 SOP' }).click();
    await video.waitForFunction(() => document.getElementById('player').readyState >= 2);
    await video.getByRole('button', { name: '提取当前暂停画面' }).first().click();
    await video.getByRole('img', { name: /步骤 1 视频参考帧/ }).waitFor();
    assert.equal(await video.getByRole('img', { name: /步骤 1 视频参考帧/ }).evaluate(img => img.naturalWidth), 640);
    await video.reload(); await video.getByRole('img', { name: /步骤 1 视频参考帧/ }).waitFor();
    assert.equal(await video.getByRole('checkbox').count(), 0);
    assert.deepEqual(errors, []);
    console.log('Browser QA passed: mobile/desktop SOP, edit/export, refresh persistence, free-model failure recovery, invalid import, real video frame extraction. No live AI requests.');
    await context.close();
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
