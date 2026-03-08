# =============================================================
# sl-Dubbing & Translation - Backend (Flask)
# =============================================================
import os, uuid, logging, random, smtplib, time
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": ["https://sl-dubbing.github.io", "http://localhost:*", "*"],
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
        msg.body = f'''
مرحباً بك في sl-Dubbing!

كود تفعيل حسابك هو: {otp_code}

هذا الكود صالح لمدة 10 دقائق.

إذا لم تقم بإنشاء حساب، يرجى تجاهل هذا البريد.

شكراً لك!
فريق sl-Dubbing
        '''
        msg.html = f'''
        <html>
        <body style="font-family: Arial, sans-serif; background: #0a0a1a; color: #e0e0ff; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #1a0533, #0a0a1a); padding: 30px; border-radius: 20px; border: 2px solid #a78bfa;">
                <h2 style="color: #a78bfa; text-align: center;">🎉 مرحباً بك في sl-Dubbing!</h2>
                <p style="text-align: center; color: #9ca3af;">كود تفعيل حسابك هو:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <span style="display: inline-block; background: linear-gradient(135deg, #7c3aed, #2563eb); color: white; padding: 20px 40px; border-radius: 12px; font-size: 2rem; font-weight: bold; letter-spacing: 5px;">{otp_code}</span>
                </div>
                <p style="text-align: center; color: #6b7280;">صالح لمدة 10 دقائق</p>
                <hr style="border: none; border-top: 1px solid rgba(255,255,255,0.1); margin: 20px 0;">
                <p style="text-align: center; color: #4b5563; font-size: 0.8rem;">إذا لم تقم بإنشاء حساب، يرجى تجاهل هذا البريد</p>
            </div>
        </body>
        </html>
        '''
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
            'verify-otp': '/api/verify-otp',
            'send-otp': '/api/send-otp',
            'entitlements': '/api/entitlements',
            'consume': '/api/consume',
            'dub': '/api/dub',
            'download': '/api/download/<filename>'
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
        
        # إنشاء OTP
        otp = str(random.randint(100000, 999999))
        
        # إنشاء المستخدم
        new_user = User(
            email=email,
            password=generate_password_hash(password),
            otp=otp,
            otp_expiry=datetime.utcnow() + timedelta(minutes=10),
            is_verified=False
        )
        db.session.add(new_user)
        db.session.commit()
        
        # إرسال OTP
        send_otp_email(email, otp)
        
        logger.info(f"New user registered: {email}")
        return jsonify({
            'success': True,
            'message': 'تم التسجيل بنجاح، تحقق من بريدك الإلكتروني لكود التفعيل',
            'email': email
        }), 201
        
    except Exception as e:
        logger.error(f"Register Error: {e}")
        return jsonify({'error': 'حدث خطأ في التسجيل'}), 500

