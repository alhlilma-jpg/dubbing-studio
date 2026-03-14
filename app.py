# =============================================================
# sl-Dubbing Backend — HF Spaces + Cloudinary Storage
# عينات الصوت تُحفظ على Cloudinary (25GB مجاناً)
# =============================================================
import os, uuid, time, logging, requests
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["*"])
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

AUDIO_DIR = Path('/tmp/sl_audio')
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# ── Cloudinary Config ─────────────────────────────────────────
CLOUD_NAME  = os.environ.get('CLOUDINARY_CLOUD_NAME', 'dxbmvzsiz')
API_KEY     = os.environ.get('CLOUDINARY_API_KEY',    '432687952743126')
API_SECRET  = os.environ.get('CLOUDINARY_API_SECRET', 'BrFvzlPFXBJZ-B-cZyxCc-0wHRo')
UPLOAD_URL  = f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/raw/upload"
FOLDER      = "sl_voices"

# ── XTTS v2 ──────────────────────────────────────────────────
TTS_ENGINE = None

def load_tts():
    global TTS_ENGINE
    if TTS_ENGINE is not None:
        return TTS_ENGINE
    try:
        from TTS.api import TTS
        logger.info("Loading XTTS v2...")
        TTS_ENGINE = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        logger.info("✅ XTTS v2 ready")
        return TTS_ENGINE
    except Exception as e:
        logger.error(f"XTTS load error: {e}")
        return None

XTTS_LANGS = {
    'ar':'ar','en':'en','es':'es','fr':'fr','de':'de',
    'it':'it','ru':'ru','tr':'tr','zh':'zh-cn','hi':'hi','nl':'nl'
}
GTTS_LANGS = {
    'ar':'ar','en':'en','es':'es','fr':'fr','de':'de','it':'it',
    'ru':'ru','tr':'tr','zh':'zh-TW','hi':'hi','fa':'fa','sv':'sv','nl':'nl'
}

GUEST_LIMIT = 6
GUEST_USAGE = {}

def reset_guest(ip):
    if ip not in GUEST_USAGE or time.time()-GUEST_USAGE[ip].get('ts',0) > 86400:
        GUEST_USAGE[ip] = {'tts':0,'dub':0,'srt':0,'ts':time.time()}

# ── Cloudinary helpers ────────────────────────────────────────
def upload_to_cloudinary(file_path, public_id):
    """رفع ملف صوتي إلى Cloudinary"""
    import hashlib, hmac, time as t
    timestamp = int(t.time())
    # توقيع الطلب
    params = f"folder={FOLDER}&public_id={public_id}&timestamp={timestamp}"
    sig = hashlib.sha1(f"{params}{API_SECRET}".encode()).hexdigest()
    with open(file_path, 'rb') as f:
        res = requests.post(UPLOAD_URL, data={
            'api_key':   API_KEY,
            'timestamp': timestamp,
            'signature': sig,
            'folder':    FOLDER,
            'public_id': public_id,
        }, files={'file': f}, timeout=60)
    if res.status_code == 200:
        data = res.json()
        logger.info(f"✅ Cloudinary upload: {data.get('secure_url')}")
        return data.get('secure_url')
    else:
        logger.error(f"Cloudinary error: {res.text}")
        return None

def download_from_cloudinary(public_id, dest_path):
    """تحميل عينة الصوت من Cloudinary إلى /tmp"""
    url = f"https://res.cloudinary.com/{CLOUD_NAME}/raw/upload/{FOLDER}/{public_id}"
    try:
        res = requests.get(url, timeout=30)
        if res.status_code == 200:
            with open(dest_path, 'wb') as f:
                f.write(res.content)
            logger.info(f"✅ Voice downloaded: {dest_path}")
            return True
    except Exception as e:
        logger.error(f"Download voice error: {e}")
    return False

def get_voice_id(email):
    """public_id للمستخدم في Cloudinary"""
    if email:
        return email.replace('@','_').replace('.','_')
    return None

def fetch_voice_for_user(email):
    """
    تحميل عينة الصوت من Cloudinary إلى /tmp للاستخدام في XTTS
    يُعيد مسار الملف المحلي أو None
    """
    vid = get_voice_id(email)
    if not vid:
        return None
    local = Path('/tmp') / f"voice_{vid}.wav"
    # إذا موجود محلياً لا نحمله مجدداً
    if local.exists():
        return str(local)
    if download_from_cloudinary(vid, str(local)):
        return str(local)
    return None

# ── TTS helpers ───────────────────────────────────────────────
def synth_xtts(text, lang, voice_path, out):
    tts = load_tts()
    if not tts: return False
    xtts_lang = XTTS_LANGS.get(lang)
    if not xtts_lang: return False
    try:
        tts.tts_to_file(text=text, speaker_wav=voice_path,
                        language=xtts_lang, file_path=str(out))
        return True
    except Exception as e:
        logger.error(f"XTTS: {e}"); return False

def synth_gtts(text, lang, out):
    try:
        from gtts import gTTS
        gTTS(text=text, lang=GTTS_LANGS.get(lang,'en')).save(str(out))
        return True
    except Exception as e:
        logger.error(f"gTTS: {e}"); return False

