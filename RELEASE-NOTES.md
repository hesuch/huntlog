# Huntlog 0.6.5

## Novidades

- Importação de party: loots e gastos somente dos personagens cadastrados em Meu perfil. Se nenhum nome coincidir, o programa avisa. O lucro é calculado pelos itens selecionados, sem atribuir o lucro total da party a uma pessoa.
- Bosses da party continuam sendo reconhecidos mesmo quando a derrota é atribuída a outro integrante. Os demais Pokémon são filtrados pelos personagens do perfil.
- Terror Zoroark conta uma vez quando houver dano causado a ele, mesmo sem aparecer em Enemies Defeated. Não duplica um registro de derrota existente.
- Cada Pokémon raro tem uma caixa Incluir na revisão da importação e em Editar hunt. Desmarque apenas os que não devem contar. A escolha é preservada no backup e na reimportação da mesma sessão, sem alterar loots ou lucro.
- O atualizador agora usa a validação nativa de certificados do Windows e apresenta uma mensagem mais clara quando não consegue validar a conexão segura.

## Como atualizar

No aplicativo, abra Atualizações → Verificar atualizações.

Se a versão antiga apresentar CERTIFICATE_VERIFY_FAILED, baixe este ZIP pelo navegador uma vez. Feche o Huntlog, extraia todo o ZIP para uma nova pasta e abra Huntlog.exe. Mantenha _internal junto do executável. Os dados continuam na mesma pasta do usuário do Windows.

Quem atualiza de uma versão anterior à 0.6.4 pode precisar finalizar o Huntlog no Gerenciador de Tarefas e abri-lo novamente uma última vez, caso a janela fique oculta.

Faça um backup antes de atualizar. Esta versão mantém a correção de reinício da 0.6.4.
