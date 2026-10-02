(() => {
  'use strict';
  const root = document.getElementById('workbench');
  const F = window.TutorialFrames;
  const params = new URLSearchParams(location.search);
  const videoId = params.get('id'), demoMode = params.get('demo') === 'button';
  const storageKey = 'slowly-sop-v1:' + (demoMode ? 'button-example' : videoId || 'manual');
  let tutorial = null, busy = false, editorOpen = false, generatorOpen = false, transcriptText = '', errorText = '', saveWarning = '', localFile = null, localURL = null;
  const hasVideo = () => Boolean(localFile || (videoId && !demoMode));
  const videoReady = () => Boolean(localFile || window.tutorialVideo?.status === 'ready');
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const button = (text, action, cls = '', disabled = false) => {
    const node = el('button', text, cls); node.type = 'button'; node.disabled = disabled;
    node.addEventListener('click', action); return node;
  };
  const row = (...children) => { const node = el('div', null, 'row'); node.append(...children); return node; };
  const notice = text => el('p', text, 'notice');
  const time = value => `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}.${Math.floor((value % 1) * 10)}`;
  function persist() {
    if (!tutorial) return;
    try { localStorage.setItem(storageKey, JSON.stringify({ version: 1, tutorial })); saveWarning = ''; }
    catch { saveWarning = '浏览器无法保存草稿，请导出 SOP 保存。'; }
  }
  function validate(value) {
    const strings = (items, max) => Array.isArray(items) && items.length <= max && items.every(x => typeof x === 'string' && x.length <= 2000);
    if (!value || value.version !== 1 || typeof value.title !== 'string' || !value.title.trim() || value.title.length > 300
      || !strings(value.conditions, 12) || !Array.isArray(value.tools) || value.tools.length > 20
      || !Array.isArray(value.steps) || !value.steps.length || value.steps.length > 16) throw Error('SOP 格式不正确');
    if (new Set(value.steps.map(s => s.id)).size !== value.steps.length || new Set(value.tools.map(t => t.id)).size !== value.tools.length) throw Error('步骤或工具 ID 重复');
    const safeId = id => typeof id === 'string' && /^[a-zA-Z0-9-]{1,64}$/.test(id) && !['constructor', 'prototype', '__proto__'].includes(id);
    const safeImage = image => typeof image === 'string' && image.length <= 400000 && /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(image);
    for (const tool of value.tools) if (!safeId(tool.id) || typeof tool.name !== 'string' || !tool.name.trim() || typeof tool.amount !== 'string' || typeof tool.alternative !== 'string' || typeof tool.required !== 'boolean') throw Error('工具格式不正确');
    for (const step of value.steps) {
      F.migrate(step);
      if (!safeId(step.id) || typeof step.title !== 'string' || !step.title.trim() || !strings(step.actions, 8) || !step.actions.length
        || typeof step.done !== 'string' || !step.done.trim() || !strings(step.safety, 8) || !strings(step.mistakes, 8)
        || typeof step.recovery !== 'string' || typeof step.evidence !== 'string'
        || !Number.isInteger(step.wait_minutes) || step.wait_minutes < 0 || step.wait_minutes > 1440
        || (step.timestamp !== null && (!Number.isFinite(step.timestamp) || step.timestamp < 0 || step.timestamp > 86400))
        || (step.clip_end !== null && (!Number.isFinite(step.clip_end) || step.clip_end <= (step.timestamp ?? 0)))
        || step.frames.length > F.LIMIT || step.frames.some(f => !f || !safeImage(f.url) || !Number.isFinite(f.time) || f.time < 0)) throw Error('步骤格式不正确');
    }
    return value;
  }
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (saved?.version === 1) tutorial = validate(saved.tutorial);
  } catch { saveWarning = '本地草稿无法读取，请重新生成或导入 SOP。'; }
  if (!tutorial && demoMode) tutorial = validate(structuredClone(window.TutorialExample.demo));
  if (tutorial?.video_ref?.type === 'local') document.getElementById('localVideoHint').textContent = `请重新选择原视频「${tutorial.video_ref.name}」以继续提取画面；已有 SOP 和画面已保留。`;

  function selectLocalVideo(file) {
    if (!file || busy) return;
    if (!file.type.startsWith('video/') && !/\.(mp4|mov|webm|m4v)$/i.test(file.name)) { errorText = '请选择视频文件'; render(); return; }
    const ref = { type: 'local', name: file.name, size: file.size, modified: file.lastModified };
    const old = tutorial?.video_ref;
    if (old && JSON.stringify(old) !== JSON.stringify(ref)) {
      if (!confirm('更换视频会移除原参考帧和片段时间，SOP 文字会保留。继续吗？')) return;
      tutorial.steps.forEach(s => { s.frames = []; s.timestamp = null; s.clip_end = null; s.evidence = ''; s.origin = 'manual'; });
      tutorial.source = 'manual'; tutorial.source_note = '保留的 SOP 文字尚未与新视频核对，请调整后再使用。';
    }
    if (localURL) URL.revokeObjectURL(localURL);
    localFile = file; localURL = URL.createObjectURL(file);
    if (tutorial) { tutorial.video_ref = ref; persist(); }
    window.setLocalTutorialVideo(localURL, file.name);
    document.getElementById('localVideoHint').textContent = `${file.name} · 仅在浏览器读取。刷新后需重新选择同一视频；SOP 和已提取画面仍可保留。`;
    errorText = ''; render();
  }
  document.getElementById('localVideoInput').addEventListener('change', event => selectLocalVideo(event.target.files[0]));
  document.getElementById('player').addEventListener('error', () => { if (localFile) { errorText = '浏览器无法播放这个视频，请使用可播放的 MP4 或 WebM 格式。'; render(); } });
  document.getElementById('player').addEventListener('loadedmetadata', event => {
    const video = event.target;
    // Some camera/MediaRecorder WebM files omit duration until their final cluster is read.
    if (localFile && video.duration === Infinity) {
      video.addEventListener('seeked', () => { if (Number.isFinite(video.duration)) video.currentTime = 0; }, { once: true });
      video.currentTime = 1000000;
    }
  });

  function exportDraft() {
    const blob = new Blob([JSON.stringify({ version: 1, tutorial }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob), anchor = el('a');
    anchor.href = url; anchor.download = 'slowly-tutorial-sop.json'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function importDraft(file) {
    if (!file || busy) return;
    try {
      if (file.size > 32000000) throw Error('文件过大，请使用小于 32MB 的 SOP 草稿');
      const record = JSON.parse(await file.text()), draft = validate(record.tutorial || record);
      draft.source = 'manual'; draft.source_note = '导入的 SOP 草稿，请核对文字与原视频；画面仅供参考。';
      for (const s of draft.steps) { s.origin = 'manual'; s.evidence = ''; }
      tutorial = draft; editorOpen = false; generatorOpen = false; errorText = ''; persist(); render();
    } catch (error) { errorText = error.message; render(); }
  }
  function importButton() {
    const label = el('label', '导入 SOP', 'file-button'); const input = el('input');
    input.type = 'file'; input.accept = '.json,application/json'; input.disabled = busy; input.setAttribute('aria-label', '导入 SOP');
    input.onchange = () => importDraft(input.files[0]); label.append(input); return label;
  }
  async function generate(useVideo) {
    if (busy) return;
    busy = true; errorText = ''; render();
    try {
      const response = await fetch('/api/tutorial', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(useVideo ? { videoId } : { text: transcriptText }), signal: AbortSignal.timeout(110000),
      });
      let result;
      try { result = await response.json(); } catch { throw Error('服务没有返回有效内容，请确认服务已启动'); }
      if (!response.ok) throw Error(result.error || 'SOP 生成失败');
      tutorial = validate(result.tutorial); generatorOpen = false;
      if (localFile) tutorial.video_ref = { type: 'local', name: localFile.name, size: localFile.size, modified: localFile.lastModified };
      else if (videoId) tutorial.video_ref = { type: 'saved', id: videoId };
      persist();
    } catch (error) { errorText = error.name === 'TimeoutError' ? '处理超时，请重试或粘贴教程文字。' : error.message; }
    finally { busy = false; render(); }
  }
  function generator() {
    root.append(el('p', '视频拆解 · 分步骤 SOP', 'eyebrow'), el('h2', '把教程整理成清晰的步骤'), notice('优先根据真实字幕整理，没有字幕时可粘贴教程文字。输出为可编辑的 SOP 草稿；尚未进行视频视觉分析。'));
    if (videoId && !localFile) {
      const ready = window.tutorialVideo?.status === 'ready';
      const make = button(busy ? '正在提取字幕并整理…' : '从视频字幕生成 SOP', () => generate(true), 'primary', busy || !ready); make.id = 'subtitleGenerate'; root.append(row(make));
      const hint = el('p', ready ? '重复生成会使用本机缓存的字幕。' : '等待视频下载完成后可提取字幕，也可以先用下方文字生成。', 'subtle'); hint.id = 'subtitleHint'; root.append(hint);
    }
    const label = el('label', '教程文字或字幕'); const text = el('textarea'); text.value = transcriptText; text.maxLength = 20000; text.rows = 7;
    text.placeholder = '请粘贴具体操作、材料和注意事项（20～20000 字）。仅有标题无法可靠拆解。'; text.setAttribute('aria-label', '教程文字');
    text.oninput = () => { transcriptText = text.value; document.getElementById('textGenerate').disabled = busy || transcriptText.trim().length < 20; }; label.append(text); root.append(label);
    const subtitleLabel = el('label', '导入字幕 / 讲解文字', 'file-button'), subtitleFile = el('input'); subtitleFile.type = 'file'; subtitleFile.accept = '.srt,.vtt,.txt'; subtitleFile.disabled = busy; subtitleFile.setAttribute('aria-label', '导入字幕或讲解文字');
    subtitleFile.onchange = async () => { try { const file = subtitleFile.files[0]; if (!file) return; if (file.size > 100000) throw Error('字幕文件过大，请截取操作片段'); const value = await file.text(); if (value.length > 20000) throw Error('请使用不超过 20000 字的字幕片段'); transcriptText = value; errorText = ''; render(); } catch (error) { errorText = error.message; render(); } }; subtitleLabel.append(subtitleFile);
    const make = button(busy ? '正在整理 SOP…' : '根据文字生成 SOP', () => generate(false), 'primary', busy || transcriptText.trim().length < 20); make.id = 'textGenerate'; root.append(row(make, subtitleLabel, importButton()));
    if (localFile) root.append(el('p', '导入带时间点的 SRT/VTT 字幕后，SOP 可以关联视频片段并提取多张画面。没有字幕时仍需提供教程文字。', 'subtle'));
    const example = el('a', '看看缝纽扣 SOP 示例 →', 'source'); example.href = '/video.html?demo=button'; root.append(example);
    root.append(el('p', '仅使用免费模型生成，不会回退到付费模型。', 'subtle'));
    if (tutorial) root.append(row(button('返回当前 SOP', () => { generatorOpen = false; errorText = ''; render(); }, '', busy)), el('p', '成功生成后才会替换当前草稿。', 'subtle'));
  }
  function jumpVideo(timestamp) {
    const video = document.getElementById('player');
    if (video.hidden || !Number.isFinite(video.duration)) { errorText = '视频尚未就绪，请等待下载和加载完成。'; render(); return; }
    video.currentTime = Math.max(0, Math.min(timestamp, Math.max(0, video.duration - .1))); video.pause(); video.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  function frameData(video) {
    if (video.hidden || video.readyState < 2 || !video.videoWidth || video.seeking) throw Error('请先在视频中暂停到想保存的画面，等待加载后再提取。');
    const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = Math.round(640 * video.videoHeight / video.videoWidth);
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    return { url: canvas.toDataURL('image/jpeg', .7), time: video.currentTime };
  }
  function captureFrame(step) {
    if (busy) return;
    try { F.add(step, frameData(document.getElementById('player'))); errorText = ''; persist(); render(); }
    catch (error) { errorText = error.message; render(); }
  }
  async function captureCueFrame(step) {
    if (busy) return;
    const video = document.getElementById('player');
    if (video.hidden || video.readyState < 1 || !Number.isFinite(video.duration)) { errorText = '视频尚未就绪，请稍后再提取画面。'; render(); return; }
    busy = true; errorText = ''; video.pause(); render();
    const target = Math.min(step.timestamp, Math.max(0, video.duration - .1));
    try {
      if (Math.abs(video.currentTime - target) > .02 || video.readyState < 2) {
        await new Promise((resolve, reject) => {
          const timeout = setTimeout(() => { cleanup(); reject(Error('画面加载超时，请在播放器中手动暂停到该位置。')); }, 8000);
          const done = () => { cleanup(); resolve(); };
          const cleanup = () => { clearTimeout(timeout); video.removeEventListener('seeked', done); };
          video.addEventListener('seeked', done, { once: true }); video.currentTime = target;
        });
      }
      F.add(step, frameData(video)); persist();
    } catch (error) { errorText = error.message; }
    finally { busy = false; render(); }
  }
  async function seekFrame(video, target) {
    if (Math.abs(video.currentTime - target) > .015 || video.readyState < 2) {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => { cleanup(); reject(Error('视频画面加载超时，请换一个片段重试。')); }, 8000);
        const done = () => { cleanup(); resolve(); };
        const cleanup = () => { clearTimeout(timer); video.removeEventListener('seeked', done); };
        video.addEventListener('seeked', done, { once: true }); video.currentTime = target;
      });
    }
    return frameData(video);
  }
  async function captureSequence(step) {
    if (busy) return;
    const video = document.getElementById('player');
    try {
      const points = F.sample(step.timestamp, step.clip_end, video.duration);
      const newPoints = points.filter(point => !step.frames.some(frame => Math.abs(frame.time - point) < .06));
      if (!newPoints.length) throw Error('这个片段的参考画面已经提取，可以调整片段或手动补充画面。');
      if (step.frames.length + newPoints.length > F.LIMIT) throw Error('每步最多 8 张画面，请先删除不需要的画面。');
      if (video.hidden) throw Error('请先选择或加载原视频。');
      busy = true; errorText = ''; video.pause(); render();
      const draft = { frames: [...step.frames] };
      for (const point of newPoints) F.add(draft, await seekFrame(video, point));
      step.frames = draft.frames; persist();
    } catch (error) { errorText = error.message; }
    finally { busy = false; render(); }
  }
  async function captureAllFrames() {
    if (busy) return;
    const video = document.getElementById('player');
    const eligible = tutorial.steps.filter(s => s.timestamp !== null && s.clip_end !== null);
    busy = true; errorText = ''; video.pause(); render();
    let extracted = 0, failed = 0;
    try {
      for (const step of eligible) {
        try {
          const points = F.sample(step.timestamp, step.clip_end, video.duration).filter(point => !step.frames.some(frame => Math.abs(frame.time - point) < .06));
          if (!points.length) continue;
          if (step.frames.length + points.length > F.LIMIT) { failed++; continue; }
          const draft = { frames: [...step.frames] };
          for (const point of points) F.add(draft, await seekFrame(video, point));
          step.frames = draft.frames; extracted += points.length; persist();
        } catch { failed++; }
      }
      const missing = tutorial.steps.length - eligible.length;
      if (failed || missing) errorText = `已追加 ${extracted} 张画面。${missing ? `${missing} 步缺少片段时间，请先填写。` : ''}${failed ? `${failed} 步提取失败或已达到上限，可在对应步骤重试。` : ''}`;
    } finally { busy = false; render(); }
  }
  function breakdown() {
    root.append(el('p', '视频拆解 · SOP 草稿', 'eyebrow'), el('h2', tutorial.title), notice(tutorial.source_note));
    root.append(row(button('编辑 SOP', () => { editorOpen = true; render(); }, '', busy), button('导出 SOP', exportDraft, '', busy), importButton(), button('重新拆解', () => { generatorOpen = true; errorText = ''; render(); }, '', busy)));
    if (hasVideo()) root.append(row(button(busy ? '正在提取画面…' : '一键提取各步骤多张关键帧', captureAllFrames, 'primary', busy || !videoReady() || !tutorial.steps.some(s => s.timestamp !== null && s.clip_end !== null))), el('p', '按每步片段采样开始、中间、结束的画面。缺少时间范围的步骤需先填写，已有画面不会被覆盖。', 'subtle'));
    root.append(el('h3', '工具与材料'));
    if (!tutorial.tools.length) root.append(el('p', '资料未明确说明工具，请补充确认。', 'subtle'));
    for (const tool of tutorial.tools) {
      const item = el('div', null, 'tool-row');
      item.append(el('span', tool.required ? '必需' : '可选', 'pill'), el('strong', tool.name), el('span', tool.amount || '用量待确认', 'subtle')); root.append(item);
      if (tool.alternative) root.append(el('p', tool.alternative, 'subtle'));
    }
    if (tutorial.conditions.length) { root.append(el('h3', '待确认的条件')); tutorial.conditions.forEach(c => root.append(el('p', '• ' + c, 'subtle'))); }
    root.append(el('h3', `分步骤 SOP · ${tutorial.steps.length} 步`));
    tutorial.steps.forEach((step, index) => {
      const card = el('section', null, 'sop-step'); card.setAttribute('aria-label', `步骤 ${index + 1} ${step.title}`);
      card.append(el('h3', `${index + 1}. ${step.title}`));
      const origin = step.origin === 'subtitle' ? `操作参考字幕 ${time(step.timestamp)}；易错点、补救和安全提示包含 AI 补充。` : step.origin === 'example' ? '人工编写的 SOP 示例' : 'AI／用户整理的操作指导，未核对视频画面。';
      card.append(el('p', origin, 'subtle'));
      if (step.evidence) card.append(notice('字幕原文：' + step.evidence));
      card.append(el('h4', `视频关键帧 · ${step.frames.length} 张`));
      if (step.frames.length) {
        const gallery = el('div', null, 'frame-gallery');
        step.frames.forEach((f, frameIndex) => {
          const figure = el('figure'), image = el('img', null, 'frame'); image.src = f.url; image.alt = `步骤 ${index + 1} 关键帧 ${frameIndex + 1} ${time(f.time)}`;
          const caption = el('figcaption'); caption.append(el('span', time(f.time)), row(button('回看这一帧', () => jumpVideo(f.time), '', busy || !hasVideo()), button('删除', () => { step.frames.splice(frameIndex, 1); persist(); render(); }, '', busy)));
          figure.append(image, caption); gallery.append(figure);
        });
        card.append(gallery, el('p', '画面来自原视频。按时间点提取尚未进行语义筛选，请保留能展示动作与结果的画面。', 'subtle'));
      }
      if (hasVideo()) {
        const ready = videoReady();
        const controls = row(button('追加当前暂停画面', () => captureFrame(step), '', busy || !ready || step.frames.length >= F.LIMIT));
        if (step.timestamp !== null) controls.prepend(button(`回看 ${time(step.timestamp)}`, () => jumpVideo(step.timestamp), '', busy || !ready), button('提取字幕时间点画面', () => captureCueFrame(step), '', busy || !ready));
        card.append(controls);
        const range = el('div', null, 'clip-range');
        const startLabel = el('label', '片段开始（秒）'), start = el('input'); start.type = 'number'; start.min = 0; start.step = '.1'; start.value = step.timestamp ?? ''; start.disabled = busy; startLabel.append(start);
        const endLabel = el('label', '片段结束（秒）'), end = el('input'); end.type = 'number'; end.min = 0; end.step = '.1'; end.value = step.clip_end ?? ''; end.disabled = busy; endLabel.append(end);
        const capture = button(busy ? '正在提取…' : '按本步片段提取多帧', () => captureSequence(step), '', busy || !ready || step.frames.length >= F.LIMIT || step.timestamp === null || step.clip_end === null);
        const update = () => {
          const first = start.value === '' ? null : Number(start.value), last = end.value === '' ? null : Number(end.value);
          const valid = Number.isFinite(first) && Number.isFinite(last) && first >= 0 && last > first;
          capture.disabled = busy || !ready || !valid || step.frames.length >= F.LIMIT;
          if (!valid) return;
          if (first !== step.timestamp || last !== step.clip_end) { step.origin = 'manual'; step.evidence = ''; }
          step.timestamp = first; step.clip_end = last; persist();
        };
        start.onchange = end.onchange = update; range.append(startLabel, endLabel, capture); card.append(range, el('p', '片段提取会采样开始、中间、结束的画面，每步最多 8 张。可手动追加或删除。', 'subtle'));
      } else if (!step.frames.length) card.append(el('p', tutorial.video_ref?.type === 'local' ? `请重新选择原视频「${tutorial.video_ref.name}」，再提取画面。` : '请在页面顶部上传视频，或使用已下载的原视频提取画面。', 'subtle'));
      const actions = el('ol', null, 'actions'); step.actions.forEach(action => actions.append(el('li', action))); card.append(actions, el('div', '完成标准：' + step.done, 'done-box'));
      if (step.wait_minutes) card.append(el('p', `等待时间：${step.wait_minutes} 分钟，请核对原教程。`, 'subtle'));
      if (step.mistakes.length || step.recovery) {
        const box = el('div', null, 'mistake-box'); box.append(el('strong', '容易出错的位置')); step.mistakes.forEach(m => box.append(el('div', '• ' + m)));
        if (step.recovery) box.append(el('p', '补救建议：' + step.recovery)); card.append(box);
      }
      if (step.safety.length) { card.append(el('h4', '安全提示')); step.safety.forEach(s => card.append(el('p', '• ' + s, 'subtle'))); }
      root.append(card);
    });
    root.append(el('p', saveWarning || 'SOP 草稿已保存在此浏览器，刷新后可继续查看与编辑。', 'subtle'));
  }
  function editInput(parent, text, value, multiline = false) {
    const label = el('label', text), input = el(multiline ? 'textarea' : 'input'); input.value = value; input.maxLength = multiline ? 5000 : 1000; label.append(input); parent.append(label); return input;
  }
  function editor() {
    const draft = structuredClone(tutorial); root.append(el('h2', '编辑 SOP'), notice('可调整工具、操作、完成标准与提示。修改的内容会标为用户编辑，原有参考画面保留。'));
    const form = el('form'), title = editInput(form, '任务名称', draft.title), conditions = editInput(form, '待确认条件（每行一项）', draft.conditions.join('\n'), true);
    const toolFields = [], tools = el('div'); form.append(el('h3', '工具与材料'), tools);
    const addTool = tool => {
      const box = el('div', null, 'editor-tool'), f = { tool, box };
      f.name = editInput(box, '工具名称', tool.name); f.amount = editInput(box, '用量或待确认', tool.amount); f.alternative = editInput(box, '替代方案／备注', tool.alternative);
      const label = el('label', '工具类型'), select = el('select'); select.setAttribute('aria-label', '工具类型');
      for (const [value, text] of [['required', '必需'], ['optional', '可选']]) { const option = el('option', text); option.value = value; select.append(option); }
      select.value = tool.required ? 'required' : 'optional'; label.append(select); box.append(label); f.type = select;
      box.append(button('移除此工具', () => { toolFields.splice(toolFields.indexOf(f), 1); box.remove(); })); toolFields.push(f); tools.append(box);
    };
    draft.tools.forEach(addTool); form.append(button('添加工具', () => { if (toolFields.length < 20) addTool({ id: 'tool-' + crypto.randomUUID(), name: '', amount: '', alternative: '', required: true }); }));
    const stepFields = [], steps = el('div'); form.append(el('h3', '步骤'), steps);
    const addStep = step => {
      const box = el('div', null, 'editor-step'), f = { step, box };
      f.title = editInput(box, '步骤名称', step.title); f.actions = editInput(box, '操作（每行一个动作）', step.actions.join('\n'), true);
      f.done = editInput(box, '完成标准', step.done); f.mistakes = editInput(box, '易错点（每行一项）', step.mistakes.join('\n'), true);
      f.recovery = editInput(box, '补救建议', step.recovery); f.safety = editInput(box, '安全提示（每行一项）', step.safety.join('\n'), true);
      f.wait = editInput(box, '等待时间（分钟，0 表示不需要）', String(step.wait_minutes)); f.wait.type = 'number'; f.wait.min = 0; f.wait.max = 1440;
      box.append(row(button('上移', () => {
        const index = stepFields.indexOf(f); if (index < 1) return;
        steps.insertBefore(box, stepFields[index - 1].box); [stepFields[index - 1], stepFields[index]] = [stepFields[index], stepFields[index - 1]];
      }), button('移除此步骤', () => { if (stepFields.length <= 1) return; stepFields.splice(stepFields.indexOf(f), 1); box.remove(); })));
      stepFields.push(f); steps.append(box);
    };
    draft.steps.forEach(addStep); form.append(button('添加步骤', () => { if (stepFields.length < 16) addStep({ id: 'step-' + crypto.randomUUID(), title: '', actions: [], done: '', mistakes: [], recovery: '', safety: [], wait_minutes: 0, origin: 'manual', timestamp: null, clip_end: null, evidence: '', frames: [] }); }));
    const save = el('button', '保存 SOP', 'primary'); save.type = 'submit'; form.append(row(save, button('取消编辑', () => { editorOpen = false; render(); })));
    const error = el('p', '', 'error-text'); error.setAttribute('role', 'alert'); form.append(error);
    form.onsubmit = event => {
      event.preventDefault(); const lines = value => value.split('\n').map(s => s.trim()).filter(Boolean);
      try {
        draft.title = title.value.trim(); draft.conditions = lines(conditions.value);
        draft.tools = toolFields.map(f => ({ id: f.tool.id, name: f.name.value.trim(), amount: f.amount.value.trim(), alternative: f.alternative.value.trim(), required: f.type.value === 'required' }));
        draft.steps = stepFields.map(f => ({ ...f.step, title: f.title.value.trim(), actions: lines(f.actions.value), done: f.done.value.trim(), mistakes: lines(f.mistakes.value), recovery: f.recovery.value.trim(), safety: lines(f.safety.value), wait_minutes: Number(f.wait.value), origin: 'manual', evidence: '' }));
        draft.source = 'manual'; draft.source_note = '用户编辑的 SOP 草稿；视频参考画面仅供回看，操作和安全提示请结合实际核对。';
        tutorial = validate(draft); editorOpen = false; errorText = ''; persist(); render();
      } catch (err) { error.textContent = err.message + '，请检查名称、动作、完成标准和等待时间。'; }
    };
    root.append(form);
  }
  function render() {
    document.getElementById('localVideoInput').disabled = busy || editorOpen;
    root.replaceChildren();
    if (!tutorial || generatorOpen) generator(); else if (editorOpen) editor(); else breakdown();
    if (errorText) { const error = el('p', errorText, 'error-text'); error.setAttribute('role', 'alert'); root.append(error); }
    if (saveWarning && !tutorial) root.append(el('p', saveWarning, 'subtle'));
  }
  window.addEventListener('tutorial-video', () => {
    const make = document.getElementById('subtitleGenerate');
    if (make) {
      make.disabled = busy || window.tutorialVideo?.status !== 'ready';
      const hint = document.getElementById('subtitleHint'); if (hint && window.tutorialVideo?.status === 'ready') hint.textContent = '重复生成会使用本机缓存的字幕。';
    } else if (tutorial && !editorOpen && !busy) render();
  });
  window.addEventListener('beforeunload', event => { if (busy || editorOpen) { event.preventDefault(); event.returnValue = ''; } });
  render();
})();
