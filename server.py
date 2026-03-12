# =============================================================
# sl-Dubbing & Translation — Backend احترافي
# XTTS v2 Voice Cloning | 13 Languages | Flask
# =============================================================
import os, uuid, logging, random, time, json, io
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {
    "origins": ["https://sl-dubbing.github.io", "http://localhost:*", "*"],
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}})

# ── Config ────────────────────────────────────────────────────
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

db = SQLAlchemy(app)

# مجلدات الملفات
AUDIO_DIR = Path('/tmp/sl_audio')
VOICE_DIR = Path('/tmp/sl_voices')
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
VOICE_DIR.mkdir(parents=True, exist_ok=True)

# ── XTTS v2 — تحميل مرة واحدة ──────────────────────────────
TTS_ENGINE = None

def load_tts():
    """تحميل XTTS v2 عند الحاجة"""
    global TTS_ENGINE
    if TTS_ENGINE is not None:
        return TTS_ENGINE
    try:
        from TTS.api import TTS
        logger.info("Loading XTTS v2 model...")
        TTS_ENGINE = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        logger.info("✅ XTTS v2 loaded successfully")
        return TTS_ENGINE
    except Exception as e:
        logger.error(f"❌ XTTS v2 load error: {e}")
        return None

# ── خريطة اللغات لـ XTTS v2 ────────────────────────────────
XTTS_LANG_MAP = {
    'ar': 'ar',
    'en': 'en',
    'es': 'es',
    'fr': 'fr',
    'de': 'de',
    'it': 'it',
    'ru': 'ru',
    'tr': 'tr',
    'zh': 'zh-cn',
    'hi': 'hi',
    'nl': 'nl',
    # هذه اللغات لا تدعمها XTTS v2 — نستخدم gTTS fallback
    'fa': None,
    'sv': None,
}

GTTS_LANG_MAP = {
    'ar': 'ar', 'en': 'en', 'es': 'es', 'fr': 'fr',
    'de': 'de', 'it': 'it', 'ru': 'ru', 'tr': 'tr',
    'zh': 'zh-TW', 'hi': 'hi', 'fa': 'fa', 'sv': 'sv', 'nl': 'nl'
}

# ── نموذج المستخدم ───────────────────────────────────────────
class User(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password      = db.Column(db.String(200), nullable=False)
    otp           = db.Column(db.String(6))
    otp_expiry    = db.Column(db.DateTime)
    is_verified   = db.Column(db.Boolean, default=True)   # مفعّل بالكامل
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    usage_tts     = db.Column(db.Integer, default=0)
    usage_dub     = db.Column(db.Integer, default=0)
    usage_srt     = db.Column(db.Integer, default=0)
    unlocked_tts  = db.Column(db.Boolean, default=False)
    unlocked_dub  = db.Column(db.Boolean, default=False)
    unlocked_srt  = db.Column(db.Boolean, default=False)
    voice_sample  = db.Column(db.String(200))   # مسار عينة الصوت

with app.app_context():
    db.create_all()

GUEST_LIMIT = 6
GUEST_USAGE = {}

# ── دوال مساعدة ─────────────────────────────────────────────
def reset_guest(ip):
    if ip in GUEST_USAGE and time.time() - GUEST_USAGE[ip].get('ts', 0) > 86400:
        GUEST_USAGE[ip] = {'tts': 0, 'dub': 0, 'srt': 0, 'ts': time.time()}
    elif ip not in GUEST_USAGE:
        GUEST_USAGE[ip] = {'tts': 0, 'dub': 0, 'srt': 0, 'ts': time.time()}

def get_voice_sample(email=None):
    """إرجاع مسار عينة الصوت إن وجدت"""
    if email:
        user = User.query.filter_by(email=email).first()
        if user and user.voice_sample and Path(user.voice_sample).exists():
            return user.voice_sample
    # البحث عن أي ملف صوتي محفوظ عالمياً
    samples = list(VOICE_DIR.glob('*.wav')) + list(VOICE_DIR.glob('*.mp3'))
    if samples:
        return str(samples[-1])
    return None

def synthesize_xtts(text, lang_code, voice_path, output_path):
    """توليد صوت بـ XTTS v2 مع نسخ النبرة"""
    tts = load_tts()
    if tts is None:
        return False
    try:
        xtts_lang = XTTS_LANG_MAP.get(lang_code)
        if not xtts_lang:
            return False
        tts.tts_to_file(
            text=text,
            speaker_wav=voice_path,
            language=xtts_lang,
            file_path=str(output_path)
        )
        return True
    except Exception as e:
        logger.error(f"XTTS error: {e}")
        return False

def synthesize_gtts(text, lang_code, output_path):
    """توليد صوت بـ gTTS كبديل"""
    try:
        from gtts import gTTS
        gtts_lang = GTTS_LANG_MAP.get(lang_code, 'en')
        tts = gTTS(text=text, lang=gtts_lang, slow=False)
        tts.save(str(output_path))
        return True
    except Exception as e:
        logger.error(f"gTTS error: {e}")
        return False

def generate_audio(text, lang_code, email=None):
    """
    توليد الصوت:
    1. إذا كانت عينة صوت موجودة → XTTS v2 (نسخ النبرة)
    2. إذا لم تكن عينة صوت أو لغة غير مدعومة → gTTS
    """
    output_file = AUDIO_DIR / f"{uuid.uuid4()}.wav"
    voice_path = get_voice_sample(email)

    if voice_path:
        logger.info(f"Using XTTS v2 with voice sample for lang={lang_code}")
        ok = synthesize_xtts(text, lang_code, voice_path, output_file)
        if ok:
            return str(output_file)
        logger.warning("XTTS failed, falling back to gTTS")

    # Fallback → gTTS
    mp3_file = output_file.with_suffix('.mp3')
    ok = synthesize_gtts(text, lang_code, mp3_file)
    if ok:
        return str(mp3_file)

    return None

# ══════════════════════════════════════════════════════════════
# API Endpoints
# ══════════════════════════════════════════════════════════════

@app.route('/')
def root():
    return jsonify({'status': 'ok', 'service': 'sl-Dubbing Backend'})

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'sl-Dubbing Backend',
        'xtts_ready': TTS_ENGINE is not None
    })

