# =============================================================
# sl-Dubbing & Translation - Backend (Flask)
# =============================================================
import os, uuid, logging, random, smtplib, time
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from gtts import gTTS
from pydub import AudioSegment
from werkzeug.security import generate_password_hash, check_password_hash
from email.mime.text import MIMEText
from datetime import datetime

# إعداد السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# =============================================================
# إعداد قاعدة البيانات (SQLite)
# =============================================================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///alhashmi_users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# =============================================================
# إعدادات الحد المجاني
# =============================================================
GUEST_LIMIT = 6  # ✅ 6 محاولات مجانية لكل ميزة (كان 3)
GUEST_USAGE = {}  # format: {ip: {'tts': 0, 'dub': 0, 'srt': 0, 'last_reset': timestamp}}

# =============================================================
# تعريف نموذج المستخدم
# =============================================================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # ✅ تم إصلاح: self.String → db.String
    otp = db.Column(db.String(6))
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # حقول الاستخدام المجاني (لكل ميزة على حدة)
    usage_tts = db.Column(db.Integer, default=0)
    usage_dub = db.Column(db.Integer, default=0)
    usage_srt = db.Column(db.Integer, default=0)
    
    # حقول الشراء/التفعيل (لكل ميزة على حدة)
    unlocked_tts = db.Column(db.Boolean, default=False)
    unlocked_dub = db.Column(db.Boolean, default=False)
    unlocked_srt = db.Column(db.Boolean, default=False)

# إنشاء الجداول عند بدء التشغيل
with app.app_context():
    db.create_all()

# =============================================================
# إعدادات اللغات
# =============================================================
LANGUAGES = {
    'en': 'en', 'es': 'es', 'fr': 'fr', 'de': 'de',
    'ru': 'ru', 'tr': 'tr', 'ar': 'ar',
    'zh': 'zh-CN', 'hi': 'hi', 'fa': 'fa',
    'it': 'it', 'nl': 'nl', 'sv': 'sv'
}

# =============================================================
# دالة إرسال OTP عبر الإيميل
# =============================================================
def send_otp_email(user_email, otp_code):
    sender = "your-email@gmail.com"  # ⚠️ ضع إيميلك هنا
    password = "xxxx xxxx xxxx xxxx"  # ⚠️ كلمة مرور التطبيقات من جوجل
    
    msg = MIMEText(f"كود التحقق الخاص بك هو: {otp_code}")
    msg['Subject'] = 'كود تفعيل استوديو الهاشمي'
    msg['From'] = sender
    msg['To'] = user_email
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, user_email, msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Mail Error: {e}")
        return False

# =============================================================
# دالة إعادة تعيين استخدام الضيوف (كل 24 ساعة)
# =============================================================
def reset_guest_usage_if_needed(ip):
    """إعادة تعيين عداد الضيف إذا مر 24 ساعة"""
    if ip in GUEST_USAGE:
        last_reset = GUEST_USAGE[ip].get('last_reset', 0)
        if time.time() - last_reset > 86400:  # 24 ساعة = 86400 ثانية
            GUEST_USAGE[ip] = {'tts': 0, 'dub': 0, 'srt': 0, 'last_reset': time.time()}
    else:
        GUEST_USAGE[ip] = {'tts': 0, 'dub': 0, 'srt': 0, 'last_reset': time.time()}

# =============================================================
# مسار الصحة (Health Check)
# =============================================================
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})

# =============================================================
# مسارات الحسابات
# =============================================================

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or '@' not in email:
            return jsonify({'error': 'البريد الإلكتروني غير صحيح'}), 400
        
        if not email.endswith('@gmail.com'):
            return jsonify({'error': 'مقبول فقط بريد Gmail (@gmail.com)'}), 400
        
        if len(password) < 8:
            return jsonify({'error': 'كلمة المرور يجب أن تكون 8 أحرف على الأقل'}), 400
        
        # التحقق من وجود المستخدم
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({'error': 'البريد مسجل بالفعل'}), 400
        
        # إنشاء كود OTP
        otp = str(random.randint(100000, 999999))
        
        # إنشاء المستخدم الجديد
        new_user = User(
            email=email,
            password=generate_password_hash(password),
            otp=otp,
            is_verified=False
        )
        db.session.add(new_user)
        db.session.commit()
        
        # إرسال OTP عبر الإيميل
        send_otp_email(email, otp)
        
        logger.info(f"New user registered: {email}")
        return jsonify({
            'success': True,
            'message': 'تم إرسال كود التحقق إلى بريدك الإلكتروني'
        }), 201
        
    except Exception as e:
        logger.error(f"Register Error: {e}")
        return jsonify({'error': 'حدث خطأ في التسجيل'}), 500

