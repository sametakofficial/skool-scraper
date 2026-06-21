#!/opt/homelab/skool-dl/.venv/bin/python
"""Transcribe all MP4 files under a folder using Groq Whisper API."""
import os, sys, json, subprocess, tempfile, time
from pathlib import Path

API_KEY = os.environ.get("GROQ_API_KEY", "")
API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = "whisper-large-v3-turbo"
REQUEST_DELAY = 2  # seconds between API calls

def find_mp4_files(root_dir):
    return sorted(Path(root_dir).rglob("*.mp4"))

def extract_audio(mp4_path, audio_path):
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(mp4_path),
        "-vn", "-acodec", "aac", "-b:a", "64k",
        str(audio_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return result.returncode == 0 and audio_path.exists()

def transcribe(audio_path):
    import urllib.request, urllib.error
    boundary = "----GroqBoundary" + str(int(time.time()))
    audio_data = audio_path.read_bytes()
    fname = audio_path.name

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="model"\r\n\r\n'
        f"{MODEL}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="response_format"\r\n\r\n'
        f"text\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
        f"Content-Type: audio/mp4\r\n\r\n"
    ).encode() + audio_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(API_URL, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        resp = urllib.request.urlopen(req, timeout=300)
        return resp.read().decode("utf-8").strip(), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)[:200]

def main():
    if len(sys.argv) < 2:
        print("Usage: transcribe.py /path/to/download/folder")
        sys.exit(1)

    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"Not a directory: {root}")
        sys.exit(1)

    mp4_files = find_mp4_files(root)
    total = len(mp4_files)
    print(f"Found {total} MP4 files under {root}\n")

    done = 0
    skipped = 0
    failed = 0

    for i, mp4 in enumerate(mp4_files, 1):
        txt_path = mp4.with_suffix(mp4.suffix + "-transcript.txt")
        if txt_path.exists():
            skipped += 1
            print(f"[{i}/{total}] ⏭️  {mp4.name} (already transcribed)")
            continue

        print(f"[{i}/{total}] 🔄 {mp4.name} ...", end=" ", flush=True)

        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
            audio_path = Path(tmp.name)

        try:
            if not extract_audio(mp4, audio_path):
                print("❌ audio extract failed")
                failed += 1
                continue

            text, err = transcribe(audio_path)
            if err:
                print(f"❌ {err}")
                failed += 1
                continue

            txt_path.write_text(text, encoding="utf-8")
            done += 1
            chars = len(text)
            print(f"✅ {chars} chars")
            time.sleep(REQUEST_DELAY)

        except KeyboardInterrupt:
            print("\nInterrupted.")
            break
        finally:
            if audio_path.exists():
                audio_path.unlink()

    print(f"\n{'='*50}")
    print(f"Done: {done}  Skipped: {skipped}  Failed: {failed}")
    print(f"Total: {done + skipped}/{total}")

if __name__ == "__main__":
    main()
