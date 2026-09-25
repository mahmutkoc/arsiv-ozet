# Arşiv Künye Çıkarıcı

Devlet Arşivleri katalogundan indirilen çok sayfalı Latin harfli Türkçe
belgeleri okuyup **katalog künyesi** üretir. **Tamamen yerelde çalışır** —
Kurulum tamamlandıktan sonra yerel kullanımda internet bağlantısı ve API
anahtarı gerekmez. İnternetten paylaşım açılırsa belgeler paylaşım tüneli
üzerinden sunucu bilgisayara iletilir; model yine bu bilgisayarda çalışır.

## Şifreli paylaşım

`.venv/bin/python demo_start.py --archive` komutu ana uygulamayı 8503
portunda şifreli olarak başlatır. İlk başlatmada oluşturulan şifre
`.demo/password.txt` dosyasındadır; Git'e yüklenmez. Giriş yapan kişiler
mevcut kayıtları görür ve yeni belgeleri ortak arşive kaydedebilir.
Yerel klasör yolu bu modda kapalıdır. Harici erişim için ayrıca güvenli
bir tünel gerekir. Bu geçici paylaşım modu kurumsal rol yönetimi sağlamaz.

`--archive` olmadan başlatılan demo mevcut arşivi göstermez ve sonuçları
yalnızca oturumda tutar. Her iki modda da model çıktıları insan kontrolü
gerektirir. Belge, veritabanı, model ve şifre dosyaları bu depoya dahil değildir.

Bu depo yalnızca kaynak kodu içerir. Arşiv belgeleri, veritabanı, çıkarılan
metinler ve model dosyaları paylaşılmaz. Kurulum sırasında bağımlılıkları
ve modeli indirmek için internet gerekir; kurulumdan sonra belge işleme
yerelde çalışır. Gerçek belgelerle çalışan ölçüm betikleri için örnek
belgeleri kendi bilgisayarınızda `data/` altına koymanız gerekir.

## Ne yapar

