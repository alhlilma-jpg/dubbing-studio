# =============================================================
# app.py (server.py) — sl-Dubbing Backend
# HF Spaces + Cloudinary + XTTS v2 + gTTS
# =============================================================
import os, uuid, time, logging, subprocess, json as _json
from pathlib import Path
from datetime import datetime

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

from utils import upload_to_cloudinary, fetch_voice_sample, mp3_to_wav, purge_tmp_folder
from voice_engine import synthesize as voice_synthesize

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["https://sl-dubbing.github.io", "http://localhost:*", "*"])
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

AUDIO_DIR = Path('/tmp/sl_audio')
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# ── نموذج المستخدم ────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'
    id              = db.Column(db.Integer, primary_key=True)
    email           = db.Column(db.String(120), unique=True, nullable=False)
    password        = db.Column(db.String(200), nullable=False)
    voice_public_id = db.Column(db.String(255))
    usage_tts       = db.Column(db.Integer, default=0)
    usage_dub       = db.Column(db.Integer, default=0)
    usage_srt       = db.Column(db.Integer, default=0)
    unlocked_tts    = db.Column(db.Boolean, default=False)
    unlocked_dub    = db.Column(db.Boolean, default=False)
    unlocked_srt    = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

GUEST_LIMIT = 6
GUEST_USAGE = {}

def reset_guest(ip):
    now = time.time()
    if ip not in GUEST_USAGE or now - GUEST_USAGE[ip].get('ts',0) > 86400:
        GUEST_USAGE[ip] = {'tts':0,'dub':0,'srt':0,'ts':now}

@app.before_request
def before_any():
    purge_tmp_folder()

# ══════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════

@app.route('/')
@app.route('/api/health')
def health():
    return jsonify({
        'status':     'ok',
        'service':    'sl-Dubbing Backend',
        'cloudinary': os.environ.get('CLOUDINARY_CLOUD_NAME','dxbmvzsiz')
    })

# ── تسجيل ─────────────────────────────────────────────────────
@app.route('/api/register', methods=['POST'])
def register():
    try:
        d     = request.get_json() or {}
        email = d.get('email','').strip().lower()
        pw    = d.get('password','')
        if not email or '@' not in email:
            return jsonify({'error':'بريد غير صالح'}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({'error':'البريد مسجّل مسبقاً'}), 400
        db.session.add(User(email=email, password=generate_password_hash(pw)))
        db.session.commit()
        return jsonify({'success':True,'email':email}), 201
    except Exception as e:
        logger.error(f"register: {e}")
        return jsonify({'error':'خطأ داخلي'}), 500

# ── دخول ──────────────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    try:
        d     = request.get_json() or {}
        email = d.get('email','').strip().lower()
        pw    = d.get('password','')
        user  = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, pw):
            return jsonify({'error':'بيانات غير صحيحة'}), 401
        return jsonify({
            'success':   True,
            'email':     user.email,
            'has_voice': bool(user.voice_public_id),
            'usage':    {'tts':user.usage_tts,'dub':user.usage_dub,'srt':user.usage_srt},
            'unlocked': {'tts':user.unlocked_tts,'dub':user.unlocked_dub,'srt':user.unlocked_srt}
        })
    except Exception as e:
        logger.error(f"login: {e}")
        return jsonify({'error':'خطأ داخلي'}), 500