def generate(text, lang, email=None):
    voice = fetch_voice_for_user(email)
    logger.info(f"generate: lang={lang} email={email} voice={'✅' if voice else '❌ none'}")
    out = AUDIO_DIR / f"{uuid.uuid4()}.wav"
    if voice:
        logger.info(f"Trying XTTS v2...")
        if synth_xtts(text, lang, voice, out):
            logger.info("✅ XTTS v2 success")
            return str(out), 'xtts_v2'
        logger.warning("XTTS failed → fallback gTTS")
    mp3 = out.with_suffix('.mp3')
    if synth_gtts(text, lang, mp3):
        return str(mp3), 'gtts'
    return None, None

# ══════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════

@app.route('/')
@app.route('/api/health')
def health():
    return jsonify({
        'status':      'ok',
        'service':     'sl-Dubbing — Cloudinary Storage',
        'xtts_ready':  TTS_ENGINE is not None,
        'cloud':       CLOUD_NAME
    })

@app.route('/api/upload-voice', methods=['POST'])
def upload_voice():
    """رفع عينة الصوت إلى Cloudinary"""
    try:
        email = request.form.get('email','').strip().lower()
        if 'voice' not in request.files:
            return jsonify({'error':'لم يتم رفع ملف'}), 400

        file = request.files['voice']
        ext  = Path(file.filename).suffix.lower() or '.wav'

        # حفظ مؤقت في /tmp
        tmp = Path('/tmp') / f"upload_{uuid.uuid4()}{ext}"
        file.save(str(tmp))

        # تحويل لـ WAV إذا لزم
        wav_path = tmp
        if ext != '.wav':
            try:
                import subprocess
                wav_path = tmp.with_suffix('.wav')
                subprocess.run(
                    ['ffmpeg','-y','-i',str(tmp),'-ar','22050','-ac','1',str(wav_path)],
                    capture_output=True, timeout=30
                )
                if wav_path.exists():
                    tmp.unlink(missing_ok=True)
                else:
                    wav_path = tmp
            except Exception as e:
                logger.warning(f"ffmpeg: {e}")
                wav_path = tmp

        # رفع إلى Cloudinary
        public_id = get_voice_id(email) or f"guest_{uuid.uuid4()}"
        url = upload_to_cloudinary(str(wav_path), public_id)
        wav_path.unlink(missing_ok=True)

        if not url:
            return jsonify({'error':'فشل الرفع إلى Cloudinary'}), 500

        # احفظ نسخة محلية في /tmp للاستخدام الفوري
        local = Path('/tmp') / f"voice_{public_id}.wav"
        download_from_cloudinary(public_id, str(local))

        logger.info(f"✅ Voice uploaded for {email}: {url}")
        return jsonify({
            'success':    True,
            'message':    'تم حفظ عينة الصوت على Cloudinary ✅',
            'url':        url,
            'public_id':  public_id
        })
    except Exception as e:
        logger.error(f"upload_voice: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dub', methods=['POST'])
def dub():
    try:
        d       = request.get_json() or {}
        text    = d.get('text','')
        lang    = d.get('lang','ar')
        email   = (d.get('email') or '').strip().lower()
        feature = d.get('feature','dub')

        if not text:
            return jsonify({'error':'النص فارغ'}), 400

        # فحص الحد
        ip = request.remote_addr
        reset_guest(ip)
        if GUEST_USAGE[ip].get(feature,0) >= GUEST_LIMIT:
            return jsonify({'error':'انتهى الحد المجاني','limit_reached':True}), 403
        GUEST_USAGE[ip][feature] = GUEST_USAGE[ip].get(feature,0) + 1
        remaining = GUEST_LIMIT - GUEST_USAGE[ip][feature]

        audio_path, method = generate(text, lang, email)
        if not audio_path:
            return jsonify({'error':'فشل توليد الصوت'}), 500

        fname     = Path(audio_path).name
        audio_url = f"{request.host_url.rstrip('/')}/api/download/{fname}"

        return jsonify({
            'success':   True,
            'remaining': remaining,
            'audio_url': audio_url,
            'method':    method,
            'lang':      lang
        })
    except Exception as e:
        logger.error(f"dub: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<filename>')
def download(filename):
    filename = Path(filename).name
    p = AUDIO_DIR / filename
    if p.exists():
        mime = 'audio/wav' if filename.endswith('.wav') else 'audio/mpeg'
        return send_file(str(p), as_attachment=True, download_name=filename, mimetype=mime)
    return jsonify({'error':'الملف غير موجود'}), 404

@app.route('/api/debug')
def debug():
    email = request.args.get('email','')
    vid   = get_voice_id(email) if email else None
    voice_url = f"https://res.cloudinary.com/{CLOUD_NAME}/raw/upload/{FOLDER}/{vid}" if vid else None
    return jsonify({
        'cloud_name':  CLOUD_NAME,
        'email':       email,
        'voice_id':    vid,
        'voice_url':   voice_url,
        'xtts_loaded': TTS_ENGINE is not None
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
