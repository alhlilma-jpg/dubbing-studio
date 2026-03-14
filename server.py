# server.py
# ==============================================================
# sl‑Dubbing & Translation – Backend (Render / HF Spaces)
# يدعم:
#   • تسجيل/دخول (SQLite)
#   • رفع عينة صوت (Cloudinary) وربطها بالحساب
#   • دبلجة النصوص باستخدام XTTS (مع عينة مخصَّصة) أو gTTS
#   • حدّ الضيوف (6 طلبات/يوم) و Rate‑Limiting
# ==============================================================

import os, uuid, time, logging, subprocess
from pathlib import Path
from datetime import datetime

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# -----------------------------------------------------------------
# استيراد الأدوات المساعدة من utils.py
# -----------------------------------------------------------------
from utils import (
    upload_to_cloudinary,
    fetch_voice_sample,
    mp3_to_wav,
    purge_tmp_folder,
)

# -----------------------------------------------------------------
# Logging
# -----------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------
# Flask & CORS (محدّد الأصول الموثوقة)
# -----------------------------------------------------------------
app = Flask(__name__)

ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "https://sl-dubbing.github.io, http://localhost:*"
).split(",")

CORS(app,
     resources={r"/api/*": {"origins": ALLOWED_ORIGINS}},
     supports_credentials=True)

# -----------------------------------------------------------------
# Rate Limiting
# -----------------------------------------------------------------
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
)

# -----------------------------------------------------------------
# قاعدة البيانات (SQLite)
# -----------------------------------------------------------------
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = 'users'
    id               = db.Column(db.Integer, primary_key=True)
    email            = db.Column(db.String(120), unique=True, nullable=False)
    password         = db.Column(db.String(200), nullable=False)

    # معرف العينة الصوتية في Cloudinary (public_id)
    voice_public_id  = db.Column(db.String(255), nullable=True)

    usage_tts        = db.Column(db.Integer, default=0)
    usage_dub        = db.Column(db.Integer, default=0)
    usage_srt        = db.Column(db.Integer, default=0)

    unlocked_tts     = db.Column(db.Boolean, default=False)
    unlocked_dub     = db.Column(db.Boolean, default=False)
    unlocked_srt     = db.Column(db.Boolean, default=False)


with app.app_context():
    db.create_all()


# -----------------------------------------------------------------
# إعدادات ملفات الصوت المؤقتة
# -----------------------------------------------------------------
AUDIO_DIR = Path('/tmp/sl_audio')
VOICE_DIR = Path('/tmp/sl_voices')
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
VOICE_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------
# إعداد حدّ الضيوف (6 طلبات/يوم)
# -----------------------------------------------------------------
GUEST_LIMIT = 6
GUEST_USAGE = {}

def reset_guest(ip: str):
    now = time.time()
    usage = GUEST_USAGE.get(ip)
    if usage is None or now - usage.get('ts', 0) > 86400:
        GUEST_USAGE[ip] = {'tts': 0, 'dub': 0, 'srt': 0, 'ts': now}


# -----------------------------------------------------------------
# استدعاء محرك الصوت من voice_engine.py
# -----------------------------------------------------------------
from voice_engine import synthesize as voice_synthesize


# -----------------------------------------------------------------
# قبل كل طلب: تنظيف /tmp من الملفات القديمة
# -----------------------------------------------------------------
@app.before_request
def before_any_request():
    purge_tmp_folder()


# -----------------------------------------------------------------
# Routes
# -----------------------------------------------------------------
@app.route('/')
def root():
    return jsonify({
        'status'    : 'ok',
        'service'   : 'sl‑Dubbing Backend',
        'xtts_ready': True,
        'cloudinary': os.getenv('CLOUDINARY_CLOUD_NAME')
    })


@app.route('/api/health')
def health():
    return jsonify({
        'status'    : 'ok',
        'xtts_ready': True,
        'cloudinary': os.getenv('CLOUDINARY_CLOUD_NAME')
    })


