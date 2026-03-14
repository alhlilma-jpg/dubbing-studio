# voice_engine.py
# ==============================================================
# محرك الصوت – يُستدعى من server.py لتوليد الصوت
# يدعم:
#   • XTTS‑v2 مع عينة صوت مخصَّصة (ABDU SELAM أو أي عينة أخرى)
#   • gTTS كبديل افتراضي
# ==============================================================
import os, uuid, logging
from pathlib import Path

# -----------------------------------------------------------------
# Logging
# -----------------------------------------------------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )

# -----------------------------------------------------------------
# مسارات مؤقتة
# -----------------------------------------------------------------
TMP = Path('/tmp')
TMP.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------
# خرائط اللغات
# -----------------------------------------------------------------
XTTS_LANGS = {
    'ar': 'ar', 'en': 'en', 'es': 'es', 'fr': 'fr',
    'de': 'de', 'it': 'it', 'ru': 'ru', 'tr': 'tr',
    'zh': 'zh-cn', 'hi': 'hi', 'nl': 'nl'
}
GTTS_LANGS = {
    'ar': 'ar', 'en': 'en', 'es': 'es', 'fr': 'fr',
    'de': 'de', 'it': 'it', 'ru': 'ru', 'tr': 'tr',
    'zh': 'zh', 'hi': 'hi', 'fa': 'fa',
    'sv': 'sv', 'nl': 'nl'
}

# -----------------------------------------------------------------
# استيراد الأدوات المساعدة من utils.py
# -----------------------------------------------------------------
from utils import fetch_voice_sample, mp3_to_wav

# -----------------------------------------------------------------
# تحميل نموذج XTTS مرة واحدة
# -----------------------------------------------------------------
_TTS_ENGINE = None

def _load_xtts():
    """تحميل نموذج XTTS v2 مرة واحدة فقط."""
    global _TTS_ENGINE
    if _TTS_ENGINE is not None:
        return _TTS_ENGINE
    try:
        from TTS.api import TTS
        logger.info("⏳ Loading XTTS v2 model …")
        _TTS_ENGINE = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        logger.info("✅ XTTS v2 loaded")
        return _TTS_ENGINE
    except Exception as exc:
        logger.error(f"❌ XTTS load failed: {exc}")
        return None


# -----------------------------------------------------------------
# توليد صوت بـ XTTS
# -----------------------------------------------------------------
def _synthesize_xtts(text: str, lang: str, voice_path: str, out_path: str) -> bool:
    """يُعيد True إذا نجح توليد الصوت بـ XTTS."""
    tts = _load_xtts()
    if not tts:
        return False

    xtts_lang = XTTS_LANGS.get(lang)
    if not xtts_lang:
        logger.warning(f"XTTS does not support language '{lang}'")
        return False

    try:
        tts.tts_to_file(
            text=text,
            speaker_wav=voice_path,
            language=xtts_lang,
            file_path=out_path,
        )
        logger.info(f"✅ XTTS generated → {out_path}")
        return True
    except Exception as exc:
        logger.error(f"❌ XTTS generation error: {exc}")
        return False


# -----------------------------------------------------------------
# توليد صوت بـ gTTS
# -----------------------------------------------------------------
def _synthesize_gtts(text: str, lang: str, out_path: str) -> bool:
    """يُعيد True إذا نجح توليد الصوت بـ gTTS."""
    try:
        from gtts import gTTS
        gtts_lang = GTTS_LANGS.get(lang, 'en')
        gTTS(text=text, lang=gtts_lang, slow=False).save(out_path)
        logger.info(f"✅ gTTS generated → {out_path}")
        return True
    except Exception as exc:
        logger.error(f"❌ gTTS error: {exc}")
        return False


# -----------------------------------------------------------------
# الدالة العامة التي يُستدعى منها من الـ backend
# -----------------------------------------------------------------
def synthesize(text: str, lang: str, use_custom_voice: bool = False) -> tuple:
    """
    توليد ملف صوت من النص.

    Parameters
    ----------
    text               : النص المطلوب تحويله.
    lang               : رمز اللغة (ar, en, …).
    use_custom_voice   : True → استخدم عينة الصوت المخصَّصة (ABDU SELAM أو غيرها)؛
                         False → استخدم gTTS (الصوت الافتراضي).

    Returns
    -------
    (file_path, method)   – `method` إما "xtts_v2" أو "gtts".
    (None, None)         – عند الفشل.
    """
    out_wav = TMP / f"out_{uuid.uuid4()}.wav"
    out_mp3 = TMP / f"out_{uuid.uuid4()}.mp3"

    if use_custom_voice:
        voice_path = fetch_voice_sample()            # تحمَّل/استخدم العينة الافتراضية
        if voice_path:
            if _synthesize_xtts(text, lang, str(voice_path), str(out_wav)):
                return str(out_wav), 'xtts_v2'
            logger.warning("XTTS generation failed → fallback to gTTS")
        else:
            logger.warning("Voice sample not available → fallback to gTTS")

    # fallback إلى gTTS
    if _synthesize_gtts(text, lang, str(out_mp3)):
        # تحويل MP3 إلى WAV لتوحيد الصيغة مع باقي ال API
        if mp3_to_wav(out_mp3, out_wav):
            return str(out_wav), 'gtts'
        else:
            logger.error("ffmpeg conversion failed (gTTS → WAV)")
            return None, None
    else:
        return None, None


# -----------------------------------------------------------------
# اختبار مباشر (python voice_engine.py)
# -----------------------------------------------------------------
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("\n🧪 اختبار voice_engine …")

    # اختبار gTTS (بدون عينة مخصَّصة)
    p, m = synthesize("مرحباً بكم في sl‑Dubbing", "ar", use_custom_voice=False)
    print(f"gTTS   → method: {m}, file: {p}")

    # اختبار XTTS (يتطلب اتصال Cloudinary + العينة الافتراضية)
    p, m = synthesize("Hello from sl‑Dubbing", "en", use_custom_voice=True)
    print(f"XTTS   → method: {m}, file: {p}")

    print("\n✅ الاختبار انتهى")
