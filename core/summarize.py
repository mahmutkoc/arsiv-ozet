"""Belge metninden katalog künyesi çıkarır.

Çıktı, katalog giriş formundaki alanlara karşılık gelir: kısa belge özeti
ile yer, şahıs ve tüzel kuruluş adları.

Model tamamen yerelde, llama.cpp sunucusu üzerinden çalışır; hiçbir veri
dışarı gitmez. Uzun belgelerde önce sayfa sayfa not çıkarılıp sonra bu notlar
birleştiriliyor (map-reduce), çünkü tek seferde verilen çok uzun metinde
model ortadaki ayrıntıları atlama eğiliminde.

Model çıktısı JSON yerine etiketli metin olarak isteniyor: llama.cpp'nin
şema kipi bu kurulumda çalışmadı, ayrıca küçük modeller etiketli biçimde
daha az hata yapıyor. Ayrıştırıcı bozuk ve eksik biçimlere dayanacak
şekilde savunmacı yazıldı (bkz. tests/test_kunye.py).
"""

from __future__ import annotations

import atexit
import difflib
import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx
from openai import OpenAI

from core.text import fold, turkish_lower, turkish_upper

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LLAMA_SERVER = PROJECT_ROOT / ".mamba/bin/llama-server"
MODEL_DIR = PROJECT_ROOT / "modeller"

# Sabit port. Rastgele port her çalıştırmada yeni sunucu doğurup belleği
# tüketiyordu; sabit portta çalışan sağlıklı sunucu yeniden kullanılır.
SERVER_PORT = 8977

CONTEXT_TOKENS = 16384
# Sayfa notlarını birleştirirken bağlamı taşırmamak için notlar bu kelime
# sınırını aşarsa önce gruplar halinde birleştirilip sonra tek özete iniliyor.
REDUCE_BATCH_WORD_LIMIT = 3000
PAGE_NOTE_TOKENS = 400
# Türkçede sözcükler daha uzun olduğu için token/kelime oranı İngilizceden
# yüksek; tek geçişte özetleme sınırını buna göre temkinli tutuyoruz.
TOKENS_PER_WORD = 2.0
# Bu sınır bilerek düşük tutuluyor. Envanter türü, sayı yoğun belgelerde tek
# geçişte özetleme rakamları karıştırıyor ve bölüm atlıyor; sayfa sayfa not
# çıkarıp birleştirmek sayıları belirgin şekilde daha iyi koruyor.
SINGLE_PASS_WORD_LIMIT = 500

SYSTEM_PROMPT = """Sen Türk devlet arşivi belgelerini inceleyen bir uzmansın.

Sana verilen metin, 1920-1940 döneminde daktiloyla yazılmış bir belgenin OCR
çıktısıdır. İki özelliğini bil:

1. Dönemin imlası kullanılır: "vucud", "mıntaka", "digeri", "taktirde",
   "mevcud" gibi yazımlar hatalı değil, dönemin kendi yazımıdır.
2. OCR hataları olabilir: harf karışmaları, bozuk imza satırları, kopuk
   kelimeler. Bunları bağlamdan anlamaya çalış.

Kurallar:
- Yalnızca belgede yazana dayan. Bilmediğin bir şeyi tamamlama, tahmin etme.
- Sayıları belgede yazdığı gibi, rakamı rakamına aktar. Sayıları asla
  toplama, çarpma, birleştirme ya da yuvarlama. Belge "her biri 15.000"
  diyorsa "15.000" yaz; iki tesis var diye 30.000 yazma.
- Belgedeki hiçbir bölümü atlama. Numaralı ya da harfli bölümler
  (I, II, III… veya A, B, C…) varsa hepsini kapsa.
- Tarihleri ve yer adlarını olduğu gibi aktar.
- Bir bilgi OCR yüzünden okunamıyorsa "(okunamadı)" diye belirt.
- Sade, bugünün Türkçesiyle yaz."""