# -----------------------------------------------------------------
# تسجيل مستخدم جديد
# -----------------------------------------------------------------
@app.route('/api/register', methods=['POST'])
@limiter.limit("10 per hour")
def register():
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip().lower()
        pw    = data.get('password', '')

        if not email or '@' not in email:
            return jsonify({'error': 'بريد غير صالح'}), 400
        if not pw:
            return jsonify({'error': 'كلمة المرور فارغة'}), 400

        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'البريد مسجَّل مسبقاً'}), 400

        user = User(email=email,
                    password=generate_password_hash(pw))
        db.session.add(user)
        db.session.commit()
        logger.info(f"✅ New user registered: {email}")

        return jsonify({'success': True, 'email': email}), 201
    except Exception as exc:
        logger.error(f"Register error: {exc}")
        return jsonify({'error': 'خطأ داخلي'}), 500


# -----------------------------------------------------------------
# تسجيل الدخول
# -----------------------------------------------------------------
@app.route('/api/login', methods=['POST'])
@limiter.limit("15 per hour")
def login():
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip().lower()
        pw    = data.get('password', '')

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, pw):
            return jsonify({'error': 'بيانات غير صحيحة'}), 401

        return jsonify({
            'success'   : True,
            'email'     : user.email,
            'has_voice' : bool(user.voice_public_id),
            'usage'     : {
                'tts': user.usage_tts,
                'dub': user.usage_dub,
                'srt': user.usage_srt,
            },
            'unlocked'  : {
                'tts': user.unlocked_tts,
                'dub': user.unlocked_dub,
                'srt': user.unlocked_srt,
            }
        })
    except Exception as exc:
        logger.error(f"Login error: {exc}")
        return jsonify({'error': 'خطأ داخلي'}), 500


# -----------------------------------------------------------------
# رفع عينة صوت (Cloudinary) وربطها بالحساب إذا تم إرسال email
# -----------------------------------------------------------------
@app.route('/api/upload-voice', methods=['POST'])
@limiter.limit("20 per hour")
def upload_voice():
    try:
        email = request.form.get('email', '').strip().lower()
        if 'voice' not in request.files:
            return jsonify({'error': 'لم يتم رفع ملف'}), 400

        file = request.files['voice']
        if not file.filename:
            return jsonify({'error': 'اسم الملف فارغ'}), 400

        ext = Path(file.filename).suffix.lower()
        if ext not in {'.wav', '.mp3', '.ogg', '.m4a'}:
            return jsonify({'error': 'امتداد غير مدعوم (wav/mp3/ogg/m4a)'}), 400

        # حفظ مؤقت
        tmp_path = Path('/tmp') / f"voice_{uuid.uuid4()}{ext}"
        file.save(str(tmp_path))

        # إذا لم يكن WAV → تحويله إلى WAV
        wav_path = tmp_path
        if ext != '.wav':
            wav_path = tmp_path.with_suffix('.wav')
            try:
                subprocess.run(
                    ['ffmpeg', '-y', '-i', str(tmp_path), '-ar', '22050', '-ac', '1', str(wav_path)],
                    capture_output=True,
                    timeout=30,
                )
                if wav_path.exists():
                    tmp_path.unlink(missing_ok=True)
                else:
                    wav_path = tmp_path   # fallback إذا فشل التحويل
            except Exception as exc:
                logger.warning(f"ffmpeg conversion error: {exc}")

        # إنشاء public_id فريد (إذا كان email موجودًا ندمجه مع UUID لتفادي التعارض)
        uid_part = email if email else f"guest_{uuid.uuid4()}"
        public_id = f"{uid_part}_{uuid.uuid4()}"
        url = upload_to_cloudinary(str(wav_path), public_id)
        wav_path.unlink(missing_ok=True)

        if not url:
            return jsonify({'error': 'فشل الرفع إلى Cloudinary'}), 500

        # ربط العينة بالمستخدم (إن كان مسجلاً)
        if email:
            user = User.query.filter_by(email=email).first()
            if user:
                user.voice_public_id = public_id
                db.session.commit()
                logger.info(f"✅ Voice sample linked to user {email}")

        return jsonify({
            'success'   : True,
            'message'   : 'تم حفظ عينة الصوت على Cloudinary ✅',
            'url'       : url,
            'public_id' : public_id,
        })
    except Exception as exc:
        logger.error(f"/api/upload-voice error: {exc}")
        return jsonify({'error': str(exc)}), 500


