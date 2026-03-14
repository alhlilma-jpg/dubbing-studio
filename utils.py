# utils.py
# ==========================================================
# مجموعة أدوات مساعدة للـ backend:
#   • رفع / تحميل عينات صوتية من Cloudinary
#   • تحويل MP3 → WAV (ffmpeg من imageio‑ffmpeg)
#   • حذف ملفات مؤقّتة قديمة
# ==========================================================
import os, logging, uuid, requests, subprocess, time
from pathlib import Path
import cloudinary
import cloudinary.uploader
import cloudinary.api
from imageio_ffmpeg import get_ffmpeg_exe   # نسخة ffmpeg مدمجة داخل الحزمة

logger = logging.getLogger(__name__)

# ---------- Cloudinary configuration ----------
CLOUD_NAME        = os.getenv('CLOUDINARY_CLOUD_NAME')
API_KEY           = os.getenv('CLOUDINARY_API_KEY')
API_SECRET        = os.getenv('CLOUDINARY_API_SECRET')
FOLDER            = os.getenv('CLOUDINARY_FOLDER', 'sl_voices')
DEFAULT_VOICE_ID  = os.getenv('DEFAULT_VOICE_ID', '5_gtygjb')   # ← معرّف العينة الافتراضية

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
    """يرجع الـ secure_url إذا نجح الرفع، وإلا None
