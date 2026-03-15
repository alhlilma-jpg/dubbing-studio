// ============================================================
// script.js — العقل البرمجي لواجهة sl-Dubbing
// ============================================================

// ── الإعدادات المركزية ────────────────────────────────────────
const CONFIG = {
  // رابط الخادم — يتغير تلقائياً حسب البيئة
  API_BASE: 'https://abdulselam1996-sl-dubbing-backend.hf.space',
  GUEST_LIMIT: 6,
  LANGS: [
    {c:'ar', n:'العربية',   f:'🇸🇦'},
    {c:'en', n:'English',   f:'🇺🇸'},
    {c:'es', n:'Español',   f:'🇪🇸'},
    {c:'fr', n:'Français',  f:'🇫🇷'},
    {c:'de', n:'Deutsch',   f:'🇩🇪'},
    {c:'it', n:'Italiano',  f:'🇮🇹'},
    {c:'ru', n:'Русский',   f:'🇷🇺'},
    {c:'tr', n:'Türkçe',    f:'🇹🇷'},
    {c:'zh', n:'中文',       f:'🇨🇳'},
    {c:'hi', n:'हिन्दी',    f:'🇮🇳'},
    {c:'fa', n:'فارسی',     f:'🇮🇷'},
    {c:'sv', n:'Svenska',   f:'🇸🇪'},
    {c:'nl', n:'Nederlands', f:'🇳🇱'},
  ]
};

// ── الحالة ────────────────────────────────────────────────────
const STATE = {
  lang:        'ar',
  voiceMode:   'gtts',     // 'gtts' أو 'xtts'
  srtData:     [],
  isRecording: false,
  recorder:    null,
  chunks:      [],
  voiceBlob:   null,
  voiceUploaded: false,
};

// ── Toast ─────────────────────────────────────────────────────
function showToast(msg, duration = 3000) {
  let t = document.getElementById('toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast';
    t.style.cssText = 'position:fixed;bottom:28px;left:50%;transform:translateX(-50%) translateY(120px);background:linear-gradient(135deg,#7c3aed,#2563eb);color:#fff;padding:14px 28px;border-radius:12px;font-weight:600;box-shadow:0 10px 35px rgba(0,0,0,.4);transition:transform .3s;z-index:9999';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.transform = 'translateX(-50%) translateY(0)';
  clearTimeout(t._t);
  t._t = setTimeout(() => t.style.transform = 'translateX(-50%) translateY(120px)', duration);
}

// ── Header المستخدم ───────────────────────────────────────────
function initHeader() {
  const hdr = document.getElementById('hdr');
  if (!hdr) return;
  try {
    const u = JSON.parse(localStorage.getItem('sl_user'));
    if (u) {
      hdr.innerHTML = `
        <div class="avatar">${u.avatar || '👤'}</div>
        <span class="username">${u.name || u.email}</span>
        <button class="btn-logout" onclick="logout()">خروج</button>`;
    } else {
      hdr.innerHTML = `<a href="login.html" class="btn-login">تسجيل الدخول</a>`;
    }
  } catch(e) {
    hdr.innerHTML = `<a href="login.html" class="btn-login">تسجيل الدخول</a>`;
  }
}

function logout() {
  localStorage.removeItem('sl_user');
  location.href = 'index.html';
}

function requireLogin() {
  try {
    const u = JSON.parse(localStorage.getItem('sl_user'));
    if (u) return u;
  } catch(e) {}
  sessionStorage.setItem('returnUrl', location.href);
  location.href = 'login.html';
  return null;
}

// ── فحص الخادم ───────────────────────────────────────────────
async function checkServer() {
  const badge = document.getElementById('srv');
  const txt   = document.getElementById('srvTxt');
  if (!badge) return;
  try {
    const r = await fetch(CONFIG.API_BASE + '/api/health',
                          {signal: AbortSignal.timeout(6000)});
    const ok = r.ok;
    badge.className = 'srv-badge' + (ok ? ' on' : '');
    txt.textContent = ok ? 'الخادم متصل ✓' : 'الخادم غير متاح';
  } catch {
    badge.className = 'srv-badge';
    if (txt) txt.textContent = 'الخادم غير متاح';
  }
}

// ── اللغة ─────────────────────────────────────────────────────
function initLangs(containerId = 'langs') {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = CONFIG.LANGS.map(l => `
    <button class="lang-btn ${l.c === STATE.lang ? 'active' : ''}"
            onclick="selectLang('${l.c}', this)">
      <span class="lang-flag">${l.f}</span>
      <span>${l.n}</span>
    </button>`).join('');
}

function selectLang(code, btn) {
  STATE.lang = code;
  document.querySelectorAll('.lang-btn')
          .forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

// ── اختيار الصوت ─────────────────────────────────────────────
function selectVoice(mode, el) {
  STATE.voiceMode = mode;
  document.querySelectorAll('.voice-choice').forEach(e => {
    e.style.borderColor = 'rgba(255,255,255,.1)';
    e.style.background  = 'rgba(255,255,255,.02)';
  });
  el.style.borderColor = mode === 'xtts' ? '#a78bfa' : '#60a5fa';
  el.style.background  = mode === 'xtts'
    ? 'rgba(124,58,237,.15)' : 'rgba(96,165,250,.12)';
}

// ── SRT ───────────────────────────────────────────────────────
function loadSRTFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById('srtTxt').value = e.target.result;
    parseSRT();
  };
  reader.readAsText(file);
}

