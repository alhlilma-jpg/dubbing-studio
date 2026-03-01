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
        data = request.get_json()
        text = data.get('text', '')
        lang = data.get('lang', 'ar')
        
        if not text:
            return jsonify({'error': 'No text'}), 400
        
        voice = LANGUAGES.get(lang, 'ar-SA-HamedNeural')
        filename = f"dub_{uuid.uuid4().hex}.mp3"
        filepath = f"/tmp/{filename}"
        
        # Generate audio
        communicate = edge_tts.Communicate(text, voice)
        asyncio.run(communicate.save(filepath))
        
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return jsonify({'success': True, 'file': filename})
        else:
            return jsonify({'error': 'Generation failed'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<filename>')
def download(filename):
    try:
        filepath = f"/tmp/{filename}"
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=filename)
        return jsonify({'error': 'Not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