PAGE_NOTE_INSTRUCTION = """Aşağıdaki belge sayfasının içeriğini maddeler
halinde not çıkar. Sayıları ve isimleri koru, yorum ekleme.

SAYFA {number}:
"""

CONDENSE_INSTRUCTION = """Aşağıdaki sayfa notlarını tek bir nota indir.
Bilgi kaybetme: bütün sayı, tarih, isim ve bölüm başlıklarını koru.
Yorum ekleme, sadece sıkıştır.

NOTLAR:
"""


# Özet ve adlar ayrı çağrılarda isteniyor. Tek çağrıda ikisini birden
# istediğimizde model dikkatini bölüyor ve özet kuralları (dolgu ifade
# yasağı, ilk cümle kuralı) ezilip gidiyordu: liste doğru çıkarken özet
# "detaylı bilgi verilmektedir" gibi boş kalıplara düşüyordu.
OZET_INSTRUCTION = """Aşağıdaki arşiv belgesinin özetini yaz.

Kurallar:
- 2-4 KISA CÜMLE, en fazla 55 kelime yaz. Dördüncü cümleden sonra dur.
- Başka hiçbir şey ekleme: başlık, madde işareti, liste yok.
- İLK CÜMLE belgedeki asıl olayı söylesin: kim, kime, neyi yaptı ya da
  ne talep etti. Belgenin yazılma sebebi bu cümlede geçmeli.
- Eylemi yapan kişiyi, mesajı göndereni ve mesajı ileteni birbirine
  karıştırma. Görüşmelerde her görüşü onu söyleyen tarafa bağla; farklı
  kişilerin sözlerini tek kişinin görüşü gibi birleştirme. Konuşan taraf
  açık değilse kişiye atfetmeden görüşülen konuyu yaz.
- Tarih, taraf veya önemli sonuç yalnızca belgenin ana olayını anlamak
  için gerekliyse yaz. Envanterdeki bütün miktarları, yerleri ve ayrıntıları
  sıralama.
- Şu kalıpları KULLANMA: "bilgi verilmektedir", "hakkında bilgi
  sunulmaktadır", "detaylı olarak açıklanmaktadır", "özetlemektedir".
  Bunlar belgenin ne söylediğini anlatmaz. Olayı doğrudan yaz.
- Belgede yazmayan hiçbir şey ekleme.

BELGE:
"""

ADLAR_INSTRUCTION = """Aşağıdaki arşiv belgesinde geçen adları listele.

Yalnızca şu biçimde, başka hiçbir şey yazmadan cevap ver:

YER:
- (yer adı)
ŞAHIS:
- (kişi adı)
KURUM:
- (kurum adı)

Kurallar:
- HER ADI KENDİ SATIRINA, başına "- " koyarak yaz. Adları tek satırda
  virgülle ayırma.
- YER: şehir, kasaba, köy, mevki, çiftlik, köşk ve arazi adları. Bir yerin
  adını taşıyan çiftlik, bahçe, köşk YER'e yazılır, KURUM'a değil.
- ŞAHIS: kişi adları. Belgede unvanı geçiyorsa adın ardına virgül koyup
  unvanı yaz, yoksa yalnız adı yaz. Tek başına unvan yazma: bir makam adı
  kişi adı değildir.
- KURUM: makam, daire ve teşkilat adları — bakanlık, nezaret, vekâlet,
  müdürlük, kâtiblik, alay gibi. Belgeyi yazan ya da belgenin gönderildiği
  makam varsa mutlaka bu listede olmalı.
  Buraya YAZILMAZ: bina ve tesisler — fabrika, imalathane, değirmen,
  mağaza, müze, bahçe, ambar, ahır. Bunlar mülktür, makam değil.
  Genel ifadeler de yazılmaz: "çiftlikler", "ziraat sahası" gibi.
- Yer ve kurum adlarını BÜYÜK HARFLE yaz.
- Aynı adı bir kez yaz.
- OCR bozuk okumuş olabilir; emin olmadığın adı yazma.
- Bir başlıkta hiç ad yoksa altına "- yok" yaz.

ÖNEMLİ: Yukarıdaki açıklamalarda geçen sözcükler yalnızca tür belirtir.
Bunları ad olarak listene YAZMA. Yalnızca belgenin kendi metninde okuduğun
adları yaz. Belgede geçmeyen hiçbir ad üretme.

BELGE:
"""


