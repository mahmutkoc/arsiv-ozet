# Yedekleme ve geri yükleme listesi

## Özel yedeğe alınacaklar

- Proje: tüm Python kodu, `core/`, `tests/`, CSS, logo, `.streamlit/` ve belgeler.
- `data/`: SQLite arşivi ve kaynak belge klasörleri. Çalışan veritabanı düz dosya
  kopyasıyla değil, SQLite backup API ile tutarlı anlık görüntü alınarak saklanır.
- `cikti/`: üretilmiş çıktılar ve model not önbelleği.
- `modeller/`: Gemma 3 12B Q4_K_M GGUF model dosyası.
- `.mamba/`: Tesseract, dil verileri ve llama.cpp ortamı.
- `.venv/`: kurulu Python paketleri (yalnızca aynı sistem için yardımcı kopya).
- `.demo/`: uygulama parolası, Cloudflare/GitHub anahtarları ve cloudflared.
- `.git/`: yerel sürüm geçmişi; geçmişte belge görüntüleri içerdiğinden özeldir.
- Masaüstündeki üç başlatma/yetkilendirme `.command` dosyası.
- Ayrı `mahmutkoc-site` klasöründeki kişisel site dosyaları.
- Python 3.13 çalışma ortamı ve kurulu paket sürümleri envanteri.

## GitHub'a konulmayacaklar

`.demo`, `.env`, Streamlit secrets, gerçek belgeler, veritabanları, çıktılar,
modeller ve kurulu çalışma ortamları. Tam özel yedeği GitHub'a yüklemeyin.
GitHub kaynak kod yedeğidir; kayıtların ve modelin yedeği değildir.

## Geri yükleme

1. Uygulamayı kapatın. Mevcut dosyaları silmeden önce ayrı yedeğini alın.
2. Özel yedekten proje klasörünü geri kopyalayın. Mevcut Mac'teki konumu
   `/Users/mahmut/arsiv-ozet` olarak korumak mutlak yolları korur.
3. Başka bilgisayarda Python 3.13 ve README'deki bağımlılıkları yeniden kurun.
   `.venv`/`.mamba` kopyaları farklı işletim sistemi, işlemci veya yolda doğrudan
   çalışmayabilir. Python framework kopyası taşınabilir kurulum paketi değildir.
4. Modeli `modeller/`, SQLite görüntüsünü `data/arsiv.db` konumuna geri koyun.
   Özel anahtar dosyalarını yalnızca güvenilir cihazda, sadece kullanıcı okuyacak
   izinlerle geri yükleyin; sızıntı şüphesinde anahtarları yenileyin.
5. Masaüstü başlatıcılarının içindeki kullanıcı/proje yollarını kontrol edin.
   Yerelde `demo_start.py --archive`, internet paylaşımı için `share_start.py`
   kullanılır. Önce yerel giriş ve kayıtlar, sonra dış bağlantı test edilir.
6. Aynı tüneli yanlış bilgisayara yönlendirmemek için eski cihazdaki tüneli kapatın.

## Hesaplarda kalan ayarlar

Namecheap alan adı sahipliği/yenilemesi, Cloudflare DNS ve yayın rotaları,
GitHub Pages ayarları dosya yedeğiyle otomatik geri gelmez. Hesap erişimleri ve
2FA kurtarma kodları güvenli parola yöneticisinde tutulmalıdır.
Mevcut sabit uygulama rotası: `arsiv.mahmutkoc.me` → `http://127.0.0.1:8503`.
Kişisel site: `mahmutkoc.me`, GitHub Pages projesi: `mahmutkoc1/mahmutkoc-site`.
DNS sunucuları: `julian.ns.cloudflare.com`, `nicole.ns.cloudflare.com`.

Aynı diskteki kopya disk arızasına karşı korumaz. Doğrulanan yedeği ayrıca
şifreli harici diske kopyalayın. Özel yedek şifre içerir; herkese açık paylaşmayın.
