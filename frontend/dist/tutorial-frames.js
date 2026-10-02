(function (root) {
  'use strict';
  const LIMIT = 8;
  function migrate(step) {
    if (!Array.isArray(step.frames)) step.frames = step.frame ? [step.frame] : [];
    delete step.frame;
    if (step.clip_end === undefined) step.clip_end = null;
    return step;
  }
  function add(step, frame) {
    migrate(step);
    if (step.frames.some(f => Math.abs(f.time - frame.time) < .06)) throw Error('这个时间点已经有画面，请换一个时间点。');
    if (step.frames.length >= LIMIT) throw Error('每步最多保存 8 张画面，请先移除不需要的画面。');
    step.frames.push(frame); step.frames.sort((a, b) => a.time - b.time);
  }
  function sample(start, end, duration) {
    if (![start, end, duration].every(Number.isFinite) || start < 0 || end <= start || end > duration + .1 || start >= duration) throw Error('请设置有效的本步片段起止时间，不能超出视频时长。');
    const last = Math.max(start, Math.min(end - .03, duration - .03)), first = Math.min(start + .03, last);
    return [first, (first + last) / 2, last].filter((value, index, values) => index === 0 || value - values[index - 1] >= .06);
  }
  const api = { LIMIT, migrate, add, sample };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.TutorialFrames = api;
})(typeof window === 'undefined' ? globalThis : window);
