# =============================================================
# utils.py — أدوات مساعدة
# Cloudinary upload/download + تنظيف /tmp
# =============================================================
import os, uuid, time, logging, requests, hashlib, subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', 'dxbmvzsiz')
API_KEY    = os.environ.get('CLOUDINARY_API_KEY',    '432687952743126')
API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', 'BrFvzlPFXBJZ-B-cZyxCc-0wHRo')
FOLDER     = "sl_voices"
UPLOAD_URL = f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/raw/upload"

TMP = Path('/tmp')

# ── Cloudinary ────────────────────────────────────────────────
def upload_to_cloudinary(file_path: str, public_id: str) -> str | None:
    """رفع ملف صوتي إلى Cloudinary — يُعيد secure_url أو None"""
    try:
        timestamp = int(time.time())
        params    = f"folder={FOLDER}&public_id={public_id}&timestamp={timestamp}"
        signature = hashlib.sha1(f"{params}{API_SECRET}".encode()).hexdigest()
        with open(file_path, 'rb') as f:
            res = requests.post(UPLOAD_URL, data={
                'api_key':   API_KEY,
                'timestamp': timestamp,
                'signature': signature,
                'folder':    FOLDER,
                'public_id': public_id,
            }, files={'file': f}, timeout=60)
        if res.status_code == 200:
            url = res.json().get('secure_url')
            logger.info(f"✅ Cloudinary upload OK: {url}")
            return url
        logger.error(f"Cloudinary upload failed: {res.status_code} {res.text[:200]}")
    except Exception as e:
        logger.error(f"upload_to_cloudinary: {e}")
    return None

def fetch_voice_sample(public_id: str | None = None) -> str | None:
    """
    تحميل عينة الصوت من Cloudinary إلى /tmp
    يُخزّن محلياً — لا يُعاد التحميل إلا إذا اختفى الملف
    """
    vid   = public_id or os.environ.get('DEFAULT_VOICE_ID', '5_gtygjb')
    local = TMP / f"voice_{vid}.wav"

    if local.exists() and local.stat().st_size > 5000:
        logger.info(f"✅ Using cached voice: {local}")
        return str(local)

    url = f"https://res.cloudinary.com/{CLOUD_NAME}/raw/upload/{FOLDER}/{vid}"
    logger.info(f"⬇️  Downloading voice: {url}")
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            with open(local, 'wb') as f:
                f.write(r.content)
            logger.info(f"✅ Voice saved: {local} ({local.stat().st_size/1024:.1f} KB)")
            return str(local)
        # جرب MP3 إذا لم يكن WAV
        url_mp3 = f"https://res.cloudinary.com/{CLOUD_NAME}/video/upload/v1773450710/{vid}.mp3"
        r2 = requests.get(url_mp3, timeout=30)
        if r2.status_code == 200:
            mp3 = TMP / f"voice_{vid}.mp3"
            with open(mp3, 'wb') as f:
                f.write(r2.content)
            # تحويل إلى WAV
            wav = mp3_to_wav(str(mp3), str(local))
            if wav:
                return wav
        logger.error(f"Voice not found on Cloudinary: {r.status_code}")
    except Exception as e:
        logger.error(f"fetch_voice_sample: {e}")
    return None

# ── تحويل MP3 → WAV ──────────────────────────────────────────
def mp3_to_wav(mp3_path: str, wav_path: str) -> str | None:
    """تحويل MP3 إلى WAV 22050Hz mono"""
    try:
        result = subprocess.run(
            ['ffmpeg', '-y', '-i', mp3_path, '-ar', '22050', '-ac', '1', wav_path],
            capture_output=True, timeout=30
        )
        if Path(wav_path).exists() and Path(wav_path).stat().st_size > 1000:
            logger.info(f"✅ Converted to WAV: {wav_path}")
            Path(mp3_path).unlink(missing_ok=True)
            return wav_path
    except Exception as e:
        logger.error(f"mp3_to_wav: {e}")
    return None

# ── تنظيف /tmp ───────────────────────────────────────────────
_last_purge = 0

def purge_tmp_folder(max_age_seconds: int = 3600):
    """احذف ملفات /tmp/sl_audio الأقدم من ساعة"""
    global _last_purge
    now = time.time()
    if now - _last_purge < 300:  # كل 5 دقائق فقط
        return
    _last_purge = now
    audio_dir = TMP / 'sl_audio'
    if not audio_dir.exists():
        return
    deleted = 0
    for f in audio_dir.iterdir():
        try:
            if now - f.stat().st_mtime > max_age_seconds:
                f.unlink()
                deleted += 1
        except:
            pass
    if deleted:
        logger.info(f"🗑️  Purged {deleted} old audio files")
