"""Cloudflare connector tokenını kabuk geçmişine veya ekrana yazmadan kaydet."""
import base64
from getpass import getpass
import json
import os
from pathlib import Path
import shlex

TOKEN_FILE = Path(__file__).resolve().parent / '.demo' / 'cloudflare-token'
EXPECTED_TUNNEL = 'b2e691a6-805b-4e3e-9423-c65994f481b4'


def extract_token(value):
    for part in shlex.split(value):
        candidate = part.removeprefix('--token=')
        try:
            data = json.loads(base64.b64decode(candidate + '=' * (-len(candidate) % 4), validate=True))
        except (ValueError, UnicodeError):
            continue
        if isinstance(data, dict) and data.get('t') == EXPECTED_TUNNEL and data.get('s') and data.get('a'):
            return candidate
    raise ValueError('Bu tünele ait geçerli anahtar bulunamadı. Cloudflare komutunu yeniden kopyalayın.')


def main():
    print('Cloudflare → arsiv-uygulamasi → Add a connector → Mac\n'
          'Anahtarı içeren komutu kopyalayıp aşağıya yapıştırın.\n'
          'Komut çalıştırılmaz. Yazdıklarınız ekranda görünmez.\n')
    try:
        token = extract_token(getpass('Cloudflare komutu veya anahtarı: ').strip())
        TOKEN_FILE.parent.mkdir(mode=0o700, exist_ok=True)
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(token + '\n')
        print('Anahtar güvenli dosyaya kaydedildi. Henüz tünel başlatılmadı.')
    except (ValueError, OSError):
        print('Kaydedilemedi. arsiv-uygulamasi tüneline ait anahtarlı komutu kopyalayıp tekrar deneyin.')
    except (KeyboardInterrupt, EOFError):
        print('\nİptal edildi.')


if __name__ == '__main__':
    main()
