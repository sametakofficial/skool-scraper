#!/usr/bin/env python3
"""Use Playwright to inject cookies and verify login."""
import sys, time, json
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

profile_dir = "/opt/homelab/skool-dl/skool-chrome-profile"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        profile_dir,
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    
    # Add cookies BEFORE any navigation
    ctx.add_cookies(COOKIES)
    print(f"✅ {len(COOKIES)} cookies added to context")
    
    page = ctx.new_page()
    print("🌐 Navigating to skool.com...")
    
    try:
        page.goto("https://www.skool.com/is-guc-yapayzeka/classroom", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#__NEXT_DATA__", state="attached", timeout=15000)
        
        # Check login
        logged_in = page.evaluate("""() => {
            try {
                const el = document.getElementById('__NEXT_DATA__');
                if (!el) return false;
                const data = JSON.parse(el.textContent);
                return Array.isArray(data?.props?.pageProps?.renderData?.allCourses);
            } catch(e) { return false; }
        }""")
        
        print(f"🔐 Login check: {logged_in}")
        
        if logged_in:
            courses = page.evaluate("""() => {
                const data = JSON.parse(document.getElementById('__NEXT_DATA__').textContent);
                const courses = data.props.pageProps.renderData.allCourses
                    .filter(c => c.metadata?.hasAccess === 1)
                    .map(c => ({
                        id: c.id,
                        name: c.name,
                        title: c.metadata.title,
                        numModules: c.metadata.numModules
                    }));
                return courses;
            }""")
            
            print(f"\n📊 Found {len(courses)} courses:")
            for i, c in enumerate(courses, 1):
                print(f"  {i:2d}. {c['title']} ({c['numModules']} lessons)")
            
            # For each course, count videos
            print(f"\n📹 Fetching video counts per course...")
            for ci, c in enumerate(courses, 1):
                try:
                    course_url = f"https://www.skool.com/is-guc-yapayzeka/classroom/{c['name']}"
                    page.goto(course_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_selector("#__NEXT_DATA__", state="attached", timeout=15000)
                    
                    lessons = page.evaluate("""() => {
                        const data = JSON.parse(document.getElementById('__NEXT_DATA__').textContent);
                        const tree = data.props.pageProps.renderData.course;
                        const results = [];
                        function walk(node) {
                            const info = node.course || {};
                            const meta = info.metadata || {};
                            if (info.unitType === 'module' && meta.videoId) {
                                results.push({title: meta.title, videoId: meta.videoId});
                            }
                            if (info.unitType === 'module' && meta.desc) {
                                results.push({title: meta.title, hasDesc: true});
                            }
                            (node.children || []).forEach(walk);
                        }
                        walk(tree);
                        return results;
                    }""")
                    
                    video_count = len([l for l in lessons if l.get('videoId')])
                    desc_count = len([l for l in lessons if l.get('hasDesc')])
                    
                    print(f"  [{ci}/{len(courses)}] {c['title']}: {video_count} videos, {desc_count} descriptions, {len(lessons)} total modules")
                    time.sleep(0.5)
                except Exception as e:
                    print(f"  [{ci}/{len(courses)}] {c['title']}: ERROR - {e}")
        else:
            # Show what we got
            try:
                raw = page.evaluate("""() => {
                    const el = document.getElementById('__NEXT_DATA__');
                    return el ? el.textContent.slice(0, 500) : 'NO __NEXT_DATA__';
                }""")
                print(f"\n📄 Raw NEXT_DATA (first 500):\n{raw}")
            except Exception as e:
                print(f"Error reading data: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    ctx.close()

print("\nDone!")
