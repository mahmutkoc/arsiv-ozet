# Ubuntu 24.04 — kurum içi pilot kurulumu

Bu paket kod içerir. Belgeler, veritabanı, model, Git geçmişi, kişisel
Cloudflare/GitHub anahtarları ve Mac ortamları dahil değildir.
Sunucuda Python 3.12, Türkçe/İngilizce Tesseract ve CPU llama-server gerekir.
llama-server beklenen konum: ~/llama.cpp/build/bin/llama-server.

## Python kurulumu

Paketin içeriğini /home/mahmut.koc/arsiv-ozet içine açtıktan sonra:

```bash
cd /home/mahmut.koc/arsiv-ozet
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Bağımlılıklar mevcut uygulamanın sabit sürümleridir. Ubuntu/Python 3.12
üzerindeki kurulum henüz doğrulanmadı. Hata olursa durun; sürümleri rastgele
değiştirmeyin. Başarılı kurulumdan sonra `pip check` çalıştırın.

## Model

Mac'te kullanılan model: ggml-org/gemma-3-12b-it-GGUF deposundaki
gemma-3-12b-it-Q4_K_M.gguf. Yaklaşık 7 GB; pakete dahil değildir.
Model indirme kaynağı, lisans koşulları ve dosya bütünlüğü ayrıca
doğrulanacak. Modeli modeller/ klasörüne yerleştirin. Başka konum için
ARSIV_MODEL_PATH ortam değişkenini tam dosya yoluna ayarlayın.
Belge işleme yereldir; indirme aşaması internet gerektirir.

## İlk çalıştırma

```bash
python3 deploy/linux/password.py
bash deploy/linux/start.sh
```

İkinci terminalden sağlık kontrolü:

```bash
curl -fsS http://127.0.0.1:8503/_stcore/health
```

Bu adres SUNUCUNUN yerel adresidir; Windows tarayıcısında aynı adresi
açmak sunucuya bağlanmaz. Kurum içi tarayıcı erişimi için onaylı HTTPS
ters vekil ve Streamlit WebSocket desteği ayrıca yapılandırılmalı.
8503 ve 8977 portlarını internete açmayın. Cloudflare kullanılmaz.
Terminal kapanınca devam etmesi için systemd servisi daha sonra hazırlanmalı.

## Pilot sınırları ve doğrulama

- Önce kurumsal belge içermeyen 1 sayfalık örnekle OCR ve özet test edin.
- CPU performansı henüz ölçülmedi; görünen kaynak 4 vCPU/32 GB RAM.
- Ortak şifre vardır, kişiye özel yetkilendirme yoktur. Kayıtlar ortaktır.
- Aynı anda bir belge işlenir. İptal, mevcut OCR/model çağrısı bitince uygulanır.
- 100 sayfa / toplam 200 MB sınırı ve iptal düğmesi pakete dahildir.
- macOS yazım sözlüğü Linux'ta devre dışıdır; sözlüğe dayalı bazı kelime
  birleştirmeleri yapılmaz. OCR ve model bundan bağımsızdır.
- data/ altında oluşan SQLite veritabanı ve sunucu şifresi kurumun
  yedekleme/gizlilik politikası kapsamında korunmalıdır.

Bu bir üretim güvenlik onayı veya performans garantisi değildir.
