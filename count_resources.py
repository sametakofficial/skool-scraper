#!/opt/homelab/skool-dl/.venv/bin/python
#!/usr/bin/env python3
import json, re, time
from playwright.sync_api import sync_playwright

COOKIES = [
    {"name":"client_id","value":"7c796142aca54416a2ce346bbc05dd24","domain":".skool.com","path":"/","secure":True,"httpOnly":True,"expires":1811157285,"sameSite":"Lax"},
    {"name":"auth_token","value":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE4MTExNTczNzEsImlhdCI6MTc3OTYyMTM3MSwidXNlcl9pZCI6IjdkZmVmNDNiMmNjNzQyOTRiODU3YzBmNjdkZTFhNzA4In0.dxrmHEtpe0A6mP2jCm5_IRziCBLtr_o-irvQOS-rBe0","domain":".skool.com","path":"/","secure":True,"httpOnly":True,"expires":1811157375,"sameSite":"Lax"},
    {"name":"aws-waf-token","value":"f1bfd592-7a0e-4a36-bfc2-9768d75df65e:DgoAuk1Om9QRAAAA:CY+aYxYWaYAccsT1Ilq81dd1P16g8TS3cdI98QXO+bL0pwqCiLrGb70c1OreDJElOGXdDLPtp9mCcDpj8ynXftaj265/R97hKYrCnv4GNuyo9G7DpnVVcUtmQrh3ZQB59ihO7l7HXERVVVMrWYaU/O8FAt9aRTaZZwylDdMcJq2RftjE63pguVgHI98=","domain":".skool.com","path":"/","secure":True,"httpOnly":True,"expires":1779966973,"sameSite":"Lax"},
    {"name":"__stripe_mid","value":"b1371b32-c484-4d24-a14b-01e59b88db91b9a5ff","domain":".www.skool.com","path":"/","secure":True,"httpOnly":True,"expires":1811157379,"sameSite":"Lax"},
    {"name":"__stripe_sid","value":"ce54084f-8936-49a5-a5bb-25d88b74d4344bc719","domain":".www.skool.com","path":"/","secure":True,"httpOnly":True,"expires":1779623179,"sameSite":"Lax"},
    {"name":"AWSALBTG","value":"IcBpY1JGeumhiuGn02IxgWTMSknzZtmMjnA31NLobo2bPH++G98Cihjrm8KML/vmdW1/OyoabwEQzl+7zWl+pKMV050S9+m1juy/A8TF6GMj+jnNvL+PdrPs6fCvXkVESA4ShizJTSsMpd5hPkfxSirgxR3dleag9oz3yfWWBdWI0w9feM4=","domain":".www.skool.com","path":"/","secure":False,"httpOnly":False,"expires":1780226174,"sameSite":"Lax"},
    {"name":"AWSALBTGCORS","value":"IcBpY1JGeumhiuGn02IxgWTMSknzZtmMjnA31NLobo2bPH++G98Cihjrm8KML/vmdW1/OyoabwEQzl+7zWl+pKMV050S9+m1juy/A8TF6GMj+jnNvL+PdrPs6fCvXkVESA4ShizJTSsMpd5hPkfxSirgxR3dleag9oz3yfWWBdWI0w9feM4=","domain":".www.skool.com","path":"/","secure":True,"httpOnly":False,"expires":1780226174,"sameSite":"Lax"},
    {"name":"AWSALB","value":"ox6bvfKOfn+Z/jFqvK87aoSGZ+iyWY6IKOWcyvSp6hhIY1H5r81fwt8+6v65u4gJSH2NqyNEuyR8NmBWbNKAXvXt2qg755phejem6SbU8ZMjZ36qpEOTUNzvX1wi","domain":".www.skool.com","path":"/","secure":False,"httpOnly":False,"expires":1780226174,"sameSite":"Lax"},
    {"name":"AWSALBCORS","value":"ox6bvfKOfn+Z/jFqvK87aoSGZ+iyWY6IKOWcyvSp6hhIY1H5r81fwt8+6v65u4gJSH2NqyNEuyR8NmBWbNKAXvXt2qg755phejem6SbU8ZMjZ36qpEOTUNzvX1wi","domain":".www.skool.com","path":"/","secure":True,"httpOnly":False,"expires":1780226174,"sameSite":"Lax"},
]

group = "is-guc-yapayzeka"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        "/opt/homelab/skool-dl/skool-chrome-profile",
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx.add_cookies(COOKIES)
    page = ctx.new_page()

    page.goto(f"https://www.skool.com/{group}/classroom", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("#__NEXT_DATA__", state="attached", timeout=15000)

    courses = page.evaluate("""() => {
        const data = JSON.parse(document.getElementById('__NEXT_DATA__').textContent);
        return data.props.pageProps.renderData.allCourses
            .filter(c => c.metadata?.hasAccess === 1)
            .map(c => ({name: c.name, title: c.metadata.title, numModules: c.metadata.numModules}));
    }""")

    total_videos = 0
    total_pdfs = 0
    total_descs = 0

    for ci, c in enumerate(courses, 1):
        print(f"\n--- [{ci}/{len(courses)}] {c['title']} ---")

        page.goto(f"https://www.skool.com/{group}/classroom/{c['name']}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#__NEXT_DATA__", state="attached", timeout=15000)

        mods = page.evaluate("""() => {
            const data = JSON.parse(document.getElementById('__NEXT_DATA__').textContent);
            const tree = data.props.pageProps.renderData.course;
            const results = [];
            function walk(node, path) {
                const info = node.course || {};
                const meta = info.metadata || {};
                const ut = info.unitType || '';
                if (ut === 'module') {
                    results.push({
                        title: meta.title || '',
                        section: path.length ? path[path.length-1] : '',
                        videoId: meta.videoId || '',
                        desc: meta.desc || '',
                        resources: meta.resources || '[]',
                    });
                }
                const children = node.children || [];
                const nextPath = ut === 'set' ? [...path, meta.title || info.name || ''] : path;
                children.forEach(ch => walk(ch, nextPath));
            }
            walk(tree, []);
            return results;
        }""")

        n_videos = 0
        n_pdfs = 0
        n_descs = 0

        for m in mods:
            if m.get('videoId'):
                n_videos += 1
            if (m.get('desc') or '').strip():
                n_descs += 1
            try:
                resources = json.loads(m['resources']) if isinstance(m['resources'], str) else m.get('resources', [])
                if isinstance(resources, list):
                    n_pdfs += len(resources)
            except:
                pass

        print(f"  Modules: {len(mods)} | Videos: {n_videos} | Descriptions: {n_descs} | PDF/Resources: {n_pdfs}")
        total_videos += n_videos
        total_pdfs += n_pdfs
        total_descs += n_descs

        time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"TOPLAM:")
    print(f"   Kurs:     {len(courses)}")
    print(f"   Video:    {total_videos}")
    print(f"   Yazı:     {total_descs}")
    print(f"   PDF/Ek:   {total_pdfs}")
    print(f"{'='*60}")

    ctx.close()
