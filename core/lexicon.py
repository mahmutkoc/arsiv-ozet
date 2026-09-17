"""Türkçe kelime denetimi için macOS'un yerleşik yazım denetleyicisi.

Ayrı bir sözlük indirmek yerine sistemde hazır olanı kullanıyoruz. Denetim
Swift ile yapılıyor; kelime başına süreç açmak çok yavaş olacağı için
bütün kelimeler tek seferde sorulup sonuç önbelleğe alınıyor.

Denetleyici dönem imlasını ("vucud", "mıntaka") geçersiz sayar. Bu yüzden
sözlük yalnızca "bu birleşim gerçek bir kelime mi" sorusuna cevap vermek
için kullanılır; geçersiz diye bir kelimeyi düzeltmek için değil.
"""

from __future__ import annotations

import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

SWIFT_CHECKER = r"""
import AppKit
let checker = NSSpellChecker.shared
while let line = readLine() {
    let word = line.trimmingCharacters(in: .whitespaces)
    if word.isEmpty { print("0"); continue }
    let range = checker.checkSpelling(
        of: word, startingAt: 0, language: "tr",
        wrap: false, inSpellDocumentWithTag: 0, wordCount: nil
    )
    print(range.location == NSNotFound ? "1" : "0")
}
"""


@lru_cache(maxsize=1)
def _available() -> bool:
    """Türkçe denetleyici bu makinede var mı?"""
    try:
        result = subprocess.run(
            ["swift", "-e", "import AppKit; print(NSSpellChecker.shared.availableLanguages.contains(\"tr\"))"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return "true" in result.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def check_words(words: list[str]) -> dict[str, bool]:
    """Kelimelerin Türkçe sözlükte olup olmadığını toplu sorar.

    Denetleyici yoksa hepsi bilinmiyor (False) kabul edilir; çağıran taraf
    bu durumda hiçbir birleştirme yapmaz, yani sessizce güvenli tarafa düşer.
    """
    unique = sorted({w for w in words if w})
    if not unique or not _available():
        return {}

    # Betik dosyaya yazılıyor: `swift -` stdin'i betik olarak okuduğu için
    # betikle veriyi aynı akıştan veremiyoruz, kelimeler stdin'de kalmalı.
    with tempfile.NamedTemporaryFile("w", suffix=".swift", delete=False) as script:
        script.write(SWIFT_CHECKER)
        script_path = script.name

    try:
        result = subprocess.run(
            ["swift", script_path],
            input="\n".join(unique) + "\n",
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    finally:
        Path(script_path).unlink(missing_ok=True)

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip() in {"0", "1"}]
    if len(lines) != len(unique):
        return {}

    return {word: flag == "1" for word, flag in zip(unique, lines)}
