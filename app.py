import os
import tempfile
from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI

app = Flask(__name__, static_folder=".")

MAX_FILE_SIZE_MB = 24


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/transcribe", methods=["POST"])
def transcribe():
    api_key = request.form.get("api_key", "").strip()
    audio_file = request.files.get("audio")
    language = request.form.get("language", "ja")

    if not api_key:
        return jsonify({"error": "APIキーを入力してください"}), 400
    if not audio_file:
        return jsonify({"error": "音声ファイルを選択してください"}), 400

    # ファイルサイズチェック（Whisper API の上限は 25MB）
    audio_file.seek(0, 2)
    size_mb = audio_file.tell() / (1024 * 1024)
    audio_file.seek(0)

    if size_mb > MAX_FILE_SIZE_MB:
        return jsonify({
            "error": (
                f"ファイルサイズが {size_mb:.1f}MB です。"
                f"Whisper API の上限は 25MB のため、"
                f"ファイルを圧縮するか分割してください。\n"
                f"ヒント: 音声をモノラル・低ビットレートに変換すると小さくなります。"
            )
        }), 400

    ext = os.path.splitext(audio_file.filename)[1].lower() or ".mp3"
    client = OpenAI(api_key=api_key)

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        audio_file.save(tmp.name)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language=language,
                response_format="verbose_json",
            )
        # セグメントにタイムスタンプを付けて返す
        segments = []
        if hasattr(transcript, "segments") and transcript.segments:
            for seg in transcript.segments:
                minutes = int(seg.start // 60)
                seconds = int(seg.start % 60)
                segments.append({
                    "timestamp": f"{minutes:02d}:{seconds:02d}",
                    "text": seg.text.strip(),
                })
        return jsonify({
            "text": transcript.text,
            "segments": segments,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    import webbrowser
    import threading

    def open_browser():
        import time
        time.sleep(1)
        webbrowser.open("http://localhost:5000")

    threading.Thread(target=open_browser, daemon=True).start()
    print("=" * 50)
    print("  無限文字起こし アプリを起動しました")
    print("  ブラウザが自動で開きます")
    print("  終了するには Ctrl+C を押してください")
    print("=" * 50)
    app.run(debug=False, port=5000)