def find_model() -> Path:
    """modeller/ altındaki GGUF dosyasını bulur."""
    candidates = sorted(MODEL_DIR.rglob("*.gguf"))
    if not candidates:
        raise RuntimeError(
            f"{MODEL_DIR} içinde .gguf model yok. İndirmek için README'ye bak."
        )
    return candidates[0]


class LocalModel:
    """llama.cpp sunucusunu açıp OpenAI uyumlu istemciyle konuşur.

    Sunucu sabit bir portta çalışır. Rastgele port seçilseydi her çalıştırma
    yeni bir sunucu doğururdu; model 7 GB tuttuğu için birkaç tanesi 16 GB'lık
    makineyi doldurup "Compute error" veriyordu. Sabit portta zaten çalışan
    sağlıklı bir sunucu varsa yenisini başlatmak yerine ona bağlanıyoruz.
    """

    def __init__(self, model_path: Path | None = None, *, context: int = CONTEXT_TOKENS):
        self.model_path = model_path or find_model()
        self.context = context
        self.port = SERVER_PORT
        self._process: subprocess.Popen | None = None
        self._previous_sigterm = None

    def __enter__(self) -> "LocalModel":
        if not self._server_is_healthy():
            self._spawn()
        self.client = OpenAI(base_url=f"http://127.0.0.1:{self.port}/v1", api_key="yerel")
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()

    def _server_is_healthy(self) -> bool:
        try:
            return httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=2.0).status_code == 200
        except httpx.HTTPError:
            return False

    def _spawn(self) -> None:
        self._process = subprocess.Popen(
            [
                str(LLAMA_SERVER),
                "-m", str(self.model_path),
                "--port", str(self.port),
                "-c", str(self.context),
                "-ngl", "99",          # Tüm katmanlar Metal GPU'ya.
                "--no-warmup",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "LLAMA_LOG_LEVEL": "ERROR"},
        )

        # Süreci biz doğurduysak kapatmak da bizim işimiz. Streamlit'i `kill`
        # ile durdurmak __exit__'i çalıştırmadığı için sunucu ayakta kalıp
        # 7 GB'ı tutuyordu; atexit normal çıkışı, sinyal yakalayıcı da
        # `kill` ile gelen SIGTERM'i karşılıyor.
        atexit.register(self.stop)

        # signal.signal yalnızca ana iş parçacığından çağrılabiliyor.
        # Streamlit betiği işçi iş parçacığında çalıştırdığı için orada
        # ValueError veriyordu; o durumda atexit tek başına yeterli.
        if threading.current_thread() is threading.main_thread():
            self._previous_sigterm = signal.signal(signal.SIGTERM, self._on_sigterm)

        self._wait_until_ready()

    def _on_sigterm(self, signum, frame) -> None:
        self.stop()
        if callable(self._previous_sigterm):
            self._previous_sigterm(signum, frame)
        else:
            raise SystemExit(143)

    def stop(self) -> None:
        """Yalnızca kendi başlattığımız sunucuyu kapatır."""
        if not self._process:
            return

        process, self._process = self._process, None
        atexit.unregister(self.stop)
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()

    def _wait_until_ready(self, timeout: float = 180.0) -> None:
        """Model belleğe yüklenene kadar bekler."""
        deadline = time.monotonic() + timeout
        url = f"http://127.0.0.1:{self.port}/health"
        while time.monotonic() < deadline:
            if self._process and self._process.poll() is not None:
                raise RuntimeError("llama-server beklenmedik şekilde kapandı.")
            try:
                if httpx.get(url, timeout=2.0).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(1.0)
        raise TimeoutError(f"llama-server {timeout:.0f} saniyede hazır olmadı.")

    def ask(self, instruction: str, text: str, *, max_tokens: int = 1024) -> str:
        response = self.client.chat.completions.create(
            model="yerel",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": instruction + text},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        return (response.choices[0].message.content or "").strip()


EMPTY_MARKERS = {"yok", "-", "—", "belirtilmemiş", "bulunmuyor", ""}


BULLET_PATTERN = re.compile(r"^\s*[-•*•]\s*")


def _clean_names(lines: Sequence[str]) -> list[str]:
    """Ad satırlarını temizler, tekrarları eler.

    Her ad kendi satırında geliyor. Virgülle ayırmak mümkün değil: kişi
    kaydının kendisi virgül içeriyor ("OSMAN EFENDİ, YÜZBAŞI"), dolayısıyla
    virgül hem ad içinde hem adlar arasında geçebilirdi. Model tek satırda
    virgülle dönerse ad bölünmeden olduğu gibi bırakılıyor — birleşik bir
    kayıt, yanlış bölünmüş iki kayıttan iyidir.
    """
    seen, result = set(), []
    for line in lines:
        cleaned = " ".join(BULLET_PATTERN.sub("", line).split()).strip(" .;")
        if not cleaned or cleaned.casefold() in EMPTY_MARKERS:
            continue
        key = turkish_upper(cleaned)
        if key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


# Etiketler modelden bazen büyük, bazen küçük harfle, bazen iki nokta olmadan
# geliyor; esnek yakalayıp normalleştiriyoruz.
LABEL_PATTERN = re.compile(
    r"^\s*(ÖZET|OZET|YER|ŞAHIS|SAHIS|KİŞİ|KISI|KURUM)\s*(?:ADLARI)?\s*:\s*(.*)$",
    re.IGNORECASE,
)
LABEL_ALIASES = {
    "ozet": "ozet", "özet": "ozet",
    "yer": "yer",
    "şahis": "sahis", "sahis": "sahis", "kişi": "sahis", "kisi": "sahis",
    "kurum": "kurum",
}


def parse_kunye(raw: str) -> dict[str, list[str]]:
    """Modelin etiketli çıktısını alanlara ayırır.

    Etiket satırından sonra gelen satırlar, yeni bir etiket görülene kadar
    o alana ait sayılıyor. Model bazen etiketi atlıyor ya da özeti birden
    çok satıra yayıyor; bu yaklaşım ikisini de karşılıyor.
    """
    fields: dict[str, list[str]] = {}
    current: str | None = None

    for line in raw.splitlines():
        match = LABEL_PATTERN.match(line)
        if match:
            label, value = match.groups()
            current = LABEL_ALIASES.get(label.casefold())
            if current:
                fields.setdefault(current, [])
                if value.strip():
                    fields[current].append(value.strip())
        elif current and line.strip():
            fields[current].append(line.strip())

    return fields


# Unvan, makam ve milliyet sözcükleri. Bir kayıtta bunlardan başka bir şey
# yoksa ortada kişi değil makam vardır: "Rumen Hükümeti Reisi" bir kişiyi
# adlandırmaz. Model bu ayrımı komutla söylenmesine rağmen yapmıyordu.
# Ek almış biçimleri de yakalamak için kök olarak eşleştiriliyor
# ("elçi" → "elçisi", "hükümet" → "hükümeti").
TITLE_STEMS = (
    "reis", "reisicumhur", "cumhurbaşkan", "elçi", "sefir", "ataşe", "konsolos",
    "mareşal", "general", "albay", "binbaşı", "yüzbaşı", "mülazım", "kumandan",
    "kâtip", "kâtib", "katip", "müdür", "müsteşar", "nazır", "nezaret",
    "vekil", "vekâlet", "vekalet", "başvekil", "bakan", "bakanlık",
    "sekreter", "vali", "kaymakam", "hükümet", "riyaset", "başkan",
    "büyük", "umum", "umumi", "umumî", "genel", "efendi", "bey", "beyler",
    "paşa", "hazretleri", "sayın", "mösyö", "müsyü", "madam",
    # Milliyet ve ülke sıfatları da tek başına kişi adı yapmaz.
    "türk", "yugoslav", "bulgar", "rumen", "yunan", "arnavut", "sovyet",
    "rus", "amerikan", "ingiliz", "fransız", "alman", "italyan", "macar",
)


# Şapkalı harfler düzleştiriliyor: "Kâtip" ile "katip" aynı sözcük ve
# kökle eşleşebilmesi gerekiyor.
CIRCUMFLEX = str.maketrans("âîûÂÎÛ", "aiuAIU")

# İyelik eki. "Yugoslavya'nın Ankara Büyük Elçisi" bir kişiyi değil bir
# makamı adlandırır; içinde özel ad geçse bile kişi kaydı sayılmamalı.
# Kesme işareti OCR'da sıkça düşüyor, ekin ayrı sözcük olarak yazıldığı
# hali de yakalanıyor.
GENITIVE = re.compile(
    r"['’](n[ıiuü]n|[ıiuü]n)\b|\b\w{2,}n[ıiuü]n\b|\bn[ıiuü]n\b", re.IGNORECASE
)


# Kökler de düzleştirilmiş biçimde tutuluyor, yoksa "kâtib" kökü
# düzleştirilmiş "katibi" ile eşleşmiyordu.
NORMALIZED_STEMS = tuple(sorted({stem.translate(CIRCUMFLEX) for stem in TITLE_STEMS}))


def _is_title_word(word: str) -> bool:
    stripped = re.sub(r"[^a-zçğıöşü]", "", word.translate(CIRCUMFLEX).lower())
    if not stripped:
        return True
    return any(stripped.startswith(stem) for stem in NORMALIZED_STEMS)


def looks_like_person(entry: str) -> bool:
    """Kayıt bir kişiyi mi adlandırıyor, yoksa yalnızca makamı mı?

    "MAREŞAL TİTO" bir kişidir: unvanı attığımızda "TİTO" kalıyor.
    "RUMEN HÜKÜMETİ REİSİ" değildir, geriye özel ad kalmıyor.
    "YUGOSLAVYA'NIN ANKARA BÜYÜK ELÇİSİ" de değildir: içinde özel adlar
    geçiyor ama iyelik yapısı bunun bir makam tarifi olduğunu gösteriyor.
    """
    words = [w for w in re.split(r"[\s,]+", entry) if w.strip(" .")]
    if not words:
        return False

    if GENITIVE.search(entry) and _is_title_word(words[-1]):
        return False

    return any(not _is_title_word(word) for word in words)


# Ülke ve devlet adları katalogda yer adıdır. Model bunları zaman zaman
# tüzel kuruluş sayıyor ("Sovyet Rusya" hem yer hem kurum listesine
# düşmüştü). Liste bu evrakın dönemine göre dar tutuldu; kapsamlı olması
# gerekmiyor, çünkü asıl çözüm iki liste arasındaki çakışmayı gidermek.
COUNTRY_NAMES = frozenset(
    {
        "türkiye", "yugoslavya", "bulgaristan", "romanya", "yunanistan",
        "arnavutluk", "sovyet rusya", "rusya", "suriye", "irak", "iran",
        "mısır", "almanya", "fransa", "ingiltere", "italya", "amerika",
        "macaristan", "avusturya", "lehistan", "kıbrıs", "sovyetler birliği",
    }
)


def _normalize(entry: str) -> str:
    """Karşılaştırma için sadeleştirir: küçük harf, tek boşluk, eksiz."""
    return " ".join(turkish_lower(entry).split()).strip(" .,'’")


def looks_like_country(entry: str) -> bool:
    """Kayıt bir ülke ya da devlet adı mı?

    Tam eşleşme aranıyor: "Bulgar Komünist Partisi Genel Sekreterliği"
    içinde ülke sıfatı geçiyor ama kendisi bir kuruluş.
    """
    return _normalize(entry) in COUNTRY_NAMES


def resolve_overlaps(yer: list[str], kurum: list[str]) -> tuple[list[str], list[str]]:
    """Aynı adın iki listede birden bulunmasını giderir.

    Bir ad yer olarak listelenmişse kurum sayılmaz: yer tespiti belirgin
    şekilde daha güvenilir çıkıyor. Yalnızca kurum listesinde görünen ülke
    adları da yer'e taşınıyor.
    """
    place_keys = {_normalize(name) for name in yer}

    kept_kurum = []
    moved = []
    for name in kurum:
        if _normalize(name) in place_keys:
            continue  # Zaten yer listesinde, kurumdan düşür.
        if looks_like_country(name):
            moved.append(name)
            continue
        kept_kurum.append(name)

    return yer + moved, kept_kurum


@dataclass
class Kunye:
    """Katalog giriş formunun alanları."""

    ozet: str
    yer_adlari: list[str]
    sahis_adlari: list[str]
    kurum_adlari: list[str]
    notes: list[str]

    @classmethod
    def from_raw(cls, raw: str, notes: list[str] | None = None) -> "Kunye":
        parsed = parse_kunye(raw)
        yer, kurum = resolve_overlaps(
            _clean_names(parsed.get("yer", [])),
            _clean_names(parsed.get("kurum", [])),
        )
        return cls(
            # Etiket hiç yakalanmadıysa çıktının tamamını özet say; boş
            # dönmektense ham metni göstermek kullanıcı için daha iyi.
            ozet=" ".join(parsed.get("ozet", [])).strip() or (raw.strip() if not parsed else ""),
            yer_adlari=yer,
            # Makam tarifleri kişi listesinden ayıklanıyor: model komutla
            # söylenmesine rağmen "Reisicumhur", "Rumen Hükümeti Reisi" gibi
            # unvanları kişi adı olarak yazmayı sürdürüyor.
            sahis_adlari=[
                name for name in _clean_names(parsed.get("sahis", [])) if looks_like_person(name)
            ],
            kurum_adlari=kurum,
            notes=notes or [],
        )

    def as_markdown(self) -> str:
        def listeyi_yaz(baslik: str, items: list[str]) -> str:
            # Adlar virgülle değil satır satır yazılıyor: kaydın kendisi
            # virgül içerdiği için ("HASAN RIZA SOYAK, UMUMÎ KÂTİB") virgülle
            # birleştirmek kaç ad olduğunu okunamaz hale getiriyor.
            if not items:
                return f"**{baslik}:** _yok_"
            satirlar = "\n".join(f"- {item}" for item in items)
            return f"**{baslik}:**\n{satirlar}"

        parts = [
            "**Belge Özeti:**",
            self.ozet or "_çıkarılamadı_",
            "",
            listeyi_yaz("Madde ve Yer Adları", self.yer_adlari),
            listeyi_yaz("Şahıs Adları", self.sahis_adlari),
            listeyi_yaz("Tüzel Kuruluş Adları", self.kurum_adlari),
        ]
        if self.notes:
            parts += ["", "---", "", "## Sayfa sayfa döküm", "", *self.notes]
        return "\n".join(parts)


NOTE_CACHE_DIR = PROJECT_ROOT / "cikti/notlar"


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _read_cached_note(path: Path) -> str | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))["not"]
    except (OSError, ValueError, KeyError):
        return None


