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

Use o mesmo comando de bootstrap acima, alterando somente `--inventory`
para `artifacts/private/input/synthetic.xlsx`.

Identifique esses dados como sintéticos durante a demonstração. Uma
despensa importada não confirma equipamentos, habilidades, rendimento,
condições comerciais ou aceite: essas informações ainda serão elicitadas.

<a id="perfil-hermes"></a>
## 3. Configure o perfil, modelo e pesquisa

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
suporte a chamadas de ferramentas. No configurador de ferramentas,
configure pesquisa e extração web, incluindo o acesso exigido pelo backend.

As opções, autenticação e custos dependem do provedor escolhido.
O modelo do Hermes é configurado aqui; não depende do modelo usado por
um editor ou agente de desenvolvimento.

Se o perfil já existir, confira sua configuração antes de reutilizá-lo.
Não recrie, clone ou substitua outro perfil para seguir este guia.

## 4. Conecte a aplicação e a skill

Obtenha os três caminhos absolutos desta máquina:

```sh
uv run --locked --no-sync python -c "import sys; from pathlib import Path; print('PYTHON=' + sys.executable); print('DB=' + str(Path('artifacts/private/quickstart/workspace.sqlite3').resolve())); print('SKILLS=' + Path('skills').resolve().as_posix())"
```

Nos comandos seguintes, substitua `PYTHON_ABSOLUTO`, `SQLITE_ABSOLUTO` e
`SKILLS_ABSOLUTO` pelos respectivos valores impressos. São placeholders,
não variáveis expandidas automaticamente.

```sh
hermes -p sabor-da-maria config set skills.external_dirs "['SKILLS_ABSOLUTO']"
hermes -p sabor-da-maria mcp add dona_maria --command "PYTHON_ABSOLUTO" --connect-timeout 15 --env "DONA_MARIA_DB_PATH=SQLITE_ABSOLUTO" --args -X utf8 -B -m dona_maria.mcp_server
```

Mantenha `--args` como a última opção: o restante pertence ao subprocesso.

A descoberta MCP pode pedir seleção das ferramentas. Confira o catálogo
de negócio apresentado e habilite as ferramentas necessárias da aplicação.
Se `dona_maria` já estiver configurado, confira seu alvo antes de alterá-lo.

O Python impresso usa `.venv/Scripts/python.exe` no Windows e `.venv/bin/python`
no Linux/macOS. Mantenha caminhos com espaços entre aspas. Para o caminho
da skill, use barras `/` e preserve a lista YAML no argumento de `config set`.

Passe somente `DONA_MARIA_DB_PATH` ao servidor de negócio. Credenciais de
modelo e pesquisa pertencem à configuração privada do Hermes.
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

A listagem deve incluir `dona-maria-cardapio`; o MCP deve descobrir as
ferramentas implementadas, incluindo consulta de estado e inventário.
Descoberta não prova, por si só, uso das ferramentas pelo modelo.

## 5. Inicie uma conversa natural

Na raiz do checkout:

```sh
hermes -p sabor-da-maria chat --toolsets file,web,mcp-dona_maria --skills dona-maria-cardapio
```

A skill é carregada explicitamente. O grupo `file` permite ler suas
referências, mas também inclui ferramentas de escrita e busca de arquivos.
Esta seleção não representa um sandbox de arquivos; confira o catálogo
efetivo e não habilite shell ou execução de código para este atendimento.

Substitua o marcador pelo workspace retornado no bootstrap e envie:

```text
Meu workspace é [WORKSPACE_ID_REAL].

Quero montar o cardápio de lançamento do Sabor da Maria com a minha
despensa e até R$ 80 para complementos. Pode começar consultando o que
tenho e pesquisando receitas reais? Pergunte sobre minha cozinha e
habilidades antes de propor um prato para eu aceitar.
```

Responda às perguntas com as condições reais da cozinha. Interesse,
confirmação de fatos, aceite do prato e escolha de preço são decisões distintas.

Confira durante a conversa:

- Consulta MCP ao workspace e ao inventário importados.
- Pesquisa e extração web efetivas, com URL e conteúdo recuperado.
- Perguntas sobre os requisitos da receita, sem condições presumidas.
- Cálculos retornados pelo MCP e escolha de preço solicitada à pessoa.
- Registro anunciado somente depois de retorno de sucesso.

