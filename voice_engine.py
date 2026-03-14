# ---------------------------------------------------------------
# voice_engine.py — محرك الصوت الاحترافي
# يُستدعى من server.py لتوليد صوت XTTS أو gTTS
# ---------------------------------------------------------------
import os, uuid, logging
from pathlib import Path

# ---------------------- Logging ----------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')

# ---------------------- مسارات مؤقتة ----------------------
TMP = Path('/tmp')
TMP.mkdir(parents=True, exist_ok=True)

# ---------------------- خريطة اللغات ----------------------
XTTS_LANGS = {
    'ar': 'ar', 'en': 'en', 'es': 'es', 'fr': 'fr', 'de': 'de',
    'it': 'it', 'ru': 'ru', 'tr': 'tr',
    'zh': 'zh-cn', 'hi': 'hi', 'nl': 'nl'
}
GTTS_LANGS = {
    'ar': 'ar', 'en': 'en', 'es': 'es', 'fr': 'fr',
    'de': 'de', 'it': 'it', 'ru': 'ru', 'tr': 'tr',
    'zh': 'zh', 'hi': 'hi', 'fa': 'fa',
    'sv': 'sv', 'nl': 'nl'
}

# ---------------------- استيراد الأدوات المساعدة ----------------------
from utils import fetch_voice_sample, mp3_to_wav   # عمليات Cloudinary والتحويل

# ---------------------- تحميل نموذج XTTS (مرة واحدة) ----------------------
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
        logger.error(f"❌ Failed to load XTTS model: {exc}")
        return None


# ---------------------- توليد صوت بـ XTTS ----------------------
def _synthesize_xtts(text: str, lang: str, voice_path: str, out_path: str) -> bool:
    """يُعيد True إذا نجح توليد الصوت عبر XTTS."""
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


# ---------------------- توليد صوت بـ gTTS (fallback) ----------------------
def _synthesize_gtts(text: str, lang: str, out_path: str) -> bool:
    """يُعيد True إذا نجح توليد الصوت عبر gTTS."""
    try:
        from gtts import gTTS
        gtts_lang = GTTS_LANGS.get(lang, 'en')
        gTTS(text=text, lang=gtts_lang, slow=False).save(out_path)
        logger.info(f"✅ gTTS generated → {out_path}")
        return True
    except Exception as exc:
        logger.error(f"❌ gTTS error: {exc}")
        return False


# ---------------------- الواجهة العامة ----------------------
def synthesize(text: str, lang: str, use_custom_voice: bool = False) -> tuple:
    """
    توليد ملف صوت من النص.
    تُعيد (file_path, method) أو (None, None) عند الفشل.

    Parameters
    ----------
    text                – النص المراد تحويله.
    lang                – رمز اللغة (ar, en, …).
    use_custom_voice    – True → استخدم عينة صوت من Cloudinary (XTTS);
                         False → gTTS (الصوت الافتراضي).
    """
    out_wav = TMP / f"out_{uuid.uuid4()}.wav"
    out_mp3 = TMP / f"out_{uuid.uuid4()}.mp3"

    # ---------- محاولة XTTS (إذا طلبت صوت مخصَّص) ----------
    if use_custom_voice:
        voice_path = fetch_voice_sample()   # يحمّل العينة من Cloudinary / يستخدم الكاش
        if voice_path:
            if _synthesize_xtts(text, lang, str(voice_path), str(out_wav)):
                return str(out_wav), 'xtts_v2'
            logger.warning("XTTS generation failed → fallback إلى gTTS")
        else:
            logger.warning("Voice sample غير متوفرة → fallback إلى gTTS")

    # ---------- fallback إلى gTTS ----------
    if _synthesize_gtts(text, lang, str(out_mp3)):
        # نحول MP3 إلى WAV لتوحيد الصيغة مع باقي ال API
        if mp3_to_wav(out_mp3, out_wav):
            return str(out_wav), 'gtts'
        # إذا فشل التحويل نُعيد الـ MP3 مباشرةً (السماح للعميل بتحميله)
        return str(out_mp3), 'gtts'

    # ---------- كل شيء فشل ----------
    return None, None


# ---------------------- اختبار سريع عند تشغيل الملف مباشرةً ----------------------
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("\n🧪 اختبار voice_engine …")

    # اختبار gTTS (بدون عينة مخصَّصة)
    path, method = synthesize(
        text="مرحباً بكم في sl‑Dubbing",
        lang="ar",
        use_custom_voice=False,
    )
    print(f"gTTS   → method: {method}, file: {path}")

    # اختبار XTTS (يتطلب اتصال Cloudinary وعينة صوت)
    path, method = synthesize(
        text="Hello from sl‑Dubbing",
        lang="en",
        use_custom_voice=True,
    )
    print(f"XTTS   → method: {method}, file: {path}")

    print("\n✅ الاختبار انتهى")
