#!/usr/bin/env python3
"""
Batch MP4 → Groq Whisper transcription.
v5: [END_TRANSCRIPT] marker, detects partial/truncated transcripts from v3.
"""
import os, sys, json, subprocess, tempfile, time, urllib.request, urllib.error, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API_KEY = os.environ.get("GROQ_API_KEY", "")
API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = "whisper-large-v3-turbo"
LANGUAGE = "tr"
CHUNK_SEC = 480
OVERLAP_SEC = 5
SAFE_BYTES = 9 * 1024 * 1024
MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]
MAX_CONCURRENT = 3
END_MARKER = "[END_TRANSCRIPT]"

def find_mp4_files(root_dir):
    return sorted(Path(root_dir).rglob("*.mp4"))

def extract_audio_flac(mp4_path, flac_path):
    r = subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(mp4_path),
        "-vn","-ar","16000","-ac","1","-c:a","flac","-compression_level","0",str(flac_path)],
        capture_output=True,text=True,timeout=600)
    return r.returncode == 0 and flac_path.exists() and flac_path.stat().st_size > 0

def probe_duration(audio_path):
    try:
        r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
            "-of","default=nw=1:nk=1",str(audio_path)],capture_output=True,text=True,timeout=30)
        return float(r.stdout.strip())
    except: return None

def slice_flac(src, dst, start, duration):
    subprocess.run(["ffmpeg","-y","-loglevel","error",
        "-ss",f"{start:.3f}","-t",f"{duration:.3f}","-i",str(src),
        "-ar","16000","-ac","1","-c:a","flac","-compression_level","0",str(dst)],
        capture_output=True,timeout=300,check=True)

def chunk_windows(total_dur, chunk_sec, overlap):
    if total_dur <= chunk_sec: return [(0.0, total_dur)]
    stride = max(chunk_sec - overlap, 1)
    windows = []; start = 0.0
    while start < total_dur:
        length = min(float(chunk_sec), total_dur - start)
        windows.append((start, length))
        if start + length >= total_dur: break
        start += stride
    return windows

def upload_chunk(chunk_path, idx, total):
    boundary = f"----vt-{uuid.uuid4().hex}"
    body = b""
    for k,v in [("model",MODEL),("language",LANGUAGE),("response_format","verbose_json")]:
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"chunk.flac\"\r\nContent-Type: audio/flac\r\n\r\n".encode()
    body += chunk_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()

    last_err = None
    for attempt in range(1, MAX_RETRIES + 2):
        req = urllib.request.Request(API_URL, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {API_KEY}")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "samet-voice-transcriber/1.0")
        try:
            resp = urllib.request.urlopen(req, timeout=300)
            data = json.loads(resp.read().decode())
            text = (data.get("text") or "").strip()
            if not text: raise Exception("Empty")
            return data, None
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if e.code == 413: return None, "HTTP413"
            if e.code in (429,500,502,503): last_err = f"HTTP{e.code}"; pass
            else: return None, f"HTTP{e.code}:{body}"
        except Exception as e: last_err = str(e)[:80]
        if attempt <= MAX_RETRIES:
            time.sleep(RETRY_DELAYS[min(attempt-1,len(RETRY_DELAYS)-1)])
        else: return None, last_err
    return None, last_err

def stitch(responses, offsets, overlap):
    if len(responses) == 1: return responses[0].get("text","").strip()
    parts = []
    for i, (resp, offset) in enumerate(zip(responses, offsets)):
        segs = resp.get("segments") or []
        kept = segs if i == 0 else [s for s in segs if float(s.get("start",0) or 0) >= overlap]
        text = " ".join(str(s.get("text","")).strip() for s in kept).strip()
        if text: parts.append(text)
    return " ".join(parts)

def transcribe_video(mp4_path, work_dir):
    flac_path = work_dir / f"{mp4_path.stem}.flac"
    if not extract_audio_flac(mp4_path, flac_path): return None
    flac_size = flac_path.stat().st_size
    duration = probe_duration(flac_path)
    if flac_size <= SAFE_BYTES or not duration:
        resp, err = upload_chunk(flac_path, 0, 1)
        flac_path.unlink(missing_ok=True)
        if err: return None
        return resp.get("text","").strip()

    windows = chunk_windows(duration, CHUNK_SEC, OVERLAP_SEC)
    chunk_files = []
    for i, (start, length) in enumerate(windows):
        cp = work_dir / f"{mp4_path.stem}.chunk_{i:03d}.flac"
        slice_flac(flac_path, cp, start, length)
        chunk_files.append((cp, start, length))
    flac_path.unlink(missing_ok=True)

    futures = {}
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as pool:
        for i, (cp, start, length) in enumerate(chunk_files):
            futures[pool.submit(upload_chunk, cp, i, len(chunk_files))] = i
        results = [None] * len(chunk_files)
        for f in as_completed(futures):
            i = futures[f]
            resp, err = f.result()
            if err:
                for cp, _, _ in chunk_files: cp.unlink(missing_ok=True)
                return None
            results[i] = resp

    for cp, _, _ in chunk_files: cp.unlink(missing_ok=True)
    offsets = [w[1] for w in windows[:len(results)]]
    if not all(results): return None
    return stitch(results, offsets, OVERLAP_SEC)

def is_complete(txt_path):
    """Check if transcript has END_MARKER at the end (last 100 bytes)."""
    if not txt_path.exists(): return False
    try:
        with txt_path.open("rb") as f:
            size = f.seek(0, 2)
            if size < 20: return False  # too small, definitely incomplete
            f.seek(max(0, size - 100))
            tail = f.read().decode("utf-8", errors="ignore")
            return END_MARKER in tail
    except: return False

def main():
    if len(sys.argv) < 2: print(f"Usage: {sys.argv[0]} /path"); sys.exit(1)
    root = Path(sys.argv[1])
    mp4_files = find_mp4_files(root)
    total = len(mp4_files)
    print(f"Found {total} MP4 in {root}")

    done = skipped = failed = incomplete = 0
    for i, mp4 in enumerate(mp4_files, 1):
        txt_path = mp4.with_suffix(mp4.suffix + "-transcript.txt")
        if txt_path.exists() and is_complete(txt_path):
            skipped += 1
            continue
        if txt_path.exists():
            incomplete += 1
            print(f"[{i}/{total}] ⚠️  PARTIAL → retry {mp4.name}")

        print(f"[{i}/{total}] 🔄 {mp4.name} ...", end=" ", flush=True)
        with tempfile.TemporaryDirectory() as tmp:
            try:
                text = transcribe_video(mp4, Path(tmp))
                if text is None:
                    print("❌ FAIL"); failed += 1; continue
                txt_path.write_text(text + "\n" + END_MARKER + "\n", encoding="utf-8")
                done += 1
                print(f"✅ {len(text)}c")
            except Exception as e:
                print(f"❌ {e}")
                failed += 1
    print(f"\nDone:{done} Skip:{skipped} Failed:{failed} Recovered:{incomplete} Total:{total}")

if __name__ == "__main__":
    main()
