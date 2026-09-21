from pathlib import Path
import zipfile, re
root = Path(__file__).resolve().parent
version = (root / "version.txt").read_text().strip()
if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
    raise ValueError("Use uma versão como 0.6.0")
with zipfile.ZipFile(root / "assets.zip") as z:
    for name in z.namelist():
        target = (root / name).resolve()
        if not target.is_relative_to(root / "static"):
            raise ValueError("Caminho inválido no pacote de interface")
    z.extractall(root)
p = root / "app.py"
p.write_text(re.sub(r'APP_VERSION = "[^"]+"', f'APP_VERSION = "{version}-desktop"', p.read_text(encoding="utf-8")), encoding="utf-8")
p = root / "static/index.html"
p.write_text(re.sub(r'v[0-9]+\.[0-9]+\.[0-9]+', 'v' + version, p.read_text(encoding="utf-8")), encoding="utf-8")
print("Interface preparada:", version)
