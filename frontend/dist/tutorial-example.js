(function (root) {
  'use strict';
  const demo = {
    version: 1, source: 'example', title: '把掉下来的纽扣缝回去',
    source_note: '人工编写的 SOP 示例，没有关联视频，也没有执行 AI 视频解析。适用于普通四孔纽扣。',
    conditions: ['确认衣服是普通可手缝面料，纽扣为四孔纽扣；特殊面料或特殊纽扣请另行确认。'],
    tools: [
      { id: 'needle', name: '手缝针', amount: '1 根', required: true, alternative: '用适合面料的针；没有针时先暂停。' },
      { id: 'thread', name: '缝纫线', amount: '适量', required: true, alternative: '优先用接近衣服颜色的线。' },
      { id: 'button', name: '四孔纽扣', amount: '1 枚', required: true, alternative: '确认尺寸适合原来的扣眼。' },
      { id: 'scissors', name: '剪刀', amount: '1 把', required: true, alternative: '' },
      { id: 'chalk', name: '可擦标记笔', amount: '可选', required: false, alternative: '可以参考原缝线位置。' },
    ],
    steps: [
      { id: 'step-1', title: '穿针并打结', actions: ['剪一段方便自己操作的线，穿过针眼。', '拉齐两端，在末端打结。'], done: '线已穿好，末端的结不会轻轻一拉就散开。', mistakes: ['线太长，容易缠绕打结。'], recovery: '先放下针，理顺线；线已缠死时重新剪线穿针。', safety: ['针放在可见位置，桌面没有散落的针。'], wait_minutes: 0 },
      { id: 'step-2', title: '找准纽扣位置', actions: ['对齐衣服两侧，参考原缝线和对应扣眼找到位置。', '把纽扣放上去，确认扣合时衣服没有明显错位。'], done: '纽扣与扣眼对齐，位置已经确认。', mistakes: ['衣服没有铺平，导致纽扣位置偏移。'], recovery: '先摊平衣服重新对齐，不要急着下针。', safety: [], wait_minutes: 0 },
      { id: 'step-3', title: '交叉缝合纽扣', actions: ['从衣服背面下针，穿过纽扣的一组对角孔，再穿回布料。', '换另一组对角孔，重复交叉缝合；留一点让扣眼穿过的空间。'], done: '纽扣已固定，轻轻拨动不会脱落，衣服没有明显褶皱。', mistakes: ['拉线太紧，纽扣紧贴布料，扣眼不好穿过。', '针尖从布料下面穿出时扎到手。'], recovery: '如果扣不上或布料起皱，暂停并拆掉过紧的线，重新固定。', safety: ['手指避开针尖穿出的方向，缓慢下针。'], wait_minutes: 0 },
      { id: 'step-4', title: '收线并检查牢固程度', actions: ['把针引到衣服背面，打结固定，再剪去多余线头。', '轻拉纽扣，试着扣上、解开，检查位置和松紧。'], done: '纽扣不松脱，能正常扣合，背面的结已固定。', mistakes: ['没打结就剪线，缝线容易散开。'], recovery: '线已散开时重新固定，避免继续拉扯面料。', safety: ['剪线前确认剪刀没有夹到衣服或手指。'], wait_minutes: 0 },
      { id: 'step-5', title: '收好工具', actions: ['把针收回针盒，收好剪刀，清理剪下的线头。'], done: '针和剪刀都已收好，桌面与衣服上没有散落的针。', mistakes: ['针留在衣服上，之后穿着时容易扎伤。'], recovery: '发现针不见了先停止整理，找到针并收好。', safety: ['确认用过的针已经收回针盒。'], wait_minutes: 0 },
    ].map(s => ({ ...s, origin: 'example', timestamp: null, evidence: '', frame: null })),
  };
  const api = { demo };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.TutorialExample = api;
})(typeof window === 'undefined' ? globalThis : window);
