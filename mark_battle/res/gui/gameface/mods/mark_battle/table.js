/* MarkBattle v1.0 - Адаптивная таблица + колесо мыши (чистые названия танков без контура) */

(function () {
  'use strict';

  var IN_GAME = !!(window.engine && window.model && window.viewEnv);
  var ROW_HEIGHT = 30;

  var LEVELS = [
    { val: 5, label: 'V' },
    { val: 6, label: 'VI' },
    { val: 7, label: 'VII' },
    { val: 8, label: 'VIII' },
    { val: 9, label: 'IX' },
    { val: 10, label: 'X' },
    { val: 11, label: 'XI' }
  ];

  var TYPES = [
    { code: 'LT', label: 'ЛТ' },
    { code: 'MT', label: 'СТ' },
    { code: 'HT', label: 'ТТ' },
    { code: 'TD', label: 'ПТ' },
    { code: 'SPG', label: 'САУ' }
  ];

  var NATIONS = [
    'ussr', 'germany', 'usa', 'china', 'france',
    'uk', 'japan', 'czech', 'sweden', 'poland', 'italy'
  ];

  var state = {
    allRows: [],
    meta: { totalVehicles: 0, inHangarCount: 0, updatedAt: '', server: 'RU-BY' },
    revision: -1,
    inHangar: 1,
    selectedLevels: {},
    selectedTypes: {},
    selectedNations: {},
    sortKey: 'pct',
    sortDir: -1,
    page: 1,
    pageSize: 21,
    totalPages: 1
  };

  var elWindow = document.getElementById('tableWindow');
  var elTbody = document.getElementById('tbody');
  var elPagination = document.getElementById('pagination');
  var elStatusBar = document.getElementById('statusBar');
  var elHeaderBar = document.getElementById('headerBar');
  var elBtnClose = document.getElementById('btnClose');

  function fmtInt(n) {
    n = Math.round(Number(n) || 0);
    if (n <= 0) { return '\u2014'; }
    var s = Math.abs(n) + '';
    var out = '';
    while (s.length > 3) {
      out = ' ' + s.slice(-3) + out;
      s = s.slice(0, -3);
    }
    return s + out;
  }

  function fmtPct(n) {
    n = Number(n) || 0;
    return n.toFixed(2) + '%';
  }

  function flagUrl(nation) {
    return 'coui://gui/maps/icons/filters/nations/' + nation + '.png';
  }

  function sendReadyCmd(payload) {
    if (!IN_GAME || !window.model) { return; }
    try { window.model.ready(payload || {}); } catch (e) {}
  }

  function hasActiveKeys(map) {
    for (var k in map) {
      if (map.hasOwnProperty(k) && map[k]) { return true; }
    }
    return false;
  }

  function getClientScreenSize() {
    if (state.meta && state.meta.screenW > 0 && state.meta.screenH > 0) {
      return { w: Number(state.meta.screenW), h: Number(state.meta.screenH) };
    }
    try {
      var c = window.viewEnv.getClientSizePx();
      if (c && c.width > 0 && c.height > 0) {
        return { w: c.width, h: c.height };
      }
    } catch (e) {}
    return { w: 2560, h: 1440 };
  }

  function computeAdaptiveWindowSize() {
    var scr = getClientScreenSize();
    var maxW = Math.min(1520, Math.max(1060, Math.floor(scr.w * 0.68)));
    var maxH = Math.min(930, Math.max(540, Math.floor(scr.h * 0.66)));
    return { w: maxW, h: maxH };
  }

  function recalcPageSize() {
    try {
      var rect = elTbody.getBoundingClientRect();
      if (rect && rect.height >= ROW_HEIGHT * 5) {
        var fit = Math.floor(rect.height / ROW_HEIGHT);
        if (fit >= 5 && fit <= 35) {
          state.pageSize = fit;
          return;
        }
      }
    } catch (e) {}
  }

  function buildFilterButtons() {
    var wrapLvl = document.getElementById('filterLevels');
    LEVELS.forEach(function (item) {
      var btn = document.createElement('div');
      btn.className = 'f-btn';
      btn.textContent = item.label;
      btn.addEventListener('click', function () {
        state.selectedLevels[item.val] = !state.selectedLevels[item.val];
        btn.className = state.selectedLevels[item.val] ? 'f-btn is-active' : 'f-btn';
        state.page = 1;
        renderTable();
      });
      wrapLvl.appendChild(btn);
    });

    var wrapTypes = document.getElementById('filterTypes');
    TYPES.forEach(function (item) {
      var btn = document.createElement('div');
      btn.className = 'f-btn';
      btn.textContent = item.label;
      btn.addEventListener('click', function () {
        state.selectedTypes[item.code] = !state.selectedTypes[item.code];
        btn.className = state.selectedTypes[item.code] ? 'f-btn is-active' : 'f-btn';
        state.page = 1;
        renderTable();
      });
      wrapTypes.appendChild(btn);
    });

    var wrapNations = document.getElementById('filterNations');
    NATIONS.forEach(function (nat) {
      var btn = document.createElement('div');
      btn.className = 'f-btn f-btn--flag';
      var icon = document.createElement('div');
      icon.className = 'flag-icon';
      icon.style.backgroundImage = 'url("' + flagUrl(nat) + '")';
      btn.appendChild(icon);
      btn.addEventListener('click', function () {
        state.selectedNations[nat] = !state.selectedNations[nat];
        btn.className = state.selectedNations[nat] ? 'f-btn f-btn--flag is-active' : 'f-btn f-btn--flag';
        state.page = 1;
        renderTable();
      });
      wrapNations.appendChild(btn);
    });

    var hangarBtns = document.querySelectorAll('#filterHangar .f-btn');
    for (var i = 0; i < hangarBtns.length; i++) {
      (function (b) {
        b.addEventListener('click', function () {
          var targetVal = Number(b.getAttribute('data-hangar'));
          state.inHangar = targetVal;
          for (var j = 0; j < hangarBtns.length; j++) {
            var v = Number(hangarBtns[j].getAttribute('data-hangar'));
            hangarBtns[j].className = (v === state.inHangar)
              ? 'f-btn f-btn--wide is-active'
              : 'f-btn f-btn--wide';
          }
          state.page = 1;
          renderTable();
        });
      })(hangarBtns[i]);
    }

    var sortCols = document.querySelectorAll('.thead .col[data-sort]');
    for (var c = 0; c < sortCols.length; c++) {
      (function (colEl) {
        colEl.addEventListener('click', function () {
          var key = colEl.getAttribute('data-sort');
          if (state.sortKey === key) {
            state.sortDir = -state.sortDir;
          } else {
            state.sortKey = key;
            state.sortDir = (key === 'name' || key === 'n' || key === 'tc') ? 1 : -1;
          }
          for (var k = 0; k < sortCols.length; k++) {
            sortCols[k].classList.remove('is-sorted');
          }
          colEl.classList.add('is-sorted');
          state.page = 1;
          renderTable();
        });
      })(sortCols[c]);
    }
  }

  function filterAndSortRows() {
    var useLvl = hasActiveKeys(state.selectedLevels);
    var useType = hasActiveKeys(state.selectedTypes);
    var useNat = hasActiveKeys(state.selectedNations);

    var filtered = state.allRows.filter(function (r) {
      if (Number(r.ih) !== state.inHangar) { return false; }
      if (useLvl && !state.selectedLevels[r.lvl]) { return false; }
      if (useType && !state.selectedTypes[r.tc]) { return false; }
      if (useNat && !state.selectedNations[r.n]) { return false; }
      return true;
    });

    var sk = state.sortKey;
    var dir = state.sortDir;
    filtered.sort(function (a, b) {
      var va = a[sk];
      var vb = b[sk];
      if (typeof va === 'string') {
        var cmp = va.localeCompare(vb);
        return cmp !== 0 ? cmp * dir : (b.pct - a.pct);
      }
      var diff = (Number(va) || 0) - (Number(vb) || 0);
      if (diff !== 0) { return diff * dir; }
      return (Number(b.pct) || 0) - (Number(a.pct) || 0);
    });

    return filtered;
  }

  function renderTable() {
    recalcPageSize();
    var pageSize = state.pageSize;
    var filtered = filterAndSortRows();
    var totalFiltered = filtered.length;
    var totalPages = Math.max(1, Math.ceil(totalFiltered / pageSize));
    state.totalPages = totalPages;
    if (state.page > totalPages) { state.page = totalPages; }
    if (state.page < 1) { state.page = 1; }

    var startIdx = (state.page - 1) * pageSize;
    var pageRows = filtered.slice(startIdx, startIdx + pageSize);

    elTbody.innerHTML = '';
    var missingCds = [];

    for (var i = 0; i < pageRows.length; i++) {
      var r = pageRows[i];
      if (!r.m1 || r.m1 <= 0) {
        missingCds.push(r.cd);
      }
      var rowEl = document.createElement('div');
      rowEl.className = 'trow';

      var starsHtml = '';
      var mk = Math.max(0, Math.min(3, Number(r.mk) || 0));
      for (var s = 1; s <= 3; s++) {
        starsHtml += '<span class="t-star' + (s <= mk ? ' t-star--on' : '') + '"></span>';
      }

      rowEl.innerHTML =
        '<div class="col col--idx">' + (startIdx + i + 1) + '</div>' +
        '<div class="col col--nat"><div class="flag-icon" style="background-image:url(\'' + flagUrl(r.n) + '\')"></div></div>' +
        '<div class="col col--name' + (r.pr ? ' is-prem' : '') + '">' +
          '<span>' + r.name + '</span>' +
        '</div>' +
        '<div class="col col--lvl">' + r.lvlR + '</div>' +
        '<div class="col col--type">' + r.tr + '</div>' +
        '<div class="col col--pct">' + fmtPct(r.pct) + '</div>' +
        '<div class="col col--marks">' + starsHtml + '</div>' +
        '<div class="col col--m1">' + fmtInt(r.m1) + '</div>' +
        '<div class="col col--m2">' + fmtInt(r.m2) + '</div>' +
        '<div class="col col--m3">' + fmtInt(r.m3) + '</div>';

      elTbody.appendChild(rowEl);
    }

    if (missingCds.length > 0) {
      sendReadyCmd({ requestCds: missingCds.join(',') });
    }

    renderPagination(totalPages);
    renderStatusBar(totalFiltered);
  }

  function renderPagination(totalPages) {
    elPagination.innerHTML = '';
    if (totalPages <= 1) { return; }

    function addBtn(label, targetPage, isActive) {
      var b = document.createElement('div');
      b.className = isActive ? 'page-btn is-active' : 'page-btn';
      b.textContent = label;
      b.addEventListener('click', function () {
        if (targetPage >= 1 && targetPage <= totalPages && targetPage !== state.page) {
          state.page = targetPage;
          renderTable();
        }
      });
      elPagination.appendChild(b);
    }

    addBtn('<', Math.max(1, state.page - 1), false);
    var maxButtons = 9;
    var startP = Math.max(1, state.page - 4);
    var endP = Math.min(totalPages, startP + maxButtons - 1);
    if (endP - startP + 1 < maxButtons) {
      startP = Math.max(1, endP - maxButtons + 1);
    }
    for (var p = startP; p <= endP; p++) {
      addBtn(String(p), p, p === state.page);
    }
    addBtn('>', Math.min(totalPages, state.page + 1), false);
  }

  function renderStatusBar(shownCount) {
    var total = state.meta.totalVehicles || state.allRows.length;
    var inHangar = state.meta.inHangarCount || 0;
    var upd = state.meta.updatedAt ? (' · обновлено ' + state.meta.updatedAt) : '';
    elStatusBar.textContent =
      'Техники: ' + shownCount + ' из ' + total +
      ' · В ангаре: ' + inHangar + upd;
  }

  function applyModel() {
    if (!window.model) { return; }
    var rev = Number(window.model.revision) || 0;
    if (rev === state.revision) { return; }
    var firstLoad = (state.revision === -1);
    state.revision = rev;
    try {
      var rawVehicles = window.model.vehiclesJson || '[]';
      state.allRows = JSON.parse(rawVehicles);
    } catch (e) {
      state.allRows = [];
    }
    try {
      var rawMeta = window.model.metaJson || '{}';
      state.meta = JSON.parse(rawMeta);
    } catch (e) {}

    if (firstLoad && IN_GAME) {
      var sz = computeAdaptiveWindowSize();
      try { window.viewEnv.resizeViewRem(sz.w, sz.h); } catch (e) {}
    }
    setTimeout(renderTable, 20);
  }

  function bindWindowControls() {
    elBtnClose.addEventListener('click', function (e) {
      if (e && e.stopPropagation) { e.stopPropagation(); }
      sendReadyCmd({ closeNow: 1 });
    });

    document.addEventListener('keydown', function (e) {
      if (e && (e.keyCode === 27 || e.key === 'Escape')) {
        sendReadyCmd({ closeNow: 1 });
      }
    });

    function onWheel(e) {
      if (!e) { return; }
      var dy = e.deltaY !== undefined ? e.deltaY : -(e.wheelDelta || 0);
      if (dy > 0 && state.page < state.totalPages) {
        state.page += 1;
        renderTable();
      } else if (dy < 0 && state.page > 1) {
        state.page -= 1;
        renderTable();
      }
      if (e.preventDefault) { e.preventDefault(); }
    }

    elWindow.addEventListener('wheel', onWheel);
    elWindow.addEventListener('mousewheel', onWheel);

    elHeaderBar.addEventListener('mousedown', function (e) {
      if (e.target === elBtnClose) { return; }
      if (e.button !== undefined && e.button !== 0) { return; }
      if (IN_GAME && window.model) {
        try { window.model.dragStart({ lx: e.clientX, ly: e.clientY }); } catch (err) {}
      }
    });

    document.addEventListener('mouseup', function (e) {
      if (IN_GAME && window.model) {
        try { window.model.dragEnd({ lx: e.clientX, ly: e.clientY }); } catch (err) {}
      }
    });
  }

  function boot() {
    buildFilterButtons();
    bindWindowControls();

    if (IN_GAME) {
      window.engine.whenReady.then(function () {
        setTimeout(function () {
          var sz = computeAdaptiveWindowSize();
          try { window.viewEnv.resizeViewRem(sz.w, sz.h); } catch (e) {}
          sendReadyCmd({ viewW: sz.w, viewH: sz.h });
          applyModel();
          try { window.engine.on('viewEnv.onDataChanged', applyModel); } catch (e) {}
          setInterval(applyModel, 300);
        }, 50);
      });
    } else {
      document.documentElement.style.fontSize = '1px';
      elWindow.style.width = '1520px';
      elWindow.style.height = '930px';
      state.allRows = [
        { cd: 1, n: 'ussr', name: 'КВ-5', lvl: 8, lvlR: 'VIII', tc: 'HT', tr: 'ТТ', ih: 1, pr: 1, pct: 97.16, mk: 3, m1: 1205, m2: 1752, m3: 2220 },
        { cd: 2, n: 'ussr', name: 'Зверобой', lvl: 8, lvlR: 'VIII', tc: 'TD', tr: 'ПТ', ih: 1, pr: 1, pct: 96.67, mk: 3, m1: 1665, m2: 2417, m3: 2997 },
        { cd: 3, n: 'usa', name: 'Astron-FL', lvl: 10, lvlR: 'X', tc: 'HT', tr: 'ТТ', ih: 0, pr: 0, pct: 90.51, mk: 2, m1: 1466, m2: 2172, m3: 2766 }
      ];
      state.meta = { totalVehicles: 3, inHangarCount: 2, updatedAt: '16:25:00' };
      renderTable();
    }
  }

  boot();
})();