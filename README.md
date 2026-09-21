# Huntlog

Diário de hunts do PXG para Windows. Histórico local, preços por sessão, Hunts, Terrors, Mystery Dungeons, perfil com vários personagens, resumo semanal e exportação de imagem.

## Baixar e atualizar

Abra [a versão mais recente](https://github.com/hesuch/huntlog/releases/latest), baixe **Huntlog-Desktop-Windows.zip**, extraia tudo e abra **Huntlog.exe**. Feche a versão anterior antes de atualizar. Mantenha `_internal` junto do executável.

Os dados ficam em `%LOCALAPPDATA%\HuntlogDesktop`, fora da pasta do programa. Faça backup antes de atualizar. O pacote distribuído começa vazio e não inclui histórico, fotos pessoais nem preços particulares.

Este repositório é privado: somente o proprietário e as pessoas convidadas têm acesso aos arquivos e Releases. A partir da versão 0.6.1, use o menu Atualizações > Verificar atualizações. Ao abrir, o aplicativo também consulta novas versões. A instalação exige sua confirmação, gera um backup e reinicia o Huntlog. Enquanto este repositório estiver privado, a consulta sem login não estará disponível. Quem usa a versão 0.6.0 precisa baixar a 0.6.1 manualmente uma vez. A atualização substitui apenas Huntlog.exe e _internal; os dados pessoais ficam intactos. Se o teste de abertura falhar, a versão anterior é restaurada. A cópia anterior do programa fica em update-rollback-* na pasta de instalação.

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
