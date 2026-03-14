# utils.py
# ==========================================================
# أدوات مساعدة للـ backend:
#   • رفع / تحميل عينات صوتية من Cloudinary
#   • تحويل MP3 → WAV (ffmpeg)
#   • حذف ملفات مؤقّتة قديمة
# ==========================================================
import os, logging, uuid, requests, subprocess, time
from pathlib import Path
import cloudinary
import cloudinary.uploader
import cloudinary.api

logger = logging.getLogger(__name__)

# ---------- Cloudinary configuration ----------
CLOUD_NAME    = os.getenv('CLOUDINARY_CLOUD_NAME')
API_KEY       = os.getenv('CLOUDINARY_API_KEY')
API_SECRET    = os.getenv('CLOUDINARY_API_SECRET')
FOLDER        = os.getenv('CLOUDINARY_FOLDER', 'sl_voices')
DEFAULT_VOICE_ID = os.getenv('DEFAULT_VOICE_ID', '5_gtygjb')   # ← معرف العينة الافتراضية

if not all([CLOUD_NAME, API_KEY, API_SECRET]):
    raise RuntimeError('❌ Cloudinary credentials missing – set them in the environment.')

cloudinary.config(
    cloud_name = CLOUD_NAME,
    api_key    = API_KEY,
    api_secret = API_SECRET,
    secure     = True,
    timeout    = 30,
)

# ---------- TMP directory ----------
TMP_DIR = Path('/tmp')
TMP_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------------------------------------------
# بناء URL للملف داخل Cloudinary
# -----------------------------------------------------------------
def _cloudinary_url(public_id: str, resource_type: str = "raw") -> str:
    """إرجاع URL للملف بحسب الـ public_id ونوع المورد."""
    url, _ = cloudinary.utils.cloudinary_url(
        f"{FOLDER}/{public_id}",
        resource_type = resource_type,
        sign_url     = False,
    )
    return url


# -----------------------------------------------------------------
# رفع ملف RAW (wav/mp3/…) إلى Cloudinary
# -----------------------------------------------------------------
def upload_to_cloudinary(local_path: str, public_id: str) -> str | None:
    """يرجع secure_url إذا نجح الرفع، وإلا None."""
    try:
        result = cloudinary.uploader.upload(
            local_path,
            public_id   = public_id,
            folder      = FOLDER,
            resource_type = "raw",
            overwrite   = True,
            tags        = ["voice_sample"]
        )
        logger.info(f"✅ Cloudinary upload: {public_id} → {result.get('secure_url')}")
        return result.get('secure_url')
    except Exception as exc:
        logger.error(f"❌ Cloudinary upload error ({public_id}): {exc}")
        return None


# -----------------------------------------------------------------
# تحميل عينة صوت (مع Cache). يدعم RAW و VIDEO
# -----------------------------------------------------------------
def fetch_voice_sample(public_id: str | None = None) -> Path | None:
    """
    تحميل عينة صوت من Cloudinary إلى /tmp (مع caching).
    إذا لم يُعطى public_id يتم استعمال DEFAULT_VOICE_ID.
    يحاول أولاً كـ raw، وإن فشل يحاول كـ video (MP3 داخل حاوية video).
    النتيجة دائماً ملف WAV على /tmp.
    """
    vid = public_id or DEFAULT_VOICE_ID
    local_path = TMP_DIR / f"voice_{vid}.wav"

    # إذا كان موجوداً محلياً وحجمه > 5 KB → نعيده مباشرةً
    if local_path.exists() and local_path.stat().st_size > 5_000:
        logger.info(f"✅ Using cached voice sample: {local_path}")
        return local_path

    # --------- 1️⃣ جرب RAW ----------
    raw_url = _cloudinary_url(vid, resource_type="raw")
    logger.info(f"⬇️ Trying raw download: {raw_url}")
    try:
        r = requests.get(raw_url, timeout=30)
        if r.status_code == 200 and len(r.content) > 5_000:
            with open(local_path, "wb") as f:
                f.write(r.content)
            logger.info(f"✅ Raw voice saved: {local_path}")
            return local_path
        else:
            logger.warning(f"⚠️ Raw download failed (status {r.status_code})")
    except Exception as exc:
        logger.warning(f"⚠️ Raw download exception: {exc}")

    # --------- 2️⃣ جرب VIDEO ----------
    video_url = _cloudinary_url(vid, resource_type="video")
    logger.info(f"⬇️ Trying video download: {video_url}")
    try:
        r = requests.get(video_url, timeout=30)
        if r.status_code == 200 and len(r.content) > 5_000:
            # الملف يأتي بصيغة MP3 داخل حاوية video
            tmp_mp3 = TMP_DIR / f"{vid}.mp3"
            with open(tmp_mp3, "wb") as f:
                f.write(r.content)
            logger.info(f"✅ Video‑type MP3 downloaded → {tmp_mp3}")

            # تحويل MP3 → WAV (22 kHz, mono)
            if mp3_to_wav(tmp_mp3, local_path):
                logger.info(f"✅ Converted video MP3 → WAV: {local_path}")
                return local_path
            else:
                logger.error("❌ ffmpeg conversion failed")
                return None
        else:
            logger.error(f"❌ Video download failed (status {r.status_code})")
    except Exception as exc:
        logger.error(f"❌ Video download exception: {exc}")

    logger.error(f"❌ Unable to fetch voice sample for id `{vid}`")
    return None


# -----------------------------------------------------------------
# تحويل MP3 → WAV (ffmpeg)
# -----------------------------------------------------------------
def mp3_to_wav(mp3_path: Path, wav_path: Path) -> bool:
    """يحوّل ملف MP3 إلى WAV (22 kHz, mono) باستخدام ffmpeg."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "22050", "-ac", "1", str(wav_path)],
            capture_output=True,
            timeout=30,
        )
        if wav_path.exists():
            mp3_path.unlink(missing_ok=True)
            return True
    except Exception as exc:
        logger.error(f"ffmpeg conversion error: {exc}")
    return False


# -----------------------------------------------------------------
# تنظيف /tmp من الملفات القديمة
# -----------------------------------------------------------------
def purge_tmp_folder(older_than_seconds: int = 7_200):
    """يمسح جميع الملفات داخل /tmp التي مضى عليها أكثر من `older_than_seconds`."""
    now = time.time()
    for p in TMP_DIR.iterdir():
        if p.is_file() and (now - p.stat().st_mtime) > older_than_seconds:
            try:
                p.unlink()
                logger.debug(f"🗑️ Purged temp file: {p}")
            except Exception:
                pass
