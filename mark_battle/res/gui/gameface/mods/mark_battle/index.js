/* MarkBattle v1.2.0 - силуэт через SVG-файлы + надёжный клик для открытия таблицы */

(function () {
  'use strict';

  var IN_GAME = !!(window.engine && window.model && window.viewEnv);
  var log = function (msg) {
    try {
      if (IN_GAME) { console.warn('[MarkBattle] ' + msg); }
      else { console.log('[MarkBattle:mock] ' + msg); }
    } catch (e) {}
  };

  var card = document.getElementById('card');
  var elPercent = document.getElementById('percent');
  var elDelta = document.getElementById('delta');
  var elFill = document.getElementById('silhouetteFill');

  var readSize = { w: 200, h: 122 };
  var appliedKey = '';
  var booted = false;
  var downPos = null;

  function setText(el, text) {
    if (el && el.textContent !== text) { el.textContent = text; }
  }

  function fmtDec(n, dec) {
    n = Number(n) || 0;
    return n.toFixed(dec).replace('.', ',');
  }

  function fmtDelta(n, dec) {
    n = Number(n) || 0;
    var sign = n > 0 ? '+' : '';
    return sign + fmtDec(n, dec) + '%';
  }

  function renderStars(marks) {
    marks = Math.max(0, Math.min(3, Number(marks) || 0));
    for (var i = 1; i <= 3; i++) {
      var el = document.getElementById('star' + i);
      if (el) { el.className = (i <= marks) ? 'star star--earned' : 'star'; }
    }
  }

  function fmt(n) {
    n = Math.round(Number(n) || 0);
    var sign = n < 0 ? '-' : '';
    var s = Math.abs(n) + '';
    var out = '';
    while (s.length > 3) {
      out = '\u2009' + s.slice(-3) + out;
      s = s.slice(0, -3);
    }
    return sign + s + out;
  }

  function applyModel() {
    applyVisible();
    if (!window.model) { return; }
    var m = window.model;

    var percent = (Number(m.percentX100) || 0) / 100;
    var delta = (Number(m.deltaX100) || 0) / 100;
    var avg = Number(m.currentAvg) || 0;
    var nextValue = Number(m.nextMarkValue) || 0;
    var hasNextMark = !!m.hasNextMark;

    var key = [m.percentX100, m.deltaX100, m.marksOnGun, m.hasVehicle,
               m.currentAvg, m.nextMarkValue, m.hasNextMark].join('|');
    if (key === appliedKey) { return; }
    appliedKey = key;

    renderStars(m.marksOnGun);

    if (m.hasVehicle && percent > 0) {
      setText(elPercent, fmtDec(percent, 2) + '%');
    } else {
      setText(elPercent, '\u2014');
    }

    setText(document.getElementById('summaryAvg'), fmt(avg));
    setText(elDelta, fmtDelta(delta, 2));
    var dCls = 'summary__delta ' + (delta > 0.001 ? 'delta--pos'
                          : (delta < -0.001 ? 'delta--neg' : 'delta--zero'));
    if (elDelta) { elDelta.className = dCls; }
    setText(document.getElementById('summaryTarget'),
            hasNextMark ? fmt(nextValue) : '');

    if (elFill) {
      var p = Math.max(0, Math.min(100, percent));
      elFill.style.width = p + '%';
      if (delta > 0.001) { elFill.className = 'silhouette-fill fill--pos'; }
      else if (delta < -0.001) { elFill.className = 'silhouette-fill fill--neg'; }
      else { elFill.className = 'silhouette-fill fill--zero'; }
    }
  }

  function toBool(raw) {
    if (raw === true || raw === 1 || raw === '1' || raw === 'true') { return true; }
    if (raw === false || raw === 0 || raw === '0' || raw === 'false') { return false; }
    return true;
  }

  function applyVisible() {
    if (!booted) { return; }
    var raw;
    try { raw = window.model ? window.model.visible : undefined; }
    catch (e) { raw = undefined; }
    if (toBool(raw)) { document.body.classList.remove('is-hidden'); }
    else { document.body.classList.add('is-hidden'); }
  }

  function clientSize() {
    try {
      var c = window.viewEnv.getClientSizePx();
      if (c && c.width > 0) { return { w: c.width, h: c.height }; }
    } catch (e) {}
    return { w: 1920, h: 1080 };
  }

  function measureCard() {
    try {
      var rect = card.getBoundingClientRect();
      if (rect && rect.width >= 40 && rect.height >= 40) {
        readSize.w = Math.round(rect.width);
        readSize.h = Math.round(rect.height);
        return true;
      }
    } catch (e) {}
    return false;
  }

  function sendCmd(name, args) {
    if (!IN_GAME) { return; }
    try { window.model[name](args); }
    catch (e) { log(name + ' failed: ' + e); }
  }

  function sendReady() {
    if (!IN_GAME) { return; }
    try {
      var c = clientSize();
      window.model.ready({
        clientW: c.w, clientH: c.h,
        viewW: readSize.w, viewH: readSize.h,
        mode: 'windowed'
      });
      log('ready sent: client=' + c.w + 'x' + c.h +
          ' card=' + readSize.w + 'x' + readSize.h);
    } catch (e) { log('ready send failed: ' + e); }
  }

  function startDrag(e) {
    if (!IN_GAME) { return; }
    if (e.button !== undefined && e.button !== 0) { return; }
    downPos = { x: Number(e.screenX || e.clientX || 0), y: Number(e.screenY || e.clientY || 0) };
    try { card.classList.add('is-dragging'); } catch (err) {}
    try { document.body.classList.add('is-dragging'); } catch (err) {}
    sendCmd('dragStart', { lx: e.clientX, ly: e.clientY });
  }

  function endDrag(e) {
    if (!IN_GAME) { return; }
    try { card.classList.remove('is-dragging'); } catch (err) {}
    try { document.body.classList.remove('is-dragging'); } catch (err) {}
    sendCmd('dragEnd', { lx: e.clientX, ly: e.clientY });
    if (downPos) {
      var ux = Number(e.screenX || e.clientX || 0);
      var uy = Number(e.screenY || e.clientY || 0);
      if (Math.abs(ux - downPos.x) < 6 && Math.abs(uy - downPos.y) < 6) {
        try { window.model.ready({ toggleTable: 1 }); } catch (err) {}
      }
      downPos = null;
    }
  }

  function startGameMode() {
    log('game mode, version=' + (window.model.modVersion || '?'));

    var attempt = 0;
    var boot = function () {
      attempt += 1;
      if (!measureCard()) {
        if (attempt <= 20) { setTimeout(boot, 100); }
        return;
      }
      try { window.viewEnv.resizeViewRem(readSize.w, readSize.h); } catch (e) {}
      applyModel();
      sendReady();
      try { window.engine.on('viewEnv.onDataChanged', applyModel); } catch (e) {}
      setInterval(applyModel, 400);
      setInterval(applyVisible, 100);
      booted = true;
      applyVisible();
      log('boot complete: card=' + readSize.w + 'x' + readSize.h);
    };

    window.engine.whenReady.then(function () {
      setTimeout(boot, 50);
    });

    card.addEventListener('mousedown', startDrag);
    document.addEventListener('mouseup', endDrag);
  }

  function startMockMode() {
    document.documentElement.style.fontSize = '1px';
    document.body.style.display = 'flex';
    document.body.style.justifyContent = 'center';
    document.body.style.alignItems = 'center';
    document.body.style.minHeight = '100vh';
    renderStars(1);
    setText(elPercent, '72,67%');
    setText(document.getElementById('summaryAvg'), '1\u2009586');
    setText(elDelta, '+2,88%');
    if (elDelta) { elDelta.className = 'summary__delta delta--pos'; }
    setText(document.getElementById('summaryTarget'), '1\u2009802');
    if (elFill) {
      elFill.style.width = '72.67%';
      elFill.className = 'silhouette-fill fill--pos';
    }
    log('mock mode active');
  }

  if (IN_GAME) { startGameMode(); }
  else { startMockMode(); }
})();