# ── رفع عينة صوت ─────────────────────────────────────────────
@app.route('/api/upload-voice', methods=['POST'])
def upload_voice():
    try:
        email = request.form.get('email','').strip().lower()
        if 'voice' not in request.files:
            return jsonify({'error':'لم يتم رفع ملف'}), 400
        file = request.files['voice']
        ext  = Path(file.filename).suffix.lower() or '.wav'
        if ext not in {'.wav','.mp3','.ogg','.m4a'}:
            return jsonify({'error':'امتداد غير مدعوم'}), 400

        tmp = Path('/tmp') / f"voice_{uuid.uuid4()}{ext}"
        file.save(str(tmp))

        wav = tmp
        if ext != '.wav':
            w = tmp.with_suffix('.wav')
            try:
                subprocess.run(['ffmpeg','-y','-i',str(tmp),'-ar','22050','-ac','1',str(w)],
                               capture_output=True, timeout=30)
                if w.exists(): tmp.unlink(missing_ok=True); wav = w
            except Exception as e:
                logger.warning(f"ffmpeg: {e}")

        public_id = f"{email}_{uuid.uuid4()}" if email else f"guest_{uuid.uuid4()}"
        url = upload_to_cloudinary(str(wav), public_id)
        wav.unlink(missing_ok=True)

        if not url:
            return jsonify({'error':'فشل الرفع إلى Cloudinary'}), 500

        if email:
            user = User.query.filter_by(email=email).first()
            if user:
                user.voice_public_id = public_id
                db.session.commit()

        return jsonify({'success':True,'message':'تم حفظ العينة ✅','url':url,'public_id':public_id})
    except Exception as e:
        logger.error(f"upload_voice: {e}")
        return jsonify({'error':str(e)}), 500

# ── دبلجة ─────────────────────────────────────────────────────
@app.route('/api/dub', methods=['POST'])
def dub():
    try:
        d          = request.get_json() or {}
        text       = d.get('text','').strip()
        lang       = d.get('lang','ar')
        email      = (d.get('email') or '').strip().lower()
        voice_mode = d.get('voice_mode','gtts').lower()

        if not text:
            return jsonify({'error':'النص فارغ'}), 400

        ip = request.remote_addr
        reset_guest(ip)
        if GUEST_USAGE[ip].get('dub',0) >= GUEST_LIMIT:
            return jsonify({'error':'انتهى الحد المجاني','limit_reached':True}), 403
        GUEST_USAGE[ip]['dub'] += 1
        remaining = GUEST_LIMIT - GUEST_USAGE[ip]['dub']

        file_path, method = voice_synthesize(
            text=text,
            lang=lang,
            use_custom_voice=(voice_mode == 'xtts')
        )

        if not file_path:
            return jsonify({'error':'فشل توليد الصوت'}), 500

        filename  = Path(file_path).name
        audio_url = f"{request.host_url.rstrip('/')}/api/download/{filename}"

        return jsonify({
            'success':True,'audio_url':audio_url,'filename':filename,
            'method':method,'remaining':remaining,'lang':lang
        })
    except Exception as e:
        logger.error(f"dub: {e}")
        return jsonify({'error':str(e)}), 500

# ── تحميل ─────────────────────────────────────────────────────
@app.route('/api/download/<filename>')
def download(filename):
    safe = Path(filename).name
    p    = AUDIO_DIR / safe
    if not p.exists():
        return jsonify({'error':'الملف غير موجود'}), 404
    mime = 'audio/wav' if safe.endswith('.wav') else 'audio/mpeg'
    return send_file(str(p), as_attachment=True, download_name=safe, mimetype=mime)

# ── الأسعار ───────────────────────────────────────────────────
PRICES_FILE = Path(__file__).parent / 'prices.json'

@app.route('/api/prices')
def prices():
    try:
        with open(PRICES_FILE, encoding='utf-8') as f:
            return jsonify({'success':True,'prices':_json.load(f)})
    except Exception as e:
        return jsonify({'error':str(e)}), 500

# ── Webhook Lemon Squeezy / Payhip ───────────────────────────
@app.route('/api/webhook/payment', methods=['POST'])
def webhook():
    try:
        data  = request.get_json() or {}
        email = (data.get('email') or '').lower()
        feat  = data.get('feature','')
        if email and feat in ['tts','dub','srt']:
            user = User.query.filter_by(email=email).first()
            if user:
                setattr(user, f'unlocked_{feat}', True)
                db.session.commit()
                logger.info(f"✅ Unlocked {feat} for {email}")
        return jsonify({'success':True})
    except Exception as e:
        return jsonify({'error':str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
