#!/usr/bin/env python3
"""
Skool Extras Downloader
=======================
Downloads PDFs (resources) and lesson descriptions for every Skool lesson.
Uses the same persistent profile as skool_download.py (cookies must already exist).

Output, alongside each video:
    downloads/Course/Section/001 - Title - {pdf_title}.pdf
    downloads/Course/Section/001 - Title.md      (description, if non-empty)
    downloads/Course/_course.md                  (course-level description)

PDFs come from: api2.skool.com/files/{file_id}/download-url → CloudFront signed URL.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


def sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', name)
    return name.strip('. ')[:200]


def prosemirror_to_markdown(raw: str) -> str:
    """Convert Skool's ProseMirror "v2" JSON format to plain markdown.
    Format is "[v2]" prefix + JSON array of nodes.
    Returns empty string if input is empty/whitespace."""
    if not raw:
        return ""
    s = raw.strip()
    if s.startswith("[v2]"):
        s = s[4:]
    try:
        nodes = json.loads(s)
    except Exception:
        return raw  # not parseable — return as-is
    if not nodes or (isinstance(nodes, list) and not any(_has_content(n) for n in nodes)):
        return ""
    return _render_nodes(nodes).strip()


def _has_content(node):
    if not isinstance(node, dict):
        return False
    if node.get("text"):
        return True
    for c in node.get("content", []) or []:
        if _has_content(c):
            return True
    return False


def _render_nodes(nodes, _depth=0):
    if not isinstance(nodes, list):
        nodes = [nodes]
    out = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        t = n.get("type", "")
        if t == "text":
            text = n.get("text", "")
            for m in n.get("marks", []):
                mt = m.get("type")
                if mt == "bold":
                    text = f"**{text}**"
                elif mt == "italic":
                    text = f"*{text}*"
                elif mt == "code":
                    text = f"`{text}`"
                elif mt == "link":
                    href = m.get("attrs", {}).get("href", "")
                    text = f"[{text}]({href})"
            out.append(text)
        elif t == "paragraph":
            inner = _render_nodes(n.get("content", []), _depth)
            out.append(inner + "\n\n")
        elif t == "heading":
            level = n.get("attrs", {}).get("level", 2)
            inner = _render_nodes(n.get("content", []), _depth)
            out.append("#" * level + " " + inner + "\n\n")
        elif t == "bulletList":
            for item in n.get("content", []) or []:
                inner = _render_nodes(item.get("content", []), _depth + 1).strip()
                out.append("  " * _depth + "- " + inner + "\n")
            out.append("\n")
        elif t == "orderedList":
            for i, item in enumerate(n.get("content", []) or [], 1):
                inner = _render_nodes(item.get("content", []), _depth + 1).strip()
                out.append("  " * _depth + f"{i}. " + inner + "\n")
            out.append("\n")
        elif t == "listItem":
            out.append(_render_nodes(n.get("content", []), _depth))
        elif t == "hardBreak":
            out.append("\n")
        elif t == "blockquote":
            inner = _render_nodes(n.get("content", []), _depth).strip()
            for line in inner.split("\n"):
                out.append("> " + line + "\n")
        else:
            # unknown node — render its content if any
            out.append(_render_nodes(n.get("content", []), _depth))
    return "".join(out)


def fetch_signed_url(page, file_id: str) -> tuple[str | None, str]:
    """Call api2.skool.com/files/{id}/download-url to get the signed CloudFront URL.
    Returns (url, error_msg). url is None on failure."""
    # Try multiple HTTP methods — Skool's API uses POST for download-url (GET → 405)
    result = page.evaluate("""async (fid) => {
        const url = `https://api2.skool.com/files/${fid}/download-url?expire=28800`;
        for (const method of ['POST', 'GET']) {
            try {
                const r = await fetch(url, {
                    method,
                    credentials: 'include',
                    headers: {'Accept': 'text/plain, application/json, */*'},
                });
                const txt = await r.text();
                if (r.ok) return {url: txt.trim(), method};
                // remember last error in case all methods fail
                if (method === 'GET') return {error: `http_${r.status} via ${method}: ${txt.slice(0,200)}`};
            } catch (e) {
                if (method === 'GET') return {error: 'fetch_err via ' + method + ': ' + e.toString()};
            }
        }
        return {error: 'no method worked'};
    }""", file_id)
    if "url" in result:
        return result["url"], ""
    return None, result.get("error", "unknown")


def download_pdf(page, signed_url: str, out_path: Path) -> bool:
    """Fetch a signed URL via the browser context and save bytes to out_path.
    Avoids using Playwright's expect_download (which needs a click trigger)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and out_path.stat().st_size > 1024:
        return True  # already downloaded
    # use page.request.get inside browser context (cookies attached)
    try:
        resp = page.request.get(signed_url)
        if resp.status != 200:
            print(f"      ❌ HTTP {resp.status}")
            return False
        out_path.write_bytes(resp.body())
        return True
    except Exception as e:
        print(f"      ❌ {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="Skool classroom URL (e.g. https://www.skool.com/GROUP/classroom)")
    ap.add_argument("--profile-dir", default="./skool-chrome-profile",
                    help="Persistent Chromium profile dir (must already have Skool login)")
    ap.add_argument("--output", "-o", default="downloads", help="Output base dir")
    ap.add_argument("--server", action="store_true", help="Headless server mode (bundled chromium)")
    ap.add_argument("--course", "-c", help="Filter to courses matching this text")
    ap.add_argument("--delay", type=float, default=0.3)
    args = ap.parse_args()

    m = re.search(r"skool\.com/([^/?#]+)", args.url)
    if not m:
        print("❌ Invalid URL")
        sys.exit(1)
    group = m.group(1)
    classroom_url = f"https://www.skool.com/{group}/classroom"
    out_root = Path(args.output)

    profile_path = Path(args.profile_dir).expanduser().resolve()
    profile_path.mkdir(parents=True, exist_ok=True)

    print("📚 Skool Extras Downloader")
    print(f"   Profile: {profile_path}")
    print(f"   Output:  {out_root.resolve()}")

    with sync_playwright() as p:
        launch_kwargs = {"args": ["--disable-blink-features=AutomationControlled"]}
        if args.server:
            launch_kwargs["headless"] = True
        else:
            launch_kwargs["channel"] = "chrome"
            launch_kwargs["headless"] = False
        ctx = p.chromium.launch_persistent_context(str(profile_path), **launch_kwargs)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # Land on classroom
        page.goto(classroom_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#__NEXT_DATA__", state="attached", timeout=15000)

        is_logged_in = page.evaluate("""() => {
            try {
                const d = JSON.parse(document.getElementById('__NEXT_DATA__').textContent);
                return Array.isArray(d?.props?.pageProps?.renderData?.allCourses);
            } catch { return false; }
        }""")
        if not is_logged_in:
            print("❌ Not logged in. Run skool_download.py first to populate cookies.")
            ctx.close()
            sys.exit(1)

        courses = page.evaluate("""() => {
            const d = JSON.parse(document.getElementById('__NEXT_DATA__').textContent);
            const rd = d.props.pageProps.renderData;
            return (rd.allCourses || [])
                .filter(c => c.metadata?.hasAccess === 1)
                .map(c => ({id: c.id, name: c.name, title: c.metadata.title,
                            desc: c.metadata?.desc || ""}));
        }""")
        if args.course:
            t = args.course.lower()
            courses = [c for c in courses if t in c["title"].lower()]
        print(f"\n📊 Processing {len(courses)} course(s)\n")

        stats = {"pdfs": 0, "mds": 0, "fail": 0}

        for ci, course in enumerate(courses, 1):
            course_dir = out_root / sanitize(course["title"])
            course_dir.mkdir(parents=True, exist_ok=True)

            # Course-level description -> _course.md
            cdesc = (course.get("desc") or "").strip()
            if cdesc:
                cmd_path = course_dir / "_course.md"
                cmd_text = f"# {course['title']}\n\n{cdesc}\n"
                if not cmd_path.exists():
                    cmd_path.write_text(cmd_text, encoding="utf-8")
                    stats["mds"] += 1

            print(f"📖 [{ci}/{len(courses)}] {course['title']}")

            # Navigate to course page to get the lesson tree
            page.goto(f"https://www.skool.com/{group}/classroom/{course['name']}",
                      wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("#__NEXT_DATA__", state="attached", timeout=15000)

            lessons = page.evaluate("""() => {
                const d = JSON.parse(document.getElementById('__NEXT_DATA__').textContent);
                const rd = d.props.pageProps.renderData;
                const out = [];
                function walk(node, path) {
                    const info = node.course || {};
                    const meta = info.metadata || {};
                    const ut = info.unitType || '';
                    if (ut === 'module') {
                        out.push({
                            moduleId: info.id,
                            title: meta.title || '',
                            section: path.length ? path[path.length - 1] : '',
                            desc: meta.desc || '',
                            resources: meta.resources || '[]',
                        });
                    }
                    const children = node.children || [];
                    const nextPath = ut === 'set' ? [...path, meta.title || info.name || ''] : path;
                    for (const c of children) walk(c, nextPath);
                }
                walk(rd.course, []);
                return out;
            }""")

            for li, lesson in enumerate(lessons, 1):
                title = sanitize(lesson["title"])
                section = sanitize(lesson["section"])
                base_dir = course_dir / section if section else course_dir
                base_dir.mkdir(parents=True, exist_ok=True)
                base_name = f"{li:03d} - {title}"

                # 1) description -> markdown
                desc_md = prosemirror_to_markdown(lesson.get("desc", ""))
                if desc_md:
                    md_path = base_dir / f"{base_name}.md"
                    if not md_path.exists():
                        md_path.write_text(f"# {lesson['title']}\n\n{desc_md}\n", encoding="utf-8")
                        stats["mds"] += 1
                        print(f"   [{li}] 📝 {lesson['title']}.md ({len(desc_md)} chars)")

                # 2) resources -> PDFs (and other files)
                try:
                    res_list = json.loads(lesson["resources"]) if isinstance(lesson["resources"], str) else lesson["resources"]
                except Exception:
                    res_list = []
                if not isinstance(res_list, list):
                    res_list = []

                for r in res_list:
                    fid = r.get("file_id")
                    if not fid:
                        continue
                    fname = r.get("file_name", "file")
                    rtitle = r.get("title", fname)
                    ext = Path(fname).suffix or ".bin"
                    safe_title = sanitize(rtitle)
                    out_path = base_dir / f"{base_name} - {safe_title}{ext}"

                    if out_path.exists() and out_path.stat().st_size > 1024:
                        continue  # skip already downloaded

                    time.sleep(args.delay)
                    signed, err = fetch_signed_url(page, fid)
                    if not signed:
                        # Retry from inside the actual lesson page (different referer/origin context)
                        lesson_url = f"https://www.skool.com/{group}/classroom/{course['name']}?md={lesson['moduleId']}"
                        try:
                            page.goto(lesson_url, wait_until="domcontentloaded", timeout=30000)
                            page.wait_for_timeout(2000)
                            signed, err = fetch_signed_url(page, fid)
                        except Exception as e:
                            err = f"{err} | retry_nav_err: {e}"
                    if not signed:
                        print(f"   [{li}] ❌ {rtitle}: {err[:200]}")
                        stats["fail"] += 1
                        continue
                    print(f"   [{li}] ⬇️  {rtitle} ({fname})")
                    if download_pdf(page, signed, out_path):
                        sz = out_path.stat().st_size / 1024 / 1024
                        print(f"      ✅ {sz:.2f} MB")
                        stats["pdfs"] += 1
                    else:
                        stats["fail"] += 1

        print(f"\n{'='*50}")
        print(f"📊 Done: {stats['pdfs']} PDFs, {stats['mds']} markdown, {stats['fail']} failed")
        print(f"   Output: {out_root.resolve()}")
        ctx.close()


if __name__ == "__main__":
    main()
