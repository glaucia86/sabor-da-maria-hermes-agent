# Instalação, compatibilidade e recuperação

Para a primeira execução, siga o [Quick Start](../README.md#quick-start) e o
[passo a passo do README](../README.md#executar). Eles usam a planilha original
versionada em `doc-specs/`, seu modelo e o Hermes Desktop. Este guia reúne
instalação por sistema operacional, compatibilidade, recuperação e operação
manual; não é um segundo tutorial concorrente.

- [Versão e instalação do Hermes](#dependencias)
  - [Windows — PowerShell](#windows-powershell)
  - [macOS — zsh](#macos-zsh)
  - [Linux — bash](#linux-bash)
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
| Windows | Onboarding REAL com a planilha original até `check`, jornada Desktop em `SIMULATION`, testes e CI histórica do núcleo/MCP. |
| macOS | Somente a CI histórica do núcleo/MCP (runner arm64, versão anterior). Instalação do Hermes, onboarding e Desktop não testados. |
| Linux | Somente a CI histórica do núcleo/MCP (runner x64, versão anterior). Instalação do Hermes, onboarding e Desktop não testados. |

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
| `desktop` | Repete a verificação e abre o perfil/contexto preparados. Modelo ausente impede lançamento. |
| `review list/inspect/approve/reject` | Acessa a revisão local com banco/workspace já vinculados. |
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

Siga o [passo 10 do README](../README.md#revisao-local) e o
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
| Código/skill mudou | Prepare outro atendimento para a avaliação; não alegue que hashes antigos homologam arquivos novos. |
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
