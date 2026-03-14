// script.js
// رابط الـ backend المباشر على Hugging Face Spaces
const API_BASE = "https://ABDULSELAM1996-sl-dubbing-backend.hf.space";

// رابط العينة الصوتية على Cloudinary (احتياطي/للاختبار)
const SAMPLE_VOICE_URL = "https://res.cloudinary.com/dxbmvzsiz/video/upload/v1773450710/5_gtygjb.mp3";

// دالة مساعدة لتشغيل رابط صوتي في عنصر audio
function playUrl(url) {
  const player = document.getElementById("dubAud") || document.getElementById("player");
  if (!player) {
    alert("عنصر مشغل الصوت غير موجود في الصفحة (id='dubAud' أو id='player').");
    return;
  }
  player.src = url;
  player.play().catch(e => {
    console.warn("تعذر التشغيل التلقائي:", e);
  });
}

// دبلجة باستخدام gTTS (الصوت الافتراضي)
async function dubTextGtts() {
  const text = (document.getElementById("inputText") || {}).value;
  if (!text) { alert("أدخل نصاً أولاً"); return; }

  try {
    const resp = await fetch(`${API_BASE}/api/dub`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, lang: getSelectedLang(), voice_mode: "gtts" })
    });
    const data = await resp.json();
    if (data.success && data.audio_url) {
      playUrl(data.audio_url);
      setDownloadLink(data.audio_url);
    } else {
      alert("خطأ من الخادم: " + (data.error || JSON.stringify(data)));
    }
  } catch (err) {
    alert("فشل الاتصال بالـ backend: " + err.message);
  }
}

// دبلجة باستخدام XTTS (العينة المخصّصة)
// يتوقع أن الخادم يبحث عن العينة المرتبطة بالبريد المرسل
async function dubTextXtts() {
  const text = (document.getElementById("inputText") || {}).value;
  const email = (document.getElementById("userEmail") || {}).value;
  if (!text) { alert("أدخل نصاً أولاً"); return; }
  if (!email) { alert("أدخل بريد المستخدم المرتبط بالعينة"); return; }

  try {
    const resp = await fetch(`${API_BASE}/api/dub`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, lang: getSelectedLang(), voice_mode: "xtts", email })
    });
    const data = await resp.json();
    if (data.success && data.audio_url) {
      playUrl(data.audio_url);
      setDownloadLink(data.audio_url);
    } else {
      // اقتراح استخدام العينة المباشرة إذا لم توجد عينة مرتبطة
      if (data.error && /no voice|not found|no sample/i.test(data.error)) {
        if (confirm("لا توجد عينة مرتبطة بهذا البريد. هل تريد استخدام العينة الافتراضية المرفوعة؟")) {
          playUrl(SAMPLE_VOICE_URL);
          setDownloadLink(SAMPLE_VOICE_URL);
        }
      } else {
        alert("خطأ من الخادم: " + (data.error || JSON.stringify(data)));
      }
    }
  } catch (err) {
    alert("فشل الاتصال بالـ backend: " + err.message);
  }
}

// تعيين رابط التحميل لزر التحميل إن وُجد
function setDownloadLink(url) {
  const dl = document.getElementById("dubDl") || document.getElementById("downloadLink");
  if (dl) {
    dl.href = url;
    // اسم الملف المقترح
    dl.download = "dubbed.wav";
  }
}

// الحصول على اللغة المختارة (إن وُجد عنصر اختيار لغة)
function getSelectedLang() {
  const sel = document.getElementById("langSelect");
  return sel ? sel.value : "ar";
}

// دوال مساعدة إضافية (رفع عينة صوتية إلى backend إن رغبت)
async function uploadVoiceFile() {
  const email = (document.getElementById("userEmail") || {}).value;
  const fileInput = document.getElementById("voiceFile");
  if (!email) { alert("أدخل بريد المستخدم قبل الرفع"); return; }
  if (!fileInput || !fileInput.files.length) { alert("اختر ملف صوتي أولاً"); return; }

  const formData = new FormData();
  formData.append("email", email);
  formData.append("voice", fileInput.files[0]);

  try {
    const resp = await fetch(`${API_BASE}/api/upload-voice`, {
      method: "POST",
      body: formData
    });
    const data = await resp.json();
    if (data.success) {
      alert("تم رفع العينة بنجاح.");
    } else {
      alert("فشل الرفع: " + (data.error || JSON.stringify(data)));
    }
  } catch (err) {
    alert("فشل الاتصال بالـ backend أثناء الرفع: " + err.message);
  }
}
