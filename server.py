from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import edge_tts
import asyncio
import os
import uuid
import tempfile

app = Flask(__name__)
CORS(app)

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

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/api/dub', methods=['POST'])
def dub():
    try:
        data = request.json
        text = data.get('text', '')
        lang = data.get('lang', 'ar')
        
        if not text:
            return jsonify({'error': 'لا يوجد نص'}), 400
        
        voice = LANGUAGES.get(lang, 'ar-SA-HamedNeural')
        filename = f"dub_{uuid.uuid4().hex}.mp3"
        
        # ✅ استخدام مجلد مؤقت بدلاً من __file__
        filepath = os.path.join(tempfile.gettempdir(), filename)
        
        asyncio.run(generate_audio(text, voice, filepath))
        
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return jsonify({'success': True, 'file': filename, 'message': 'تم التوليد بنجاح'})
        else:
            return jsonify({'error': 'فشل التوليد - الملف فارغ'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<filename>')
def download(filename):
    try:
        filepath = os.path.join(tempfile.gettempdir(), filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=filename)
        return jsonify({'error': 'الملف غير موجود'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

async def generate_audio(text, voice, output_file):
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)
    except Exception as e:
        print(f"Error in generate_audio: {e}")
        raise

if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get('PORT', 5000)))