@app.route('/api/send-otp', methods=['POST'])
def send_otp():
    """إرسال OTP جديد"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'مستخدم غير موجود'}), 404
        
        # إنشاء OTP جديد
        otp = str(random.randint(100000, 999999))
        user.otp = otp
        user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
        db.session.commit()
        
        send_otp_email(email, otp)
        
        return jsonify({'success': True, 'message': 'تم إرسال الكود'})
        
    except Exception as e:
        logger.error(f"Send OTP Error: {e}")
        return jsonify({'error': 'حدث خطأ'}), 500

@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    """التحقق من OTP"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        otp = data.get('otp', '')
        
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'مستخدم غير موجود'}), 404
        
        if user.otp != otp:
            return jsonify({'error': 'كود غير صحيح'}), 400
        
        if user.otp_expiry and user.otp_expiry < datetime.utcnow():
            return jsonify({'error': 'الكود منتهي الصلاحية'}), 400
        
        # تفعيل الحساب
        user.is_verified = True
        user.otp = None
        user.otp_expiry = None
        db.session.commit()
        
        logger.info(f"User verified: {email}")
        return jsonify({
            'success': True,
            'message': 'تم تفعيل الحساب بنجاح'
        })
        
    except Exception as e:
        logger.error(f"Verify OTP Error: {e}")
        return jsonify({'error': 'حدث خطأ'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    """تسجيل الدخول"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'البريد وكلمة المرور مطلوبان'}), 400
        
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'البريد أو كلمة المرور غير صحيحة'}), 401
        
        if not check_password_hash(user.password, password):
            return jsonify({'error': 'البريد أو كلمة المرور غير صحيحة'}), 401
        
        if not user.is_verified:
            return jsonify({
                'error': 'يجب تفعيل الحساب أولاً',
                'not_verified': True
            }), 403
        
        logger.info(f"User logged in: {email}")
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

@app.route('/api/entitlements', methods=['GET'])
def get_entitlements():
    """جلب صلاحيات المستخدم"""
    try:
        email = request.args.get('email', '').strip().lower()
        
        if not email:
            return jsonify({'error': 'البريد الإلكتروني مطلوب'}), 400
        
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'المستخدم غير موجود'}), 404
        
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
            },
            'limits': {
                'tts': GUEST_LIMIT if not user.unlocked_tts else 'unlimited',
                'dub': GUEST_LIMIT if not user.unlocked_dub else 'unlimited',
                'srt': GUEST_LIMIT if not user.unlocked_srt else 'unlimited'
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Entitlements Error: {e}")
        return jsonify({'error': 'حدث خطأ'}), 500

@app.route('/api/consume', methods=['POST'])
def consume():
    """تسجيل استهلاك استخدام لميزة محلية (مثل النطق باستخدام Web Speech API)"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        feature = data.get('feature')
        
        if not email or feature not in ['tts', 'dub', 'srt']:
            return jsonify({'error': 'طلب غير صالح'}), 400
        
        user = User.query.filter_by(email=email).first()
        if not user or not user.is_verified:
            return jsonify({'error': 'المستخدم غير موجود أو غير مفعل'}), 403
        
        unlocked_field = f'unlocked_{feature}'
        usage_field = f'usage_{feature}'
        
        if getattr(user, unlocked_field):
            remaining = 'unlimited'
        else:
            current_usage = getattr(user, usage_field)
            if current_usage >= GUEST_LIMIT:
                return jsonify({
                    'error': 'انتهى الحد المجاني',
                    'limit_reached': True
                }), 403
            setattr(user, usage_field, current_usage + 1)
            db.session.commit()
            remaining = GUEST_LIMIT - getattr(user, usage_field)
        
        return jsonify({
            'success': True,
            'remaining': remaining,
            'message': 'تم تسجيل الاستخدام'
        })
        
    except Exception as e:
        logger.error(f"Consume Error: {e}")
        return jsonify({'error': 'حدث خطأ'}), 500

@app.route('/api/dub', methods=['POST'])
def dub():
    """معالجة الدبلجة/النطق (هنا يتم دمج الاستهلاك مع المعالجة الفعلية)"""
    try:
        data = request.get_json()
        text = data.get('text', '')
        lang = data.get('lang', 'ar')
        email = data.get('email', '').strip().lower() if data.get('email') else None
        feature = data.get('feature', 'dub')
        
        if feature not in ['tts', 'dub', 'srt']:
            feature = 'dub'
        
        # فحص الحد للضيوف أو المستخدمين
        if not email:
            ip = request.remote_addr
            reset_guest_usage_if_needed(ip)
            
            if GUEST_USAGE[ip].get(feature, 0) >= GUEST_LIMIT:
                return jsonify({
                    'error': 'انتهى الحد المجاني',
                    'limit_reached': True
                }), 403
            
            GUEST_USAGE[ip][feature] = GUEST_USAGE[ip].get(feature, 0) + 1
            remaining = GUEST_LIMIT - GUEST_USAGE[ip][feature]
        else:
            user = User.query.filter_by(email=email).first()
            if not user or not user.is_verified:
                return jsonify({
                    'error': 'يجب التفعيل',
                    'not_verified': True
                }), 403
            
            unlocked_field = f'unlocked_{feature}'
            usage_field = f'usage_{feature}'
            
            if not getattr(user, unlocked_field):
                current_usage = getattr(user, usage_field, 0)
                if current_usage >= GUEST_LIMIT:
                    return jsonify({
                        'error': 'انتهى الحد المجاني',
                        'limit_reached': True
                    }), 403
                
                setattr(user, usage_field, current_usage + 1)
                db.session.commit()
                remaining = GUEST_LIMIT - getattr(user, usage_field)
            else:
                remaining = 'unlimited'
        
        # هنا تضع كود المعالجة الفعلي (مثل إنشاء ملف صوتي باستخدام gTTS)
        # للتبسيط، نعيد رسالة نجاح
        return jsonify({
            'success': True,
            'remaining': remaining,
            'message': 'تمت المعالجة',
            'audio_url': None  # يمكن إضافة رابط الملف لاحقاً
        })
        
    except Exception as e:
        logger.error(f"Dub Error: {e}")
        return jsonify({'error': 'حدث خطأ'}), 500

@app.route('/api/download/<filename>')
def download(filename):
    """تنزيل الملفات"""
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

@app.route('/api/webhook/lemonsqueezy', methods=['POST'])
def lemonsqueezy_webhook():
    """Webhook لاستلام تأكيدات الدفع"""
    try:
        data = request.get_json()
        event_name = data.get('event_name', '')
        
        if event_name == 'order_created':
            order_data = data.get('data', {}).get('attributes', {})
            customer_email = order_data.get('email', '').lower()
            custom_data = order_data.get('custom', {})
            feature_hint = custom_data.get('feature_hint', '')
            
            if customer_email and feature_hint in ['tts', 'dub', 'srt']:
                user = User.query.filter_by(email=customer_email).first()
                if user:
                    unlocked_field = f'unlocked_{feature_hint}'
                    setattr(user, unlocked_field, True)
                    db.session.commit()
                    logger.info(f"User {customer_email} unlocked {feature_hint}")
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return jsonify({'error': 'Webhook failed'}), 500

# =============================================================
# تشغيل التطبيق
# =============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
