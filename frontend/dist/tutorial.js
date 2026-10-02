(() => {
  'use strict';
  const root = document.getElementById('workbench');
  const params = new URLSearchParams(location.search);
  const videoId = params.get('id'), demoMode = params.get('demo') === 'button';
  const storageKey = 'slowly-sop-v1:' + (demoMode ? 'button-example' : videoId || 'manual');
  let tutorial = null, busy = false, editorOpen = false, generatorOpen = false, transcriptText = '', errorText = '', saveWarning = '';
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
  const time = value => `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
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
      if (!safeId(step.id) || typeof step.title !== 'string' || !step.title.trim() || !strings(step.actions, 8) || !step.actions.length
        || typeof step.done !== 'string' || !step.done.trim() || !strings(step.safety, 8) || !strings(step.mistakes, 8)
        || typeof step.recovery !== 'string' || typeof step.evidence !== 'string'
        || !Number.isInteger(step.wait_minutes) || step.wait_minutes < 0 || step.wait_minutes > 1440
        || (step.timestamp !== null && (!Number.isFinite(step.timestamp) || step.timestamp < 0 || step.timestamp > 86400))
        || (step.frame && (!safeImage(step.frame.url) || !Number.isFinite(step.frame.time)))) throw Error('步骤格式不正确');
    }
    return value;
  }
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (saved?.version === 1) tutorial = validate(saved.tutorial);
  } catch { saveWarning = '本地草稿无法读取，请重新生成或导入 SOP。'; }
  if (!tutorial && demoMode) tutorial = structuredClone(window.TutorialExample.demo);

  function exportDraft() {
    const blob = new Blob([JSON.stringify({ version: 1, tutorial }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob), anchor = el('a');
    anchor.href = url; anchor.download = 'slowly-tutorial-sop.json'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function importDraft(file) {
    if (!file || busy) return;
    try {
      if (file.size > 4000000) throw Error('文件过大，请使用小于 4MB 的 SOP 草稿');
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
      tutorial = validate(result.tutorial); generatorOpen = false; persist();
    } catch (error) { errorText = error.name === 'TimeoutError' ? '处理超时，请重试或粘贴教程文字。' : error.message; }
    finally { busy = false; render(); }
  }
  function generator() {
    root.append(el('p', '视频拆解 · 分步骤 SOP', 'eyebrow'), el('h2', '把教程整理成清晰的步骤'), notice('优先根据真实字幕整理，没有字幕时可粘贴教程文字。输出为可编辑的 SOP 草稿；尚未进行视频视觉分析。'));
    if (videoId) {
      const ready = window.tutorialVideo?.status === 'ready';
      const make = button(busy ? '正在提取字幕并整理…' : '从视频字幕生成 SOP', () => generate(true), 'primary', busy || !ready); make.id = 'subtitleGenerate'; root.append(row(make));
      const hint = el('p', ready ? '重复生成会使用本机缓存的字幕。' : '等待视频下载完成后可提取字幕，也可以先用下方文字生成。', 'subtle'); hint.id = 'subtitleHint'; root.append(hint);
    }
    const label = el('label', '教程文字或字幕'); const text = el('textarea'); text.value = transcriptText; text.maxLength = 20000; text.rows = 7;
    text.placeholder = '请粘贴具体操作、材料和注意事项（20～20000 字）。仅有标题无法可靠拆解。'; text.setAttribute('aria-label', '教程文字');
    text.oninput = () => { transcriptText = text.value; document.getElementById('textGenerate').disabled = busy || transcriptText.trim().length < 20; }; label.append(text); root.append(label);
    const make = button(busy ? '正在整理 SOP…' : '根据文字生成 SOP', () => generate(false), 'primary', busy || transcriptText.trim().length < 20); make.id = 'textGenerate'; root.append(row(make, importButton()));
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
    try { step.frame = frameData(document.getElementById('player')); errorText = ''; persist(); render(); }
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
      step.frame = frameData(video); persist();
    } catch (error) { errorText = error.message; }
    finally { busy = false; render(); }
  }
  function breakdown() {
    root.append(el('p', '视频拆解 · SOP 草稿', 'eyebrow'), el('h2', tutorial.title), notice(tutorial.source_note));
    root.append(row(button('编辑 SOP', () => { editorOpen = true; render(); }, '', busy), button('导出 SOP', exportDraft, '', busy), importButton(), button('重新拆解', () => { generatorOpen = true; errorText = ''; render(); }, '', busy)));
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
      if (step.frame) { const frame = el('img', null, 'frame'); frame.src = step.frame.url; frame.alt = `步骤 ${index + 1} 视频参考帧 ${time(step.frame.time)}`; card.append(frame, el('p', `参考画面 · ${time(step.frame.time)} · 未进行视觉分析，请核对是否对应动作`, 'subtle')); }
      if (videoId && !demoMode) {
        const ready = window.tutorialVideo?.status === 'ready';
        const controls = row(button('提取当前暂停画面', () => captureFrame(step), '', busy || !ready));
        if (step.timestamp !== null) controls.prepend(button(`回看 ${time(step.timestamp)}`, () => jumpVideo(step.timestamp), '', busy || !ready), button('提取字幕时间点画面', () => captureCueFrame(step), '', busy || !ready));
        if (step.frame) controls.append(button('移除画面', () => { step.frame = null; persist(); render(); }, '', busy));
        card.append(controls);
        if (!step.frame) card.append(el('p', '可按字幕时间点提取，也可在视频里暂停到更清晰的动作画面后保存。', 'subtle'));
      } else if (!step.frame) card.append(el('p', '未关联视频画面。', 'subtle'));
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
    draft.steps.forEach(addStep); form.append(button('添加步骤', () => { if (stepFields.length < 16) addStep({ id: 'step-' + crypto.randomUUID(), title: '', actions: [], done: '', mistakes: [], recovery: '', safety: [], wait_minutes: 0, origin: 'manual', timestamp: null, evidence: '', frame: null }); }));
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
