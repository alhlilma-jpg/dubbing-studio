# =============================================================
# voice_engine.py — محرك الصوت الاحترافي
# يُستخدم من app.py لتوليد الصوت بنبرة ABDU SELAM
# =============================================================
import os, uuid, logging, requests, hashlib
from pathlib import Path

logger = logging.getLogger(__name__)

# ── إعدادات Cloudinary ───────────────────────────────────────
CLOUD_NAME    = os.environ.get('CLOUDINARY_CLOUD_NAME', 'dxbmvzsiz')
API_KEY       = os.environ.get('CLOUDINARY_API_KEY',    '432687952743126')
API_SECRET    = os.environ.get('CLOUDINARY_API_SECRET', 'BrFvzlPFXBJZ-B-cZyxCc-0wHRo')
FOLDER        = "sl_voices"
DEFAULT_VOICE = os.environ.get('DEFAULT_VOICE_ID', '5_gtygjb')

# مسارات مؤقتة
TMP = Path('/tmp')
TMP.mkdir(exist_ok=True)

# ── خريطة اللغات ─────────────────────────────────────────────
XTTS_LANGS = {
    'ar':'ar', 'en':'en', 'es':'es', 'fr':'fr', 'de':'de',
    'it':'it', 'ru':'ru', 'tr':'tr', 'zh':'zh-cn', 'hi':'hi', 'nl':'nl'
}
GTTS_LANGS = {
    'ar':'ar', 'en':'en', 'es':'es', 'fr':'fr', 'de':'de', 'it':'it',
    'ru':'ru', 'tr':'tr', 'zh':'zh-TW', 'hi':'hi', 'fa':'fa', 'sv':'sv', 'nl':'nl'
}

# ── XTTS v2 ───────────────────────────────────────────────────
_TTS_ENGINE = None

def get_tts_engine():
    global _TTS_ENGINE
    if _TTS_ENGINE is not None:
        return _TTS_ENGINE
    try:
        from TTS.api import TTS
        logger.info("⏳ Loading XTTS v2 model...")
        _TTS_ENGINE = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        logger.info("✅ XTTS v2 loaded")
        return _TTS_ENGINE
    except Exception as e:
        logger.error(f"❌ XTTS load failed: {e}")
        return None

# ── Cloudinary ────────────────────────────────────────────────
def _cloudinary_url(public_id):
    return f"https://res.cloudinary.com/{CLOUD_NAME}/raw/upload/{FOLDER}/{public_id}"

def fetch_voice_sample(public_id=None):
    """
    تحميل عينة الصوت من Cloudinary إلى /tmp
    يُخزّن محلياً لتجنب التحميل في كل مرة
    """
    vid   = public_id or DEFAULT_VOICE
    local = TMP / f"voice_{vid}.wav"

    # إذا موجود محلياً وحجمه طبيعي → استخدمه مباشرة
    if local.exists() and local.stat().st_size > 5000:
        logger.info(f"✅ Using cached voice: {local}")
        return str(local)

    # حمّله من Cloudinary
    url = _cloudinary_url(vid)
    logger.info(f"⬇️ Downloading voice from Cloudinary: {url}")
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            with open(local, 'wb') as f:
                f.write(r.content)
            logger.info(f"✅ Voice saved: {local} ({local.stat().st_size} bytes)")
            return str(local)
        else:
            logger.error(f"❌ Cloudinary returned {r.status_code}")
    except Exception as e:
        logger.error(f"❌ Download error: {e}")
    return None

# ── توليد الصوت بـ XTTS v2 ───────────────────────────────────
def generate_xtts(text: str, lang: str, voice_path: str, out_path: str) -> bool:
    """
    توليد صوت بنفس نبرة voice_path
    يدعم: ar en es fr de it ru tr zh hi nl
    """
    tts = get_tts_engine()
    if tts is None:
        return False

    xtts_lang = XTTS_LANGS.get(lang)
    if not xtts_lang:
        logger.warning(f"XTTS لا يدعم اللغة: {lang}")
        return False

    # تقسيم النص إذا كان طويلاً (XTTS يدعم حتى ~400 حرف)
    chunks = _split_text(text, max_chars=350)
    if len(chunks) == 1:
        try:
            tts.tts_to_file(
                text=text,
                speaker_wav=voice_path,
                language=xtts_lang,
                file_path=out_path
            )
            logger.info(f"✅ XTTS generated: {out_path}")
            return True
        except Exception as e:
            logger.error(f"❌ XTTS error: {e}")
            return False
    else:
        # دمج أجزاء متعددة
        return _generate_xtts_chunked(tts, chunks, xtts_lang, voice_path, out_path)

