from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import edge_tts
import asyncio
import os
import uuid

app = Flask(__name__)
CORS(app)  # يسمح للموقع بالاتصال

# اللغات المتاحة
LANGUAGES = {
    'en': 'en-US-GuyNeural',
    'es': 'es-ES-ElviraNeural',
    'fr': 'fr-FR-DeniseNeural',
    'de': 'de-DE-ConradNeural',
    'ru': 'ru-RU-DmitryNeural',
    'tr': 'tr-TR-AhmetNeural',
    'ar': 'ar-SA-HamedNeural',
    'zh': 'zh-CN-XiaoxiaoNeural',
    'hi': 'hi-IN-SwaraNeural',
    'fa': 'fa-IR-FaridNeural',
    'it': 'it-IT-DiegoNeural',
    'nl': 'nl-NL-ColetteNeural',
    'sv': 'sv-SE-MattiasNeural',
}

@app.route('/api/dub', methods=['POST'])
def dub():
    data = request.json
    text = data.get('text', '')
    lang = data.get('lang', 'ar')
    
    if not text:
        return jsonify({'error': 'لا يوجد نص'}), 400
    
    voice = LANGUAGES.get(lang, 'ar-SA-HamedNeural')
    filename = f"dub_{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(os.path.dirname(__file__), filename)
    
    # توليد الصوت
    asyncio.run(generate_audio(text, voice, filepath))
    
    if os.path.exists(filepath):
        return jsonify({
            'success': True,
            'file': filename,
            'message': 'تم التوليد بنجاح'
        })
    else:
        return jsonify({'error': 'فشل التوليد'}), 500

@app.route('/api/download/<filename>')
def download(filename):
    filepath = os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': 'الملف غير موجود'}), 404

async def generate_audio(text, voice, output_file):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 سيرفر الدبلجة يعمل على:")
    print("   http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000)