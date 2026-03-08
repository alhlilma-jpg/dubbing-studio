import os, uuid, logging, random, smtplib
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from gtts import gTTS
from pydub import AudioSegment
from pydub.effects import speedup, normalize
from werkzeug.security import generate_password_hash, check_password_hash
from email.mime.text import MIMEText

# إعداد السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# إعداد قاعدة البيانات (SQLite)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///alhashmi_users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# تتبع استخدام الضيوف (في الذاكرة - يصفر عند إعادة تشغيل السيرفر)
guest_usage = {} 
GUEST_LIMIT = 3 # عدد المحاولات المجانية للضيف

# تعريف نموذج المستخدم
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(self.String(200), nullable=False)
    otp = db.Column(db.String(6))
    is_verified = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

LANGUAGES = {'en':'en','es':'es','fr':'fr','de':'de','ru':'ru', 'tr':'tr','ar':'ar'}

def send_otp_email(user_email, otp_code):
    sender = "your-email@gmail.com"  # ايميلك هنا
    password = "xxxx xxxx xxxx xxxx" # كلمة مرور التطبيقات من جوجل
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

# --- مسارات الحسابات ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    email, password = data.get('email'), data.get('password')
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'الإيميل مسجل بالفعل'}), 400
    otp = str(random.randint(100000, 999999))
    new_user = User(email=email, password=generate_password_hash(password), otp=otp)
    db.session.add(new_user)
    db.session.commit()
    send_otp_email(email, otp)
    return jsonify({'success': True, 'message': 'تم إرسال الكود'})

@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    user = User.query.filter_by(email=data.get('email')).first()
    if user and user.otp == data.get('otp'):
        user.is_verified, user.otp = True, None
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'كود غير صحيح'}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data.get('email')).first()
    if user and check_password_hash(user.password, data.get('password')):
        if not user.is_verified:
            return jsonify({'error': 'حسابك غير مفعل', 'not_verified': True}), 403
        return jsonify({'success': True, 'email': user.email})
    return jsonify({'error': 'بيانات خاطئة'}), 401

# --- مسار الدبلجة الأساسي ---
@app.route('/api/dub', methods=['POST'])
def dub():
    data = request.get_json()
    email = data.get('email')
    
    # فحص الحد للمجهول
    if not email:
        ip = request.remote_addr
        count = guest_usage.get(ip, 0)
        if count >= GUEST_LIMIT:
            return jsonify({'error': 'انتهى الحد المجاني', 'limit_reached': True}), 403
        guest_usage[ip] = count + 1
    else:
        user = User.query.filter_by(email=email).first()
        if not user or not user.is_verified:
            return jsonify({'error': 'يجب التفعيل', 'not_verified': True}), 403

    try:
        text, lang = data.get('text', ''), data.get('lang', 'ar')
        filename = f"dub_{uuid.uuid4().hex}.mp3"
        filepath = f"/tmp/{filename}"
        tts = gTTS(text=text, lang=LANGUAGES.get(lang, 'ar'))
        tts.save(filepath)
        return jsonify({'success': True, 'file': filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<filename>')
def download(filename):
    return send_file(f"/tmp/{filename}", as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
