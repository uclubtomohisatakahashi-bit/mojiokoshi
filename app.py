import os
import tempfile
import math
from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI

app = Flask(__name__, static_folder=".")

# 10分ごとにチャンク分割（ミリ秒）
CHUNK_DURATION_MS = 10 * 60 * 1000
# チャンク書き出し時のビットレート（低くすることでファイルサイズを削減）
CHUNK_BITRATE = "64k"


def transcribe_audio(file_path: str, client: OpenAI, language: str = "ja") -> tuple[str, list]:
    """音声ファイルを文字起こし。25MB超えの場合は自動でチャンク分割する。"""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(file_path)
    except Exception as e:
        return "", [], f"音声ファイルの読み込みに失敗しました: {str(e)}"

    duration_ms = len(audio)
    total_chunks = math.ceil(duration_ms / CHUNK_DURATION_MS)

    full_text = ""
    all_segments = []

    for i in range(total_chunks):
        start_ms = i * CHUNK_DURATION_MS
        end_ms = min(start_ms + CHUNK_DURATION_MS, duration_ms)
        chunk = audio[start_ms:end_ms]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            chunk.export(tmp.name, format="mp3", bitrate=CHUNK_BITRATE)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language=language,
                    response_format="verbose_json",
                )

            full_text += transcript.text.strip() + " "

            if hasattr(transcript, "segments") and transcript.segments:
                offset_sec = start_ms / 1000
                for seg in transcript.segments:
                    actual_sec = seg.start + offset_sec
                    minutes = int(actual_sec // 60)
                    seconds = int(actual_sec % 60)
                    all_segments.append({
                        "timestamp": f"{minutes:02d}:{seconds:02d}",
                        "text": seg.text.strip(),
                    })
        except Exception as e:
            return "", [], f"チャンク{i + 1}/{total_chunks} の文字起こしに失敗しました: {str(e)}"
        finally:
            os.unlink(tmp_path)

    return full_text.strip(), all_segments, None


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

    ext = os.path.splitext(audio_file.filename)[1].lower() or ".mp3"
    client = OpenAI(api_key=api_key)

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        audio_file.save(tmp.name)
        tmp_path = tmp.name

    try:
        text, segments, error = transcribe_audio(tmp_path, client, language)
        if error:
            return jsonify({"error": error}), 500
        return jsonify({"text": text, "segments": segments})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    is_local = os.environ.get("RAILWAY_ENVIRONMENT") is None

    if is_local:
        import webbrowser, threading
        threading.Thread(
            target=lambda: __import__("time").sleep(1) or webbrowser.open(f"http://localhost:{port}"),
            daemon=True
        ).start()
        print("=" * 50)
        print("  女性面接用文字起こし を起動しました")
        print(f"  http://localhost:{port}")
        print("  終了: Ctrl+C")
        print("=" * 50)

    app.run(host="0.0.0.0", port=port, debug=False)
