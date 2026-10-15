"""İzin listesiyle, özel verileri ve Git geçmişini içermeyen ZIP üretir."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
output = Path(sys.argv[1]).resolve()
files = [root / name for name in (
    "app.py", "ozet.py", "ui.css", "requirements.txt",
    ".streamlit/config.toml", "tasarim-ornekleri/kurum-logo.png",
)]
files += sorted((root / "core").glob("*.py"))
files += sorted((root / "tests").glob("test_*.py"))
files += sorted((root / "deploy/linux").glob("*"))
manifest = {}
with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
    for file in files:
        if not file.is_file() or file.is_symlink():
            raise RuntimeError(f"Beklenmeyen dosya: {file}")
        name = file.relative_to(root).as_posix()
        content = file.read_bytes()
        manifest[name] = hashlib.sha256(content).hexdigest()
        archive.writestr(name, content)
    archive.writestr("SHA256-MANIFEST.json", json.dumps(manifest, indent=2))
print(f"{output}: {len(manifest)} dosya; SHA256 {hashlib.sha256(output.read_bytes()).hexdigest()}")
