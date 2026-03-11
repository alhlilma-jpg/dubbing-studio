/**
 * ╔══════════════════════════════════════════════════════╗
 *  sl-Dubbing & Translation — config.js
 *  ⚠️  هذا الملف هو المصدر الوحيد لكل القيم المشتركة
 *  أي تغيير هنا يتغير تلقائياً في جميع الصفحات
 * ╚══════════════════════════════════════════════════════╝
 */

const CONFIG = {

  /* ─────────────────────────────────────────────
     هوية التطبيق
  ───────────────────────────────────────────── */
  app: {
    name:      "sl-Dubbing & Translation",
    shortName: "sl-Dubbing",
    tagline:   "دبلجة وترجمة بالذكاء الاصطناعي",
    logoGif:   "logo.gif",
    logoPng:   "logo.png",
    year:      new Date().getFullYear(),
  },

  /* ─────────────────────────────────────────────
     الروابط — غيّر backend هنا فقط
  ───────────────────────────────────────────── */
  urls: {
    backend: "https://sl-dubbing.onrender.com",
    pages: {
      home:    "index.html",
      login:   "login.html",
      tts:     "tts.html",
      dubbing: "dubbing.html",
      privacy: "privacy.html",
    }
  },

  /* ─────────────────────────────────────────────
     عناوين الصفحات
  ───────────────────────────────────────────── */
  pageTitles: {
    home:    "SL-Dubbing | منصة الدبلجة الذكية",
    tts:     "نطق النصوص - sl-Dubbing",
    dubbing: "دبلجة AI - sl-Dubbing",
    login:   "تسجيل الدخول - sl-Dubbing",
    privacy: "سياسة الخصوصية | sl-Dubbing",
  },

  /* ─────────────────────────────────────────────
     اللغات المدعومة — تُستخدم في TTS و Dubbing
  ───────────────────────────────────────────── */
  languages: [
    { code: 'ar', name: 'العربية',    flag: '🇸🇦' },
    { code: 'en', name: 'English',    flag: '🇺🇸' },
    { code: 'es', name: 'Español',    flag: '🇪🇸' },
    { code: 'fr', name: 'Français',   flag: '🇫🇷' },
    { code: 'de', name: 'Deutsch',    flag: '🇩🇪' },
    { code: 'it', name: 'Italiano',   flag: '🇮🇹' },
    { code: 'ru', name: 'Русский',    flag: '🇷🇺' },
    { code: 'tr', name: 'Türkçe',     flag: '🇹🇷' },
    { code: 'zh', name: '中文',        flag: '🇨🇳' },
    { code: 'hi', name: 'हिन्दी',      flag: '🇮🇳' },
    { code: 'fa', name: 'فارسی',      flag: '🇮🇷' },
    { code: 'sv', name: 'Svenska',    flag: '🇸🇪' },
    { code: 'nl', name: 'Nederlands', flag: '🇳🇱' },
  ],

  /* ─────────────────────────────────────────────
     حسابات Google للعرض في صفحة تسجيل الدخول
  ───────────────────────────────────────────── */
  googleAccounts: [
    { name: 'Mona Alhil',       email: 'ahlil.ma@gmail.com',   initials: 'MA' },
    { name: 'ALHASHMI Design',  email: 'abd199641@gmail.com',   initials: 'AD' },
    { name: 'Rhf Alhil',        email: 'rhfalhil@gmail.com',    initials: 'RA' },
  ],

  /* ─────────────────────────────────────────────
     حدود الاستخدام المجاني
  ───────────────────────────────────────────── */
  limits: {
    freeUses: 6,
  },

  /* ─────────────────────────────────────────────
     الأسعار وروابط الشراء — غيّر الأسعار هنا
  ───────────────────────────────────────────── */
  pricing: {
    tts: {
      price:      10,
      currency:   'USD',
      label:      'نطق النصوص',
      icon:       '🎙️',
      type:       'tts',
      badge:      'TTS',
      lemonLink:  'https://sl-dubbing.lemonsqueezy.com/buy/tts',
      features: [
        'وصول غير محدود للنطق',
        '13 لغة مدعومة',
        'تحكم بالسرعة والطبقة',
        'تحميل الصوت MP3',
      ],
      desc: 'حوّل أي نص إلى صوت بالذكاء الاصطناعي بـ 13 لغة.',
    },
    dub: {
      price:      50,
      currency:   'USD',
      label:      'دبلجة AI',
      icon:       '🎬',
      type:       'dub',
      badge:      'AI DUB',
      lemonLink:  'https://sl-dubbing.lemonsqueezy.com/buy/dubbing',
      features: [
        'دبلجة غير محدودة',
        'نسخ الصوت XTTS v2',
        'رفع ملفات SRT',
        'تصدير WAV احترافي',
      ],
      desc: 'دبلج مقاطعك بصوتك الحقيقي مع تقنية XTTS v2.',
    },
    srt: {
      price:      10,
      currency:   'USD',
      label:      'ترجمة SRT',
      icon:       '📝',
      type:       'srt',
      badge:      'SRT',
      lemonLink:  'https://sl-dubbing.lemonsqueezy.com/buy/srt',
      features: [
        'ترجمة غير محدودة',
        'دعم 13 لغة',
        'حفظ توقيت الترجمة',
        'تنزيل ملف SRT مترجم',
      ],
      desc: 'ترجم ملفات SRT تلقائياً مع حفظ التوقيت الكامل.',
    },
  },

  /* ─────────────────────────────────────────────
     معلومات المالك
  ───────────────────────────────────────────── */
  owner: {
    name:    "ALHASHMI",
    youtube: "https://www.youtube.com/@alhashmimh",
    github:  "https://github.com/alhlilma-jpg",
    email:   "abd199641@gmail.com",
  },

  /* ─────────────────────────────────────────────
     نصوص الواجهة المشتركة
  ───────────────────────────────────────────── */
  ui: {
    backBtn:       "← رجوع",
    loginBtn:      "تسجيل الدخول",
    logoutBtn:     "خروج",
    buyBtn:        "شراء مدى الحياة",
    serverOnline:  "الخادم متصل",
    serverOffline: "الخادم غير متاح",
    freeLabel:     (n) => `${n} استخدام مجاني متبقٍ`,
    unlimitedLabel:"غير محدود ✓",
    toastLoading:  "جاري التحميل...",
    toastSuccess:  "✅ تم بنجاح!",
    toastError:    "❌ حدث خطأ",
    footerText:    (year, name) => `${name} © ${year} - جميع الحقوق محفوظة`,
  },

};