@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        otp = data.get('otp', '')
        
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'المستخدم غير موجود'}), 404
        
        if user.otp != otp:
            return jsonify({'error': 'كود التحقق غير صحيح'}), 400
        
        # تفعيل الحساب
        user.is_verified = True
        user.otp = None
        db.session.commit()
        
        logger.info(f"User verified: {email}")
        return jsonify({'success': True, 'message': 'تم تفعيل حسابك بنجاح'}), 200
        
    except Exception as e:
        logger.error(f"Verify OTP Error: {e}")
        return jsonify({'error': 'حدث خطأ في التفعيل'}), 500

@app.route('/api/login', methods=['POST'])
def login():
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
                'error': 'حسابك غير مفعل',
                'not_verified': True,
                'email': email
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

# =============================================================
# مسار التحقق من الصلاحيات (Entitlements)
# =============================================================
@app.route('/api/entitlements', methods=['GET'])
def get_entitlements():
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
        return jsonify({'error': 'حدث خطأ في جلب الصلاحيات'}), 500

# =============================================================
# مسار المعالجة الأساسي (يدعم tts, dub, srt)
# =============================================================
@app.route('/api/dub', methods=['POST'])
def dub():
    try:
        data = request.get_json()
        text = data.get('text', '')
        lang = data.get('lang', 'ar')
        email = data.get('email', '').strip().lower() if data.get('email') else None
        feature = data.get('feature', 'dub')  # ✅ جديد: tts, dub, أو srt
        
        # ✅ التحقق من أن الميزة مدعومة
        if feature not in ['tts', 'dub', 'srt']:
            feature = 'dub'
        
        # =============================================================
        # فحص الحد للضيوف (غير مسجّلين)
        # =============================================================
        if not email:
            ip = request.remote_addr
            reset_guest_usage_if_needed(ip)
            
            current_usage = GUEST_USAGE[ip].get(feature, 0)
            
            if current_usage >= GUEST_LIMIT:
                logger.warning(f"Guest limit reached for IP {ip} on feature {feature}")
                return jsonify({
                    'error': 'انتهى الحد المجاني (6 محاولات)',
                    'limit_reached': True,
                    'feature': feature,
                    'remaining': 0
                }), 403
            
            # زيادة العداد للميزة الحالية فقط
            GUEST_USAGE[ip][feature] = current_usage + 1
            remaining = GUEST_LIMIT - GUEST_USAGE[ip][feature]
            
            logger.info(f"Guest using {feature}: {GUEST_USAGE[ip][feature]}/{GUEST_LIMIT} (IP: {ip})")
            
        # =============================================================
        # فحص الحد للمستخدمين المسجّلين
        # =============================================================
        else:
            user = User.query.filter_by(email=email).first()
            
            if not user:
                return jsonify({
                    'error': 'المستخدم غير موجود',
                    'limit_reached': True
                }), 403
            
            if not user.is_verified:
                return jsonify({
                    'error': 'يجب تفعيل الحساب أولاً',
                    'not_verified': True
                }), 403
            
            # تحديد حقول الاستخدام والتفعيل بناءً على الميزة
            unlocked_field = f'unlocked_{feature}'
            usage_field = f'usage_{feature}'
            
            # إذا الميزة غير مفعّلة (غير مدفوعة)
            if not getattr(user, unlocked_field, False):
                current_usage = getattr(user, usage_field, 0)
                
                if current_usage >= GUEST_LIMIT:
                    logger.warning(f"User limit reached for {email} on feature {feature}")
                    return jsonify({
                        'error': 'انتهى الحد المجاني (6 محاولات)',
                        'limit_reached': True,
                        'feature': feature,
                        'remaining': 0,
                        'upgrade_needed': True
                    }), 403
                
                # زيادة العداد للميزة الحالية فقط
                setattr(user, usage_field, current_usage + 1)
                db.session.commit()
                remaining = GUEST_LIMIT - getattr(user, usage_field, 0)
                
                logger.info(f"User {email} using {feature}: {getattr(user, usage_field, 0)}/{GUEST_LIMIT}")
            else:
                # الميزة مفعّلة = استخدام غير محدود
                remaining = 'unlimited'
                logger.info(f"User {email} using {feature} (unlimited)")
        
        # =============================================================
        # معالجة الدبلجة/النطق الفعلية
        # =============================================================
        try:
            filename = f"{feature}_{uuid.uuid4().hex}.mp3"
            filepath = os.path.join('/tmp', filename)
            
            # إنشاء ملف الصوت باستخدام gTTS
            tts_lang = LANGUAGES.get(lang, 'ar')
            tts = gTTS(text=text, lang=tts_lang, slow=False)
            tts.save(filepath)
            
            # التحقق من وجود الملف
            if not os.path.exists(filepath):
                raise Exception("فشل إنشاء ملف الصوت")
            
            logger.info(f"Audio created: {filename} for feature {feature}")
            
            return jsonify({
                'success': True,
                'file': filename,
                'feature': feature,
                'remaining': remaining,
                'message': 'تم إنشاء الملف بنجاح'
            }), 200
            
        except Exception as e:
            logger.error(f"TTS Generation Error: {e}")
            return jsonify({
                'error': f'فشل إنشاء الصوت: {str(e)}',
                'feature': feature
            }), 500
            
    except Exception as e:
        logger.error(f"Processing Error: {e}")
        return jsonify({'error': 'حدث خطأ غير متوقع'}), 500

