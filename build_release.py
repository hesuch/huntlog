from pathlib import Path
import hashlib, importlib.metadata, json, shutil, subprocess, sys, tempfile, zipfile
root = Path(__file__).resolve().parent
subprocess.run([sys.executable, str(root / "prepare.py")], cwd=root, check=True)
subprocess.run([sys.executable, "-m", "unittest", "discover", "-p", "test_*.py"], cwd=root, check=True)
subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "Huntlog.spec"], cwd=root, check=True)
release = root / "dist/Huntlog"
with tempfile.TemporaryDirectory(prefix="huntlog-qa-") as temp:
    subprocess.run([str(release / "Huntlog.exe"), "--self-test", "--data-dir", temp], check=True, timeout=90)
    assert json.loads((Path(temp) / "self-test.json").read_text(encoding="utf-8"))["ok"]
shutil.copy2(root / "LEIA-ME.txt", release / "LEIA-ME.txt")
shutil.copy2(root / "README.md", release / "README.md")
shutil.copy2(root / "FONTES.txt", release / "FONTES.txt")
shutil.copy2(root / "RELEASE-NOTES.md", release / "NOVIDADES.md")
licenses = release / "licencas"
licenses.mkdir(exist_ok=True)
with zipfile.ZipFile(root / "third-party-notices.zip") as z:
    z.extractall(licenses)
shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", licenses / "Python.txt")
for name in ("PyInstaller", "PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "truststore"):
    dist = importlib.metadata.distribution(name)
    dest = licenses / name
    dest.mkdir(exist_ok=True)
    (dest / "PACKAGE-METADATA.txt").write_text(dist.read_text("METADATA") or "", encoding="utf-8")
    for file in dist.files or []:
        if "/licenses/" in str(file).lower():
            shutil.copy2(dist.locate_file(file), dest / Path(str(file)).name)
source_names = ["updater.py", "test_updater.py", "app.py", "desktop.py", "wiki_assets.py", "exemplo.json", "huntlog.ico", "assets.zip", "third-party-notices.zip", "Huntlog.spec", "requirements-build.txt", "prepare.py", "build_release.py", "test_release.py", "test_pending_release.py", "test_energy.py", "test_interface.cjs", "RELEASE-NOTES.md", "Compilar.ps1", "README.md", "LEIA-ME.txt", "version.txt", "FONTES.txt"]
with zipfile.ZipFile(release / "codigo-fonte.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for name in source_names:
        z.write(root / name, name)
assert not any(p.suffix in (".sqlite3", ".sqlite", ".db", ".log") for p in release.rglob("*"))
assert not (release / "_internal/icuuc.dll").exists()
output = root / "release"
output.mkdir(exist_ok=True)
archive = output / "Huntlog-Desktop-Windows.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
    for p in release.rglob("*"):
        if p.is_file():
            z.write(p, Path("Huntlog") / p.relative_to(release))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
archive.with_suffix(".zip.sha256.txt").write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+"  "+archive.name+"\n", encoding="utf-8")
print("Release pronta:", archive)
