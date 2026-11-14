# Verificação e reprodução integrada

S11 permanece em revisão: a leitura humana confundiu a sobra de R$1,29 com
preço/lucro no EV-07. A orientação foi corrigida para destacar o preço de venda
e explicar para quais custos a sobra ainda serve. A nova resposta precisa ser
validada; uma tentativa ficou ERROR por MCP indisponível, sem alterar estado.
A aplicação e seus testes não dependem de `doc-specs/`, `RULES.md` ou `.harness/`.
Os roteiros dos12casos ficam em [evals/cases.json](../evals/cases.json); fontes
controladas são explicitamente sintéticas e os diálogos de avaliação assistidos.
O [relatório integrado](../evals/s11-results.json) contém os 12 resultados,
29 invocações originais e uma tentativa adicional ERROR, hashes, versões,
assistência, rubricas originais do agente e o ajuste solicitado pela pessoa.

## Ambiente limpo

Uma cópia dos64arquivos públicos rastreados, com o conteúdo atual do checkout,
foi instalada num ambiente novo pelo lock usando Python3.13.15. Não foram
copiados banco pessoal, credenciais, documentos locais ou evidências privadas.
O sync offline usou pacotes já presentes no cache; não comprova download a
partir de uma máquina sem cache ou conectividade.

Regressão final na cópia limpa: 450 PASS e 1 SKIP em 260.99s. O único caso ignorado exige
a planilha original privada, que não acompanha o repositório. Esse teste foi
executado separadamente no checkout com o anexo autorizado:1PASS em0.54s,
somente leitura. Ruff:42arquivos aprovados em análise/formatação.

Para reproduzir instalação e bootstrap, siga [setup.md](setup.md) e use uma
base nova. No Windows, esta avaliação usou temporários exclusivos e desativou
o cache do pytest, após observar permissões negadas em temporários anteriores:

```powershell
uv sync --locked --python 3.13
$pytestTemp = Join-Path 'artifacts/private' ('pytest-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -X utf8 -B -m pytest tests/unit tests/integration -q -x --tb=short -p no:cacheprovider --basetemp "$pytestTemp"
.\.venv\Scripts\ruff.exe check --no-cache src tests/unit tests/integration evals
.\.venv\Scripts\ruff.exe format --check --no-cache src tests/unit tests/integration evals
```

Use um destino novo e exclusivo: pytest limpa o diretório passado em `--basetemp`.
Os comandos não corrigem permissões dos temporários antigos. O teste do anexo
original pode ser ignorado quando a fonte privada não estiver disponível.

O ambiente novo comprovou instalação da aplicação, testes e MCP stdio. A
jornada Hermes usou o ambiente do checkout com o mesmo lock e os mesmos hashes
de produto, em banco/workspaces sintéticos novos. A instalação do próprio
Hermes numa máquina sem cache não foi repetida.

## Repetir a jornada pela CLI

1. Execute instalação, criação do XLSX sintético, bootstrap, perfil e MCP do
   [guia de instalação](setup.md). Preserve o ID retornado e use um banco novo.
   Para repetir os números abaixo, inclua no XLSX também `Banana`, 40 `un`,
   quantidade comprada 40 `un` por `20.00`. Mel não consta da despensa.