def _generate_xtts_chunked(tts, chunks, lang, voice_path, out_path):
    """توليد ودمج أجزاء النص الطويل"""
    try:
        import wave, array
        parts = []
        for i, chunk in enumerate(chunks):
            part = TMP / f"chunk_{uuid.uuid4()}.wav"
            tts.tts_to_file(text=chunk, speaker_wav=voice_path,
                            language=lang, file_path=str(part))
            parts.append(part)

        # دمج WAV files
        _merge_wav(parts, out_path)
        for p in parts:
            p.unlink(missing_ok=True)
        logger.info(f"✅ XTTS chunked ({len(chunks)} parts) → {out_path}")
        return True
    except Exception as e:
        logger.error(f"❌ XTTS chunked error: {e}")
        return False

def _merge_wav(files, output):
    """دمج ملفات WAV"""
    import wave
    data = []
    params = None
    for f in files:
        with wave.open(str(f), 'rb') as w:
            if params is None:
                params = w.getparams()
            data.append(w.readframes(w.getnframes()))
    with wave.open(str(output), 'wb') as out:
        out.setparams(params)
        for d in data:
            out.writeframes(d)

def _split_text(text, max_chars=350):
    """تقسيم النص إلى أجزاء عند علامات الترقيم"""
    if len(text) <= max_chars:
        return [text]
    chunks, current = [], ""
    for sentence in text.replace('،', '.').replace('؟', '.').replace('!', '.').split('.'):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) < max_chars:
            current += sentence + '. '
        else:
            if current:
                chunks.append(current.strip())
            current = sentence + '. '
    if current:
        chunks.append(current.strip())
    return chunks if chunks else [text]

# ── توليد بـ gTTS ────────────────────────────────────────────
def generate_gtts(text: str, lang: str, out_path: str) -> bool:
    """توليد صوت افتراضي بـ gTTS — يدعم كل اللغات"""
    try:
        from gtts import gTTS
        gtts_lang = GTTS_LANGS.get(lang, 'en')
        gTTS(text=text, lang=gtts_lang, slow=False).save(out_path)
        logger.info(f"✅ gTTS generated: {out_path}")
        return True
    except Exception as e:
        logger.error(f"❌ gTTS error: {e}")
        return False

# ── الدالة الرئيسية ───────────────────────────────────────────
def synthesize(text: str, lang: str, use_custom_voice: bool = False) -> tuple:
    """
    الدالة الرئيسية لتوليد الصوت

    Args:
        text: النص المراد تحويله
        lang: رمز اللغة (ar, en, es, ...)
        use_custom_voice: True = صوت ABDU SELAM | False = صوت افتراضي

    Returns:
        (file_path, method) أو (None, None) عند الفشل
    """
    out_wav = TMP / f"out_{uuid.uuid4()}.wav"
    out_mp3 = TMP / f"out_{uuid.uuid4()}.mp3"

    if use_custom_voice:
        voice = fetch_voice_sample()
        if voice:
            if generate_xtts(text, lang, voice, str(out_wav)):
                return str(out_wav), 'xtts_v2'
            logger.warning("XTTS فشل → gTTS fallback")
        else:
            logger.warning("العينة غير متاحة → gTTS fallback")

    # gTTS fallback
    if generate_gtts(text, lang, str(out_mp3)):
        return str(out_mp3), 'gtts'

    return None, None

# ── اختبار مباشر ─────────────────────────────────────────────
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("🧪 اختبار voice_engine...")

    # اختبار gTTS
    path, method = synthesize("مرحباً بك في sl-Dubbing", "ar", use_custom_voice=False)
    print(f"gTTS: {method} → {path}")

    # اختبار XTTS (يحتاج اتصال Cloudinary)
    path, method = synthesize("Hello from sl-Dubbing", "en", use_custom_voice=True)
    print(f"XTTS: {method} → {path}")
