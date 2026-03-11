/**
 * sl-Dubbing — main.js
 * دوال مشتركة لكل الصفحات
 */

/* ─── Toast ─────────────────────────────────────── */
function showToast(msg, duration = 3000) {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add('show');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.remove('show'), duration);
}

/* ─── Auth بسيط ─────────────────────────────────── */
const Auth = {
  _key: 'sl_user',

  getCurrentUser() {
    try {
      const data = localStorage.getItem(this._key);
      return data ? JSON.parse(data) : null;
    } catch { return null; }
  },

  saveUser(user) {
    try { localStorage.setItem(this._key, JSON.stringify(user)); } catch {}
  },

  logout() {
    localStorage.removeItem(this._key);
  },

  login(email, password) {
    // محاولة الاتصال بالخادم
    return fetch(`${CONFIG.urls.backend}/api/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
      signal: AbortSignal.timeout(8000)
    })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        const user = {
          email: data.email,
          name: data.email.split('@')[0],
          avatar: data.email[0].toUpperCase(),
          usage: data.usage || { tts:0, dub:0, srt:0 },
          unlocked: data.unlocked || { tts:false, dub:false, srt:false },
          timestamp: Date.now()
        };
        this.saveUser(user);
        return true;
      }
      return false;
    })
    .catch(() => false);
  },

  consumeUsage(feature) {
    const user = this.getCurrentUser();
    if (!user) return;
    if (!user.usage) user.usage = { tts:0, dub:0, srt:0 };
    user.usage[feature] = (user.usage[feature] || 0) + 1;
    this.saveUser(user);

    // تسجيل في الخادم
    fetch(`${CONFIG.urls.backend}/api/consume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: user.email, feature })
    }).catch(() => {});
  }
};

/* ─── API ────────────────────────────────────────── */
const API = {
  generateDubbing({ text, lang, email, voiceSample }) {
    return fetch(`${CONFIG.urls.backend}/api/dub`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, lang, email, feature: 'dub' }),
      signal: AbortSignal.timeout(30000)
    }).then(r => r.json());
  }
};
