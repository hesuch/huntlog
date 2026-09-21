# Huntlog

Diário de hunts do PXG para Windows. Histórico local, preços por sessão, Hunts, Terrors, Mystery Dungeons, perfil com vários personagens, resumo semanal e exportação de imagem.

## Baixar e atualizar

Abra [a versão mais recente](https://github.com/hesuch/huntlog/releases/latest), baixe **Huntlog-Desktop-Windows.zip**, extraia tudo e abra **Huntlog.exe**. Feche a versão anterior antes de atualizar. Mantenha `_internal` junto do executável.

Os dados ficam em `%LOCALAPPDATA%\HuntlogDesktop`, fora da pasta do programa. Faça backup antes de atualizar. O pacote distribuído começa vazio e não inclui histórico, fotos pessoais nem preços particulares.

O repositório é público. No aplicativo desktop, use **Atualizações → Verificar atualizações**. A instalação pede confirmação, cria um backup e reinicia o Huntlog, preservando seus dados. A partir da 0.6.3, a janela também mostra as novidades da próxima versão. Quem usa a versão web deve atualizar os arquivos manualmente.

Veja as novidades em [RELEASE-NOTES.md](RELEASE-NOTES.md).

## Publicar uma versão

1. Atualize o código e `version.txt` (exemplo: `0.6.1`).
2. Abra **Actions → Publicar versão Windows → Run workflow**.
3. Aguarde a compilação e os testes. O workflow publica um ZIP e seu SHA-256 em Releases.

Não é necessário cadastrar senha ou token pessoal no aplicativo. O workflow usa apenas a permissão temporária do próprio GitHub Actions.

## Compilar localmente

Instale Python 3.12 de 64 bits. No PowerShell, execute `./Compilar.ps1`.

Os arquivos de interface e imagens ficam versionados em `assets.zip`, que é descompactado por `prepare.py`. Para atualizá-los, substitua os arquivos correspondentes dentro desse ZIP. Eles não contêm dados do diário.

## Recursos de terceiros

Imagens da Wiki PXG e do pacote de Pokémon fornecido para o projeto. Pokémon pertence aos respectivos titulares. Não há afiliação oficial com PokeXGames ou Nintendo. As licenças de Qt/PySide, Python e html2canvas acompanham a distribuição. Não se concede licença sobre marcas ou artes de terceiros.
