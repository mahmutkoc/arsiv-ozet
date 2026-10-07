"""Tek pencerede şifreli uygulama ve geçici paylaşım tüneli."""
import fcntl
import os
from pathlib import Path
import queue
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import ssl
import certifi
from core.site_link import update_site_link

ROOT = Path(__file__).resolve().parent
URL_PATTERN = re.compile(r"https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com")


def available_port():
    for port in range(8503, 8520):
        with socket.socket() as connection:
            try:
                connection.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("8503–8519 portları dolu. Açık uygulamaları kontrol edin.")


def main():
    private = ROOT / ".demo"
    private.mkdir(exist_ok=True, mode=0o700)
    children = []
    lock = (private / "share-launcher.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Başlatıcı zaten açık. Önceki Arşivi Başlat penceresini kullanın.")
        return

    def interrupted(*_):
        raise KeyboardInterrupt

    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, interrupted)
    try:
        token_file = private / "cloudflare-token"
        if not token_file.is_file():
            raise RuntimeError("Önce Sabit Tüneli Yetkilendir dosyasını çalıştırın.")
        port = 8503
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                raise RuntimeError("8503 portu kullanımda. Önce eski arşiv uygulamasını kapatın; sabit tünel başka porta geçemez.")
        local = f"http://127.0.0.1:{port}"
        public = "https://arsiv.mahmutkoc.me"
        print("Paylaşım hazırlanıyor… (en fazla 60 saniye)", flush=True)
        tunnel = subprocess.Popen(
            [str(private / "bin/cloudflared"), "tunnel", "--no-autoupdate", "run", "--token-file", str(token_file)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        children.append(tunnel)
        addresses = queue.Queue()

        def read_tunnel():
            with (private / "share-tunnel.log").open("w") as log:
                for line in tunnel.stdout:
                    log.write(line)
                    log.flush()
                    match = URL_PATTERN.search(line)
                    if match:
                        addresses.put(match.group())

        threading.Thread(target=read_tunnel, daemon=True).start()
        environment = dict(os.environ, ARSIV_PORT=str(port), DEMO_PUBLIC_ORIGINS=public)
        with (private / "share-app.log").open("w") as log:
            app = subprocess.Popen([sys.executable, str(ROOT / "demo_start.py"), "--archive"],
                                   cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
        children.append(app)
        for _ in range(60):
            if app.poll() is not None or tunnel.poll() is not None:
                raise RuntimeError("Başlatma başarısız. .demo klasöründeki share günlüklerini kontrol edin.")
            try:
                with urllib.request.urlopen(local + "/_stcore/health", timeout=1) as response:
                    if response.read().strip() == b"ok":
                        break
            except OSError:
                pass
            time.sleep(.5)
        else:
            raise RuntimeError("Uygulama zamanında yanıt vermedi.")
        # Yalnızca bu başlatıcının işlemlerini ve uyku önlemesini yönetir.
        children.append(subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())]))
        print(f"\nUYGULAMA HAZIR\n\nBu bilgisayarda: {local}\nPaylaşılacak adres: {public}\n", flush=True)
        print("Mevcut arşiv şifresi geçerlidir. Giriş yapanlar ortak kayıtları görebilir.\n"
              "Bu pencere açık kalsın; bilgisayarın kapağını kapatmayın.\n"
              "Durdurmak için Control + C.\n"
              "Sabit adres: https://arsiv.mahmutkoc.me — yeniden başlatınca değişmez.\n", flush=True)
        subprocess.run(["/usr/bin/open", local], check=False)
        def publish_link():
            # Tünelin dışarıdan yanıt verdiğini doğrulamadan siteye yazma.
            for _ in range(12):
                if app.poll() is not None or tunnel.poll() is not None:
                    return
                try:
                    with urllib.request.urlopen(public + "/_stcore/health", timeout=5,
                            context=ssl.create_default_context(cafile=certifi.where())) as response:
                        if response.read().strip() == b"ok":
                            print("\n✓ Sabit internet bağlantısı doğrulandı: " + public, flush=True)
                            return
                except OSError:
                    pass
                time.sleep(2)
            print("\nUYARI: Dış bağlantı henüz doğrulanamadı. Cloudflare tünel durumunu kontrol edin; sabit adres değişmedi.", flush=True)

        threading.Thread(target=publish_link, daemon=True).start()
        while app.poll() is None and tunnel.poll() is None:
            time.sleep(1)
        raise RuntimeError("Uygulama veya paylaşım bağlantısı durdu. Başlatıcıyı yeniden açın.")
    except KeyboardInterrupt:
        print("\nPaylaşım kapatılıyor…")
    except Exception as error:
        print(f"\nHata: {error}")
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        lock.close()


if __name__ == "__main__":
    main()