1. Sayfa görüntülerini (ya da PDF'i) OCR öncesi temizler
2. Tesseract ile Türkçe metni çıkarır
3. OCR artıklarını ve tekrarlayan antet satırlarını eler
4. Yerel dil modeliyle künye alanlarını doldurur
5. Sonucu SQLite'ta saklar, tam metin aramasına açar

## Çıktı

Katalog giriş formundaki alanlara karşılık gelir:

| Alan | İçerik |
|---|---|
| Belge özeti | 2-4 kısa cümle, en fazla 55 kelime |
| Madde ve yer adları | satır başına bir ad |
| Şahıs adları | `AD, UNVAN` biçiminde |
| Tüzel kuruluş adları | satır başına bir ad |

Arayüzde her alanın yanında kopyala düğmesi var; forma tek tıkla
yapıştırılır. "Açıklama" alanı doldurulmaz — uygulamada genelde boş
bırakılıyor.

## Kurulum

Python 3.13 ve `micromamba` gerekir.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Tesseract ve llama.cpp
micromamba create -y -p .mamba -c conda-forge tesseract llama.cpp

# Dil modeli (~7 GB)
.venv/bin/python -c "
from huggingface_hub import hf_hub_download
hf_hub_download('ggml-org/gemma-3-12b-it-GGUF',
                'gemma-3-12b-it-Q4_K_M.gguf', local_dir='modeller')"
```

## Kullanım

**Arayüz:**

```bash
.venv/bin/streamlit run app.py
```

**Komut satırı:**

```bash
.venv/bin/python ozet.py data/ornek --ad "Belge adı" --kaydet
.venv/bin/python ozet.py belge.pdf --metin
```

## Belgeleri nasıl indirmeli

Katalogda belgeyi açıp sayfaların **JPG** ya da **PDF** halini indir ve tek
bir klasöre koy. Dosya adları sıralı olsun (`001.jpg`, `002.jpg` …) — sıra
korunmazsa özet kopuk çıkar.

> WhatsApp veya benzeri bir uygulamadan geçirme. Sıkıştırma çözünürlüğü
> ~137 DPI'a düşürüyor ve OCR doğruluğu belirgin şekilde azalıyor.
> Katalogdan indirilen orijinal dosyayı kullan.

## Yapı

| Dosya | İş |
|---|---|
| `core/preprocess.py` | Mühür temizleme, eğrilik düzeltme, antet kırpma |
| `core/ocr.py` | Tesseract ile görüntü/PDF → metin |
| `core/clean.py` | OCR artıkları ve tekrarlayan satırların elenmesi |
| `core/summarize.py` | Yerel model (llama.cpp) ile özetleme |
| `core/store.py` | SQLite kayıt ve FTS5 arama |
| `core/pipeline.py` | Adımların birleştiği akış |
| `app.py` | Streamlit arayüzü |
| `ozet.py` | Komut satırı aracı |

## Tasarım notları

**Antet kırpma.** Antetli kâğıtta sol sütun (şube listesi, telefon numaraları)
her sayfada tekrar eder ve OCR çıktısının ~%70'ini kaplayıp özeti bozar.
Antedi gövdeden ayıran tam boy dikey çizgi bulunup sağındaki alan gövde kabul
edilir. Çizgi bulunamazsa (antetsiz sayfa) sayfa bütün bırakılır.

**Adım sırası.** Kırpma, eğrilik düzeltmeden **önce** yapılmalı: sayfa
döndürüldükten sonra ayırıcı çizgi artık dikey olmadığı için bulunamıyor.

**Sayfa bölütleme kipi.** Kırpılmış gövde için `--psm 4` kullanılır. Otomatik
kip (`3`) tablo satırlarını çok sütun sanıp `A) 582 Dönüm …` gibi satırları
parçalara ayırıyor.

**Görüntü büyütme denendi ve reddedildi.** Düşük DPI'lı taramayı OCR öncesi
büyütmek tek bir örnekte umut vericiydi (`688.000` → `88.000`), ama belgedeki
28 bilinen değerin tamamında ölçülünce net kazanç vermediği görüldü:

| Ölçek | Doğru okunan | Kaçırdığı |
|---|---|---|
| **1.0x** | **27/28** | `88.000` |
| 1.5x | 26/28 | `400`, `3.000` |
| 2.0x | 25/28 | `400`, `3.000`, `35` |
| 2.5x | 27/28 | `35` |
| 3.0x | 27/28 | `35` |

Büyütme bazı rakamları düzeltirken başkalarını bozuyor. 1.0x hem en iyi
skoru paylaşıyor hem de en ucuz olduğu için büyütme yapılmıyor. Ölçümü
tekrarlamak için `tests/olcek_kiyas.py`.

Kalan `88.000` hatası çözünürlük kaynaklı; katalogdan indirilen orijinal
dosyada görülmesi beklenmez.

**Eski imla korunur.** "vucud", "mıntaka", "digeri" gibi dönem yazımları
düzeltilmez; arşiv metninde sadakat önemlidir. Model bu konuda uyarılır.

**Sayfa sayfa özetleme.** Belge 500 kelimeyi geçtiğinde önce her sayfadan
ayrı not çıkarılıp sonra notlar birleştirilir. Bu sınır bilinçli olarak
düşük: envanter türü, sayı yoğun belgeleri tek geçişte özetlemek denendiğinde
model rakamları karıştırdı (`88.000` → `688.000`), "her biri 15.000 litre"
ifadesini toplayıp `25.000` yazdı ve bir bölümü tamamen atladı. Sistem
komutunda ayrıca sayı toplamak ve bölüm atlamak açıkça yasaklanır.

**Özet + döküm birlikte.** Sayfa notlarını tek bir anlatıya indirmek uydurma
sayıları bitirdi ama bu sefer orta listedeki kalemleri (`88.000` bağ omcası,
`6600` zeytin ağacı) eledi. İki hata da aynı kökten geliyor: sıkıştırma
kaçınılmaz olarak bilgi atıyor. Bu yüzden çıktı iki katmanlı — okunur bir
anlatı özeti, altında sayfa sayfa tam döküm. Anlatı kısa kalır, sayılar
kaybolmaz.

**Doğrulama.** `tests/dogrulama.py`, örnek belgedeki 23 kritik değeri
(sayılar, tarihler, isimler) özette arar ve bilinen yanlış değerlerin
girmediğini kontrol eder. Özetleyiciyi değiştirince gerilemeyi yakalamak
için:

```bash
.venv/bin/python tests/test_store.py                 # depolama testleri
.venv/bin/python ozet.py data/ornek > /tmp/ozet.txt  # özet doğruluğu
.venv/bin/python tests/dogrulama.py /tmp/ozet.txt
```

**Adlar satır satır saklanır.** Virgül ayırıcı olarak kullanılamıyor:
kişi kaydının kendisi virgül içeriyor ("OSMAN EFENDİ, YÜZBAŞI"), dolayısıyla
virgül hem adın içinde hem adlar arasında geçebilirdi. Modelden her adı ayrı
satıra yazması isteniyor; formdaki liste kutusuna da böyle giriliyor.

**Model sunucusu sabit portta.** Rastgele port her çalıştırmada yeni bir
`llama-server` doğuruyordu. Model 7 GB tuttuğu için birkaç tanesi 16 GB'lık
makineyi doldurup "Compute error" veriyordu. Artık sabit portta çalışan
sağlıklı sunucu yeniden kullanılıyor; ayrıca `atexit` ve SIGTERM
yakalayıcısı, uygulama `kill` ile durdurulduğunda sunucunun ayakta
kalmasını önlüyor.

**Türkçe arama.** FTS5 sorgusuna ön ek jokeri ve ünsüz yumuşaması varyantları
eklenir; `çiftlik` araması `çiftliği` kaydını da bulur.

**Veritabanı bağlantısı önbelleğe alınmaz.** `sqlite3` bir bağlantının
yalnızca onu açan iş parçacığında kullanılmasına izin veriyor; Streamlit ise
her etkileşimi ayrı iş parçacığında çalıştırabiliyor. Bağlantıyı saklamak
`SQLite objects created in a thread can only be used in that same thread`
hatası veriyordu. `check_same_thread=False` ile susturmak yerine
`store.session()` her iş için kısa ömürlü bağlantı açıyor — SQLite'ta
bağlantı açmak ucuz.

## Bilinen sınırlar

- El yazısı (imza, kenar notu) okunamaz, çöp üretir ve elenir
- Şapkalı harfler (`â`, `î`) sıklıkla düz harfe düşer
- `g`/`ğ` karışması görülür
- Sayfa sırası dosya adına göre belirlenir; belge içi numaralardan
  otomatik sıralama yapılmaz
