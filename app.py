import os
import tempfile
import math
import json
import subprocess
from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI

app = Flask(__name__, static_folder=".")

# サーバー側のAPIキー（Railway環境変数 OPENAI_API_KEY）
SERVER_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# 1チャンクの長さ（秒）
CHUNK_DURATION_SEC = 10 * 60  # 10分


def has_ffmpeg() -> bool:
    """ffmpegとffprobeが使えるか確認"""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def get_audio_duration(file_path: str) -> float:
    """ffprobeで音声の長さ（秒）を取得"""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", file_path],
        capture_output=True, text=True
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def split_audio_ffmpeg(file_path: str, duration: float) -> list:
    """ffmpegで音声を10分ごとに分割。チャンクファイルパスと開始秒のリストを返す"""
    chunks = []
    total_chunks = math.ceil(duration / CHUNK_DURATION_SEC)

    for i in range(total_chunks):
        start_sec = i * CHUNK_DURATION_SEC
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            chunk_path = tmp.name

        subprocess.run([
            "ffmpeg", "-y",
            "-i", file_path,
            "-ss", str(start_sec),
            "-t", str(CHUNK_DURATION_SEC),
            "-acodec", "mp3",
            "-ab", "64k",
            chunk_path
        ], capture_output=True)

        chunks.append((chunk_path, start_sec))

    return chunks


def transcribe_audio(file_path: str, client: OpenAI, language: str = "ja") -> tuple:
    """音声ファイルを文字起こし。長時間ファイルはffmpegで自動チャンク分割する。"""
    # ffmpegがない環境（ローカルWindowsなど）はそのままWhisperに送る
    if not has_ffmpeg():
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 24:
            return "", [], (
                f"ファイルサイズが {file_size_mb:.1f}MB です。"
                "25MB を超えるファイルを分割するには ffmpeg が必要です。"
                "Railwayサーバーをご利用ください。"
            )
        try:
            with open(file_path, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language=language,
                    response_format="verbose_json",
                )
            segments = []
            if hasattr(transcript, "segments") and transcript.segments:
                for seg in transcript.segments:
                    minutes = int(seg.start // 60)
                    seconds = int(seg.start % 60)
                    segments.append({
                        "timestamp": f"{minutes:02d}:{seconds:02d}",
                        "text": seg.text.strip(),
                    })
            return transcript.text, segments, None
        except Exception as e:
            return "", [], f"文字起こしに失敗しました: {str(e)}"

    try:
        duration = get_audio_duration(file_path)
    except Exception as e:
        return "", [], f"音声ファイルの読み込みに失敗しました: {str(e)}"

    chunks = split_audio_ffmpeg(file_path, duration)
    full_text = ""
    all_segments = []

    for chunk_path, offset_sec in chunks:
        try:
            with open(chunk_path, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language=language,
                    response_format="verbose_json",
                )

            full_text += transcript.text.strip() + " "

            if hasattr(transcript, "segments") and transcript.segments:
                for seg in transcript.segments:
                    actual_sec = seg.start + offset_sec
                    minutes = int(actual_sec // 60)
                    seconds = int(actual_sec % 60)
                    all_segments.append({
                        "timestamp": f"{minutes:02d}:{seconds:02d}",
                        "text": seg.text.strip(),
                    })
        except Exception as e:
            return "", [], f"文字起こしに失敗しました: {str(e)}"
        finally:
            os.unlink(chunk_path)

    return full_text.strip(), all_segments, None


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api-key-status")
def api_key_status():
    """サーバー側にAPIキーが設定されているか返す"""
    return jsonify({"has_server_key": bool(SERVER_API_KEY)})


@app.route("/transcribe", methods=["POST"])
def transcribe():
    # サーバー側のキーを優先、なければフォームから取得
    api_key = SERVER_API_KEY or request.form.get("api_key", "").strip()
    audio_file = request.files.get("audio")
    language = request.form.get("language", "ja")

    if not api_key:
        return jsonify({"error": "APIキーが設定されていません。管理者にお問い合わせください。"}), 400
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