/* ─────────────────────────────────────────────
   دوال مساعدة متاحة لجميع الصفحات
───────────────────────────────────────────── */

/** تعيين عنوان الصفحة من CONFIG */
function setPageTitle(key) {
  document.title = CONFIG.pageTitles[key] || CONFIG.app.name;
}

/** بناء شبكة اللغات في أي container */
function renderLanguageGrid(containerId, selectedCode = 'ar', onSelect) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = CONFIG.languages.map(l => `
    <button class="lang-btn ${l.code === selectedCode ? 'active' : ''}"
            onclick="(${onSelect.toString()})('${l.code}', this)">
      <span class="lang-flag">${l.flag}</span>
      <span>${l.name}</span>
    </button>
  `).join('');
}

/** بناء قائمة حسابات Google */
function renderGoogleAccounts(containerId, onClickFn) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';
  CONFIG.googleAccounts.forEach(account => {
    const div = document.createElement('div');
    div.className = 'google-account-item';
    div.innerHTML = `
      <div class="account-avatar">${account.initials}</div>
      <div class="account-info">
        <div class="account-name">${account.name}</div>
        <div class="account-email">${account.email}</div>
      </div>
    `;
    div.onclick = () => onClickFn(account);
    container.appendChild(div);
  });
}

/** بناء كروت الدفع */
function renderPricingCards(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = Object.values(CONFIG.pricing).map(p => `
    <div class="payment-card ${p.type}">
      <div class="payment-badge ${p.type}">${p.icon} ${p.badge}</div>
      <div class="payment-icon">${p.icon}</div>
      <div class="payment-title">${p.label}</div>
      <div class="payment-desc">${p.desc}</div>
      <ul class="payment-features">
        ${p.features.map(f => `<li>${f}</li>`).join('')}
      </ul>
      <div class="price-box">
        <div class="price-amount ${p.type}">$${p.price}</div>
        <div class="price-label">دفعة واحدة — مدى الحياة</div>
      </div>
      <a href="${p.lemonLink}" target="_blank" class="payhip-btn ${p.type}">
        🛒 ${CONFIG.ui.buyBtn}
      </a>
    </div>
  `).join('');
}

/** رابط Backend مركزي */
const API_URL = CONFIG.urls.backend;