def _write_cached_note(path: Path, note: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"not": note}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # Önbellek yazılamazsa iş yine de sürsün.


def build_notes(
    model: LocalModel,
    page_texts: Sequence[str],
    *,
    cache: bool = True,
) -> list[str]:
    """Her sayfadan ayrı not çıkarır.

    Boru hattının en pahalı adımı bu: sayfa başına bir model çağrısı.
    Sonuç sayfa metinlerinin özetine göre diske yazılıyor, aynı belge
    yeniden işlendiğinde atlanıyor. Metin değişirse anahtar da değişeceği
    için bayat not kullanılma riski yok.

    Ayrı işlev olması ayrıca aynı notlar üzerinden künyeyi birden çok kez
    üretmeyi mümkün kılıyor; oynaklık ölçümü buna dayanıyor.
    """
    filled = [(i, t) for i, t in enumerate(page_texts, start=1) if t.strip()]

    notes = []
    for number, text in filled:
        cache_file = NOTE_CACHE_DIR / f"{_cache_key(text)}.json"

        stored = _read_cached_note(cache_file) if cache else None
        if stored is None:
            stored = model.ask(
                PAGE_NOTE_INSTRUCTION.format(number=number),
                text,
                max_tokens=PAGE_NOTE_TOKENS,
            )
            if cache:
                _write_cached_note(cache_file, stored)

        notes.append(f"--- Sayfa {number} ---\n{stored}")

    return notes