# ── تسجيل الدخول ─────────────────────────────────────────────
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data  = request.get_json()
        email = data.get('email', '').strip().lower()
        pw    = data.get('password', '')
        if not email or '@' not in email:
            return jsonify({'error': 'بريد غير صحيح'}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'البريد مسجل بالفعل'}), 400
        user = User(email=email, password=generate_password_hash(pw))
        db.session.add(user)
        db.session.commit()
        return jsonify({'success': True, 'email': email}), 201
    except Exception as e:
        logger.error(f"Register: {e}")
        return jsonify({'error': 'خطأ في التسجيل'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data  = request.get_json()
        email = data.get('email', '').strip().lower()
        pw    = data.get('password', '')
        user  = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, pw):
            return jsonify({'error': 'بيانات غير صحيحة'}), 401
        return jsonify({
            'success': True, 'email': user.email,
            'unlocked': {'tts': user.unlocked_tts, 'dub': user.unlocked_dub, 'srt': user.unlocked_srt},
            'usage':    {'tts': user.usage_tts,    'dub': user.usage_dub,    'srt': user.usage_srt},
            'has_voice': bool(user.voice_sample)
        })
    except Exception as e:
        logger.error(f"Login: {e}")
        return jsonify({'error': 'خطأ في الدخول'}), 500

# ── رفع عينة الصوت ───────────────────────────────────────────
@app.route('/api/upload-voice', methods=['POST'])
def upload_voice():
    """
    رفع عينة صوتية (WAV / MP3) لنسخ النبرة.
    تُستخدم في كل لغات الدبلجة.
    """
    try:
        email = request.form.get('email', '').strip().lower()
        if 'voice' not in request.files:
            return jsonify({'error': 'لم يتم رفع ملف صوتي'}), 400

        file = request.files['voice']
        if not file.filename:
            return jsonify({'error': 'اسم الملف فارغ'}), 400

        ext = Path(file.filename).suffix.lower()
        if ext not in ['.wav', '.mp3', '.ogg', '.m4a']:
            return jsonify({'error': 'يدعم فقط WAV / MP3 / OGG / M4A'}), 400

        # حفظ الملف
        filename = f"voice_{uuid.uuid4()}{ext}"
        save_path = VOICE_DIR / filename
        file.save(str(save_path))

        # تحويل لـ WAV إذا لزم (XTTS يحتاج WAV)
        if ext != '.wav':
            try:
                import subprocess
                wav_path = save_path.with_suffix('.wav')
                subprocess.run(
                    ['ffmpeg', '-y', '-i', str(save_path), '-ar', '22050', '-ac', '1', str(wav_path)],
                    capture_output=True, timeout=30
                )
                if wav_path.exists():
                    os.remove(str(save_path))
                    save_path = wav_path
            except Exception as e:
                logger.warning(f"ffmpeg convert: {e}")

        # ربط بالمستخدم إن كان مسجلاً
        if email:
            user = User.query.filter_by(email=email).first()
            if user:
                user.voice_sample = str(save_path)
                db.session.commit()

        logger.info(f"Voice sample saved: {save_path}")
        return jsonify({
            'success': True,
            'message': 'تم حفظ عينة الصوت بنجاح ✅',
            'voice_id': filename
        })
    except Exception as e:
        logger.error(f"Upload voice: {e}")
        return jsonify({'error': 'فشل رفع الملف'}), 500

# ── توليد الصوت / الدبلجة ────────────────────────────────────
@app.route('/api/dub', methods=['POST'])
def dub():
    """
    توليد صوت مدبلج بنفس نبرة المستخدم.
    - إذا كانت عينة صوت موجودة → XTTS v2
    - وإلا → gTTS
    يدعم: ar en es fr de it ru tr zh hi fa sv nl
    """
    try:
        # دعم JSON و form-data
        if request.content_type and 'multipart' in request.content_type:
            text    = request.form.get('text', '')
            lang    = request.form.get('lang', 'ar')
            email   = request.form.get('email', '').strip().lower()
            feature = request.form.get('feature', 'dub')
            # عينة الصوت المرفوعة مباشرة مع الطلب
            inline_voice = request.files.get('voice')
        else:
            data    = request.get_json() or {}
            text    = data.get('text', '')
            lang    = data.get('lang', 'ar')
            email   = (data.get('email') or '').strip().lower()
            feature = data.get('feature', 'dub')
            inline_voice = None

        if not text:
            return jsonify({'error': 'النص فارغ'}), 400

        feature = feature if feature in ['tts', 'dub', 'srt'] else 'dub'

        # ── فحص الحد ────────────────────────────────────────
        if not email:
            ip = request.remote_addr
            reset_guest(ip)
            if GUEST_USAGE[ip].get(feature, 0) >= GUEST_LIMIT:
                return jsonify({'error': 'انتهى الحد المجاني', 'limit_reached': True}), 403
            GUEST_USAGE[ip][feature] = GUEST_USAGE[ip].get(feature, 0) + 1
            remaining = GUEST_LIMIT - GUEST_USAGE[ip][feature]
        else:
            user = User.query.filter_by(email=email).first()
            if user:
                unlocked = getattr(user, f'unlocked_{feature}')
                if not unlocked:
                    usage = getattr(user, f'usage_{feature}', 0)
                    if usage >= GUEST_LIMIT:
                        return jsonify({'error': 'انتهى الحد المجاني', 'limit_reached': True}), 403
                    setattr(user, f'usage_{feature}', usage + 1)
                    db.session.commit()
                    remaining = GUEST_LIMIT - getattr(user, f'usage_{feature}')
                else:
                    remaining = 'unlimited'
            else:
                remaining = GUEST_LIMIT

        # ── حفظ عينة الصوت المرفوعة مباشرة ──────────────────
        temp_voice_path = None
        if inline_voice and inline_voice.filename:
            ext = Path(inline_voice.filename).suffix.lower() or '.wav'
            temp_path = VOICE_DIR / f"tmp_{uuid.uuid4()}{ext}"
            inline_voice.save(str(temp_path))
            temp_voice_path = str(temp_path)
            # ربطها بالمستخدم
            if email:
                user = User.query.filter_by(email=email).first()
                if user:
                    user.voice_sample = temp_voice_path
                    db.session.commit()

        # ── توليد الصوت ──────────────────────────────────────
        audio_path = generate_audio(text, lang, email)

        # تنظيف الملف المؤقت
        if temp_voice_path and temp_voice_path != get_voice_sample(email):
            try: os.remove(temp_voice_path)
            except: pass

        if not audio_path or not Path(audio_path).exists():
            return jsonify({'error': 'فشل توليد الصوت'}), 500

        filename = Path(audio_path).name
        audio_url = f"{request.host_url}api/download/{filename}"

        return jsonify({
            'success':   True,
            'remaining': remaining,
            'audio_url': audio_url,
            'filename':  filename,
            'lang':      lang,
            'method':    'xtts_v2' if get_voice_sample(email) else 'gtts'
        })

    except Exception as e:
        logger.error(f"Dub error: {e}")
        return jsonify({'error': f'حدث خطأ: {str(e)}'}), 500

# ── تحميل الملف ──────────────────────────────────────────────
@app.route('/api/download/<filename>')
def download(filename):
    try:
        # حماية من path traversal
        filename = Path(filename).name
        filepath = AUDIO_DIR / filename
        if not filepath.exists():
            return jsonify({'error': 'الملف غير موجود'}), 404
        mime = 'audio/wav' if str(filepath).endswith('.wav') else 'audio/mpeg'
        return send_file(str(filepath), as_attachment=True,
                         download_name=filename, mimetype=mime)
    except Exception as e:
        logger.error(f"Download: {e}")
        return jsonify({'error': 'فشل التنزيل'}), 500

# ── Entitlements ──────────────────────────────────────────────
@app.route('/api/entitlements')
def entitlements():
    try:
        email = request.args.get('email', '').strip().lower()
        user  = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'غير موجود'}), 404
        return jsonify({
            'success': True,
            'unlocked': {'tts': user.unlocked_tts, 'dub': user.unlocked_dub, 'srt': user.unlocked_srt},
            'usage':    {'tts': user.usage_tts,    'dub': user.usage_dub,    'srt': user.usage_srt},
            'has_voice': bool(user.voice_sample)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── Webhook Lemon Squeezy ──────────────────────────────────────
@app.route('/api/webhook/lemonsqueezy', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if data.get('event_name') == 'order_created':
            attrs  = data.get('data', {}).get('attributes', {})
            email  = attrs.get('email', '').lower()
            feat   = attrs.get('custom', {}).get('feature_hint', '')
            if email and feat in ['tts', 'dub', 'srt']:
                user = User.query.filter_by(email=email).first()
                if user:
                    setattr(user, f'unlocked_{feat}', True)
                    db.session.commit()
                    logger.info(f"Unlocked {feat} for {email}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Webhook: {e}")
        return jsonify({'error': str(e)}), 500

# ── تشغيل ─────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
