# Instalação e conexão com o Hermes

Execute os comandos na raiz do checkout. Use Python 3.13 para reproduzir o
ambiente da aplicação e mantenha o runtime gerenciado do Hermes separado.
O smoke de leitura usa um banco vazio; o bootstrap opcional importa a despensa
e cria estado de negócio em outro banco.

## 1. Instale a aplicação

Com Git, uv e Python disponíveis:

```sh
uv sync --locked --python 3.13
uv run --locked --no-sync python -X utf8 -B -m pytest tests/unit tests/integration -q
```

Se o Hermes não estiver instalado, siga a
[instalação oficial](https://hermes-agent.nousresearch.com/docs/).
Os comandos de perfil e MCP deste guia foram conferidos na instalação
Hermes v0.23.1. Para outra versão, consulte o help correspondente.

## 2. Prepare o banco sintético

Crie um SQLite vazio para verificar a ausência de workspace. Este arquivo
fica em diretório ignorado; não use um banco pessoal.

```sh
uv run --locked --no-sync python -c "from pathlib import Path; import sqlite3; p = Path('artifacts/private/smoke/empty.sqlite3'); p.parent.mkdir(parents=True, exist_ok=True); sqlite3.connect(p).close(); print(p.resolve())"
```

Guarde o caminho absoluto impresso. A preparação cria somente um arquivo
SQLite vazio, sem tabelas, migrações, despensa ou confirmação humana.
As consultas abrem esse banco em modo somente leitura e não o criam por conta própria.

### Bootstrap opcional para usar a despensa

Para usar a despensa, coloque o anexo recebido em
`artifacts/private/input/despensa_dona_maria.xlsx` e execute a importação local:

```sh
uv run --locked --no-sync python -m dona_maria.bootstrap --database artifacts/private/smoke/workspace.sqlite3 --inventory artifacts/private/input/despensa_dona_maria.xlsx --allowed-directory artifacts/private/input
```

O comando exige XLSX dentro do diretório autorizado e imprime o `workspace_id`
e o `snapshot_id`. Guarde esses IDs localmente. Configure o caminho absoluto
de `workspace.sqlite3` no perfil para usar essa despensa; `empty.sqlite3`
continua servindo apenas ao teste de ausência de workspace.

O orçamento inicial é R$ 80,00. Preços históricos não são saldo disponível;
custos usam quantidade comprada, preservando o estoque e a origem de cada célula.
Consulte diagnósticos por `get_inventory_snapshot`. Fórmulas e dados ausentes
ou ambíguos geram pendências, sem virar zero. A correção cria nova fotografia.

Sem `--workspace-id`, cada importação cria outro workspace e reutiliza a mesma
fotografia quando hash/política coincidem. Com `--workspace-id ID_EXISTENTE`,
somente o mesmo snapshot é reutilizado, preservando estado e revisão. Outra
planilha não substitui silenciosamente o workspace existente.

Obtenha também os caminhos do Python da aplicação e da pasta de skills:

```sh
uv run --locked --no-sync python -c "import sys; from pathlib import Path; print(sys.executable); print(Path('skills').resolve())"
```

O Python fica em `.venv/Scripts/python.exe` no Windows e `.venv/bin/python`
no Linux/macOS. Os caminhos são locais; não devem ser copiados de outra máquina.

## 3. Configure um perfil dedicado

Confira os comandos disponíveis:

```sh
hermes --version
hermes profile create --help
hermes mcp add --help
```

Para um perfil novo:

```sh
hermes profile create sabor-da-maria --no-skills --no-alias
hermes -p sabor-da-maria model
```

Se esse perfil já existir, use-o sem recriá-lo. Configure um modelo com suporte
a chamadas de ferramentas e, para pesquisa real, o acesso web do Hermes.
Credenciais e eventuais custos pertencem ao provedor escolhido.

Abra a configuração privada do perfil:

```sh
hermes -p sabor-da-maria config edit
```

Mescle as seções da
[configuração de exemplo](../config/hermes.config.example.yaml), preservando
as demais opções do perfil. Substitua todos os caminhos pelos valores do passo
anterior. No Windows, caminhos YAML podem usar barras `/`, como `C:/projeto/...`.
No Linux/macOS, ajuste também o executável para `.venv/bin/python`.
O exemplo não faz expansão automática de placeholders.

Configure em `env` somente `DONA_MARIA_DB_PATH` para o subprocesso de negócio.
Não acrescente chaves de modelo ou pesquisa. A orientação `.hermes.md` é lida
do projeto; `skills.external_dirs` aponta apenas para `skills/` deste checkout.

## 4. Confira conexão e descoberta

```sh
hermes -p sabor-da-maria mcp test dona_maria
hermes -p sabor-da-maria skills list --enabled-only
```

O MCP deve descobrir `get_business_state`, `get_inventory_snapshot`,
`register_recipe_candidate`, `record_recipe_feedback`, `record_kitchen_facts`,
`set_production_plan`, `evaluate_recipe_feasibility`, `evaluate_purchase_plan`
e `accept_recipe`, além de `calculate_pricing_scenarios`, `save_menu_decision`,
`resolve_recipe_ingredient`, `record_ingredient_conversion` e
`register_complement_quote` e `confirm_complement_quote`. A listagem de skills deve
incluir `dona-maria-cardapio`. Descoberta não comprova que o corpo da skill foi
carregado; a invocação explícita abaixo é o caminho de verificação.

## 5. Abra a conversa e verifique a leitura

Inicie a sessão na raiz do projeto com os toolsets necessários:

```sh
hermes -p sabor-da-maria chat --toolsets web,mcp-dona_maria
```

Na conversa, envie primeiro:

```text
/dona-maria-cardapio Resuma a orientação para workspace ausente, sem chamar ferramentas.
```

Depois envie:

```text
Use o MCP dona_maria para chamar get_business_state com workspace_id
"00000000-0000-4000-8000-000000000001".
Informe apenas o resultado observado, sem criar workspace ou simular dados.
```

Confira a chamada efetiva da ferramenta e o retorno `NOT_FOUND`, com
`ok=false`, `data=null` e `revision=null`. O MCP marca esse resultado com
`isError=true`; o cliente pode apresentá-lo como erro de ferramenta.
Isso é esperado para o workspace sintético ausente.

Para verificar pesquisa separadamente, peça a busca e extração de uma receita
real e confira a ferramenta utilizada, URL e conteúdo recuperado. Para registrar
a candidata, use o workspace importado, fontes efetivamente extraídas e os
schemas descobertos no MCP. Rendimento, medidas ou contexto ausentes precisam
de lacunas explícitas. `complete` e outros campos derivados não são entradas.

O horário de recuperação da fonte também precisa de evidência observável em
UTC. Se ele não estiver disponível, aguarde esse dado; um marcador de meia-noite
não representa o instante observado da extração. Correções de proveniência
usam nova revisão, mantendo histórico e identidade da candidata.

`register_recipe_candidate` exige `workspace_id`, `operation_id`,
`expected_revision` e `candidate`; revisão da receita também exige `recipe_id`
e `expected_recipe_version`. A resposta confirma a gravação somente após commit.
Em resultado incerto, consulte o estado e repita o mesmo comando/ID. Payload
diferente com o mesmo ID é recusado. Reabra a conversa e consulte
`get_business_state` para reencontrar a candidata. Esse registro não valida
viabilidade, aceite, compras ou preço.

## Se algo falhar

| Sintoma | Verificação |
| --- | --- |
| Módulo `dona_maria` ausente | Execute `uv sync --locked --python 3.13` e confirme que o perfil usa o Python do checkout. |
| Banco indisponível | Confira caminho, permissões e versão do schema; banco corrompido ou mais novo é recusado e preservado. Registros precisam de permissão de escrita e do diretório do SQLite. |
| Skill ausente | Confira `skills.external_dirs`, o caminho de `skills/` e a listagem no perfil correto. |
| Sessão sem resposta | Confira modelo, provedor e conectividade no Hermes; não substitua uma chamada pendente por um resultado simulado. |
| Ferramentas inesperadas | Compare o catálogo efetivo com a lista do passo 4 e revise os filtros do perfil; web pertence ao host. |
| Catálogo antigo após atualizar o servidor | No gateway, `/reload-mcp` pode preservar conexões já registradas. No perfil dedicado, desabilite somente `mcp_servers.dona_maria.enabled`, recarregue, reabilite e recarregue novamente. Confira nomes e workspace antes de pesquisar. |

A ausência de ferramentas perigosas deve ser conferida no catálogo efetivo.
Uma skill builtin essencial pode permanecer no contexto conforme a versão;
isso não justifica habilitar shell, escrita arbitrária ou gestão de memória.
O contrato de leitura não autentica consentimento humano.

Referências: [CLI do Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/cli),
[MCP no Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp).