MAX_SUMMARY_SENTENCES = 4
# Manuel girilmiş örneklerde özet yaklaşık 30-40 kelime. Biraz pay bırakarak
# 55 kelimede kesiyoruz; alanın uzun anlatıyla dolmasını engelliyor.
MAX_SUMMARY_WORDS = 55

# Cümle sonu: nokta/soru/ünlem, ardından boşluk ya da metin sonu. Sayı
# içindeki nokta ("650.000") ve kısaltmalar bölme noktası sayılmasın diye
# noktadan sonra büyük harf ya da metin sonu aranıyor.
SENTENCE_END = re.compile(r"(?<=[.!?])(?=\s+[A-ZÇĞİÖŞÜ])|(?<=[.!?])\s*$")


def limit_sentences(
    text: str,
    limit: int = MAX_SUMMARY_SENTENCES,
    max_words: int = MAX_SUMMARY_WORDS,
) -> str:
    """Özeti katalog alanına sığacak kısa cümlelere indirir.

    Model "en fazla 4 cümle" kuralını tutmuyor; ölçümde üç koşunun üçünde
    de 5-8 cümle yazdı. Ayrıca cümleler uzun olabiliyor. Katalog alanı kısa
    özet istediği için hem cümle hem kelime sınırı kodda uygulanıyor:
    modele güvenip ummak yerine garanti ediyoruz. Cümle yarıda kesilmez.
    """
    cleaned = " ".join(text.split())
    if not cleaned:
        return cleaned

    sentences = [s.strip() for s in SENTENCE_END.split(cleaned) if s and s.strip()]
    selected: list[str] = []
    word_count = 0
    for sentence in sentences[:limit]:
        count = len(sentence.split())
        # İlk cümle uzun olsa da olay bilgisini kaybetmemek için onu koru.
        # Sonraki cümleler alanı taşıracaksa bütün olarak atlanır.
        if selected and word_count + count > max_words:
            break
        selected.append(sentence)
        word_count += count
    return " ".join(selected)


