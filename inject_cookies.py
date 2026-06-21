#!/usr/bin/env python3
"""Inject Skool cookies into Chromium profile's SQLite Cookies DB."""
import sqlite3, time

COOKIE_DB = "/opt/homelab/skool-dl/skool-chrome-profile/Default/Cookies"

def unix_to_chromium(ts):
    return int(ts * 1000000) + 11644473600000000

COOKIES = [
    { "host": ".skool.com",    "name": "client_id",      "val": "7c796142aca54416a2ce346bbc05dd24", "exp": 1811157285, "sec": 1, "http": 1 },
    { "host": ".www.skool.com", "name": "__stripe_mid",   "val": "b1371b32-c484-4d24-a14b-01e59b88db91b9a5ff", "exp": 1811157379, "sec": 1, "http": 1 },
    { "host": ".www.skool.com", "name": "__stripe_sid",   "val": "ce54084f-8936-49a5-a5bb-25d88b74d4344bc719", "exp": 1779623179, "sec": 1, "http": 1 },
    { "host": ".skool.com",    "name": "auth_token",     "val": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE4MTExNTczNzEsImlhdCI6MTc3OTYyMTM3MSwidXNlcl9pZCI6IjdkZmVmNDNiMmNjNzQyOTRiODU3YzBmNjdkZTFhNzA4In0.dxrmHEtpe0A6mP2jCm5_IRziCBLtr_o-irvQOS-rBe0", "exp": 1811157375, "sec": 1, "http": 1 },
    { "host": ".skool.com",    "name": "aws-waf-token",   "val": "f1bfd592-7a0e-4a36-bfc2-9768d75df65e:DgoAuk1Om9QRAAAA:CY+aYxYWaYAccsT1Ilq81dd1P16g8TS3cdI98QXO+bL0pwqCiLrGb70c1OreDJElOGXdDLPtp9mCcDpj8ynXftaj265/R97hKYrCnv4GNuyo9G7DpnVVcUtmQrh3ZQB59ihO7l7HXERVVVMrWYaU/O8FAt9aRTaZZwylDdMcJq2RftjE63pguVgHI98=", "exp": 1779966973, "sec": 1, "http": 1 },
    { "host": ".www.skool.com", "name": "AWSALBTG",        "val": "IcBpY1JGeumhiuGn02IxgWTMSknzZtmMjnA31NLobo2bPH++G98Cihjrm8KML/vmdW1/OyoabwEQzl+7zWl+pKMV050S9+m1juy/A8TF6GMj+jnNvL+PdrPs6fCvXkVESA4ShizJTSsMpd5hPkfxSirgxR3dleag9oz3yfWWBdWI0w9feM4=", "exp": 1780226174, "sec": 0, "http": 0 },
    { "host": ".www.skool.com", "name": "AWSALBTGCORS",   "val": "IcBpY1JGeumhiuGn02IxgWTMSknzZtmMjnA31NLobo2bPH++G98Cihjrm8KML/vmdW1/OyoabwEQzl+7zWl+pKMV050S9+m1juy/A8TF6GMj+jnNvL+PdrPs6fCvXkVESA4ShizJTSsMpd5hPkfxSirgxR3dleag9oz3yfWWBdWI0w9feM4=", "exp": 1780226174, "sec": 1, "http": 0 },
    { "host": ".www.skool.com", "name": "AWSALB",          "val": "ox6bvfKOfn+Z/jFqvK87aoSGZ+iyWY6IKOWcyvSp6hhIY1H5r81fwt8+6v65u4gJSH2NqyNEuyR8NmBWbNKAXvXt2qg755phejem6SbU8ZMjZ36qpEOTUNzvX1wi", "exp": 1780226174, "sec": 0, "http": 0 },
    { "host": ".www.skool.com", "name": "AWSALBCORS",     "val": "ox6bvfKOfn+Z/jFqvK87aoSGZ+iyWY6IKOWcyvSp6hhIY1H5r81fwt8+6v65u4gJSH2NqyNEuyR8NmBWbNKAXvXt2qg755phejem6SbU8ZMjZ36qpEOTUNzvX1wi", "exp": 1780226174, "sec": 1, "http": 0 },
]

now_chromium = int(time.time() * 1000000) + 11644473600000000

conn = sqlite3.connect(COOKIE_DB)
conn.execute("DELETE FROM cookies WHERE host_key LIKE '%skool.com%'")

seen = set()
for c in COOKIES:
    key = (c["host"], c["name"])
    if key in seen:
        continue
    seen.add(key)
    exp = unix_to_chromium(c["exp"])
    conn.execute("""
        INSERT OR REPLACE INTO cookies
        (creation_utc, host_key, top_frame_site_key, name, value, encrypted_value,
         path, expires_utc, is_secure, is_httponly, last_access_utc, has_expires,
         is_persistent, priority, samesite, source_scheme, source_port,
         last_update_utc, source_type, has_cross_site_ancestor)
        VALUES (?, ?, ?, ?, ?, '',
                '/', ?, ?, ?,
                ?, 1, 1, 1, 1, 2, 443,
                ?, 0, 0)
    """, (now_chromium, c["host"], c["host"], c["name"], c["val"],
          exp, c["sec"], c["http"],
          now_chromium, now_chromium))

conn.commit()
conn.close()
print(f"Cookies injected: {len(seen)} skool.com cookies")