# =============================================================
# مسار تنزيل الملفات
# =============================================================
@app.route('/api/download/<filename>', methods=['GET'])
def download(filename):
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
# مسار ترجمة SRT (مثال - يحتاج لتكامل مع API ترجمة)
# =============================================================
@app.route('/api/translate-srt', methods=['POST'])
def translate_srt():
    try:
        data = request.get_json()
        content = data.get('content', '')
        target_lang = data.get('target_lang', 'en')
        email = data.get('email', '').strip().lower() if data.get('email') else None
        feature = 'srt'
        
        # نفس منطق التحقق من الحد
        if not email:
            ip = request.remote_addr
            reset_guest_usage_if_needed(ip)
            
            if GUEST_USAGE[ip].get(feature, 0) >= GUEST_LIMIT:
                return jsonify({'error': 'انتهى الحد المجاني', 'limit_reached': True}), 403
            
            GUEST_USAGE[ip][feature] = GUEST_USAGE[ip].get(feature, 0) + 1
        else:
            user = User.query.filter_by(email=email).first()
            if not user or not user.is_verified:
                return jsonify({'error': 'يجب التفعيل', 'not_verified': True}), 403
            
            if not user.unlocked_srt and user.usage_srt >= GUEST_LIMIT:
                return jsonify({'error': 'انتهى الحد المجاني', 'limit_reached': True}), 403
            
            if not user.unlocked_srt:
                user.usage_srt += 1
                db.session.commit()
        
        # ⚠️ هنا تضع كود الترجمة الفعلي (يمكن استخدام Google Translate API أو غيره)
        # هذا مجرد مثال حالي يعيد نفس النص
        translated_content = content
        
        return jsonify({
            'success': True,
            'translated': translated_content,
            'message': 'تمت المعالجة بنجاح'
        }), 200
        
    except Exception as e:
        logger.error(f"Translate SRT Error: {e}")
        return jsonify({'error': 'حدث خطأ في المعالجة'}), 500

# =============================================================
# مسار Webhook لاستلام تأكيدات الدفع من Lemon Squeezy
# =============================================================
@app.route('/api/webhook/lemonsqueezy', methods=['POST'])
def lemonsqueezy_webhook():
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
                    return jsonify({'success': True}), 200
        
        return jsonify({'success': True, 'ignored': True}), 200
        
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return jsonify({'error': 'Webhook failed'}), 500

# =============================================================
# مسار حذف الحساب (للتوافق مع GDPR)
# =============================================================
@app.route('/api/delete-account', methods=['POST'])
def delete_account():
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'البريد وكلمة المرور مطلوبان'}), 400
        
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'المستخدم غير موجود'}), 404
        
        if not check_password_hash(user.password, password):
            return jsonify({'error': 'كلمة المرور غير صحيحة'}), 401
        
        # حذف المستخدم
        db.session.delete(user)
        db.session.commit()
        
        logger.info(f"Account deleted: {email}")
        return jsonify({'success': True, 'message': 'تم حذف حسابك بنجاح'}), 200
        
    except Exception as e:
        logger.error(f"Delete Account Error: {e}")
        return jsonify({'error': 'حدث خطأ في حذف الحساب'}), 500

# =============================================================
# تشغيل التطبيق
# =============================================================
if __name__ == '__main__':
    # إنشاء مجلد /tmp إذا لم يكن موجوداً
    os.makedirs('/tmp', exist_ok=True)
    
    # تشغيل السيرفر
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    )