# Adlar çağrısı birkaç kez yapılıp sonuçlar birleştiriliyor. Ölçümde kurum
# listesi koşudan koşuya %43 örtüşüyordu: "Birleşmiş Milletler" bir koşuda
# çıkıp diğerinde çıkmıyordu. Arşivci fazlasını silebilir ama hiç görmediği
# adı ekleyemez, o yüzden kesişim değil birleşim alınıyor.
NAME_RUNS = 3

# İki kurum kaydının aynı sayılması için gereken benzerlik. "hariciye
# nezaret" ile "hariciye nezareti" tek harf farkla aynı makam.
INSTITUTION_SIMILARITY = 0.85


def _merge_similar(entries: list[str]) -> list[str]:
    """Yazım farkıyla tekrarlayan kayıtları teke indirir; uzun olanı tutar."""
    kept: list[str] = []
    for entry in entries:
        key = fold(entry).replace(" ", "")
        for index, existing in enumerate(kept):
            other = fold(existing).replace(" ", "")
            if difflib.SequenceMatcher(None, key, other).ratio() >= INSTITUTION_SIMILARITY:
                if len(entry) > len(existing):
                    kept[index] = entry
                break
        else:
            kept.append(entry)
    return kept


def _merge_contained(entries: list[str]) -> list[str]:
    """Biri diğerinin içinde geçen kayıtları birleştirir, uzun olanı tutar.

    Kişi adı kimi koşuda yalnız ("TODOJİVKO"), kimi koşuda unvanıyla
    ("... GENEL SEKRETERİ TODOJİVKO") geliyor. Aynı kişi; unvanlı biçim
    katalog için daha bilgilendirici.

    Bu kural yer adlarına uygulanmıyor: "ANKARA" ile "ANKARA ORMAN
    ÇİFTLİĞİ" ayrı yerlerdir, birleştirilemez.
    """
    kept: list[str] = []
    for entry in sorted(entries, key=len, reverse=True):
        key = fold(entry)
        if any(key in fold(existing) for existing in kept):
            continue
        kept.append(entry)
    return kept


