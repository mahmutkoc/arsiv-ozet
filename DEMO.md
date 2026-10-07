# Arkadaşlar için paylaşım demosu

## Güncel paylaşım: ana uygulama ve mevcut arşiv

Kullanıcının mevcut kayıtları paylaşma onayıyla 22 Eylül'de 8503 portu,
şifreli ana uygulamaya geçirildi. Başlatma:
`.venv/bin/python demo_start.py --archive`.
Bu seçenek `ARSIV_SHARED=1` ile `app.py` çalıştırır. Aşağıdaki demo izolasyonu
açıklamaları yalnızca `--archive` olmadan başlatılan eski demo için geçerlidir.

Ana arayüzde Belge işle ve Kayıtlı belgeler sekmeleri vardır. Mevcut arşiv
görünür; yeni belgeler aynı arşive kaydedilir ve tüm giriş yapanlarca görülebilir.
Silme/düzenleme işlemi sunulmaz. Yerel klasör yolu dış erişimde kapatılır;
yüklemeler doğrulanır (15 sayfa, 20 MB) ve aynı anda tek işlem yapılır.
Şifre aynı `.demo/password.txt` dosyasındadır. Şifresiz arşiv sorgusu yapılmaz.
Dosyalar Cloudflare üzerinden sunucuya gelir; işlem yerel modelde yapılır.
Bu geçici arkadaş paylaşımıdır; kurumsal erişim/rol ve denetim altyapısı değildir.

Güncel sabit bağlantı: https://arsiv.mahmutkoc.me/
Başlatma: `.venv/bin/python share_start.py`. Tünel anahtarı önce
`tunnel_authorize.py` ile özel `.demo/cloudflare-token` dosyasına kaydedilir.
Bilgisayar açık ve uyanık kalmalıdır. Adres yeniden başlatmada değişmez.
Port 8503 başka uygulama tarafından kullanılıyorsa başlatıcı uyarı verir.

**Aşağıdaki bölümler eski denemelerin tarihsel notlarıdır. Eski geçici adresleri
ve LocalTunnel yönergelerini güncel kurulumda kullanmayın.**

## Önceki izole demo

Ana uygulama `app.py` ile 8502 portunda kalır. İnternete yalnızca
`demo_app.py` (8503) yönlendirilir. Ana uygulamaya tünel açmayın.

Başlatma: `.venv/bin/python demo_start.py`

İlk açılışta rastgele şifre `.demo/password.txt` dosyasına yazılır.
Bu dosya Git'e eklenmez. Şifreyi yalnızca deneyecek kişilerle paylaşın.
Demo, asıl veritabanını açmaz ve sayfa notlarını diske önbelleklemez.
Sonuçlar tarayıcı oturumunda kalır; yenileme veya çıkışta kaybolabilir.
Geçici yüklemeler okuma tamamlandığında silinir (ani süreç/cihaz kapanması
halinde geçici dosyalar kalabilir).

Bir işlemde en fazla 15 sayfa, toplam 20 MB, görüntü başına 20 megapiksel.
Tek PDF veya birden çok tek sayfalık görüntü kabul edilir.
Demo işleri bir çalışanla işlenir; işlenen dahil en fazla üç iş sıraya alınır.
Kurgusal örnek metin seçeneği dosya yüklemeden model akışını dener; OCR testi değildir.
Deneme sırasında ana uygulamadan da iş başlatmayın: aynı yerel model kullanılır.

Geçici internet bağlantısı:

```
.demo/bin/cloudflared tunnel --url http://127.0.0.1:8503 --no-autoupdate
```

Cloudflare çıktısındaki HTTPS adresini paylaşın. Tüneli Ctrl+C ile kapatmak
internet erişimini keser. Uygulamayı da kendi terminalinde Ctrl+C ile durdurun.
Bilgisayar açık, uyanık ve internete bağlı kalmalıdır. Yeniden tünel açıldığında
adres değişebilir. Bu bir kurum geneli kullanım veya kalıcı barındırma çözümü değildir.
Trafik Cloudflare üzerinden geçer; yalnızca paylaşılabilir örnek belge kullanın.

İsimli ücretsiz alternatif: `npx --yes localtunnel --port 8503 --local-host 127.0.0.1 --subdomain mahmutkoc-arsiv-demo-0922`
İstenen isim müsaitse `https://mahmutkoc-arsiv-demo-0922.loca.lt` verilir; kalıcı isim
rezervasyonu değildir. Bu bağlantı LocalTunnel üzerinden geçer. İlk ziyarette
hizmetin karşılama ekranındaki IP adresini girip Continue'a basın; ardından
demo şifresini kullanın. Ana uygulamanın 8502 portunu paylaşmayın.
Demo başlangıcında `DEMO_PUBLIC_ORIGINS` ortam değişkenine izin verilen
tam HTTPS adreslerini virgülle ayırarak verin. CORS ve XSRF kontrolleri açık kalır.

22 Eylül denemesinde LocalTunnel adresi tahsis edildi ve HTTP sağlık kontrolü
geçti; ancak tarayıcıdaki arayüz yüklenemedi. Bir JavaScript dosyası 33 saniyede
geldi. Bu adres henüz çalışır demo olarak doğrulanmadı; Cloudflare bağlantısı
yedek olarak açık bırakıldı; daha sonra eski tünelin düştüğü görüldü.

Son kontrol: `mahmutkoc-arsiv.loca.lt` bize ait olmayan bir ekran gösterdi;
bu eski adresi kullanmayın. Yeni adres `mahmutkoc-arsiv-demo-0922.loca.lt`.
Yeni adresin WebSocket bağlantısından doğru demo şifre ekranı doğrulandı,
ancak tarayıcı arayüzünün yüklenmesi henüz doğrulanmadı.
Başlatma: `DEMO_PUBLIC_ORIGINS=https://mahmutkoc-arsiv-demo-0922.loca.lt .venv/bin/python demo_start.py`

## Doğrulanan isimli yönlendirme (22 Eylül)

`https://mahmutkoc-demo.loca.lt` yalnızca Cloudflare demosuna yönlendirilir.
Tarayıcıda bu bağlantı üzerinden **Arşiv Künye · Demo / Demo şifresi** ekranına
ulaşıldı. Açıldıktan sonra adres çubuğu Cloudflare adresini gösterir.
Bu isim size ait kalıcı bir alan adı değildir; tünel açıkken kullanılmalıdır.

Cloudflare tüneli başlatıldıktan sonra çıktısındaki yeni HTTPS adresiyle:

```sh
.venv/bin/python demo_redirect.py https://receipt-hardware-formatting-layers.trycloudflare.com/
```

Ayrı terminalde:

```sh
npx --yes localtunnel --port 8504 --local-host 127.0.0.1 --subdomain mahmutkoc-demo
```

Yukarıdaki Cloudflare adresi bu oturuma aittir; yeni tünelde değişirse yönlendirme
sunucusunu yeni adresle yeniden başlatın. LocalTunnel başka isim verirse yalnızca
çıktıda verilen, doğru demo ekranına ulaştığı kontrol edilmiş adresi paylaşın.
İlk ziyaretin karşılama sayfasında gösterilen IP adresini girip Continue'a basın;
demo şifresi yalnızca doğru Cloudflare demo ekranına girilmelidir.
Paylaşımı bitirince her iki tüneli ve yönlendirme sunucusunu Ctrl+C ile kapatın.
