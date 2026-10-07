"""Yalnızca kişisel sitenin bağlantı dosyasını GitHub Contents API ile günceller."""
import base64
import json
import os
from pathlib import Path
import re
import ssl
import certifi
import urllib.error
import urllib.request

TOKEN_FILE = Path(__file__).resolve().parents[1] / ".demo" / "github-site-token"
API = "https://api.github.com/repos/mahmutkoc1/mahmutkoc-site/contents/project-link.js"
ASSIGNMENT = re.compile(r"(?m)^(\s*link\.href\s*=\s*)(['\"])([^'\"\r\n]+)\2(\s*;)")


def replace_link(source, address):
    if address.rstrip('/') != "https://arsiv.mahmutkoc.me" and not re.fullmatch(r"https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com/?", address):
        raise ValueError("Geçersiz paylaşım adresi.")
    if len(ASSIGNMENT.findall(source)) != 1:
        raise ValueError("Bağlantı dosyasının yapısı değişmiş; otomatik güncelleme yapılmadı.")
    return ASSIGNMENT.sub(lambda m: m[1] + m[2] + address.rstrip('/') + '/' + m[2] + m[4], source)


def save_token(token):
    TOKEN_FILE.parent.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(token.strip())


def request(method, token, payload=None):
    url = API + ("?ref=main" if method == "GET" else "")
    req = urllib.request.Request(url, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "User-Agent": "arsiv-site-link"})
    with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context(cafile=certifi.where())) as response:
        return json.load(response)


def update_site_link(address):
    try:
        token = TOKEN_FILE.read_text().strip()
    except OSError:
        return False, "GitHub yetkisi eksik. Masaüstündeki ‘Site Bağlantısını Yetkilendir’ dosyasını bir kez çalıştırın."
    if not token:
        return False, "GitHub erişim anahtarı boş; yeniden yetkilendirin."
    try:
        # Güncel dosyayı ve SHA'yı okur; başka dosyalara veya değişikliklere dokunmaz.
        for attempt in range(2):
            current = request("GET", token)
            original = base64.b64decode(current["content"]).decode("utf-8")
            updated = replace_link(original, address)
            if updated == original:
                return True, "GitHub bağlantısı zaten güncel."
            try:
                request("PUT", token, {"message": "Update archive presentation link",
                    "branch": "main", "sha": current["sha"],
                    "content": base64.b64encode(updated.encode()).decode()})
                return True, "GitHub bağlantısı güncellendi. Pages yayını birkaç dakika sürebilir; gerekirse siteyi zorla yenileyin."
            except urllib.error.HTTPError as error:
                if error.code == 409 and attempt == 0:
                    continue
                raise
    except urllib.error.HTTPError as error:
        return False, f"GitHub güncellenemedi (HTTP {error.code}). Hesap, anahtar süresi ve depo yazma iznini kontrol edin."
    except (OSError, ValueError, KeyError):
        return False, "Site bağlantısı güncellenemedi. Ağ bağlantısını ve project-link.js dosyasını kontrol edin."
    return False, "Site güncellemesi tamamlanamadı."