def collect_names(model: LocalModel, text: str, runs: int = NAME_RUNS) -> Kunye:
    """Adlar çağrısını birkaç kez yapıp sonuçları birleştirir."""
    results = [Kunye.from_raw(model.ask(ADLAR_INSTRUCTION, text, max_tokens=600)) for _ in range(runs)]

    def birlestir(alan: str) -> list[str]:
        seen: dict[str, str] = {}
        for result in results:
            for name in getattr(result, alan):
                seen.setdefault(fold(name), name)
        return list(seen.values())

    yer = birlestir("yer_adlari")
    sahis = _merge_contained(birlestir("sahis_adlari"))
    kurum = _merge_similar(birlestir("kurum_adlari"))

    yer, kurum = resolve_overlaps(yer, kurum)
    return Kunye(ozet="", yer_adlari=yer, sahis_adlari=sahis, kurum_adlari=kurum, notes=[])


def kunye_from_text(model: LocalModel, text: str, notes: list[str] | None = None) -> Kunye:
    """Verilen metinden özet ve adları ayrı çağrılarla üretir."""
    parsed = collect_names(model, text)
    parsed.notes = notes or []
    # Özet ayrı çağrıdan geliyor; adlar çağrısı ÖZET etiketi içermiyor.
    parsed.ozet = limit_sentences(model.ask(OZET_INSTRUCTION, text, max_tokens=500)).strip()
    return parsed


