#!/usr/bin/env python3
"""Transcribe all MP4 files under a folder using Groq Whisper API."""
import os, sys, json, subprocess, tempfile, time, urllib.request, urllib.error, uuid
from pathlib import Path

API_KEY = os.environ.get("GROQ_API_KEY", "")
API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = "whisper-large-v3-turbo"
LANGUAGE = "tr"
DELAY = 2

def find_mp4_files(root_dir):
    return sorted(Path(root_dir).rglob("*.mp4"))

def extract_audio(mp4_path, audio_path):
    r = subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(mp4_path),
        "-ar","16000","-ac","1","-c:a","flac","-compression_level","8",str(audio_path)],
        capture_output=True,text=True,timeout=300)
    return r.returncode==0 and audio_path.exists() and audio_path.stat().st_size>0

def transcribe(audio_path):
    boundary = f"----voice-transcriber-{uuid.uuid4().hex}"
    fields = {"model":MODEL,"language":LANGUAGE,"response_format":"text"}
    parts = []
    for k,v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{audio_path.name}\"\r\nContent-Type: audio/flac\r\n\r\n".encode())
    parts.append(audio_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(API_URL, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Accept", "text/plain")
    req.add_header("User-Agent", "samet-voice-transcriber/1.0")
    try:
        resp = urllib.request.urlopen(req, timeout=300)
        return resp.read().decode("utf-8").strip(), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)[:200]

def main():
    if len(sys.argv) < 2:
        print("Usage: transcribe_v2.py /path/to/folder")
        sys.exit(1)
    root = Path(sys.argv[1])
    mp4_files = find_mp4_files(root)
    total = len(mp4_files)
    print(f"Found {total} MP4 files\n")
    done = skipped = failed = 0
    for i, mp4 in enumerate(mp4_files, 1):
        txt_path = mp4.with_suffix(mp4.suffix + "-transcript.txt")
        if txt_path.exists():
            skipped += 1
            print(f"[{i}/{total}] SKIP {mp4.name}")
            continue
        print(f"[{i}/{total}] {mp4.name} ...", end=" ", flush=True)
        with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as tmp:
            audio_path = Path(tmp.name)
        try:
            if not extract_audio(mp4, audio_path):
                print("FAIL audio")
                failed += 1; continue
            text, err = transcribe(audio_path)
            if err:
                print(f"FAIL {err}")
                failed += 1; continue
            txt_path.write_text(text, encoding="utf-8")
            done += 1
            print(f"OK ({len(text)} chars)")
            time.sleep(DELAY)
        finally:
            if audio_path.exists(): audio_path.unlink()
    print(f"\nDone:{done} Skip:{skipped} Fail:{failed}")
if __name__=="__main__": main()