Depois, abra uma nova conversa com o mesmo perfil, checkout e banco:

```text
Retome o workspace [WORKSPACE_ID_REAL]. Mostre o cardápio e as pendências
usando o estado salvo, sem registrar novas decisões.
```

Compare com o estado observado anteriormente. Memória da conversa não
substitui a consulta ao SQLite.

<a id="smoke-negativo"></a>
## 6. Smoke negativo — diagnóstico opcional

Em um banco recém-importado que contenha somente o workspace retornado,
consulte um UUID diferente dele e que não tenha sido cadastrado:

```text
Use o MCP dona_maria para chamar get_business_state com workspace_id
[UUID_NAO_CADASTRADO]. Informe o resultado observado, sem criar workspace
ou simular dados.
```

O resultado esperado é `NOT_FOUND`, `ok=false`, `data=null` e `revision=null`.
O MCP marca esse resultado com `isError=true`; o cliente pode apresentá-lo
como erro de ferramenta. Isso verifica uma recusa de leitura; não demonstra
importação, pesquisa, viabilidade, aceite ou preço.

Depois retome a conversa usando o workspace real. O percurso principal
não depende de obter um erro primeiro.

## Se algo falhar

| Sintoma | Verifique |
| --- | --- |
| Clone recusado ou repositório não encontrado | URL, conta autenticada e autorização de acesso ao repositório privado. |
| `uv` ou `hermes` não encontrado | Instalação e PATH; reabra o terminal. |
| Módulo `dona_maria` ausente | Sync concluído e MCP usando o Python da aplicação. |
| Importação recusada | Arquivo XLSX, abas/colunas, diretório autorizado e diretório pai do SQLite existente. |
| Banco indisponível | Caminho, permissões e versão do schema; banco corrompido ou mais novo é recusado e preservado. Registros exigem escrita no SQLite e no diretório pai. |
| `NOT_FOUND` na conversa principal | Workspace copiado do bootstrap e MCP apontando para o mesmo banco. |
| Busca indisponível | Backend web, autenticação, conectividade e limites do provedor. Habilitar o toolset não configura acesso por si só. |
| Skill ausente | Perfil correto, lista `skills.external_dirs` e caminho somente da skill de domínio. |
| Referência da skill não lida | Catálogo efetivo e disponibilidade das ferramentas de arquivo previstas neste guia. |
| Catálogo ou banco antigo | Confira a conexão ativa antes de repetir escritas. Use o procedimento de reconexão abaixo; não apague banco nem reinicie gateways alheios. |
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

O catálogo inclui `get_business_state`, `get_inventory_snapshot`,
`register_recipe_candidate`, `record_user_preferences`, `record_recipe_feedback`,
`record_kitchen_facts`, `set_production_plan`, `evaluate_recipe_feasibility`,
`evaluate_purchase_plan`, `accept_recipe`, `calculate_pricing_scenarios`,
`save_menu_decision`, `resolve_recipe_ingredient`, `record_ingredient_conversion`,
`register_complement_quote` e `confirm_complement_quote`.

Para registrar a candidata, o agente usa o workspace importado, fontes
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

### Reconexão do perfil dedicado

No gateway, `/reload-mcp` pode preservar conexões já registradas. No perfil
dedicado, desabilite somente `mcp_servers.dona_maria.enabled`, recarregue,
reabilite e recarregue novamente. Confira nomes e workspace antes de pesquisar.

A ausência de ferramentas perigosas deve ser conferida no catálogo efetivo.
Uma skill builtin essencial pode permanecer no contexto conforme a versão;
isso não justifica habilitar shell, execução de código ou gestão de memória.
O contrato de leitura não autentica consentimento humano.

<a id="teste-do-original"></a>
### Teste opcional do anexo original

O teste adicional procura `doc-specs/despensa_dona_maria.xlsx`. Seu skip é
esperado em um clone limpo. Colocar o anexo em `artifacts/private/input/`
para importação não ativa esse teste automaticamente. O diretório local
`doc-specs/` não é requisito para instalar, importar ou conversar com a aplicação.

Referências: [CLI do Hermes](https://hermes-agent.nousresearch.com/docs/reference/cli-commands),
[MCP no Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp).