def extract_kunye(model: LocalModel, page_texts: Sequence[str], *, cache_notes: bool = True) -> Kunye:
    """Sayfa metinlerinden katalog künyesini üretir."""
    filled = [(i, t) for i, t in enumerate(page_texts, start=1) if t.strip()]
    if not filled:
        return Kunye("Belgede okunabilir metin bulunamadı.", [], [], [], [])

    total_words = sum(len(t.split()) for _, t in filled)

    if total_words <= SINGLE_PASS_WORD_LIMIT:
        joined = "\n\n".join(f"--- Sayfa {i} ---\n{t}" for i, t in filled)
        return kunye_from_text(model, joined)

    notes = build_notes(model, page_texts, cache=cache_notes)

    reducible = notes
    while len(" ".join(reducible).split()) > REDUCE_BATCH_WORD_LIMIT and len(reducible) > 1:
        reducible = _condense(model, reducible)

    return kunye_from_text(model, "\n\n".join(reducible), notes=notes)


def _condense(model: LocalModel, notes: list[str]) -> list[str]:
    """Not listesini, bağlama sığana kadar gruplayarak kısaltır."""
    batches: list[list[str]] = []
    current: list[str] = []
    current_words = 0

    for note in notes:
        words = len(note.split())
        if current and current_words + words > REDUCE_BATCH_WORD_LIMIT:
            batches.append(current)
            current, current_words = [], 0
        current.append(note)
        current_words += words
    if current:
        batches.append(current)

    if len(batches) == len(notes):  # Tek not bile sınırı aşıyorsa daha fazla bölemeyiz.
        return notes

    return [
        model.ask(CONDENSE_INSTRUCTION, "\n\n".join(batch), max_tokens=800)
        for batch in batches
    ]
