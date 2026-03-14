# =============================================================
# sl-Dubbing Backend — HF Spaces + Cloudinary Storage
# عينات الصوت تُحفظ على Cloudinary (25GB مجاناً)
# =============================================================
import os, uuid, time, logging
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from voice_engine import synthesize, fetch_voice_sample

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
        text       = d.get('text','')
        lang       = d.get('lang','ar')
        email      = (d.get('email') or '').strip().lower()
        feature    = d.get('feature','dub')
        voice_mode = d.get('voice_mode','gtts')  # 'gtts' أو 'xtts'

        if not text:
            return jsonify({'error':'النص فارغ'}), 400

        # فحص الحد
        ip = request.remote_addr
        reset_guest(ip)
        if GUEST_USAGE[ip].get(feature,0) >= GUEST_LIMIT:
            return jsonify({'error':'انتهى الحد المجاني','limit_reached':True}), 403
        GUEST_USAGE[ip][feature] = GUEST_USAGE[ip].get(feature,0) + 1
        remaining = GUEST_LIMIT - GUEST_USAGE[ip][feature]

        # استخدم الصوت المطلوب
        audio_path, method = generate(text, lang, use_custom=(voice_mode=='xtts'))
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

# ── الأسعار — تُقرأ من prices.json ──────────────────────────
import json as _json

PRICES_FILE = Path(__file__).parent / 'prices.json'

def load_prices():
    try:
        with open(PRICES_FILE, 'r', encoding='utf-8') as f:
            return _json.load(f)
    except Exception as e:
        logger.error(f"prices.json error: {e}")
        return {}

@app.route('/api/prices')
def prices():
    """يُرجع الأسعار من prices.json — غيّر الملف فقط"""
    return jsonify({'success': True, 'prices': load_prices()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
