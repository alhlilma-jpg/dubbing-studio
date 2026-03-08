# =============================================================
# sl-Dubbing & Translation - Backend (Flask)
# =============================================================
import os
import uuid
import logging
import random
import smtplib
import time
import tempfile
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from gtts import gTTS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": ["*"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# =============================================================
# إعدادات التطبيق
# =============================================================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# إعدادات البريد
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'your-email@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'your-app-password')
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

db = SQLAlchemy(app)
mail = Mail(app)

# =============================================================
# نموذج المستخدم
# =============================================================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    otp = db.Column(db.String(6))
    otp_expiry = db.Column(db.DateTime)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # الاستخدام
    usage_tts = db.Column(db.Integer, default=0)
    usage_dub = db.Column(db.Integer, default=0)
    usage_srt = db.Column(db.Integer, default=0)

    # الصلاحيات
    unlocked_tts = db.Column(db.Boolean, default=False)
    unlocked_dub = db.Column(db.Boolean, default=False)
    unlocked_srt = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

# =============================================================
# ثوابت
# =============================================================
GUEST_LIMIT = 6
GUEST_USAGE = {}

# =============================================================
# دوال مساعدة
# =============================================================
def send_otp_email(user_email, otp_code):
    """إرسال كود OTP عبر الإيميل"""
    try:
        msg = Message(
            '🔐 كود تفعيل حسابك - sl-Dubbing',
            sender=app.config['MAIL_USERNAME'],
            recipients=[user_email]
        )
        msg.body = f"""
مرحباً بك في sl-Dubbing!

كود تفعيل حسابك هو: {otp_code}

هذا الكود صالح لمدة 10 دقائق.

إذا لم تقم بإنشاء حساب، يرجى تجاهل هذا البريد.

شكراً لك!
فريق sl-Dubbing
        """
        mail.send(msg)
        logger.info(f"OTP sent to {user_email}")
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False

def reset_guest_usage_if_needed(ip):
    """إعادة تعيين استخدام الضيف كل 24 ساعة"""
    if ip in GUEST_USAGE:
        last_reset = GUEST_USAGE[ip].get('last_reset', 0)
        if time.time() - last_reset > 86400:
            GUEST_USAGE[ip] = {'tts': 0, 'dub': 0, 'srt': 0, 'last_reset': time.time()}
    else:
        GUEST_USAGE[ip] = {'tts': 0, 'dub': 0, 'srt': 0, 'last_reset': time.time()}

# =============================================================
# المسارات
# =============================================================

@app.route('/')
def index():
    return jsonify({
        'status': 'ok',
        'message': 'sl-Dubbing Backend API',
        'endpoints': {
            'health': '/api/health',
            'login': '/api/login',
            'register': '/api/register',
            'dub': '/api/dub'
        }
    })

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'sl-Dubbing Backend'
    })

@app.route('/api/register', methods=['POST'])
def register():
    """تسجيل مستخدم جديد"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        if not email or '@' not in email:
            return jsonify({'error': 'بريد إلكتروني غير صحيح'}), 400

        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'البريد مسجل بالفعل'}), 400

        otp = str(random.randint(100000, 999999))

        new_user = User(
            email=email,
            password=generate_password_hash(password),
            otp=otp,
            otp_expiry=datetime.utcnow() + timedelta(minutes=10),
            is_verified=False
        )
        db.session.add(new_user)
        db.session.commit()

        send_otp_email(email, otp)

        return jsonify({
            'success': True,
            'message': 'تم التسجيل بنجاح',
            'email': email
        }), 201

    except Exception as e:
        logger.error(f"Register Error: {e}")
        return jsonify({'error': 'حدث خطأ في التسجيل'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    """تسجيل الدخول"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            return jsonify({'error': 'البريد أو كلمة المرور غير صحيحة'}), 401

        return jsonify({
            'success': True,
            'email': user.email,
            'unlocked': {
                'tts': user.unlocked_tts,
                'dub': user.unlocked_dub,
                'srt': user.unlocked_srt
            },
            'usage': {
                'tts': user.usage_tts,
                'dub': user.usage_dub,
                'srt': user.usage_srt
            }
        }), 200

    except Exception as e:
        logger.error(f"Login Error: {e}")
        return jsonify({'error': 'حدث خطأ في تسجيل الدخول'}), 500

@app.route('/api/dub', methods=['POST'])
def dub():
    """معالجة الدبلجة مع إنشاء ملف صوتي حقيقي"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        lang = data.get('lang', 'ar')
        email = data.get('email', '').strip().lower() if data.get('email') else None
        feature = data.get('feature', 'dub')

        if not text:
            return jsonify({'error': 'النص مطلوب'}), 400

        # فحص الحدود
        remaining = None
        if not email:
            ip = request.remote_addr
            reset_guest_usage_if_needed(ip)

            if GUEST_USAGE[ip].get(feature, 0) >= GUEST_LIMIT:
                return jsonify({'error': 'انتهى الحد المجاني', 'limit_reached': True}), 403

            GUEST_USAGE[ip][feature] = GUEST_USAGE[ip].get(feature, 0) + 1
            remaining = GUEST_LIMIT - GUEST_USAGE[ip][feature]
        else:
            user = User.query.filter_by(email=email).first()
            if not user:
                return jsonify({'error': 'المستخدم غير موجود'}), 404

            if not getattr(user, f'unlocked_{feature}'):
                current_usage = getattr(user, f'usage_{feature}', 0)
                if current_usage >= GUEST_LIMIT:
                    return jsonify({'error': 'انتهى الحد المجاني', 'limit_reached': True}), 403

                setattr(user, f'usage_{feature}', current_usage + 1)
                db.session.commit()
                remaining = GUEST_LIMIT - getattr(user, f'usage_{feature}')
            else:
                remaining = 'unlimited'

        # إنشاء ملف صوتي
        try:
            # تقسيم النص إذا كان طويلاً
            max_chars = 5000
            if len(text) > max_chars:
                text = text[:max_chars]

            # إنشاء ملف مؤقت
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3', dir='/tmp')
            temp_path = temp_file.name
            temp_file.close()

            # توليد الصوت باستخدام gTTS
            tts = gTTS(text=text, lang=lang, slow=False)
            tts.save(temp_path)

            filename = os.path.basename(temp_path)
            logger.info(f"Audio generated: {filename}")

            return jsonify({
                'success': True,
                'remaining': remaining,
                'message': 'تم توليد الملف الصوتي',
                'audio_url': f'/api/download/{filename}'
            })

        except Exception as e:
            logger.error(f"gTTS Error: {e}")
            return jsonify({'error': f'خطأ في توليد الصوت: {str(e)}'}), 500

    except Exception as e:
        logger.error(f"Dub Error: {e}")
        return jsonify({'error': f'حدث خطأ: {str(e)}'}), 500

@app.route('/api/download/<filename>')
def download(filename):
    """تنزيل الملفات الصوتية"""
    try:
        filepath = os.path.join('/tmp', filename)

        if not os.path.exists(filepath):
            return jsonify({'error': 'الملف غير موجود'}), 404

        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='audio/mpeg'
        )

    except Exception as e:
        logger.error(f"Download Error: {e}")
        return jsonify({'error': 'فشل تنزيل الملف'}), 500

# =============================================================
# تشغيل التطبيق
# =============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
