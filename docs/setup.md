# Instalação, percurso REAL e recuperação

O [README](../README.md#quick-start) traz a sequência curta de comandos. Este
guia detalha a instalação por sistema operacional, o percurso REAL passo a
passo com resultados esperados, a aprovação local, a recuperação e a operação
manual. Ele usa a planilha original versionada em `doc-specs/`, seu modelo e o
Hermes Desktop.

- [Versão e instalação do Hermes](#dependencias)
  - [Windows — PowerShell](#windows-powershell)
  - [macOS — zsh](#macos-zsh)
  - [Linux — bash](#linux-bash)
- [Percurso REAL passo a passo](#percurso-real)
- [Problemas comuns de execução](#problemas)
- [Comandos e arquivos locais](#comandos)
- [Pesquisa real e termos públicos](#pesquisa)
- [Aprovação local](#aprovacao-local)
- [Retomada e recuperação](#recuperacao)
- [Importação manual](#despensa)
- [Simulação opcional](#demo-portatil)
- [Conferência da planilha original](#teste-do-original)

<a id="dependencias"></a>
## Versão e instalação do Hermes

O plugin de pesquisa verifica **Hermes 0.23.1** e o commit completo
`3b421578588243f920886e6fe79a6faa87ea026e` na inicialização. A conexão MCP sozinha
não comprova que esse plugin carregou. Não retire a verificação para aceitar outra versão.

Consulte a [instalação oficial](https://hermes-agent.nousresearch.com/docs/getting-started/installation)
e o [Desktop oficial](https://hermes-agent.nousresearch.com/docs/user-guide/desktop).
Instaladores sem versão explícita podem entregar outra versão. Os exemplos abaixo
usam a opção de commit do instalador por código-fonte; são destinados a uma
**instalação nova**. Se já tem Hermes pessoal incompatível, não reinstale por cima:
use uma instalação isolada/conta de teste ou valide a compatibilidade separadamente.
O perfil isola dados e configuração, mas não isola a versão nem dependências do host.

Python 3.13 não precisa ser instalado à parte: `uv sync --locked --python 3.13`
usa um Python 3.13 existente ou baixa uma versão gerenciada pelo uv. Os comandos
`uv run …` do projeto são iguais nos três sistemas; as diferenças estão na
instalação das ferramentas e nos detalhes abaixo.

| Sistema | O que foi executado neste projeto |
| --- | --- |
| Windows | Onboarding REAL com a planilha original, [jornada REAL no Desktop](verification-desktop-real.md) até a viabilidade, [jornada `SIMULATION`](verification-desktop-e2e.md) completa, testes e CI do núcleo/MCP. |
| macOS | Somente a CI do núcleo/MCP (runner arm64). Instalação do Hermes, onboarding e Desktop não testados. |
| Linux | Somente a CI do núcleo/MCP (runner x64). Instalação do Hermes, onboarding e Desktop não testados. |

<a id="windows-powershell"></a>
### Windows — PowerShell

1. Instale o Git ([download](https://git-scm.com/downloads) ou `winget install --id Git.Git -e`)
   e o uv pelo [instalador oficial](https://docs.astral.sh/uv/getting-started/installation/):

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. Em uma pasta de trabalho local, baixe o instalador oficial do Hermes e
   execute-o com o commit compatível:

   ```powershell
   Invoke-WebRequest https://hermes-agent.nousresearch.com/install.ps1 -OutFile install-hermes.ps1
   & ./install-hermes.ps1 -Commit 3b421578588243f920886e6fe79a6faa87ea026e
   ```

3. Reabra o terminal e confira `git --version`, `uv --version` e `hermes --version`.

- Os comandos do README funcionam em PowerShell 7 e no Windows PowerShell 5.1.
  A exceção são argumentos JSON passados ao `hermes config set`: o 5.1 remove
  as aspas internas. Veja [argumentos JSON no PowerShell](#json-powershell).
- Para abrir o guia interativo: `start docs\demo\hermes-desktop-walkthrough.html`.
- Se o pytest recusar a pasta temporária padrão (`WinError 5`), use
  `--basetemp` conforme a [nota do README](../README.md#validar).

<a id="macos-zsh"></a>
### macOS — zsh

1. Instale o Git com `xcode-select --install` (Command Line Tools) ou
   `brew install git`, e o uv com `curl -LsSf https://astral.sh/uv/install.sh | sh`
   ou `brew install uv`.
2. Para uma instalação nova do Hermes:

   ```sh
   curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o install-hermes.sh
   bash install-hermes.sh --commit 3b421578588243f920886e6fe79a6faa87ea026e
   ```

3. Abra um novo terminal e confira `git --version`, `uv --version` e `hermes --version`.

- A [documentação do Desktop](https://hermes-agent.nousresearch.com/docs/user-guide/desktop)
  indica suporte a macOS com Apple Silicon. Este projeto não testou o Desktop no macOS.
- Por padrão, o zsh interativo não trata `#` como comentário: cole os comandos
  sem linhas de comentário.
- Para abrir o guia interativo: `open docs/demo/hermes-desktop-walkthrough.html`.
- Para o fluxo opcional `scripts/demo.py`, use `python3` se `python` não existir.

<a id="linux-bash"></a>
### Linux — bash

1. Instale o Git pelo gerenciador da sua distribuição (por exemplo,
   `sudo apt install git` no Debian/Ubuntu) e o uv com
   `curl -LsSf https://astral.sh/uv/install.sh | sh`.
2. Para uma instalação nova do Hermes:

   ```sh
   curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o install-hermes.sh
   bash install-hermes.sh --commit 3b421578588243f920886e6fe79a6faa87ea026e
   ```

3. Abra um novo terminal e confira `git --version`, `uv --version` e `hermes --version`.

- O Desktop exige uma sessão gráfica. A documentação oficial lista Linux entre
  as plataformas suportadas; este projeto não o testou no Linux.
- Para abrir o guia interativo: `xdg-open docs/demo/hermes-desktop-walkthrough.html`.
- Para o fluxo opcional `scripts/demo.py`, use `python3` se `python` não existir.

Os instaladores oficiais aceitam o commit (`-Commit` no PowerShell, `--commit`
no bash). O `install.sh` atende Linux e macOS; no Windows, use `install.ps1`.
A instalação Desktop por pacote
pode usar outro backend: confira também a identidade do backend efetivo da sessão.
Não atualize automaticamente uma instalação homologada antes da demonstração.
Windows, Linux, macOS e WSL possuem caminhos e requisitos próprios; a matriz
oficial do Hermes determina o suporte de arquitetura. WSL não comprova Windows nativo.

No checkout da aplicação, `uv sync --locked --python 3.13` cria `.venv`.
O Python gerenciado pelo Hermes é independente. O primeiro `desktop` pode construir
a interface e instalar componentes do host; reserve tempo para esse preparo.

<a id="percurso-real"></a>
## Percurso REAL passo a passo

Este é o percurso oficial e reproduzível: **planilha original → seu modelo no Hermes → pesquisa web → conversa no Desktop → aprovação local → cardápio e preço**. Não usa respostas gravadas nem credenciais da autora. Mantenha dois canais abertos: o Desktop, para conversar, e um terminal, para revisar propostas.

> [!IMPORTANT]
> O plugin de pesquisa suporta **Hermes 0.23.1, commit `3b421578588243f920886e6fe79a6faa87ea026e`**. O lock Python não fixa o Hermes. Outra versão é recusada pelo plugin até validação de compatibilidade; instalar simplesmente a versão mais recente não garante funcionamento. Siga a [instalação do seu sistema](#dependencias) e não substitua uma instalação pessoal para seguir o tutorial. Custos e autenticação do modelo dependem do provedor escolhido; **o modelo e o provedor de pesquisa são configurações diferentes**.

<a id="requisitos"></a>
### 1. Clone o repositório

```sh
git clone https://github.com/glaucia86/sabor-da-maria-hermes-agent.git
cd sabor-da-maria-hermes-agent
```

Confira antes `git --version`, `uv --version` e `hermes --version`. Todos os comandos seguintes partem desta pasta.

<a id="instalacao-local"></a>
### 2. Instale as dependências da aplicação

```sh
uv sync --locked --python 3.13
```

**Esperado:** ambiente `.venv` criado e dependências instaladas pelo lock. O runtime Python do Hermes é separado; não instale as dependências da aplicação nele. Não é necessário Docker.

<a id="planilha"></a>
### 3. Prepare a planilha original

A entrada padrão é a planilha original do desafio, versionada em [`doc-specs/despensa_dona_maria.xlsx`](../doc-specs/despensa_dona_maria.xlsx). O projeto **não altera esse arquivo**: o passo 4 o lê, copia para `artifacts/private/local/inventory.xlsx`, fora do Git, e trabalha somente sobre a cópia. Confira a integridade do original:

```sh
uv run --locked --no-sync python -c "import hashlib; print(hashlib.sha256(open('doc-specs/despensa_dona_maria.xlsx', 'rb').read()).hexdigest())"
```

**Esperado:** `56df15d6fd2da64901534b48124ab1da43428849e019607577ead1211db3c8d2`. Um valor diferente indica arquivo alterado; restaure a versão do repositório com `git restore doc-specs/despensa_dona_maria.xlsx` antes de continuar.

Para avaliar com outra planilha real, copie-a para `artifacts/private/input/`, que também fica fora do Git, informe esse caminho no passo 4 e use um `--directory` novo. Ela precisa ter estas abas e cabeçalhos exatos:

| Aba | Cabeçalhos, na ordem |
| --- | --- |
| `Despensa` | `Ingrediente`, `Quantidade em estoque`, `Unidade` |
| `Precos` | `Ingrediente`, `Quantidade comprada`, `Unidade`, `Preço total pago (R$)` |

O importador preserva a origem por célula e aponta dados ausentes ou ambíguos. Não preencha lacunas com valores arbitrários. Os formatos de embalagem são explicados em [Da planilha ao preço](../README.md#precificacao).

<a id="setup-real"></a>
### 4. Prepare o atendimento REAL

```sh
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding setup-real --inventory "doc-specs/despensa_dona_maria.xlsx" --directory "artifacts/private/local"
```

**Esperado:** `context_mode: REAL`, 37 itens importados da planilha original, total histórico `663.39`, diagnósticos de custo e nenhuma decisão humana. O comando cria a cópia da planilha, o SQLite, os backups das migrações e o manifesto local. Confira que a cópia operacional está protegida do versionamento:

```sh
git check-ignore artifacts/private/local/inventory.xlsx
```

**Esperado:** o comando imprime esse caminho.

Use **o mesmo `--directory` em todas as etapas**. Repetir `setup-real` com o mesmo arquivo preserva o atendimento; outro arquivo ou contexto exige outra pasta. Não edite o manifesto nem reutilize um banco de simulação. Os identificadores são vinculados automaticamente; você não precisa copiá-los para a conversa.

<a id="configuracao-local"></a>
### 5. Configure o perfil e a pesquisa Exa

O percurso usa o **Exa pelo endpoint anônimo**, sem chave de API e sem fallback automático. O provedor `web-exa` acompanha o Hermes; não há componente opcional a instalar nem `EXA_API_KEY` a configurar. O endpoint anônimo tem cota e disponibilidade externas: uma falha deixa a pesquisa pendente, sem trocar de provedor. Não é necessário instalar um serviço de gateway para seguir este guia.

```sh
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding configure --directory "artifacts/private/local"
```

Informe ingredientes ou pratos públicos separados por vírgulas, por exemplo `arroz, feijão, frango`. Para seguir o guia interativo, inclua o que pretende pesquisar. Confira a lista exibida e digite `LIBERAR PESQUISA` somente se concordar. Apenas esses termos podem compor consultas de receitas ou ofertas; quantidades, preços históricos e a planilha inteira não são enviados pelo plugin. Para ampliar os termos depois, siga a [reconfiguração de pesquisa](#pesquisa).

**Esperado:** `configured: true`, perfil `sabor-real-…` e `research: CONFIGURED_NOT_EXERCISED`. O comando cria um perfil vazio e vincula MCP, política, pesquisa e skill, sem copiar credenciais pessoais. O nome do perfil serve para conferência no Desktop; os comandos do projeto o resolvem sozinhos.

### 6. Selecione e autentique o modelo

```sh
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding model --directory "artifacts/private/local"
```

No seletor do **seu Hermes**, escolha provedor e modelo com suporte a ferramentas e conclua a autenticação. Para modelo local, informe a conexão suportada pelo Hermes e mantenha seu servidor disponível. Nenhum modelo da autora é imposto; não cole chaves no chat, na planilha ou no repositório.

**Esperado:** seleção salva no perfil exclusivo. Para trocar de modelo, repita este comando, verifique o perfil e inicie uma nova conversa. A qualidade da elicitação pode variar por modelo; registre qual você avaliou.

<a id="verificar-local"></a>
### 7. Verifique o MCP, o perfil e a pesquisa

```sh
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding check --directory "artifacts/private/local"
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding verify-profile --directory "artifacts/private/local"
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding check-research --directory "artifacts/private/local"
```

**Esperado:**

- `check`: `mcp: PASS`, `context_mode: REAL` e zero decisões humanas. Confere as seis ferramentas MCP e a recusa de uma ferramenta proibida, sem usar LLM.
- `verify-profile`: configuração, plugins, skill e conexão MCP em `PASS`, além de `model_configured: true`. `credentials: NOT_CHECKED` e `host_dispatch_and_conversation: NOT_RUN` são intencionais: o diagnóstico não envia mensagem ao modelo.
- `check-research`: `research: LIVE_SEARCH_AND_EXTRACTION_PASS`, `provider: exa`, `authentication: ANONYMOUS` e `business_writes: false`. Busca `receita <primeiro termo liberado>` e extrai o primeiro resultado, sem gravar fontes, propostas ou decisões nem usar o modelo.

<a id="desktop-local"></a>
### 8. Abra o Hermes Desktop

```sh
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding desktop --directory "artifacts/private/local"
```

O comando repete a verificação e abre `hermes -p <perfil preparado> desktop --cwd <contexto preparado>`. Em uma instalação por código-fonte, o primeiro lançamento pode preparar os componentes do Desktop. Confira na interface o perfil `sabor-real-…` e mantenha o diretório de conversa preparado; não selecione o checkout como projeto. Na inspeção técnica do host, confira seis ferramentas MCP e duas de pesquisa; se faltar alguma, resolva a configuração antes de avaliar.

<a id="guia-html"></a>
### 9. Converse como Dona Maria com o guia interativo

Abra [`docs/demo/hermes-desktop-walkthrough.html`](demo/hermes-desktop-walkthrough.html) no navegador, conforme a [dica de abertura](../README.md#comece-aqui). Nele, você interpreta a Dona Maria e conversa em linguagem natural, copiando prompts em primeira pessoa, sem IDs, hashes ou comandos. Para este percurso, use o modo **Jornada completa — 14 etapas**. Depois da preparação, são 13 etapas de conversa: despensa, pesquisa Exa, escolha da receita, condições da cozinha, adaptação, plano de produção, viabilidade, compras, interesse, aceite, cenários de preço, seleção do cardápio e conferência final.

Cada etapa explica o objetivo, o que o agente faz, as ferramentas MCP envolvidas, o resultado esperado e como reconhecer que terminou. O seletor **REAL / SIMULATION** separa os prompts para os seus dados dos prompts usados no ensaio. Os apêndices trazem o fluxo de aprovação e a recuperação dos erros observados.

Sem o guia, comece por exemplo com:

> Quero planejar meu cardápio de lançamento. Consulte minha despensa e pesquise receitas reais que aproveitem os ingredientes. Tenho R$ 80 para complementos. Antes de aceitar um prato, me ajude a conferir se consigo prepará-lo.

**Esperado:** consulta da despensa importada, pesquisa com fontes e perguntas sobre preferências e condições reais. Informe seus equipamentos, habilidades e limitações verdadeiros; não confirme um cenário fictício só para avançar.

<a id="revisao-local"></a>
### 10. Revise as aprovações no segundo terminal

Quando o agente criar uma proposta, use outro terminal na raiz do repositório:

```sh
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding review --directory "artifacts/private/local" list
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding review --directory "artifacts/private/local" inspect ID_DA_PROPOSTA
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding review --directory "artifacts/private/local" approve ID_DA_PROPOSTA --hash HASH_DA_INSPECAO
```

Substitua `ID_DA_PROPOSTA` pelo identificador retornado por `list` e `HASH_DA_INSPECAO` pelo hash de `inspect`. Leia o resumo. Somente se ele corresponder ao que você realmente informou ou decidiu, digite **`ATESTO ` seguido do hash** no terminal. Para recusar, use `reject ID_DA_PROPOSTA --hash HASH_DA_INSPECAO` no lugar de `approve`.

Esse procedimento se repete nas mudanças que dependem de confirmação: receita, fatos, plano, interesse, aceite e escolha do preço. Aprove uma proposta por vez, espere `"ok": true` e só então volte ao Desktop e peça para consultar o estado atualizado. O agente não pode aprovar por você. Se você representar cozinheira e operadora, deixe os dois papéis explícitos. Propostas expiram em dez minutos; conteúdo ou estado alterado exige nova revisão. O [Apêndice A do guia](demo/hermes-desktop-walkthrough.html#apendice-a) detalha o que conferir em cada proposta.

<a id="persistencia"></a>
### 11. Confira a persistência e retome sem reimportar

Ao final, peça à consultora o que ficou salvo: prato, preço escolhido, sobra após taxa e ingredientes, pendências e saldo. No segundo terminal, `review list` não deve mostrar proposta pendente. O estoque físico não é baixado e nada é comprado.

Para retomar, feche a interface normalmente, repita o comando `desktop` do passo 8, confira o mesmo perfil e retome a sessão ou abra outra conversa pedindo o estado atual do cardápio. As decisões persistem no SQLite, independentemente do histórico do LLM. **Não execute outra importação para retomar.** A planilha original continua com o mesmo hash do passo 3.

<a id="problemas"></a>
## Problemas comuns de execução

| Sintoma | Próximo passo |
| --- | --- |
| `hermes` ou `uv` não encontrado | Reabra o terminal após instalar e confira o PATH. |
| Planilha ausente/inválida | Confira caminho entre aspas, abas, cabeçalhos e limite de 5 MiB. A aplicação não gera uma substituta. |
| Outra planilha/contexto ou pasta incompleta | Preserve a pasta; escolha outro `--directory`. Não edite manifesto ou banco. |
| Modelo ausente ou falha de autenticação | Repita `model` no mesmo diretório; autentique localmente. `model_configured` não prova credenciais válidas. |
| Pesquisa incompatível/indisponível | Confira versão/commit do Hermes, termos liberados e rede; execute `check-research`. Cota ou indisponibilidade do endpoint anônimo Exa deixa a pesquisa pendente. Não habilite busca livre como fallback. |
| Perfil REAL preparado com o provedor anterior | Execute `refresh-research` no mesmo diretório, reabra o Desktop e repita `check-research` e `verify-profile`. Não reimporte a planilha. Detalhes no [guia](#comandos). |
| Aprovação concluída, mas o agente ainda vê `PENDING` | A consulta pode ter ocorrido antes do commit. Aguarde `ok: true` no terminal e peça nova consulta do estado. |
| Termo desejado não foi liberado | Siga [como revisar termos](#pesquisa); não peça ao modelo para contornar a restrição. |
| Desktop mostra outro perfil ou ferramentas extras | Interrompa o atendimento e confira perfil/contexto. O catálogo esperado é seis MCP e duas de pesquisa. |
| Proposta expirada ou hash divergente | Consulte novamente o estado; peça uma proposta atual e faça nova inspeção. |
| Modelo afirma que salvou, mas o estado não mudou | Confira a revisão local e consulte `get_business_state`; texto do modelo não prova persistência. |

Para retomar sem reimportar, veja [Retomada e recuperação](#recuperacao).

<a id="comandos"></a>
## Comandos e arquivos locais

Todos os comandos são executados na raiz do repositório, pelo prefixo:

```sh
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding
```

Acrescente a ação abaixo e `--directory "artifacts/private/local"`.

| Ação | Efeito |
| --- | --- |
| `setup-real --inventory "CAMINHO.xlsx"` | Valida/copia sua planilha; cria banco REAL e migrações com backup. Mesmo arquivo e diretório reaproveitam o atendimento. |
| `check` | Confere MCP stdio, catálogo de seis e recusa de ferramenta não exposta; consulta estado, sem LLM. |
| `configure` | Solicita termos públicos, cria perfil exclusivo, copia plugins e prepara contexto/skill. Não escolhe modelo. |
| `model` | Abre o seletor nativo do Hermes no perfil correspondente; você escolhe e autentica. |
| `verify-profile` | Confere configurações, arquivos, skill, conexão MCP e registro dos plugins no gateway REAL. Não prova autenticação nem conversa. |
| `check-research` | Busca `receita <primeiro termo liberado>` e extrai o primeiro resultado no runtime do perfil REAL, pelo Exa anônimo. Não grava fontes nem decisões e não usa o modelo. |
| `refresh-research` | Somente em perfil REAL já preparado: copia o plugin de pesquisa do checkout e regrava a configuração de pesquisa (`plugins.enabled`, settings do plugin e `web.*`). Não reimporta a planilha, não altera o banco nem os termos de `research.json`. |
| `refresh-context` | Somente em perfil REAL já preparado: regrava `conversation/.hermes.md` com as orientações e a skill do checkout. Não abre o SQLite nem altera perfil, credenciais, plugins, pesquisa ou configurações. Veja [como atualizar](#atualizar-orientacoes). |
| `desktop` | Repete a verificação e abre o perfil/contexto preparados. Modelo ausente impede lançamento. |
| `review list/inspect/approve/reject` | Acessa a revisão local com banco/workspace já vinculados. |
| `review reviews NÚMERO_DA_RECEITA` | Somente leitura: mostra o texto integral vigente das revisões de categoria da receita, sem metadados de proveniência. Veja [justificativas vigentes](#justificativa-vigente). |
| `doctor` | Diagnostica executáveis e dependências; não configura nem autentica o modelo. |

O diretório privado contém `inventory.xlsx`, `workspace.sqlite3`, backups de
migração, `demo.json` (manifesto compartilhado pelo onboarding), `research.json`
(termos liberados) e `profile-ready.json`. O nome histórico `demo.json` não indica
simulação: `context_mode` e o banco precisam corresponder a `REAL`.
Não edite IDs, modo ou hashes para reutilizar outra base.

O perfil se chama `sabor-real-<identificador local>`. `configure` exibe seu nome;
os comandos do projeto o resolvem automaticamente. Caminhos e IDs ficam na
configuração local, nunca precisam ser informados pela cozinheira no chat.
As orientações e a skill são incorporadas ao `.hermes.md` de `conversation`,
fora do checkout. Assim o Desktop não depende da opção CLI `--skills` nem
carrega instruções de engenharia do repositório.

`platform_toolsets.cli` é a chave usada pelo backend consultado pelo Desktop
na versão examinada; não substitua por uma chave `desktop` presumida.
Conferir a configuração não substitui verificar o catálogo efetivo da sessão.

Os plugins devem usar `plugins.isolation: host`. No Hermes 0.23.1, o gateway
compartilhado pode já conter `dona_maria` de outra origem; o plugin recusa esse
conflito em vez de substituir módulos. O isolamento mantém um processo de
plugins por perfil, sem ampliar a allowlist.

Para atualizar a pesquisa de um perfil REAL existente (plugin do checkout e
provedor Exa), preserve a planilha e o SQLite e use o mesmo diretório:

```sh
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding refresh-research --directory "artifacts/private/local"
```

**Esperado:** `research: UPDATED_NOT_EXERCISED` e `business_writes: false`.
O comando exige `profile-ready.json` e recusa perfis `SIMULATION`.

Perfis preparados antes do isolamento de plugins também precisam destas duas
chaves, que `refresh-research` não altera:

```sh
hermes -p NOME_DO_PERFIL config set plugins.isolation host
hermes -p NOME_DO_PERFIL config set agent.disabled_toolsets '["desktop_ui"]'
```

No Windows PowerShell 5.1, escreva o segundo valor como `'[\"desktop_ui\"]'`
(veja [argumentos JSON no PowerShell](#json-powershell)).

Recarregue os plugins ou reinicie normalmente o gateway desse perfil e abra
uma nova conversa. Execute `check-research` e `verify-profile` antes do
atendimento; `verify-profile` consulta `plugins.list` no gateway que abre a
sessão e recusa registro ausente. Não reimporte a planilha nem recrie o banco
para corrigir esse problema.

<a id="atualizar-orientacoes"></a>
### Atualizar as orientações do Desktop REAL

Quando `.hermes.md` ou a skill mudam no checkout, `verify-profile` recusa o
perfil com "Orientações desatualizadas". `configure` não regrava um perfil já
preparado. Feche o Desktop desse perfil e, no mesmo diretório, execute:

```sh
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding refresh-context --directory "artifacts/private/local"
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding verify-profile --directory "artifacts/private/local"
```

**Esperado:** `conversation_context: UPDATED` e `business_writes: false`; uma
segunda execução retorna `UNCHANGED` sem regravar. Depois, `verify-profile`
em `PASS`; abra então uma nova conversa pelo `desktop`.

O comando exige `profile-ready.json` do mesmo perfil REAL, o vínculo MCP com o
banco e o workspace deste diretório e um `conversation/.hermes.md` regular
gerado pelo `configure`. Ele recusa, sem alterar nada, symlink, junção ou
caminho fora do perfil e arquivo sem a estrutura gerenciada: a primeira linha de
`.hermes.md` e exatamente um cabeçalho da skill `dona-maria-cardapio`. A
validação é só estrutural; edições manuais internas que preservem essa
estrutura são sobrescritas. Grava somente esse arquivo, por
substituição atômica; não abre o SQLite nem toca credenciais, plugins, pesquisa,
configurações ou decisões. O `verify-profile` seguinte continua consultando o
banco somente para leitura, como antes.

`plugins doctor dona-maria-mediated-research --ci` usa um home temporário sem
os settings do perfil nessa versão. Sua falha `SOURCE_NOT_CONFIGURED` não
comprova falha do perfil configurado. `SOURCE_CONFLICT` identifica a recusa
de um módulo de outra origem; os diagnósticos omitem caminhos e mensagens
internas. Confira a [verificação desta correção](verification-hermes-research.md).

`desktop_ui` fica excluído do catálogo enviado ao modelo, mesmo quando o Hermes
o acrescenta pela superfície Desktop. Os hooks continuam recusando chamadas
diretas às ferramentas excluídas; a exclusão não amplia nenhuma permissão.

<a id="pesquisa"></a>
## Pesquisa real e termos públicos

O percurso guiado usa o provedor Exa pelo endpoint anônimo, sem `EXA_API_KEY`.
`configure` habilita o plugin `web-exa`, distribuído com o Hermes, e grava
`web.search_backend: exa`, `web.provider_tier.exa: free` e
`web.keyless_fallback: false`. Não há componente opcional a instalar. Não
instale pacotes Hermes na `.venv` da aplicação.

O endpoint anônimo tem cota e disponibilidade externas. `check-research`
diagnostica a pesquisa ao vivo; uma falha não ativa outro provedor e não
grava fonte ou decisão. Tente mais tarde, sem habilitar busca livre.

`configure` pede termos separados por vírgula: apenas letras, espaços e hífens,
de 1 a 100 caracteres por termo, até 200 termos. Você vê a lista exata e precisa
digitar `LIBERAR PESQUISA`. O texto não é obtido automaticamente da planilha.
O plugin constrói consultas de receita/oferta a partir desses termos; não aceita
URL ou consulta livre produzida pelo modelo. O provedor pode estar indisponível ou
retornar resultados inadequados: registre a falha, sem inventar uma fonte.

Para **revisar os termos de um atendimento existente**, encerre a sessão e edite
somente os valores/entradas de `research.json` no seu diretório privado. O arquivo
é um objeto JSON com chaves como `termo-1` e valores como `arroz`; não altere outros
arquivos. A edição local representa sua autorização explícita dos novos termos.
Use o perfil exibido por `configure` neste comando (bash, zsh ou PowerShell 7):

```sh
hermes -p NOME_DO_PERFIL config set plugins.entries.dona-maria-mediated-research.settings.public_terms '{"termo-1":"arroz","termo-2":"feijão"}'
```

<a id="json-powershell"></a>
**Argumentos JSON no PowerShell.** O PowerShell 7 repassa o JSON entre aspas
simples sem alteração. O Windows PowerShell 5.1 remove as aspas duplas internas
ao chamar um executável e o valor chega como `{termo-1:arroz}`. Nele, escape
cada aspa interna:

```powershell
hermes -p NOME_DO_PERFIL config set plugins.entries.dona-maria-mediated-research.settings.public_terms '{\"termo-1\":\"arroz\",\"termo-2\":\"feijão\"}'
```

O comportamento das duas versões foi conferido com um executável Python que
imprime o argumento recebido; o `hermes` recebe argumentos pelo mesmo mecanismo.
No PowerShell 7, a forma escapada chegaria com as barras invertidas.

O objeto precisa ser **idêntico ao de `research.json`**. Depois execute
`verify-profile` e abra uma nova sessão via `desktop`. Divergência é recusada;
nenhum ajuste é feito pelo LLM. Para mudar de provedor, o exemplo
[hermes.s17.example.yaml](../config/hermes.s17.example.yaml) é referência técnica
de configuração manual, não uma opção homologada pelo onboarding Exa.

O estado `CONFIGURED_NOT_EXERCISED` significa configuração preparada. Somente
uma busca/extração reais na sessão comprovam pesquisa. O catálogo completo
esperado é seis ferramentas MCP mais `search_culinary_sources` e
`extract_culinary_source`, do plugin. Não habilite busca livre como fallback.

<a id="aprovacao-local"></a>
## Aprovação local

Siga o [passo 10 do percurso](#revisao-local) e o
[Apêndice A do guia interativo](demo/hermes-desktop-walkthrough.html#apendice-a): liste, inspecione e aprove
somente após conferir o resumo. O ID da proposta e seu hash são referências
do terminal do operador, não dados que a cozinheira precisa memorizar.
`approve` exige a digitação de `ATESTO <hash>`. Não automatize essa entrada.
`reject` registra a recusa local sem habilitar nenhuma capacidade ao modelo.

`review` impede sobrescrever o binding por argumentos e não executa migrações.
A revisão chama `ApprovalService` diretamente; o SQLite coordena a persistência
com o processo MCP. Não há uma chamada MCP de aprovação nem autenticação forte
da identidade da cozinheira. O operador atesta sua manifestação sobre conteúdo
exato; no teste, a mesma pessoa pode exercer ambos os papéis.

Proposta vencida, hash divergente ou premissa alterada exigem consulta do estado
e nova proposta/revisão. Aprovação repetida não duplica o efeito. Uma decisão
histórica não recupera validade perdida por alteração posterior.

<a id="justificativa-vigente"></a>
### Justificativa vigente de uma categoria

Uma alteração por categoria substitui a justificativa inteira, e o agente não
recebe esse texto. Quando ele pedir a leitura da justificativa vigente, consulte
no terminal do operador, somente para leitura:

```sh
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding review --directory "artifacts/private/local" reviews NÚMERO_DA_RECEITA
```

O número é a posição da receita na ordem de registro: a mesma referência
`recipe` do atendimento e a ordem de `recipes` no resumo de `review inspect`.
A saída mostra a versão da receita e, por categoria, `current`,
`requirement_keys`, o texto integral de `not_applicable_reason` e o tipo da
origem, sem eventos, evidências ou referências internas. Nada é gravado.
Leia o texto completo à cozinheira; ela manifesta a nova justificativa inteira,
preservando o que quiser manter. Só então o agente prepara a proposta, que você
inspeciona e aprova como de costume. Não copie trechos para o chat além do
necessário nem edite o banco.

<a id="recuperacao"></a>
## Retomada e recuperação

| Situação | Ação |
| --- | --- |
| Reinício normal | Use `desktop` com o mesmo `--directory` e perfil. Peça o estado atual. |
| Deseja outro modelo | Execute `model`, `verify-profile` e abra nova conversa no mesmo perfil/banco. |
| Deseja outra planilha | Execute `setup-real` em pasta nova; não substitua a cópia nem o manifesto. |
| Preparação interrompida antes do manifesto | Preserve a pasta para diagnóstico e use outra pasta nova. Não há limpeza destrutiva automática. |
| Perfil existe sem marcador de conclusão | Não é sobrescrito. Preserve-o e prepare outro diretório/perfil. |
| Configuração divergente | O diagnóstico nomeia a chave; revise-a localmente conforme a configuração esperada. Não substitua o YAML inteiro. |
| Código/skill mudou | No perfil REAL preparado, atualize as orientações com [`refresh-context`](#atualizar-orientacoes) e repita `verify-profile`. Não alegue que hashes antigos homologam arquivos novos. |
| Pesquisa indisponível ou perfil com provedor anterior | Execute `check-research`; se o perfil REAL foi preparado com o provedor anterior, use `refresh-research`, reabra o Desktop e verifique o perfil. |
| Aprovação concluída, mas o agente ainda vê `PENDING` | A consulta pode ter ocorrido antes do commit. Aguarde `ok: true` no terminal e peça nova consulta do estado. |
| Plugin incompatível | Confira versão e commit efetivos. Não desative o bloqueio nem alegue pesquisa a partir do MCP isolado. |
| Interface expõe detalhes privados na conversa normal | Não considere o canal aprovado; registre o comportamento observado. |

Não remova diretórios de perfil, banco ou dados do Hermes para tentar corrigir
uma falha. A limpeza é manual e posterior à identificação do atendimento que
você realmente deseja descartar. Bancos e credenciais permanecem fora do Git.

### Reconexão do perfil dedicado

No gateway, `/reload-mcp` pode preservar conexões já registradas. No perfil
dedicado, desabilite somente `mcp_servers.dona_maria.enabled`, recarregue,
reabilite e recarregue novamente. Confira catálogo e vínculo antes de atender.
Na instalação v0.23.1 observada em S19, a recarga compara nomes habilitados:
alterar somente `env` manteve o banco anterior. Confirme ausência de ferramentas
após desabilitar e o estado esperado após reconectar; “no server changes” ou
seis ferramentas, isoladamente, não comprovam troca de banco.

A ausência de ferramentas perigosas deve ser conferida no catálogo efetivo.
Uma skill builtin essencial pode permanecer no contexto conforme a versão;
isso não justifica habilitar shell, execução de código ou gestão de memória.
O contrato de leitura não autentica consentimento humano.

<a id="despensa"></a>
## Importação manual para diagnóstico

O percurso recomendado é `setup-real`, que inclui as migrações necessárias.
Para operadores que precisam somente importar um XLSX em uma pasta nova, copie
antes a planilha original para a entrada privada e crie a pasta do banco; o
original em `doc-specs/` fica intacto:

```sh
uv run --locked --no-sync python -c "import pathlib, shutil; pathlib.Path('artifacts/private/manual').mkdir(parents=True, exist_ok=True); pathlib.Path('artifacts/private/input').mkdir(parents=True, exist_ok=True); shutil.copy2('doc-specs/despensa_dona_maria.xlsx', 'artifacts/private/input/')"
uv run --locked --no-sync python -X utf8 -m dona_maria.bootstrap --database artifacts/private/manual/workspace.sqlite3 --inventory artifacts/private/input/despensa_dona_maria.xlsx --allowed-directory artifacts/private/input --context-mode REAL
```

Esse comando isolado não cria
perfil, plugins ou manifesto do onboarding; não misture os dois percursos.
Migrações explícitas são oferecidas pela CLI `dona_maria.approval_cli` com backup
novo (`migrate` e depois `migrate-research`). Os contratos são os mesmos usados
por `setup-real`; não há migração automática no startup MCP.

<a id="dados-sinteticos"></a>
<a id="demo-portatil"></a>
## Simulação opcional para testar o núcleo

```sh
python scripts/demo.py setup
uv run --locked --no-sync python -X utf8 scripts/demo.py check
```

Esse fluxo histórico cria somente arroz em `artifacts/private/demo-s20`, modo
`SIMULATION`, sem pesquisa. Não usa a planilha original e não é o percurso completo
do avaliador. Os comandos `configure`, `model`, `chat` e `review` desse modo
continuam disponíveis para diagnóstico assistido; não promovem a base a REAL.
Em sistemas sem `python`, use `python3` no primeiro comando.

O onboarding atual **não configura pesquisa em perfis `SIMULATION`**:
`configure` habilita somente o MCP e a política, e `refresh-research` exige
REAL. Se a pesquisa for acrescentada manualmente, `verify-profile` e `desktop`
recusam o perfil por divergência de configuração; `check-research` só pode
diagnosticar uma configuração já feita à mão. A
[jornada E2E assistida](verification-desktop-e2e.md) usou um perfil
`SIMULATION` completado dessa forma; o procedimento não faz parte do percurso
reproduzível do avaliador.

### Agent Evals integrados S19

Para a versão integrada S19, consulte o
[CLI de evidências](../evals/README.md#jornada-integrada-s19). `prepare` cria um
banco sintético schema3 já migrado; não execute novamente `migrate` nesse banco.
Configuração, catálogo e atestações no Hermes continuam sendo passos humanos
separados. Resultados históricos não aprovam a versão integrada.

Os 18 casos foram concluídos no recorte CLI assistido registrado na
[matriz S19](../evals/s19-results.json), com tentativas e limitações preservadas.
Isso não homologa o novo perfil S20 nem o canal Desktop. Após integrar as
orientações e os plugins, prepare outro atendimento e repita o preflight;
configuração e bytes conferidos antes da integração são evidências históricas.

<a id="teste-do-original"></a>
## Conferência da planilha original

A planilha original do desafio é versionada em `doc-specs/despensa_dona_maria.xlsx`
e é a entrada padrão do README. SHA-256 esperado:
`56df15d6fd2da64901534b48124ab1da43428849e019607577ead1211db3c8d2`.
`setup-real` só a lê; a cópia operacional fica em `<--directory>/inventory.xlsx`,
dentro de `artifacts/private/`, fora do Git. O código não depende de `doc-specs/`:
qualquer XLSX com as abas e cabeçalhos do README pode ser informado em
`--inventory`.

Os demais testes usam fixtures temporárias. O teste em
`tests/unit/test_inventory_import.py` lê a planilha original sem alterá-la:
confere 37 itens, custos por compra, origem por célula e o hash antes e depois.
Ele só é ignorado se o arquivo estiver ausente. Em 17/11/2026, executado
isoladamente no Windows, passou (1 aprovado). Conferir uma planilha transcrita
não equivale a conferir o binário original.
