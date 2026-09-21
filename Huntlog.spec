from pathlib import Path
import sys

project = Path(SPECPATH)
a = Analysis(
    [str(project / 'desktop.py')],
    pathex=[], binaries=[],
    datas=[(str(project / 'static'), 'static'), (str(project / 'exemplo.json'), '.')],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[], noarchive=False, optimize=0,
)

# These are Windows components. A foreign ICU copied from another application
# exports different symbols and prevents Qt from starting.
system_dlls = {'icuuc.dll', 'icuin.dll', 'ucrtbase.dll'}
clean_binaries = []
for destination, source, kind in a.binaries:
    name = Path(destination).name.lower()
    if name in system_dlls or name.startswith(('api-ms-win-', 'ext-ms-win-', 'icudt')):
        continue
    if name in {'libssl-3-x64.dll', 'libcrypto-3-x64.dll'}:
        python_dll = Path(sys.base_prefix) / 'DLLs' / name
        if python_dll.exists():
            source = str(python_dll)
    clean_binaries.append((destination, source, kind))
a.binaries = clean_binaries

# Widgets + WebEngine do not use the bundled QML UI modules. Keep Qt DLLs:
# WebEngine can link to QtQuick/Qml even when no QML interface is used.
def needed(entry):
    path = Path(entry[0]).as_posix().replace('\\', '/').lower()
    if '/qml/' in path or path.endswith('qtwebengine_devtools_resources.debug.pak'):
        return False
    if '/translations/' in path:
        name = path.rsplit('/', 1)[-1]
        return name in ('en-us.pak', 'pt-br.pak') or name.endswith(('_pt.qm', '_pt_br.qm', '_en.qm'))
    return True

a.datas = [entry for entry in a.datas if needed(entry)]
a.binaries = [entry for entry in a.binaries if needed(entry)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='Huntlog', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=True, console=False,
    disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None, icon=[str(project / 'huntlog.ico')],
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True,
               upx_exclude=[], name='Huntlog')
