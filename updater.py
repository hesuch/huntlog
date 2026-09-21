"""Public GitHub release updater; never writes to the user's diary directory."""
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO = 'hesuch/huntlog'
ASSET = 'Huntlog-Desktop-Windows.zip'

def version(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-desktop)?', value)
    if not match:
        raise ValueError('Versão inválida')
    return tuple(map(int, match.groups()))

def read_url(url, limit):
    request = urllib.request.Request(url, headers={'User-Agent': 'Huntlog-Updater', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        result = response.read(limit + 1)
    if len(result) > limit:
        raise ValueError('Arquivo maior que o limite permitido')
    return result

def latest(current):
    try:
        release = json.loads(read_url(f'https://api.github.com/repos/{REPO}/releases/latest', 1_000_000))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ValueError('As atualizações ainda não estão públicas no GitHub. Você pode continuar usando esta versão.') from error
        raise
    if release.get('draft') or release.get('prerelease') or version(release['tag_name']) <= version(current):
        return None
    assets = {a['name']: a['browser_download_url'] for a in release['assets']}
    for name in (ASSET, ASSET + '.sha256.txt'):
        expected = f"https://github.com/{REPO}/releases/download/{release['tag_name']}/{name}"
        if assets.get(name) != expected:
            raise ValueError('Esta versão ainda não tem um pacote completo de atualização')
    return {'tag': release['tag_name'], 'assets': assets}

def extract(archive, destination):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive) as package:
        if sum(i.file_size for i in package.infolist()) > 3_000_000_000:
            raise ValueError('Pacote descompactado muito grande')
        for info in package.infolist():
            target = (destination / info.filename).resolve()
            if not target.is_relative_to(destination / 'Huntlog') or ':' in info.filename or '\\' in info.filename or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Caminho inválido na atualização')
        package.extractall(destination)
    root = destination / 'Huntlog'
    if not (root / 'Huntlog.exe').is_file() or not (root / '_internal').is_dir():
        raise ValueError('Atualização incompleta')
    return root

def download(release):
    work = Path(tempfile.mkdtemp(prefix='huntlog-update-'))
    try:
        checksum = read_url(release['assets'][ASSET + '.sha256.txt'], 1024).decode().split()[0]
        if not re.fullmatch('[0-9a-fA-F]{64}', checksum):
            raise ValueError('Checksum inválido')
        payload = read_url(release['assets'][ASSET], 600_000_000)
        if hashlib.sha256(payload).hexdigest() != checksum.lower():
            raise ValueError('O download não passou na verificação de integridade. Tente novamente.')
        archive = work / ASSET
        archive.write_bytes(payload)
        return extract(archive, work / 'staging')
    except Exception:
        shutil.rmtree(work)
        raise

INSTALL_SCRIPT = r'''
param([string]$Install,[string]$Stage,[int]$ParentId,[string]$Data,[switch]$NoRestart)
$ErrorActionPreference = 'Stop'
$Install = [IO.Path]::GetFullPath($Install)
$Stage = [IO.Path]::GetFullPath($Stage)
if (!(Test-Path -LiteralPath (Join-Path $Install 'Huntlog.exe')) -or !(Test-Path -LiteralPath (Join-Path $Stage 'Huntlog.exe'))) { exit 2 }
$oldProcess = Get-Process -Id $ParentId -ErrorAction SilentlyContinue
if ($oldProcess -and !$oldProcess.WaitForExit(120000)) { exit 3 }
$rollback = Join-Path $Install ('update-rollback-' + [guid]::NewGuid().ToString('N'))
$qa = Join-Path $Stage ('qa-' + [guid]::NewGuid().ToString('N'))
$moved = @()
$installed = @()
try {
    New-Item -ItemType Directory -Path $rollback | Out-Null
    foreach ($name in @('Huntlog.exe', '_internal')) {
        $target = Join-Path $Install $name
        Move-Item -LiteralPath $target -Destination (Join-Path $rollback $name)
        $moved += $name
        Move-Item -LiteralPath (Join-Path $Stage $name) -Destination $target
        $installed += $name
    }
    $test = Start-Process -FilePath (Join-Path $Install 'Huntlog.exe') -ArgumentList @('--self-test','--data-dir',('"' + $qa + '"')) -WindowStyle Hidden -PassThru
    if (!$test.WaitForExit(90000)) { $test.Kill(); throw 'Tempo limite no teste da atualização' }
    if ($test.ExitCode -ne 0) { throw 'A nova versão falhou no teste de abertura' }
    'Atualização instalada com sucesso.' | Set-Content -LiteralPath (Join-Path $Data 'update-result.txt') -Encoding UTF8
} catch {
    $failure = $_.Exception.Message
    foreach ($name in $installed) {
        Move-Item -LiteralPath (Join-Path $Install $name) -Destination (Join-Path $Stage ('failed-' + $name))
    }
    foreach ($name in $moved) {
        Move-Item -LiteralPath (Join-Path $rollback $name) -Destination (Join-Path $Install $name)
    }
    ('Atualização cancelada; versão anterior restaurada. ' + $failure) | Set-Content -LiteralPath (Join-Path $Data 'update-result.txt') -Encoding UTF8
}
if (!$NoRestart) { Start-Process -FilePath (Join-Path $Install 'Huntlog.exe') -ArgumentList @('--data-dir',('"' + $Data + '"')) -WindowStyle Hidden }
'''

def launch_install(stage, executable, data, pid):
    install = Path(executable).resolve().parent
    # Check permissions before asking the running application to close.
    with tempfile.TemporaryFile(dir=install):
        pass
    script = Path(stage).parent / 'install.ps1'
    script.write_text(INSTALL_SCRIPT, encoding='utf-8-sig')
    return subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                             '-Install', str(install), '-Stage', str(stage), '-ParentId', str(pid), '-Data', str(data)],
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
