// ===== Loupe 自动填表 v5.0.0 - 列自适应 =====
(function() {
'use strict';

// ===== 扫描页面可用列 =====
function getAvailableColumns() {
  var cols = {};
  // 方式1: 从 header cells 找
  document.querySelectorAll('.ag-header-cell').forEach(function(h) {
    var el = h.querySelector('[col-id]') || h;
    var id = el.getAttribute('col-id');
    if (id && id !== '0' && id !== 'action') cols[id] = true;
  });
  // 方式2: 从任何 [col-id] 元素找（兜底）
  document.querySelectorAll('[col-id]').forEach(function(el) {
    var id = el.getAttribute('col-id');
    if (id && id !== '0' && id !== 'action') cols[id] = true;
  });
  return Object.keys(cols);
}

// 必填列（缺失时非阻塞警告）
var REQUIRED_COLS = ['jade_conclusion', 'note_one'];

// 按逗号分割后逐段精确匹配表，返回结论名数组
function matchMaterials(material) {
  if (!material) return [];
  var map = typeof MATERIAL_MAP !== 'undefined' ? MATERIAL_MAP : {};

  // 按逗号分割，每段 trim
  var parts = material.split(/[,，]/).map(function(p) { return p.trim(); }).filter(Boolean);

  // 每段精确匹配表
  var matched = [];
  parts.forEach(function(part) {
    // 优先精确匹配
    if (map[part]) {
      matched.push(map[part]);
    } else {
      // 兜底：子串最长匹配
      var best = '';
      Object.keys(map).forEach(function(key) {
        if (part.indexOf(key) >= 0 && key.length > best.length) best = key;
      });
      if (best) matched.push(map[best]);
    }
  });

  return matched;
}

// 检测依据
var CHECK_BASE_MAP = {
  '1': 'GB/T16552,GB/T16553',
  '2': 'GB/T16552,GB/T16553,GB11887,GB/T18043,QB/T1690',
  '3': 'GB11887,GB/T18043,QB/T1690'
};

// ===== 精确金属判断（避免"金"单字误判：青金石/金珀/金绿宝石/金丝玉等含"金"字但非金属） =====
function isMetalStr(v) {
  v = String(v || '');
  // 数字+K金：18K金 / 14K金 / 9K金 / 22K金（K可小写、可有空格）
  if (/[0-9０-９]+\s*[Kk]\s*金/.test(v)) return true;
  // 足金 / 千足金 / 纯金 / 镀金 / 黄金 / 金含量 / 金Au
  if (/(足金|千足金|纯金|镀金|黄金|金含量|金\s*[Aa][Uu])/.test(v)) return true;
  // 铂 / 铂金 / 足铂 / 铂Pt
  if (/铂/.test(v)) return true;
  // 银：925银 / 银925 / S925 / 足银 / 纯银 / 镀银
  if (/(925\s*银|银\s*925|S\s*925|925\s*S|足银|纯银|镀银)/.test(v)) return true;
  // 钛钢 / 合金
  if (/(钛钢|合金)/.test(v)) return true;
  return false;
}

// 款式类型 & 别名（与 rules/r9_style_check.py 同步）
var TYPE_WORDS = ['摆件','吊坠','耳饰','耳钉','挂件','挂坠','戒指','链坠','饰品','手串','手链','手镯','项链'];
var STYLE_ALIAS = { '手链':'手串','耳钉':'耳饰' };

function classifyCheckBase(matched) {
  if (matched.length === 0) return '';
  var hasMetal = matched.some(function(v) { return isMetalStr(v); });
  var hasGem = matched.some(function(v) { return !isMetalStr(v); });
  var code = '';
  if (hasGem && hasMetal) code = '2';
  else if (hasGem) code = '1';
  else if (hasMetal) code = '3';
  return CHECK_BASE_MAP[code] || '';
}

// 镶嵌材质 → 贵金属材料及纯度 映射表
var P_METALS_MAP = {
  '未镶嵌': '',
  '素款无配件': '',
  '无配饰': '',
  '合金锁扣': '合金',
  '合金延长链': '合金',
  '合金胸针扣': '合金',
  '合金': '合金',
  '钛钢': '钛钢',
  '银S925': '银925',
  '银S925镶嵌': '银925',
  '银S925镀金镶嵌': '银925（镀金）',
  '925银': '银925',
  '坠链均925银': '银925',
  '吊坠925银': '银925',
  '链子925银': '银925',
  '足银': '足银',
  '坠链均足银': '足银',
  '吊坠足银': '足银',
  '链子足银': '足银',
  '足银镶嵌': '足银',
  '足铂': '',
  '足铂镶嵌': '',
  '铂Pt850': '铂850',
  '铂Pt850镶嵌': '铂850',
  '铂Pt900': '铂900',
  '铂Pt900镶嵌': '铂900',
  '铂Pt950': '铂950',
  '铂Pt950镶嵌': '铂950',
  '9K金': '9K金',
  '9K金镶嵌': '9K金',
  '14K金': '14K金',
  '14K金镶嵌': '14K金',
  '18K金': '18K金',
  '18K金镶嵌': '18K金',
  '22K金': '22K金',
  '22K金镶嵌': '22K金',
  '足金': '足金（金含量≥999‰）',
  '足金（金含量≥999‰）': '足金（金含量≥999‰）',
  '足金（金含量999‰）': '足金（金含量999‰）',
  '足金镶嵌': '足金（金含量≥999‰）',
};

function getPMetals(inlay) {
  if (!inlay) return '';
  // 精确匹配
  if (P_METALS_MAP[inlay]) return P_METALS_MAP[inlay];
  // 子串最长匹配
  var best = '';
  Object.keys(P_METALS_MAP).forEach(function(key) {
    if (inlay.indexOf(key) >= 0 && key.length > best.length) best = key;
  });
  return P_METALS_MAP[best] || '';
}

// 去除忽略词（去掉逗号前的忽略词部分）
function stripIgnore(text) {
  var ignores = typeof IGNORE_WORDS !== 'undefined' ? IGNORE_WORDS : [];
  // 按逗号拆分，过滤掉忽略词部分
  var parts = text.split(/[,，]/).map(function(p) { return p.trim(); });
  var filtered = parts.filter(function(p) {
    return ignores.indexOf(p) < 0 && p.length > 0;
  });
  return filtered.join(', ');
}

// 生成备注
function buildNote(matched) {
  if (matched.length <= 1) return '';
  var parts = [];
  var others = matched.slice(1).filter(function(v) { return !isMetalStr(v); });
  var metals = matched.slice(1).filter(function(v) { return isMetalStr(v); });
  if (others.length > 0) parts.push('另配' + others.join(','));
  if (metals.length > 0) parts.push('金属配件为' + metals.join(','));
  return parts.join(';');
}

var btn = null;
var vp = null;

function injectBtn() {
  if (btn) return;
  btn = document.createElement('div');
  btn.id = 'loupe-btn';
  btn.textContent = '🔍 自动填表';
  btn.style.cssText = 'position:fixed;bottom:80px;right:24px;z-index:999999;padding:10px 20px;' +
    'background:#b8960f;color:#fff;border-radius:8px;cursor:pointer;font-size:14px;' +
    'font-family:sans-serif;box-shadow:0 4px 12px rgba(0,0,0,0.2);user-select:none;';
  btn.onclick = doFill;
  document.body.appendChild(btn);
  vp = document.querySelector('.ag-body-viewport');
}

// ===== 滚动到行 =====
function scrollToRow(rowIdx) {
  if (!vp) vp = document.querySelector('.ag-body-viewport');
  if (!vp) return;
  vp.scrollTop = rowIdx * 44;
  vp.dispatchEvent(new Event('scroll', { bubbles: true }));
}

// ===== 获取 AG-Grid API =====
function getGridApi() {
  try {
    var selectors = ['.ag-root-wrapper', '.ag-root', '.ag-body-viewport', '.ag-header'];
    for (var i = 0; i < selectors.length; i++) {
      var el = document.querySelector(selectors[i]);
      if (!el) continue;
      var keys = Object.keys(el);
      for (var k = 0; k < keys.length; k++) {
        if (keys[k].indexOf('__reactFiber') < 0) continue;
        var fiber = el[keys[k]];
        for (var s = 0; s < 40 && fiber; s++) {
          if (fiber.stateNode && fiber.stateNode.gridApi) return fiber.stateNode.gridApi;
          fiber = fiber.return;
        }
      }
    }
  } catch(e) {}
  return null;
}

// ===== 写入单元格 =====
function writeCell(rowIdx, colId, val, delay) {
  delay = delay || 50;
  return new Promise(function(resolve) {
    var rIdx = String(rowIdx);

    var cell = null;
    var rows = document.querySelectorAll('[row-index="' + rIdx + '"]');
    for (var i = 0; i < rows.length && !cell; i++) {
      cell = rows[i].querySelector('[col-id="' + colId + '"]');
    }
    if (!cell) { resolve(false); return; }

    // 试试 API setDataValue
    var api = getGridApi();
    if (api) {
      try {
        api.forEachNode(function(node) {
          if (node.rowIndex === parseInt(rowIdx)) { node.setDataValue(colId, val); }
        });
        resolve(true);
        return;
      } catch(e) {}
    }

    // 兜底：dblclick
    cell.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));

    setTimeout(function() {
      var editor = cell.querySelector('input:not([type="hidden"]), select, textarea, [contenteditable="true"]');
      if (!editor) {
        editor = document.querySelector('.ag-popup-editor input, .ag-popup-editor select, .ag-popup-editor textarea');
      }
      if (editor) {
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(editor, val);
        editor.dispatchEvent(new Event('input', { bubbles: true }));
        editor.dispatchEvent(new Event('change', { bubbles: true }));
        editor.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true }));
      }
      resolve(!!editor);
    }, delay);
  });
}