function parseSRT() {
  const content = document.getElementById('srtTxt')?.value;
  if (!content) { showToast('الرجاء إدخال محتوى SRT'); return; }
  STATE.srtData = [];
  let cur = null;
  for (let line of content.split('\n')) {
    line = line.trim();
    if (!line) continue;
    if (/^\d+$/.test(line)) {
      if (cur) STATE.srtData.push(cur);
      cur = {i: parseInt(line), t: '', x: ''};
    } else if (line.includes('-->')) {
      if (cur) cur.t = line;
    } else if (cur) {
      cur.x += line + ' ';
    }
  }
  if (cur) STATE.srtData.push(cur);
  const list = document.getElementById('srtList');
  if (list) {
    list.innerHTML = STATE.srtData.map(i =>
      `<div class="srt-item">
        <span class="srt-time">${i.t}</span>
        <span>${i.x}</span>
      </div>`).join('');
    list.style.display = 'block';
  }
  showToast(`✅ تم تحليل ${STATE.srtData.length} جملة`);
}

// ── توليد الدبلجة ─────────────────────────────────────────────
async function genDub() {
  if (!STATE.srtData.length) {
    showToast('الرجاء تحميل ملف SRT أولاً'); return;
  }
  const user = JSON.parse(localStorage.getItem('sl_user') || '{}');
  const btn  = document.getElementById('dubBtn');
  const prog = document.getElementById('prog');
  const pf   = document.getElementById('pf');
  const pt   = document.getElementById('pt');

  btn.disabled = true;
  prog.classList.add('on');
  pf.style.width = '0%';

  const fullText = STATE.srtData.map(i => i.x.trim()).join('\n');

  // شريط تقدم وهمي
  let p = 0;
  const iv = setInterval(() => {
    p = Math.min(p + 2, 85);
    pf.style.width = p + '%';
    if (pt) pt.textContent = 'جاري التوليد... ' + p + '%';
  }, 600);

  try {
    const res = await fetch(CONFIG.API_BASE + '/api/dub', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        text:       fullText,
        lang:       STATE.lang,
        email:      user.email || '',
        feature:    'dub',
        voice_mode: STATE.voiceMode
      }),
      signal: AbortSignal.timeout(120000)
    });

    clearInterval(iv);
    pf.style.width = '100%';
    const d = await res.json();

    if (d.success && d.audio_url) {
      prog.classList.remove('on');
      btn.disabled = false;
      const aud = document.getElementById('dubAud');
      const dl  = document.getElementById('dubDl');
      aud.src = d.audio_url;
      aud.classList.add('show');
      dl.href = d.audio_url;
      dl.classList.add('show');
      const method = d.method === 'xtts_v2'
        ? 'بصوت ABDU SELAM 🎤' : 'بصوت افتراضي';
      showToast('✅ تم التوليد ' + method, 4000);
      return;
    }
    showToast('❌ ' + (d.error || 'فشل التوليد'));
  } catch(e) {
    clearInterval(iv);
    showToast('❌ تعذر الاتصال بالخادم');
  }
  pf.style.width = '0%';
  prog.classList.remove('on');
  btn.disabled = false;
}

// ── تحديث رابط الخادم (للـ Colab) ───────────────────────────
function setBackendUrl(url) {
  CONFIG.API_BASE = url.trim().replace(/\/$/, '');
  localStorage.setItem('sl_backend_url', CONFIG.API_BASE);
  showToast('✅ تم تحديث رابط الخادم');
}

// ── تهيئة الصفحة ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // استرجع رابط Colab إن كان محفوظاً
  const saved = localStorage.getItem('sl_backend_url');
  if (saved) CONFIG.API_BASE = saved;

  initHeader();
  initLangs();
  checkServer();
});
