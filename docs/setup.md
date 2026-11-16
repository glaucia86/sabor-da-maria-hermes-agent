# Instalação, compatibilidade e recuperação

Para a primeira execução, siga as [dez etapas do README](../README.md#executar).
Elas usam sua planilha real, seu modelo e o Hermes Desktop. Este guia reúne
compatibilidade, recuperação e operação manual; não é um segundo tutorial concorrente.

- [Versão e instalação do Hermes](#dependencias)
- [Comandos e arquivos locais](#comandos)
- [Pesquisa real e termos públicos](#pesquisa)
- [Aprovação local](#aprovacao-local)
- [Retomada e recuperação](#recuperacao)
- [Importação manual](#despensa)
- [Simulação opcional](#demo-portatil)
- [Conferência do anexo original](#teste-do-original)

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

### Windows — PowerShell

Instale [Git](https://git-scm.com/downloads) e
[uv](https://docs.astral.sh/uv/getting-started/installation/). Em uma pasta de
trabalho local, baixe o instalador oficial e execute-o com o commit compatível:

```powershell
Invoke-WebRequest https://hermes-agent.nousresearch.com/install.ps1 -OutFile install-hermes.ps1
& ./install-hermes.ps1 -Commit 3b421578588243f920886e6fe79a6faa87ea026e
```

### Linux/macOS — bash ou zsh

Instale Git e uv conforme seu sistema. Para uma instalação nova do Hermes:

```sh
curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o install-hermes.sh
bash install-hermes.sh --commit 3b421578588243f920886e6fe79a6faa87ea026e
```

Reabra o terminal e confira `hermes --version`. A instalação Desktop por pacote
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
| `verify-profile` | Confere configurações, arquivos copiados, skill e conexão MCP. Não prova autenticação nem conversa. |
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

<a id="pesquisa"></a>
## Pesquisa real e termos públicos

O percurso guiado usa o provedor DDGS, plugin `web-ddgs`. Se o componente não
estiver instalado, execute `hermes tools post-setup ddgs` e reinicie normalmente
os processos do Hermes. Essa instalação afeta o runtime compartilhado do host.
Não instale pacotes Hermes na `.venv` da aplicação.

`configure` pede termos separados por vírgula: apenas letras, espaços e hífens,
de 1 a 100 caracteres por termo, até 200 termos. Você vê a lista exata e precisa
digitar `LIBERAR PESQUISA`. O texto não é obtido automaticamente da planilha.
O plugin constrói consultas de receita/oferta a partir desses termos; não aceita
URL ou consulta livre produzida pelo modelo. DDGS pode estar indisponível ou
retornar resultados inadequados: registre a falha, sem inventar uma fonte.

Para **revisar os termos de um atendimento existente**, encerre a sessão e edite
somente os valores/entradas de `research.json` no seu diretório privado. O arquivo
é um objeto JSON com chaves como `termo-1` e valores como `arroz`; não altere outros
arquivos. A edição local representa sua autorização explícita dos novos termos.
Use o perfil exibido por `configure` neste comando (PowerShell ou shell):

```sh
hermes -p NOME_DO_PERFIL config set plugins.entries.dona-maria-mediated-research.settings.public_terms '{"termo-1":"arroz","termo-2":"feijão"}'
```

O objeto precisa ser **idêntico ao de `research.json`**. Depois execute
`verify-profile` e abra uma nova sessão via `desktop`. Divergência é recusada;
nenhum ajuste é feito pelo LLM. Para mudar de provedor, o exemplo
[hermes.s17.example.yaml](../config/hermes.s17.example.yaml) é referência técnica
de configuração manual, não uma opção homologada pelo onboarding DDGS.

O estado `CONFIGURED_NOT_EXERCISED` significa configuração preparada. Somente
uma busca/extração reais na sessão comprovam pesquisa. O catálogo completo
esperado é seis ferramentas MCP mais `search_culinary_sources` e
`extract_culinary_source`, do plugin. Não habilite busca livre como fallback.

<a id="aprovacao-local"></a>
## Aprovação local

Siga a [etapa 9 do README](../README.md#desktop-local): liste, inspecione e aprove
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
| Dependência de pesquisa ausente | Instale o componente pelo Hermes e abra um processo novo. |
| Plugin incompatível | Confira versão e commit efetivos. Não desative o bloqueio nem alegue pesquisa a partir do MCP isolado. |
| Interface expõe detalhes privados na conversa normal | Não considere o canal aprovado; registre o comportamento observado. |

Não remova diretórios de perfil, banco ou dados do Hermes para tentar corrigir
uma falha. A limpeza é manual e posterior à identificação do atendimento que
você realmente deseja descartar. Bancos e credenciais permanecem fora do Git.

<a id="despensa"></a>
## Importação manual para diagnóstico

O percurso recomendado é `setup-real`, que inclui as migrações necessárias.
Para operadores que precisam somente importar um XLSX em uma pasta nova:

```sh
uv run --locked --no-sync python -X utf8 -m dona_maria.bootstrap --database artifacts/private/manual/workspace.sqlite3 --inventory artifacts/private/input/despensa_dona_maria.xlsx --allowed-directory artifacts/private/input --context-mode REAL
```

Crie `artifacts/private/manual` antes de executar. Esse comando isolado não cria
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
`SIMULATION`, sem pesquisa. Não usa sua planilha e não é o percurso completo
do avaliador. Os comandos `configure`, `model`, `chat` e `review` desse modo
continuam disponíveis para diagnóstico assistido; não promovem a base a REAL.
Em sistemas sem `python`, use `python3` no primeiro comando.

<a id="teste-do-original"></a>
## Conferência do anexo original

A suíte pública usa fixtures temporárias para permanecer reproduzível e não
distribuir o anexo. O teste opcional em `tests/unit/test_inventory_import.py`
procura `doc-specs/despensa_dona_maria.xlsx`; se ausente, fica ignorado. Essa
localização histórica é exclusiva do teste opcional, não do atendimento REAL.
O funcionamento de `setup-real` não depende dessa fixture ou de `doc-specs/`.
Conferir uma planilha transcrita não equivale a conferir o binário original.