// ===== 调 API =====
function fetchApi(body) {
  return new Promise(function(resolve) {
    chrome.runtime.sendMessage({ action: 'fetch_api', body: body }, function(resp) {
      resolve(resp && resp.data ? resp.data : resp);
    });
  });
}

function getBatchId() {
  var m = location.href.match(/inspectionBatchId=(\d+)/);
  return m ? m[1] : null;
}

function getTimeRange() {
  var now = new Date();
  var start = Math.floor(new Date(now.getFullYear(), now.getMonth(), 1).getTime() / 1000);
  var end = Math.floor(new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59).getTime() / 1000);
  return { start: start, end: end };
}

// ===== 一次性拉取整个批次的数据，按序号匹配 =====
async function doFill() {
  btn.textContent = '运行中…';
  btn.style.pointerEvents = 'none';
  btn.style.opacity = '0.7';

  // 读取用户配置的字段顺序
  var fieldOrder = await new Promise(function(resolve) {
    if (chrome && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get('fieldOrder', function(data) {
      resolve((data && data.fieldOrder && data.fieldOrder.length >= 5)
        ? data.fieldOrder
        : ['note_one', 'note_two', 'check_base', 'jade_conclusion', 'style', 'p_metals']);
      });
    } else {
      resolve(['note_one', 'note_two', 'check_base', 'jade_conclusion', 'style']);
    }
  });

  // 扫描页面可用列
  var availableCols = getAvailableColumns();

  // 检查必填列
  var missingRequired = REQUIRED_COLS.filter(function(c) { return availableCols.indexOf(c) < 0; });
  if (missingRequired.length === REQUIRED_COLS.length) {
    alert('⚠ 缺少必填列：' + missingRequired.join(', ') + '\n请添加后再填表');
    btn.textContent = '🔍 自动填表';
    btn.style.opacity = '1';
    return;
  }

  btn.textContent = '⏳ 拉取批次数据...';

  var tr = getTimeRange();
  var batchId = getBatchId();

  var apiBody = {
    checkType: 1,
    inspectionBatchStartTime: tr.start,
    inspectionBatchEndTime: tr.end,
    page: 1,
    pageSize: 200
  };
  if (batchId) apiBody.inspectionBatchId = parseInt(batchId);
  var resp = await fetchApi(apiBody);

  var orders = [];
  if (resp && resp.data && resp.data.list) orders = resp.data.list;
  else if (resp && resp.list) orders = resp.list;

  if (orders.length === 0) {
    alert('未查到订单数据');
    btn.textContent = '🔍 自动填表';
    btn.style.pointerEvents = '';
    btn.style.opacity = '1';
    return;
  }

  // API 返回顺序 = 表格显示顺序

  // ---- 第一遍：每行独立计算字段值 ----
  var rowsData = [];
  for (var i = 0; i < orders.length; i++) {
    var order = orders[i];
    var cert = order.certificationCode || '';
    var material = (order.productInfo && order.productInfo.material) || '';
    var accessories = (order.productInfo && order.productInfo.accessories) || '';
    var cleanMaterial = stripIgnore(material);
    var matched = matchMaterials(cleanMaterial);

    // fallback
    if (matched.length === 0 && accessories) {
      var cleanAcc = stripIgnore(accessories);
      if (cleanAcc) {
        var accParts = cleanAcc.split(/[,，]/).map(function(p) { return p.trim(); }).filter(Boolean);
        var gemParts = accParts.filter(function(p) { return !isMetalStr(p); });
        var metalParts = accParts.filter(function(p) { return isMetalStr(p); });
        if (gemParts.length > 0) {
          matched = matchMaterials(gemParts[0]);
          accessories = gemParts.slice(1).concat(metalParts).join(', ');
        } else if (metalParts.length > 0) {
          matched = matchMaterials(metalParts[0]);
          accessories = metalParts.slice(1).join(', ');
        }
      }
    }
    if (matched.length === 0) {
      var inlayRaw = (order.productInfo && order.productInfo.mosaicMaterial) || '';
      var cleanInlay = stripIgnore(inlayRaw);
      if (cleanInlay) matched = matchMaterials(cleanInlay);
    }

    var conclusion = '', note = '', noteTwo = '';
    if (matched.length === 1) conclusion = matched[0];
    else if (matched.length > 1) conclusion = matched[0];
    if (matched.length <= 1) note = '---';
    if (matched.length > 1) noteTwo = buildNote(matched);

    // 全局：忽略 → 映射转化 → 生成备注（排除已出现的值）
    function buildNoteFromParts(rawStr, exclude) {
      exclude = exclude || [];
      var clean = stripIgnore(rawStr);
      if (!clean) return '';
      var parts = clean.split(/[,，]/).map(function(p) { return p.trim(); }).filter(Boolean);
      var mapped = parts.map(function(p) { var m = matchMaterials(p); return m.length > 0 ? m[0] : p; });
      // 排除已出现
      mapped = mapped.filter(function(v) { return exclude.indexOf(v) < 0; });
      var gems = mapped.filter(function(v) { return !isMetalStr(v); });
      var metals = mapped.filter(function(v) { return isMetalStr(v); });
      var result = '';
      if (gems.length > 0) result = '另配' + gems.join(',');
      if (metals.length > 0) result += (result ? ';' : '') + '金属配件为' + metals.join(',');
      return result;
    }

    // 计算贵金属纯度（早算，给去重用）
    var inlay = (order.productInfo && order.productInfo.mosaicMaterial) || '';
    var pMetals = getPMetals(inlay);

    if (accessories && accessories !== material) {
      var accN = buildNoteFromParts(accessories, [conclusion, pMetals].filter(Boolean));
      if (accN) {
        noteTwo = noteTwo ? noteTwo + '，' + accN : accN;
        if (note === '---') note = '';
      }
    }

    // 镶嵌材质：按配件角色填备注2（去重）
    if (inlay) {
      var inlayN = buildNoteFromParts(inlay, [conclusion, pMetals].filter(Boolean));
      if (inlayN) {
        noteTwo = noteTwo ? noteTwo + '，' + inlayN : inlayN;
        if (note === '---') note = '';
      }
    }

    var allText = conclusion + ' ' + note + ' ' + noteTwo;
    var hasGem = /玉|翠|石|晶|宝|牙|玛瑙|珍珠|珊瑚|贝壳|琥珀|蜜蜡/i.test(allText);
    var hasMetal = isMetalStr(allText);
    var checkBase = '';
    if (hasGem && hasMetal) checkBase = CHECK_BASE_MAP['2'];
    else if (hasGem) checkBase = CHECK_BASE_MAP['1'];
    else if (hasMetal) checkBase = CHECK_BASE_MAP['3'];

    var vals = {
      'note_one': note, 'note_two': noteTwo, 'check_base': checkBase,
      'jade_conclusion': conclusion, 'style': '饰品', 'p_metals': pMetals
    };
    if (order.inspectionInfo && order.inspectionInfo.tag) vals['hang_tag'] = order.inspectionInfo.tag;

    // 款式匹配：从商品名称提取款式词，匹配产品样式字段
    var pname = (order.productInfo && order.productInfo.name) || '';
    var mstyle = (order.productInfo && order.productInfo.style) || '';
    if (mstyle && mstyle !== '饰品') {
      var mstyleNorm = STYLE_ALIAS[mstyle] || mstyle;
      for (var si = 0; si < TYPE_WORDS.length; si++) {
        var tw = TYPE_WORDS[si];
        if (pname.indexOf(tw) >= 0) {
          var twNorm = STYLE_ALIAS[tw] || tw;
          if (mstyle.indexOf(tw) >= 0 || twNorm === mstyleNorm) { vals['style'] = twNorm; break; }
        }
      }
    }

    // 按配置顺序，只保留可用的
    var fields = [];
    for (var o = 0; o < fieldOrder.length; o++) {
      var cid = fieldOrder[o];
      var v = vals[cid];
      if (availableCols.indexOf(cid) >= 0 && (v || v === '')) fields.push({ colId: cid, val: v });
    }

    rowsData.push({ cert: cert, fields: fields, conclusion: conclusion, note: note, checkBase: checkBase });
  }

  // ---- 分析：全行一致的字段 ----
  var allSame = {};
  for (var f = 0; f < fieldOrder.length; f++) {
    var cid = fieldOrder[f];
    if (availableCols.indexOf(cid) < 0) continue;
    var firstVal = rowsData[0].fields.find(function(x) { return x.colId === cid; });
    if (!firstVal) continue;
    var same = true;
    for (var r = 1; r < rowsData.length; r++) {
      var cur = rowsData[r].fields.find(function(x) { return x.colId === cid; });
      if (!cur || cur.val !== firstVal.val) { same = false; break; }
    }
    allSame[cid] = same;
  }

  // ---- 第二遍：填入 ----
  // 首行150ms冷启动 | 同值后续10ms极速 | 异值50ms保稳定
  var totalFilled = 0;
  var filledRows = 0;

  for (var r = 0; r < rowsData.length; r++) {
    var rd = rowsData[r];
    var rowIdx = r;
    btn.textContent = '⏳ ' + (r+1) + '/' + orders.length + ' ' + rd.cert;
    scrollToRow(rowIdx);
    await new Promise(function(rr) { setTimeout(rr, 50); });

    var rowFilled = 0;
    for (var f = 0; f < rd.fields.length; f++) {
      // 同值字段极速10ms，异值字段50ms保稳定
      var ok = await writeCell(rowIdx, rd.fields[f].colId, rd.fields[f].val, 100);
      if (ok) rowFilled++;
    }
    totalFilled += rowFilled;
    if (rowFilled > 0) filledRows++;
  }

  var msg = '✅ ' + filledRows + '/' + orders.length + ' 行, 共填 ' + totalFilled + ' 格';
  btn.textContent = '已完成';
  btn.style.pointerEvents = '';
  btn.style.opacity = '1';
  setTimeout(function() { btn.textContent = '🔍 自动填表'; }, 3000);
}

function init() {
  if (location.hostname.indexOf('qms.bytedance.com') < 0) return;
  setTimeout(injectBtn, 2000);
}

if (document.readyState === 'complete') init();
else window.addEventListener('load', init);

})();
