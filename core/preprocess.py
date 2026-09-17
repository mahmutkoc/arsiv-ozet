"""Arşiv belgesi tarama görüntülerini OCR öncesi temizler.

Bu belgelerde tekrar eden üç bozucu unsur var:
  - Metnin üstüne binen kırmızı arşiv mühürleri
  - Sayfanın hafif eğri taranmış olması
  - Sararmış kâğıt yüzünden düşük kontrast
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

# Mühür kırmızısını yakalarken lacivert daktilo mürekkebini elemek için eşikler.
# Mühür pikselinde R kanalı diğer ikisini belirgin şekilde geçer.
RED_DOMINANCE = 40
RED_MINIMUM = 90




def remove_red_stamps(img: np.ndarray) -> np.ndarray:
    """Kırmızı mühür piksellerini kâğıt rengiyle doldurur.

    Metin siyah/lacivert olduğu için kırmızı baskınlığına bakmak, mührün
    altında kalan harfleri bozmadan mührü kaldırmaya yetiyor.
    """
    b, g, r = (c.astype(np.int16) for c in cv2.split(img))
    mask = ((r - g > RED_DOMINANCE) & (r - b > RED_DOMINANCE) & (r > RED_MINIMUM)).astype(np.uint8)

    # Mührün kenarındaki yarı saydam pikseller de gitsin.
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=2)

    paper = np.median(img.reshape(-1, 3), axis=0).astype(np.uint8)
    out = img.copy()
    out[mask == 1] = paper
    return out


def measure_skew(binary: np.ndarray, max_angle: float = 5.0, step: float = 0.25) -> float:
    """İzdüşüm profili yöntemiyle eğrilik açısını ölçer.

    Sayfa doğru açıya geldiğinde metin satırları ile satır araları keskinleşir,
    yani satır toplamlarının varyansı tepe yapar. Aday açıları tarayıp varyansı
    en yükselten açıyı seçiyoruz. Metin bloğunun şekline bakan minAreaRect'in
    aksine bu yöntem çok sütunlu sayfalarda da şaşmıyor.
    """
    small = cv2.resize(binary, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    h, w = small.shape

    best_angle, best_score = 0.0, -1.0
    for candidate in np.arange(-max_angle, max_angle + step, step):
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), float(candidate), 1.0)
        rotated = cv2.warpAffine(small, matrix, (w, h), flags=cv2.INTER_NEAREST)
        score = float(np.var(rotated.sum(axis=1)))
        if score > best_score:
            best_angle, best_score = float(candidate), score

    return best_angle


def deskew(img: np.ndarray) -> np.ndarray:
    """Metin satırlarını yatay eksene oturtur."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    angle = measure_skew(binary)
    if abs(angle) < 0.25:
        return img

    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def normalize_contrast(img: np.ndarray) -> np.ndarray:
    """Sararmış kâğıtta soluk daktilo izini belirginleştirir."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    lightness, a, b = cv2.split(lab)
    lightness = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lightness)
    return cv2.cvtColor(cv2.merge([lightness, a, b]), cv2.COLOR_LAB2BGR)


def find_body_column(img: np.ndarray) -> tuple[int, int] | None:
    """Antedi gövdeden ayıran dikey çizgiyi bulur.

    Bu evrakta matbu antedin sol sütunu, gövdeden tam boy bir dikey çizgiyle
    ayrılmış. Çizginin (x, üst_y) konumunu döndürür; üst_y aynı zamanda üstteki
    antet bandının bittiği yerdir. Antetsiz sayfalarda böyle bir çizgi
    olmadığı için None döner ve sayfa bütün bırakılır.
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

    # Sadece sayfa yüksekliğinin yarısını aşan dikey çizgiler kalsın.
    vertical = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, h // 2))
    )

    # Ayırıcı çizgi sol yarıdadır; sayfa kenarındaki tarama gölgesini eleriz.
    search_start, search_end = int(w * 0.10), int(w * 0.50)
    column_strength = vertical[:, search_start:search_end].sum(axis=0)
    if column_strength.size == 0 or column_strength.max() < 255 * (h * 0.5):
        return None

    split_x = search_start + int(column_strength.argmax())
    line_rows = np.flatnonzero(vertical[:, split_x])
    return split_x, int(line_rows[0])


def crop_to_body(img: np.ndarray, margin: int = 12) -> np.ndarray:
    """Antedin sol sütununu ve üst bandını atıp gövde metnini bırakır."""
    found = find_body_column(img)
    if found is None:
        return img

    split_x, top_y = found
    return img[max(top_y - margin, 0) :, split_x + margin :]


def prepare_array(img: np.ndarray, *, strip_stamps: bool = True, body_only: bool = True) -> np.ndarray:
    """Bellekteki bir sayfa görüntüsünü OCR'a hazır hale getirir."""
    if strip_stamps:
        img = remove_red_stamps(img)

    # Kırpma önce yapılmalı: antedi ayıran dikey çizgi, sayfa döndürüldükten
    # sonra artık dikey olmadığı için bulunamıyor.
    #
    # Görüntüyü OCR öncesi büyütmek denendi ve reddedildi: bazı rakamları
    # düzeltirken başkalarını bozuyor, net kazanç vermiyor.
    # Ölçüm için tests/olcek_kiyas.py.
    if body_only:
        img = crop_to_body(img)

    return normalize_contrast(deskew(img))


def prepare(path: Path, **kwargs) -> np.ndarray:
    """Diskteki bir sayfayı OCR'a hazır hale getirir."""
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Görüntü okunamadı: {path}")
    return prepare_array(img, **kwargs)