2. Abra a CLI indicada no guia, com skill e web habilitados, e informe o ID.
   Peça busca e extração de uma receita real e de uma oferta complementar;
   confira as chamadas e URLs, sem substituir extração por memória do modelo.
   Nesta execução, a receita-base foi [sorvete de banana do Panelinha](https://panelinha.com.br/receita/sorvete-de-banana)
   e a oferta foi [mel Natureza Pura 500 g](https://www.zaffari.com.br/mel-natureza-pura-500g-1010359/p).
   Preço extraído em 14/11/2026: R$ 34,98; não é garantia de preço atual.
3. No teste, a manifestação humana propôs **adaptação sintética** de um lote
   com 8 bananas e 200 g de mel, quatro porções, consumo imediato. A receita
   original não prescreve esse mel. Peça registro das origens separadas e
   responda explicitamente às perguntas sobre processador, técnica,
   congelamento, tempo e organização. Não reutilize falas fictícias como fatos
   de uma cozinha real.
4. Confira embalagem, quantidade, fornecedor, encargos e disponibilidade.
   Nesta avaliação, retirada gratuita e um pacote disponível foram condições
   **sintéticas**, confirmadas no roteiro; a página comercial não as comprovou.
   Confirme somente o escopo apresentado pelo MCP. O plano deve mostrar compra
   inteira de R$ 34,98, saldo R$ 45,02 e sobra planejada de 300 g de mel.
5. Após resumo e avaliação favorável, envie separadamente `Aceito este prato.`.
   Confira o cálculo MCP antes de escolher: CMV por porção R$ 4,498; mínimo
   R$ 5,00; cenários R$ 5,63 / R$ 6,43 / R$ 7,50. Envie `Escolho M20.` somente
   se essa for a escolha desejada. O registro deve conter R$ 6,43, sem baixa
   física de estoque ou compra efetuada.
6. Abra outra conversa e retome o mesmo workspace, como no guia. Compare plano,
   preço, orçamento e inventário consultados; não execute bootstrap novamente.
7. Para o bloqueio, registre uma candidata cuja fonte exija forno, deixe a
   disponibilidade desconhecida e demonstre que interesse não autoriza aceite.
   Informe ausência: deve ficar bloqueada. Para agregação, use as duas
   candidatas sintéticas do EV-05: 4 kg e 3 kg de arroz, estoque 5 kg, pacote
   complementar de 5 kg por R$ 30,00, com condições sintéticas confirmadas.
   Confirme um lote de cada, depois B → A. Devem faltar 2 kg, comprar um único
   pacote, sobrar 3 kg e manter R$ 50,00; aceites antigos ficam invalidados.
   Capacidade/tempo da composição nova exigem confirmação própria.

Os [roteiros](../evals/cases.json) definem os demais casos; o relatório contém
as manifestações realmente usadas. A execução é assistida pela CLI oficial,
com exportação e comparação do estado público; não há comando `hermes eval`.
As recusas seguras e os esclarecimentos necessários foram mantidos no
histórico. EV-07 precisou de assistência com horários reais da extração,
`context_source` do schema e frase literal de aceite. São limites de autonomia.

Na revisão humana posterior, “resultado após ingredientes” foi interpretado
como preço/lucro. Por isso, o PASS original do agente no EV-07 não é aprovação
humana: o relatório registra FAIL de clareza. `.hermes.md` e a referência de
precificação agora separam preço cobrado, sobra para pagar os demais custos e
lucro ainda desconhecido. A sessão adicional carregou o novo contexto, mas
ficou sem MCP e recusou confirmar números; não valida o texto corrigido.
Sua conexão temporária foi removida com alvo/readback verificados.

A revisão humana também pediu clareza no EV-09: “aceite/cálculo/preço
invalidados” e “capacidade compartilhada” não explicam o próximo passo de modo
acessível. `.hermes.md` e a referência de correções agora orientam frases
curtas, consequências concretas e uma pergunta por vez, com tom adulto e
respeitoso. A proposta explica quatro porções em vez de duas, prato ainda fora
do cardápio e novo cálculo/escolha após conferir e confirmar o preparo. Não
houve nova execução Hermes para essa proposta; qualidade EV-09 permanece FAIL
até validação, com assertions originais de estado preservadas.

## Cobertura por critério

PASS determinístico refere-se à execução limpa acima, complementada pelo teste
local do original. Os resultados conversacionais têm assertions de estado e
revisão do agente; a amostra humana é registrada separadamente no relatório.

| AC | Fronteira/testes e evidência | Estado atual |
| --- | --- | --- |
| AC-001 | `test_inventory_import.py`, teste local do anexo autorizado | PASS |
| AC-002 | `test_inventory_import.py`, ruído/ausências/fórmulas/identidade | PASS |
| AC-003 | `test_candidate_stdio.py`; pesquisa e extração reais EV-07 | PASS técnico |
| AC-004 | `test_acceptance.py`, `test_corrections.py`; EV-10 | PASS técnico |
| AC-005 | `test_acceptance.py` e EV-01/02/03 atuais | PASS crítico |
| AC-006 | `test_acceptance_stdio.py`, guards sem mutação | PASS |
| AC-007 | `test_ingredient_resolution.py`, `test_ingredient_stdio.py`; EV-06 | PASS crítico |
| AC-008 | `test_shared_plan.py`, `test_shared_plan_stdio.py`; EV-05 em duas etapas | PASS crítico |
| AC-009 | `test_quote_confirmation.py`, fronteiras80/80.01/95; EV-04 | PASS crítico |
| AC-010 | `test_quote_confirmation.py`, `test_confirmation_stdio.py`; EV-11 | PASS técnico |
| AC-011 | `test_acceptance.py`, `test_acceptance_stdio.py`; aceite explícito EV-07 | PASS técnico |
| AC-012 | `test_pricing.py`, dinheiro Decimal textual e arredondamento | PASS |
| AC-013 | `test_pricing.py`, `test_pricing_stdio.py`; escolha EV-07 | PASS técnico |
| AC-014 | conversão→preço em `test_ingredient_resolution.py`; plano→invalidação→restart em `test_shared_plan_stdio.py`; EV-09 | PASS técnico |
| AC-015 | `test_bootstrap.py`, `test_operation_replay.py`, `test_recovery_stdio.py`; EV-10/12 | PASS técnico |
| AC-016 | `test_acceptance_stdio.py`, `test_candidate_stdio.py`, `test_operation_replay.py` | PASS |
| AC-017 | `test_recovery_stdio.py`, falhas seguras e sem gravação parcial | PASS determinístico; limites do host registrados |
| AC-018 | instalação limpa, catálogo stdio e jornada CLI com complemento EV-07 | PASS técnico; limites abaixo |
| AC-019 | `test_agent_eval_audit.py`, `test_eval_web_stdio.py`; EV-08 | PASS técnico |
| AC-020 | logs correlacionados em `test_candidate_stdio.py`; relatório sanitizado e métricas abaixo | PASS técnico |
| AC-021 | contexto atualizado nas exportações; skill carregada e referências lidas sob demanda | PASS técnico |
| AC-022 | suíte limpa/stdio e 12 EVs na versão integrada | Revisão humana da amostra pendente |

Os três cruzamentos exigidos em S11 já têm testes públicos: conversão seguida
de cálculo/escolha em `test_ingredient_resolution.py`; alteração de plano,
invalidação e reinício em `test_shared_plan_stdio.py`; expiração, retomada e nova
confirmação em `test_confirmation_stdio.py`. Não foram criados testes literais
de documentos nem alteradas regras de negócio para fazer a avaliação passar.

## Plataformas e métricas

| Ambiente | Núcleo/SQLite | MCP stdio | Hermes CLI/projeto | Desktop/projeto |
| --- | --- | --- | --- | --- |
| Windows nativo, Python3.13.15 | PASS na cópia limpa | PASS,16ferramentas/protocolo2025-11-25 | 12 casos executados; revisão humana pendente | Não testado |
| Windows runner, Python3.13.17/x64 | PASS na CI | PASS na CI | Não testado nessa CI | Não testado |
| Linux runner, Python3.13.18/x64 | PASS na CI | PASS na CI | Não testado | Não testado |
| macOS runner, Python3.13.17/arm64 | PASS na CI | PASS na CI | Não testado | Não testado |

Execução remota conferida em 14/11/2026 no [CI do PR](https://github.com/glaucia86/sabor-da-maria-hermes-agent/actions/runs/43626864729),
head `87738981bcb650b09ed4c6d1dac1c2d62ef03a69`: 450 PASS/1 SKIP em cada
sistema, mais Ruff e formatação PASS. Tempos pytest: Windows445.11s,
Linux192.21s e macOS273.83s. O skip é o anexo privado ausente.

O [CI do push da mesma alteração](https://github.com/glaucia86/sabor-da-maria-hermes-agent/actions/runs/43626850154)
interrompeu Windows com448PASS/1SKIP/2sem resultado: a anotação do GitHub
confirma o limite de10min do job excedido. Esse cancelamento não é PASS nem
falha de assertion. O limite local do workflow foi ampliado para20min para
acomodar variação do runner; essa alteração ainda não foi executada remotamente.
Os testes e seus limites individuais foram preservados. WSL não é prova de
Windows nativo; a CI não comprova paridade de interface CLI/Desktop.

Baseline de uma execução Windows com3linhas sintéticas e plano vazio: importação
0.012587s, avaliação0.001937s, criação/inicialização MCP1.563929s e consulta MCP
0.226694s. São medições locais únicas, sem SLA ou extrapolação para outros dados.
Tokens são reportados conforme as exportações; custo ausente permanece
“não disponível”, sem valor zero presumido.

Versões do host observadas: Hermes 0.23.1, commit `3b4215785882`, Python do
host 3.14.9 e OpenAI SDK 2.54.0; modelo `openai/gpt-6.1-sol`, faturamento
`nous`. Aplicação: MCP 2.3.0, Pydantic 2.14.3, pytest 9.2.0, Ruff 0.17.4 e
Hypothesis 6.170.15. O lock da aplicação não fixa o Hermes ou o modelo.

## Limites da entrega

Estoque/custos e manifestações dos evals são sintéticos; fontes web reais são
identificadas separadamente. Pesquisa e confirmação não efetuam compra nem
comprovam operação comercial, capacidade física ou transporte de alimentos.
`UserEvidence` não autentica a pessoa. Extrator controlado sem rede não prova
proteção completa contra SSRF ou isolamento geral do host.
No EV-07, o pacote de arquivos também permitiu consultar cache web e um índice
com URLs públicas ao procurar horários. Isso está declarado no relatório;
ausência observada de leitura de segredos não comprova isolamento de arquivos.
As duas conexões temporárias S11 foram removidas, com alvo e remoção conferidos;
o servidor original não foi alvo.

Desktop e vídeo não foram verificados nesta etapa; S12 não foi executado.
Contato, canal e horário de submissão continuam pendentes de definição pela
responsável; o alvo16/11/2026 não implica23h59. Nenhuma submissão é automática.
