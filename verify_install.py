import sys,subprocess,tempfile,shutil
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root))
import updater
with tempfile.TemporaryDirectory(prefix='huntlog-install-qa-', ignore_cleanup_errors=True) as temporary:
    base=Path(temporary); install=base/'install'; stage=base/'stage'; data=base/'data'
    install.mkdir();data.mkdir()
    (install/'Huntlog.exe').write_text('old version marker')
    (install/'_internal').mkdir();(install/'_internal/old-marker').write_text('old')
    (data/'diary-marker').write_text('do not change')
    shutil.copytree(root/'dist/Huntlog',stage)
    script=base/'install.ps1';script.write_text(updater.INSTALL_SCRIPT,encoding='utf-8-sig')
    result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-Install',str(install),'-Stage',str(stage),'-Data',str(data),'-ParentId','999999','-NoRestart'],capture_output=True,text=True,timeout=150)
    assert result.returncode==0,(result.stdout,result.stderr)
    message=(data/'update-result.txt').read_text(encoding='utf-8-sig')
    assert 'sucesso' in message,message
    assert (data/'diary-marker').read_text()=='do not change'
    assert (install/'Huntlog.exe').stat().st_size>100000
    assert list(install.glob('update-rollback-*/_internal/old-marker'))
    print('Instalacao real, abertura da nova versao e preservacao de dados: OK')
    print(next(stage.glob('qa-*/self-test.json')).read_text(encoding='utf-8'))
