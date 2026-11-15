# Instalação e conexão com o Hermes

Execute os comandos da aplicação na raiz do checkout. Este guia separa
testes locais, conversa com Hermes, smoke negativo e origem dos dados.

<a id="dependencias"></a>
## 1. Instale as ferramentas

Instale o [Git](https://git-scm.com/downloads) se ainda não estiver disponível.

### Windows — PowerShell

Instale uv pelo [instalador oficial](https://docs.astral.sh/uv/getting-started/installation/):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Para o percurso conversacional, instale também Hermes:

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```

### Linux/macOS — shell

Instale uv pelo [instalador oficial](https://docs.astral.sh/uv/getting-started/installation/):

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Para o percurso conversacional, instale também Hermes:

```sh
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

Confira os pré-requisitos e a arquitetura suportada na
[instalação oficial do Hermes](https://hermes-agent.nousresearch.com/docs/getting-started/installation).
WSL2 é uma alternativa no Windows; não misture Python, checkout e caminhos
de sistemas diferentes na mesma configuração MCP.

Reabra o terminal após a instalação e confira:

```sh
git --version
uv --version
```

Para conversar com Hermes, confira também:

```sh
hermes --version
```

Agora execute o clone, a instalação Python 3.13 e o sync descritos no
[Quick Start do README](../README.md#executar). Os comandos de testes
também ficam centralizados no [README](../README.md#validar).

O Python 3.13 é da aplicação. Não instale as dependências deste projeto
dentro do runtime gerenciado do Hermes.

<a id="despensa"></a>
## 2. Prepare uma despensa e importe

Use um diretório novo para esta primeira execução, sem reaproveitar banco pessoal.

```sh
uv run --locked --no-sync python -c "from pathlib import Path; Path('artifacts/private/input').mkdir(parents=True, exist_ok=True); Path('artifacts/private/quickstart').mkdir(parents=True, exist_ok=True)"
```

### Com o anexo original

Obtenha `despensa_dona_maria.xlsx` pelo canal autorizado do desafio e coloque
uma cópia em:

```text
artifacts/private/input/despensa_dona_maria.xlsx
```

O arquivo não acompanha o repositório. Preserve o original e não publique
a planilha, o banco importado ou credenciais.

Confira a proteção dos caminhos:

```sh
git check-ignore artifacts/private/input/despensa_dona_maria.xlsx artifacts/private/quickstart/workspace.sqlite3
```

Importe a cópia:

```sh
uv run --locked --no-sync python -X utf8 -B -m dona_maria.bootstrap --database artifacts/private/quickstart/workspace.sqlite3 --inventory artifacts/private/input/despensa_dona_maria.xlsx --allowed-directory artifacts/private/input
```

O comando imprime JSON com `workspace_id`, `snapshot_id`, `revision` e
`budget_initial`. Guarde o `workspace_id` real: ele será usado na conversa.

Não substitua esse valor por um UUID de exemplo. Não repita o bootstrap
para iniciar cada conversa: sem `--workspace-id`, ele cria outro workspace.
O estado permanece no SQLite e independe da sessão Hermes.

<a id="dados-sinteticos"></a>
### Sem o anexo: demonstração sintética

A demonstração não representa a despensa original. Este comando cria um
XLSX mínimo, com um ingrediente fictício de teste:

```sh
uv run --locked --no-sync python -c "from pathlib import Path; from openpyxl import Workbook; p=Path('artifacts/private/input/synthetic.xlsx'); p.parent.mkdir(parents=True, exist_ok=True); w=Workbook(); s=w.active; s.title='Despensa'; s.append(['Ingrediente','Quantidade em estoque','Unidade']); s.append(['Arroz',5,'kg']); s=w.create_sheet('Precos'); s.append(['Ingrediente','Quantidade comprada','Unidade','Preço total pago (R$)']); s.append(['Arroz',5,'kg','24.90']); w.save(p); w.close(); print(p.resolve())"
```

Crie um banco separado para o contexto fictício:

```sh
uv run --locked --no-sync python -X utf8 -B -m dona_maria.bootstrap --database artifacts/private/simulation/workspace.sqlite3 --inventory artifacts/private/input/synthetic.xlsx --allowed-directory artifacts/private/input --context-mode SIMULATION
```

Crie previamente o diretório `artifacts/private/simulation` se necessário.
Configure o binding privado com o banco e o workspace retornado. O modo é
imutável: o bootstrap recusa reutilizar banco REAL como SIMULATION e vice-versa,
inclusive após renomear/copiar o arquivo. Não recrie nem apague um banco por
incompatibilidade. Um banco legado sem modo permanece REAL; use outro banco
novo para a demonstração fictícia. Nenhuma ferramenta MCP troca esse modo.

Identifique esses dados como sintéticos durante a demonstração. Uma
despensa importada não confirma equipamentos, habilidades, rendimento,
condições comerciais ou aceite: essas informações ainda serão elicitadas.

<a id="perfil-hermes"></a>
## 3. Configure o perfil e o modelo

Os comandos de perfil e MCP deste guia têm como referência a instalação
Hermes v0.23.1 e a [CLI oficial](https://hermes-agent.nousresearch.com/docs/reference/cli-commands).
Os instaladores podem entregar outra versão; confira o `--help` correspondente.
O lock da aplicação não fixa a versão do Hermes.

Para um perfil novo:

```sh
hermes profile create sabor-da-maria --no-skills --no-alias
hermes -p sabor-da-maria model
hermes -p sabor-da-maria tools
```

No seletor de modelo, configure um provedor acessível e um modelo com
suporte a chamadas de ferramentas. No atendimento vinculado, habilite somente
`mcp-dona_maria`. Pesquisa, arquivos, shell, memória, administração e outros
servidores/plugins ficam desabilitados. A skill será pré-carregada.

As opções, autenticação e custos dependem do provedor escolhido.
O modelo do Hermes é configurado aqui; não depende do modelo usado por
um editor ou agente de desenvolvimento.

Se o perfil já existir, confira sua configuração antes de reutilizá-lo.
Não recrie, clone ou substitua outro perfil para seguir este guia.

## 4. Conecte a aplicação e a skill

Instale primeiro a política local de atendimento. Consulte a pasta do perfil:

```sh
hermes -p sabor-da-maria config path
```

Na pasta que contém esse arquivo de configuração, crie
`plugins/dona-maria-attendance-policy/` e copie para ela somente `__init__.py`
e `plugin.yaml` de `src/dona_maria/hermes_policy/` deste checkout. Preserve
arquivos preexistentes; não clone nem substitua o perfil inteiro. Habilite:

```sh
hermes -p sabor-da-maria plugins enable dona-maria-attendance-policy --no-allow-tool-override
```

A política não registra ferramentas. Ela compara o nome original emitido
pelo modelo com o nome que o host pretende executar e veta nomes proibidos,
inclusive após correção automática do Hermes. Ausência de observação válida
também recusa a chamada. Usa os hooks públicos `post_api_request` e
`pre_tool_call`, conferidos na versão instalada; não altera o código do host.
No perfil sem pesquisa mediada, mantenha somente essa política na allowlist de plugins.
O perfil isolado de pesquisa tem configuração e gate próprios em
[S17](s17-mediated-research.md); não amplie automaticamente este perfil.
Não disponibilize o atendimento sem repetir o teste de catálogo e de chamada
proibida no host efetivo. Após atualizar a política, copie novamente apenas
esses dois arquivos e inicie uma sessão nova.

Obtenha os três caminhos absolutos desta máquina:

```sh
uv run --locked --no-sync python -c "import sys; from pathlib import Path; print('PYTHON=' + sys.executable); print('DB=' + str(Path('artifacts/private/quickstart/workspace.sqlite3').resolve())); print('SKILLS=' + Path('skills').resolve().as_posix())"
```

Nos comandos seguintes, substitua `PYTHON_ABSOLUTO`, `SQLITE_ABSOLUTO` e
`SKILLS_ABSOLUTO` pelos respectivos valores impressos. São placeholders,
não variáveis expandidas automaticamente.

```sh
hermes -p sabor-da-maria config set skills.external_dirs "['SKILLS_ABSOLUTO']"
hermes -p sabor-da-maria mcp add dona_maria --command "PYTHON_ABSOLUTO" --connect-timeout 15 --env "DONA_MARIA_DB_PATH=SQLITE_ABSOLUTO" "DONA_MARIA_WORKSPACE_ID=WORKSPACE_IMPORTADO" "DONA_MARIA_MODE=ATTENDANCE" --args -X utf8 -B -m dona_maria.launcher
```

Mantenha `--args` como a última opção: o restante pertence ao subprocesso.
No Hermes0.23.1, use `--env` uma única vez, seguido de todos os pares:
repetir a opção conserva somente os valores da última ocorrência.

A descoberta MCP pode pedir seleção das ferramentas. Confira o catálogo
de negócio apresentado e habilite as ferramentas necessárias da aplicação.
Se `dona_maria` já estiver configurado, confira seu alvo antes de alterá-lo.

O Python impresso usa `.venv/Scripts/python.exe` no Windows e `.venv/bin/python`
no Linux/macOS. Mantenha caminhos com espaços entre aspas. Para o caminho
da skill, use barras `/` e preserve a lista YAML no argumento de `config set`.

Substitua `WORKSPACE_IMPORTADO` somente na configuração privada, pelo valor
da importação local. O caminho deve ser absoluto e o arquivo já deve existir.
Ausência, workspace incompatível ou modo diferente de `ATTENDANCE` impedem
startup. Não existe descoberta automática do único workspace. Reinício conserva
o vínculo; não execute bootstrap novamente para retomar.

O launcher repassa ao processo de negócio apenas ambiente operacional mínimo
e os três campos `DONA_MARIA_*` acima. Credenciais ficam no Hermes. Diagnóstico,
bootstrap e testes legados são contexto local do operador, fora do atendimento.
A orientação `.hermes.md` é lida do projeto; `skills.external_dirs` aponta
apenas para `skills/` deste checkout.

A [configuração YAML de exemplo](../config/hermes.config.example.yaml) é uma
referência dos mesmos campos; não é necessário aplicar os dois procedimentos
nem substituir o arquivo inteiro de configuração.

Confira conexão e descoberta:

```sh
hermes -p sabor-da-maria mcp test dona_maria
hermes -p sabor-da-maria skills list --enabled-only
```

A listagem deve incluir `dona-maria-cardapio`; o MCP deve descobrir exatamente
`get_business_state`, `get_inventory_snapshot`, `evaluate_recipe_feasibility`
`evaluate_purchase_plan`, `propose_user_change` e `calculate_pricing_scenarios`.
A configuração de exemplo aplica os mesmos nomes
em `tools.include` e desabilita wrappers resources/prompts, ferramentas adiadas
e memória. Não habilite o canal se catálogo ou execução divergirem, inclusive
após refresh/retomada/gateway. Aprovação e decisões diretas nunca são expostas.
As duas novas ferramentas persistem proposta e cálculo técnico, respectivamente.
O catálogo de seis ferramentas precisa de conferência no perfil real; as provas
anteriores do catálogo de quatro não homologam esta configuração.
Descoberta não prova, por si só, uso das ferramentas pelo modelo.

## 5. Inicie uma conversa natural

Na raiz do checkout:

```sh
hermes -p sabor-da-maria chat --oneshot -Q --toolsets mcp-dona_maria --skills dona-maria-cardapio -q "Olá! Quero saber o que posso preparar com os ingredientes que tenho." 2>> artifacts/private/atendimento-operador.log
```

A skill é pré-carregada de fonte local confiável. Use apresentação sem cartões
técnicos (`-Q` na CLI assistida; `display.tool_progress: "off"` no perfil).
O canal validado é a CLI assistida: a pessoa operadora executa os comandos e
mantém `stderr` no log privado acima; a cliente recebe apenas a resposta de
`stdout`. O diretório `artifacts/private/` deve existir. O metadado de sessão
do Hermes fica no log do operador, sem ser solicitado à cozinheira.
Confira o canal real antes de disponibilizá-lo: texto, cartões e retornos
automáticos não devem mostrar identificadores, caminhos ou detalhes privados.
Perfil não constitui sandbox do sistema operacional.

A fala inicial já está no argumento `-q`, sem identificadores:

```text
Olá! Quero saber o que posso preparar com os ingredientes que tenho.
```

O contexto já está fixado. O atendimento consulta ingredientes, candidatas e
decisões persistidas; explica pendências sem criar receitas ou fatos. Pesquisa,
aprovação, aceite e preço novos ainda não estão disponíveis nesse catálogo.

Confira durante a conversa:

- Estado e despensa corretos, sem pedir identificadores à cozinheira.
- Reutilização de fatos vigentes e perguntas ligadas às lacunas reais.
- Recusa de troca de contexto, diagnóstico e operações não disponíveis.
- Nenhuma gravação, decisão ou pesquisa executada nesta etapa.

Para retomar, a pessoa operadora usa privadamente o identificador da sessão
registrado no log. Não o peça nem o apresente à cozinheira:

```sh
hermes -p sabor-da-maria chat --oneshot -Q --resume ID_DA_SESSAO --toolsets mcp-dona_maria --skills dona-maria-cardapio -q "Vamos continuar. Mostre o que já está confirmado e o que ainda falta." 2>> artifacts/private/atendimento-operador.log
```

A fala da cliente continua sem conceitos técnicos:

```text
Vamos continuar. Mostre o que já está confirmado e o que ainda falta.
```

Compare com o estado observado anteriormente. Memória da conversa não
substitui a consulta ao SQLite.

<a id="smoke-negativo"></a>
## 6. Smoke negativo — diagnóstico opcional

Faça diagnóstico somente em sessão local do operador e com banco sintético.
Não conceda privilégios por conversa. O teste do binding inválido pode iniciar
um subprocesso de atendimento com UUID não cadastrado na configuração privada:

```text
DONA_MARIA_WORKSPACE_ID=UUID_NAO_CADASTRADO
```

Esse é um valor de configuração, não uma fala nem um comando de shell.
O startup deve falhar sem servir MCP, sem traceback e sem alterar o banco.
Uma chamada com `workspace_id` extra também deve ser recusada. Os testes
`test_attendance.py` e `test_attendance_stdio.py` verificam essas fronteiras.

Depois restaure o vínculo sintético válido fora da conversa e reinicie o
processo. Não faça esse experimento contra o banco real da demonstração.

## Se algo falhar

| Sintoma | Verifique |
| --- | --- |
| Clone recusado ou repositório não encontrado | URL, conta autenticada e autorização de acesso ao repositório privado. |
| `uv` ou `hermes` não encontrado | Instalação e PATH; reabra o terminal. |
| Módulo `dona_maria` ausente | Sync concluído e MCP usando o Python da aplicação. |
| Importação recusada | Arquivo XLSX, abas/colunas, diretório autorizado e diretório pai do SQLite existente. |
| Banco indisponível | Caminho, permissões e versão do schema; banco corrompido ou mais novo é recusado e preservado. Registros exigem escrita no SQLite e no diretório pai. |
| Atendimento indisponível | Operador confere banco absoluto, workspace explícito e modo; não pede UUID à cozinheira. |
| Busca indisponível | Pesquisa ainda não está habilitada. Não use ferramentas alternativas. |
| Skill ausente | Perfil correto, lista `skills.external_dirs` e caminho somente da skill de domínio. |
| Referência da skill não lida | Pré-carregue a skill confiável; não habilite ferramentas genéricas de arquivo. |
| Catálogo ou banco antigo | Confira a conexão ativa antes de repetir consultas. Use a reconexão abaixo; não apague banco nem reinicie gateways alheios. |
| Resultado de escrita incerto | Consulte o estado antes de repetir. Não anuncie gravação sem confirmação. |
| Sessão sem resposta | Modelo, provedor e conectividade; não substitua uma chamada pendente por resultado simulado. |
| Ferramentas inesperadas | Catálogo efetivo e filtros do perfil; web pertence ao host. |

## CLI/TUI e Desktop

A CLI/TUI é o percurso principal deste projeto. Desktop é uma interface
opcional do Hermes, não uma dependência da aplicação.

Não suponha que o Desktop usa o mesmo perfil, diretório, banco ou catálogo
da sessão CLI. A validação dessa interface é separada e não integra este
Quick Start.

## Detalhes da importação e dos registros

O orçamento inicial é R$ 80,00. Preços históricos não são saldo disponível;
custos usam quantidade comprada, preservando o estoque e a origem de cada célula.
Consulte diagnósticos por `get_inventory_snapshot`. Fórmulas e dados ausentes
ou ambíguos geram pendências, sem virar zero. A correção cria nova fotografia.

Sem `--workspace-id`, cada importação cria outro workspace e reutiliza a mesma
fotografia quando hash/política coincidem. Com `--workspace-id ID_EXISTENTE`,
somente o mesmo snapshot é reutilizado, preservando estado e revisão. Outra
planilha não substitui silenciosamente o workspace existente.

O catálogo técnico legado, usado somente em testes sintéticos fora do
atendimento, inclui `get_business_state`, `get_inventory_snapshot`,
`register_recipe_candidate`, `record_user_preferences`, `record_recipe_feedback`,
`record_kitchen_facts`, `set_production_plan`, `evaluate_recipe_feasibility`,
`evaluate_purchase_plan`, `accept_recipe`, `calculate_pricing_scenarios`,
`save_menu_decision`, `resolve_recipe_ingredient`, `record_ingredient_conversion`,
`register_complement_quote` e `confirm_complement_quote`.

Os contratos internos abaixo preservam compatibilidade; não estão disponíveis
como decisões diretas no atendimento. Use propostas e aprovação local; no schema
migrado, novas escritas humanas diretas são recusadas também pelo repositório.
Nos testes legados, o agente usa o workspace importado, fontes
efetivamente extraídas e os schemas descobertos no MCP. Rendimento, medidas
ou contexto ausentes precisam de lacunas explícitas. `complete` e outros
campos derivados não são entradas.

O horário de recuperação da fonte também precisa de evidência observável em
UTC. Se ele não estiver disponível, aguarde esse dado; um marcador de meia-noite
não representa o instante observado da extração. Correções de proveniência
usam nova revisão, mantendo histórico e identidade da candidata.

`register_recipe_candidate` exige `workspace_id`, `operation_id`,
`expected_revision` e `candidate`; revisão da receita também exige `recipe_id`
e `expected_recipe_version`. A resposta confirma a gravação somente após commit.
Em resultado incerto, consulte o estado e repita o mesmo comando/ID. Payload
diferente com o mesmo ID é recusado. `get_business_state` permite reencontrar
a candidata. Esse registro não valida viabilidade, aceite, compras ou preço.

### Retomada após falha e novo workspace

Para continuar, mantenha o mesmo banco e `workspace_id` e peça
`get_business_state` em uma nova conversa. Não execute bootstrap novamente:
o plano, as preferências e as decisões vigentes vêm do banco.

Se uma escrita perder a resposta, o resultado é incerto. Consulte o estado e
repita exatamente a ferramenta, `operation_id`, `expected_revision` e payload
originais. O replay retorna a resposta comprometida, sem nova revisão ou
decisão. Conteúdo ou ferramenta diferentes com o mesmo ID geram
`IDEMPOTENCY_CONFLICT`. Não crie outro ID para contornar o erro.

`STORAGE_BUSY` permite no máximo uma repetição automática com o mesmo comando.
Persistindo a falha, informe e aguarde. Em `STORAGE_UNAVAILABLE`, confira
caminho, permissões e integridade; em `CALCULATION_ERROR`, confira as entradas.
Nenhum desses erros confirma gravação ou autoriza cálculo textual substituto.
Revisão desatualizada exige reler/reavaliar e obter novas confirmações afetadas.

Para reset de demonstração ou nova planilha, a pessoa operadora executa o
bootstrap da seção 2 **sem `--workspace-id`** e configura o novo ID explicitamente.
O workspace anterior permanece consultável; o mesmo hash/política reutiliza
o snapshot. Não há ferramenta MCP de apagar ou sobrescrever workspaces.
Banco corrompido ou com schema mais novo é recusado: preserve o arquivo e
verifique a versão ou uma cópia de segurança antes de continuar.

### Reconexão do perfil dedicado

No gateway, `/reload-mcp` pode preservar conexões já registradas. No perfil
dedicado, desabilite somente `mcp_servers.dona_maria.enabled`, recarregue,
reabilite e recarregue novamente. Confira catálogo e vínculo antes de atender.

A ausência de ferramentas perigosas deve ser conferida no catálogo efetivo.
Uma skill builtin essencial pode permanecer no contexto conforme a versão;
isso não justifica habilitar shell, execução de código ou gestão de memória.
O contrato de leitura não autentica consentimento humano.

<a id="aprovacao-local"></a>
### Revisão local de decisões

Este é um fluxo assistido. A pessoa operadora atesta que a cozinheira manifestou
a decisão sobre o conteúdo exato; não escolhe prato ou preço em seu lugar.
A identidade registrada é a sessão local do sistema operacional, sem alegar
autenticação da cozinheira. Não disponibilize este comando, shell ou SQL ao
Hermes. O perfil é controle de capacidades, sem isolamento contra código já
executando na mesma conta do sistema.

Banco legado continua legível. Antes de habilitar propostas, faça a migração
local explícita de schema 1 para 2, com aplicação parada. Ela cria somente a
tabela de propostas e um backup consistente que inclui WAL, sem regravar
snapshots, estado, decisões, operações ou hashes antigos. O backup deve ser
novo; não sobrescreva cópia existente. Banco futuro ou corrompido é recusado.
Não há migração no startup do atendimento.

Defina `BANCO_LOCAL`, `WORKSPACE_LOCAL` e `BACKUP_NOVO` com os valores privados
do operador. Execute cada ação separadamente na raiz do checkout:

```text
uv run --locked --no-sync python -m dona_maria.approval_cli --database BANCO_LOCAL --workspace WORKSPACE_LOCAL migrate --backup BACKUP_NOVO
uv run --locked --no-sync python -m dona_maria.approval_cli --database BANCO_LOCAL --workspace WORKSPACE_LOCAL list
uv run --locked --no-sync python -m dona_maria.approval_cli --database BANCO_LOCAL --workspace WORKSPACE_LOCAL inspect PROPOSTA
uv run --locked --no-sync python -m dona_maria.approval_cli --database BANCO_LOCAL --workspace WORKSPACE_LOCAL approve PROPOSTA --hash HASH_REVISADO
uv run --locked --no-sync python -m dona_maria.approval_cli --database BANCO_LOCAL --workspace WORKSPACE_LOCAL reject PROPOSTA --hash HASH_REVISADO
```

`inspect` mostra payload canônico, dependências, resumo, revisão, hash e prazo.
`approve` apresenta o resumo e exige digitar `ATESTO HASH_REVISADO`, declarando
a manifestação da cozinheira sobre aquele conteúdo. Não aprove com base apenas
na narrativa do modelo. A aplicação revalida contexto, hash, revisão, prazo e
guards; efeito, auditoria, consumo e resultado são gravados juntos.

Propostas duram dez minutos. Expiração, alteração de conteúdo ou conflito de
estado exigem nova proposta/apresentação. Rejeição não modifica o negócio.
Resposta perdida pede consulta e replay idêntico; não gere outra decisão para
compensar incerteza. O resultado anterior continua histórico e não renova
autorizações. Fatos legados necessários precisam de revisão local; cotação,
aceite e preço exigem novas manifestações. Decisões invalidadas não são
restauradas automaticamente.

Os comandos tipados cobrem preferências, feedback, fatos, plano/seleções,
equivalências, conversões e aquisição histórica por conversão, confirmação
de cotação, aceite, preço e revisões de candidatas/ofertas já existentes.
Novos overlays de estoque/aquisição, proveniência expandida e pesquisa mediada
não são habilitados aqui. Snapshot original permanece imutável.

Provas determinísticas usam SQLite sintético, CLI em processo separado e MCP
stdio real. A homologação do catálogo ampliado no Hermes real e o aceite humano
da entrega permanecem pendentes; siga a experimentação humana um passo por vez.

<a id="teste-do-original"></a>
### Teste opcional do anexo original

O teste adicional procura `doc-specs/despensa_dona_maria.xlsx`. Seu skip é
esperado em um clone limpo. Colocar o anexo em `artifacts/private/input/`
para importação não ativa esse teste automaticamente. O diretório local
`doc-specs/` não é requisito para instalar, importar ou conversar com a aplicação.

Referências: [CLI do Hermes](https://hermes-agent.nousresearch.com/docs/reference/cli-commands),
[MCP no Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp).