# -----------------------------------------------------------------
# دبلجة النص (XTTS إذا طلبت ووجدت عينة، وإلا fallback إلى gTTS)
# -----------------------------------------------------------------
@app.route('/api/dub', methods=['POST'])
@limiter.limit("30 per hour")
def dub():
    try:
        data = request.get_json() or {}
        text       = data.get('text', '').strip()
        lang       = data.get('lang', 'ar')
        email      = (data.get('email') or '').strip().lower()
        voice_mode = data.get('voice_mode', 'gtts').lower()   # "gtts" أو "xtts"

        if not text:
            return jsonify({'error': 'النص فارغ'}), 400

        # ---- حدّ الضيوف ----
        ip = request.remote_addr
        reset_guest(ip)
        if GUEST_USAGE[ip].get('dub', 0) >= GUEST_LIMIT:
            return jsonify({'error': 'انتهى الحد المجاني', 'limit_reached': True}), 403
        GUEST_USAGE[ip]['dub'] += 1
        remaining = GUEST_LIMIT - GUEST_USAGE[ip]['dub']

        # ---- استدعاء محرك الصوت ----
        use_xtts = (voice_mode == 'xtts')
        file_path, method = voice_synthesize(
            text=text,
            lang=lang,
            use_custom_voice=use_xtts          # إذا طلبنا XTTS سيحاول تحميل العينة تلقائيًا
        )

        if not file_path:
            return jsonify({'error': 'فشل توليد الصوت'}), 500

        # ---- إرجاع رابط التحميل ----
        filename  = Path(file_path).name
        audio_url = f"{request.host_url.rstrip('/')}/api/download/{filename}"

        logger.info(f"✅ Dub OK – method={method} – remaining={remaining}")

        return jsonify({
            'success'   : True,
            'audio_url' : audio_url,
            'filename'  : filename,
            'method'    : method,
            'remaining' : remaining,
            'lang'      : lang,
        })
    except Exception as exc:
        logger.error(f"/api/dub error: {exc}")
        return jsonify({'error': str(exc)}), 500


# -----------------------------------------------------------------
# تحميل ملف الصوت المُولَّد
# -----------------------------------------------------------------
@app.route('/api/download/<filename>')
def download(filename):
    try:
        safe_name = Path(filename).name          # منع path‑traversal
        fpath = AUDIO_DIR / safe_name
        if not fpath.exists():
            return jsonify({'error': 'الملف غير موجود'}), 404

        mime = 'audio/wav' if safe_name.endswith('.wav') else 'audio/mpeg'
        return send_file(str(fpath), as_attachment=True,
                         download_name=safe_name, mimetype=mime)
    except Exception as exc:
        logger.error(f"Download error: {exc}")
        return jsonify({'error': 'فشل التحميل'}), 500


# -----------------------------------------------------------------
# الأسعار (من prices.json)
# -----------------------------------------------------------------
import json as _json
PRICES_FILE = Path(__file__).parent / 'prices.json'

def load_prices():
    try:
        with open(PRICES_FILE, 'r', encoding='utf-8') as f:
            return _json.load(f)
    except Exception as exc:
        logger.error(f"prices.json load error: {exc}")
        return {}

@app.route('/api/prices')
def prices():
    """إرجاع الأسعار – عدّلها مباشرةً في ملف prices.json."""
    return jsonify({'success': True, 'prices': load_prices()})


# -----------------------------------------------------------------
# معلومات عن امتلاك عينة صوت (لـ frontend)
# -----------------------------------------------------------------
@app.route('/api/entitlements')
def entitlements():
    """
    تُستَخدم من الـ frontend لمعرفة ما إذا كان للمستخدم
    عينة صوت مخصَّصة (has_voice) ومعرفها (voice_id).
    """
    email = request.args.get('email', '').strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'error': 'المستخدم غير موجود'}), 404

    return jsonify({
        'success'   : True,
        'has_voice'  : bool(user.voice_public_id),
        'voice_id'   : user.voice_public_id,
    })


# -----------------------------------------------------------------
# تشغيل التطبيق (للتطوير المحلي فقط)
# -----------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    logger.info(f"🚀 Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
