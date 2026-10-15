"""Sunucuda yeni parola oluşturur; mevcut parolayı asla üzerine yazmaz."""
import getpass
import os
from pathlib import Path

root = Path(__file__).resolve().parents[2]
password = getpass.getpass("Yeni arşiv şifresi (en az 16 karakter): ")
if len(password.strip()) < 16 or password != password.strip():
    raise SystemExit("En az 16 karakter kullanın; başta/sonda boşluk bırakmayın.")
if password != getpass.getpass("Şifre tekrar: "):
    raise SystemExit("Şifreler eşleşmedi.")
directory = root / ".demo"
directory.mkdir(mode=0o700, exist_ok=True)
with os.fdopen(os.open(directory / "password.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
    handle.write(password + "\n")
print("Yeni sunucu şifresi kaydedildi.")
