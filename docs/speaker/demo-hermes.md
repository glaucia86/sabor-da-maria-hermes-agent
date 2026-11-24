# Demonstração ao vivo no Hermes Desktop — jornada REAL completa

Roteiro da demo de terça: **13 minutos (máximo 15)** depois dos slides, num
atendimento REAL novo com a planilha original. Você faz dois papéis: a **Dona
Maria**, no Desktop, e a **operadora**, no PowerShell ao lado. São 10 cenas e
6 aprovações locais, da pesquisa à escolha do preço.

O mesmo roteiro está no [guia interativo](../demo/hermes-desktop-walkthrough.html),
modo **Demo ao vivo**, com prompts copiáveis e cronômetro por cena. Ele foi
validado em 19/11 no Desktop e no CLI
([registro](../verification-desktop-real-complete.md)). Os valores esperados
abaixo são os daquele ensaio.

As falas da Dona Maria são de demonstração. Diga isso no início: o que é real é
a planilha, a pesquisa, o modelo, as tools, o banco REAL e as aprovações.

## Antes da terça

### D-1 (segunda-feira)

Na raiz do checkout, no PowerShell:

```powershell
# 1. Modelo do atendimento da demo (interativo): provedor nous, openai/gpt-6.1-sol
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding model --directory "artifacts/private/demo-24nov"

# 2. Gateway compartilhado do Hermes recarregado (com o Desktop fechado)
hermes gateway restart

# 3. Pesquisa e perfil (uma vez; o Exa anônimo tem cota)
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding check-research --directory "artifacts/private/demo-24nov"
uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding verify-profile --directory "artifacts/private/demo-24nov"
```

O esperado é `LIVE_SEARCH_AND_EXTRACTION_PASS` e, no perfil, `configuration`,
`gateway_plugin_registration` e `hermes_mcp_connection` em `PASS`, com
`model_configured: true`.

**Não converse no `demo-24nov` antes da demo.** Para ensaiar, use outra pasta
REAL. Se puder, grave um ensaio completo com a tela inteira: ele serve de plano B.

### D-0, 30 minutos antes

| # | Ação | Comando ou detalhe |
| --- | --- | --- |
| 1 | Feche todos os Hermes Desktop abertos | Inclusive de outros perfis |
| 2 | Recarregue o gateway | `hermes gateway restart` |
| 3 | Confira o perfil | `verify-profile` do D-1, item 3 |
| 4 | Sirva os slides e o guia | `python -m http.server 8765 --bind 127.0.0.1 --directory docs` num terminal separado |
| 5 | Abra os slides | <http://127.0.0.1:8765/speaker/slides/> em tela cheia (**F**); notas com **S** |
| 6 | Abra o guia na segunda tela | <http://127.0.0.1:8765/demo/hermes-desktop-walkthrough.html>, modo **Demo ao vivo** |
| 7 | Abra o PowerShell da operadora e carregue os atalhos | `. .\docs\speaker\demo-terminal.ps1 -Directory "artifacts/private/demo-24nov"` |
| 8 | Abra o Desktop por este comando | `uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding desktop --directory "artifacts/private/demo-24nov"` |
| 9 | No Desktop | Confira o perfil `sabor-real-4c332a24…`, abra uma **conversa nova** e não digite nada |
| 10 | Teste o terminal | `pend` deve responder "Nenhuma proposta pendente válida" |
| 11 | Tela | Fonte maior no Desktop (Ctrl + `+`) e no PowerShell; notificações desligadas; e-mail e chat fechados |
| 12 | Plano B à mão | Vídeo do ensaio, se gravado; `docs/verification-desktop-real-complete.md` aberto |

Os atalhos `pend`, `aprovar`, `ver` e `historico` valem só para a janela em que
foram carregados. Não use `rv`: é um apelido do próprio PowerShell.

### Layout de tela

- **Slides:** navegador em tela cheia, compartilhado.
- **Na demo:** compartilhe a tela com o Desktop (dois terços, à esquerda) e o
  PowerShell (um terço, à direita). O guia e este roteiro ficam na segunda tela.
- Transição: no slide 14, Alt+Tab para o Desktop. No fim, volte ao navegador e
  avance para o slide 15.

## Como cada aprovação funciona no terminal

Quando o Hermes disser que enviou uma proposta para revisão:

```powershell
aprovar
```

O atalho mostra o resumo e, em uma linha separada, a frase de atestação com o
hash completo. **Leia o resumo em voz alta e confira com a fala.** Se estiver
correto, pressione Ctrl+V para preencher a entrada com a frase que o atalho
copiou. Confira `ATESTO` e o hash na linha colada e então pressione Enter. O
esperado é `Aprovada: … · revisão N`.

- Se houver mais de uma proposta, `aprovar` lista as duas. Aprove a que
  corresponde à fala (`aprovar 1` ou `aprovar 2`) e peça ao Hermes que refaça a
  outra.
- `ver 1` mostra o conteúdo completo; `historico` lista tudo o que já foi
  decidido.

**Frase-âncora** (diga a cada aprovação): "O agente só propôs. Eu confiro o
conteúdo e atesto fora do modelo; só agora o estado muda."

## Roteiro

| Cena | Janela | Fala | Aprovação |
| --- | --- | --- | --- |
| 1 · Despensa e pesquisa | 0:00–1:30 | 1 | — |
| 2 · Receita da Dona Maria | 1:30–3:30 | 2 | 1 · receita |
| 3 · Condições da cozinha | 3:30–4:45 | 3 | 2 · fatos |
| 4 · Interesse | 4:45–5:45 | 4 | 3 · interesse |
| 5 · Plano | 5:45–6:45 | 5 | 4 · plano |
| 6 · O que tem e o que falta | 6:45–7:45 | 6 | — |
| 7 · Aceite | 7:45–8:45 | 7 | 5 · aceite |
| 8 · CMV e cenários | 8:45–10:30 | 8 | — |
| 9 · Escolha do preço | 10:30–11:30 | 9 | 6 · preço |
| 10 · Retomada e fechamento | 11:30–13:00 | 10 | — |

### Cena 1 · Despensa e pesquisa (1 min 30 s)

**Abertura (antes de colar):** "Este é um atendimento REAL novo, criado com a
planilha original; ninguém conversou nele. Eu faço a Dona Maria aqui e a
operadora no terminal. As falas são de demonstração."

**Cole:**

```text
Oi! Quero montar meu cardápio de delivery. Veja o que tenho na despensa e pesquise uma receita real de frango acebolado que aproveite meus ingredientes.
```

**Por trás:** `get_business_state`, `get_inventory_snapshot`,
`search_culinary_sources` (só termos liberados) e `extract_culinary_source`.

**Explique:** "Os números da despensa vêm do banco. A pesquisa usa só os termos
que a operadora liberou, e o conteúdo da página entra como dado não confiável."

**Esperado:** despensa com peito de frango, cebola, alho, óleo e sal; receita
**Frango acebolado, TudoGostoso**, 4 porções. O agente aponta que a fonte usa
sobrecoxa, não peito, e lista o que falta. Nenhuma proposta.

**Se der errado:** se a pesquisa falhar (`DATA_SOURCE_UNAVAILABLE`), diga
"o Exa anônimo oscila; o agente não inventou receita" e cole:
`A pesquisa pode ter falhado por instabilidade momentânea. Tente pesquisar de novo uma receita real de frango acebolado.`
Se falhar de novo, siga para a cena 2: a receita própria da Dona Maria é um
caminho válido do sistema.

### Cena 2 · Receita da Dona Maria (2 min)

**Cole:**

```text
Gostei da ideia, mas prefiro a minha versão: frango acebolado na frigideira. Uso 600 g de peito de frango, 200 g de cebola, 10 g de alho, 30 ml de óleo de soja e 6 g de sal; todas as quantidades são dos ingredientes crus, do jeito que vão para a frigideira. Não uso água nem outro ingrediente. Corto o frango em tiras, douro no óleo numa frigideira grande, junto cebola e alho, tempero com sal e cozinho até não ter parte rosada. Rende 4 porções e vendo por porção, não por peso. Revisei as três categorias: equipamento, só fogão e frigideira grande, que tenho; habilidade, só dourar frango, que sei; operação, já fiz muitas vezes, leva 40 minutos do início até porcionar, tenho 60 minutos por cozinhada, faço um lote por vez e a entrega sai logo depois, sem armazenar. Por enquanto, registre só a receita; as condições da cozinha eu confirmo em seguida.
```

**Por trás:** `propose_user_change` com `register_recipe_candidate`. A proposta
fica pendente, com hash e a revisão em que foi criada. O negócio não muda.

**No terminal:** `aprovar`. Confira 5 ingredientes `RAW`, 4 porções, 3
categorias revisadas e 0 lacunas.

**Explique:** "Ela disse que tudo é cru e revisou equipamento, habilidade e
operação. Sem isso, o sistema deixaria a base como desconhecida e não aceitaria
o prato."

**Se der errado:** se o resumo mostrar um ingrediente sem `RAW` ou faltar
categoria, não aprove. Cole `Faltou registrar que todos os ingredientes são crus e as três categorias. Refaça só a proposta da receita.`

### Cena 3 · Condições da cozinha (1 min 15 s)

**Cole:**

```text
A receita foi aprovada. Agora registre só as condições da minha cozinha: tenho fogão e frigideira grande, sei dourar frango, tenho 60 minutos por cozinhada, faço um lote por vez e a entrega sai logo depois do preparo, sem armazenar.
```

**Por trás:** `record_kitchen_facts`. Cada requisito da receita procura um fato
com a mesma chave.

**No terminal:** `aprovar`. São 6 fatos, com o tempo em 60 min.

**Explique:** "A receita exige 40 minutos; ela tem 60. Se tivesse 30, o
requisito ficaria `BLOCKED` e o aceite não sairia. É o coração do desafio:
descobrir antes de deixar comprar."

### Cena 4 · Interesse (1 min)

**Cole:**

```text
As condições foram aprovadas. Quero fazer esse prato. Registre só o meu interesse; a quantidade eu confirmo depois.
```

**Por trás:** `record_recipe_feedback` = `INTERESTED`.

**No terminal:** `aprovar`.

**Explique:** "Gostar não é aceitar. O interesse é um registro separado, e o
aceite vem só no fim."

**Se der errado:** se aparecer também uma proposta de plano, **não a aprove**:
"a Dona Maria ainda não disse a quantidade". Aprove só o interesse; na cena 5,
o Hermes refaz o plano.

### Cena 5 · Plano (1 min)

**Cole:**

```text
O interesse foi aprovado. Confirmo 1 lote, 4 porções.
```

**Por trás:** `set_production_plan`.

**No terminal:** `aprovar`. Deve aparecer 1 lote, 4 porções.

**Explique:** "A quantidade é decisão dela. O plano é o que faz o sistema somar
a demanda e comparar com a despensa."

### Cena 6 · O que tem e o que falta (1 min)

**Cole:**

```text
O plano foi aprovado. O que eu já tenho e o que falta comprar? Cabe nos R$ 80?
```

**Por trás:** `evaluate_recipe_feasibility` e `evaluate_purchase_plan`; só
consulta.

**Esperado:** tabela com os 5 ingredientes, tudo em estoque, **R$ 0,00** a
comprar e saldo de **R$ 80,00**.

**Explique:** "O orçamento de R$ 80 é um só para o cardápio inteiro, somando os
faltantes de todos os pratos. Estoque não é custo zero: o CMV usa o que ela já
pagou."

### Cena 7 · Aceite (1 min)

**Cole exatamente:**

```text
Aceito este prato conforme este resumo.
```

**Por trás:** `accept_recipe`, vinculado à avaliação atual. Só é aceito com a
receita `ELIGIBLE`, as compras `CONFIRMED`, o custo completo e o interesse
registrado.

**No terminal:** `aprovar`.

**Explique:** "O aceite precisa ser inequívoco. Um 'parece bom' não vira aceite."

### Cena 8 · CMV e cenários (1 min 45 s)

**Cole:**

```text
Me mostre o CMV e os cenários de preço, com a conta.
```

**Por trás:** `calculate_pricing_scenarios`. O cálculo é gravado pelo Python,
sem aprovação, e não escolhe preço.

**Esperado:**

| Item | Valor |
| --- | --- |
| Lote | R$ 9,6811 (frango R$ 8,40 · cebola R$ 0,80 · alho R$ 0,20 · óleo R$ 0,27 · sal R$ 0,0111) |
| CMV por porção | R$ 9,6811 ÷ 4 = **R$ 2,42** |
| Piso | R$ 2,42 ÷ 0,90 = **R$ 2,69** |
| M10 / M20 / M30 | **R$ 3,03 / R$ 3,46 / R$ 4,04** |

**Explique:** "A taxa de 10% é sobre a venda: ela recebe 90%. O piso é o CMV
dividido por 0,90, arredondado para cima. A conta é do Python, com `Decimal`; o
modelo só explica."

### Cena 9 · Escolha do preço (1 min)

**Cole exatamente:**

```text
Escolho o cenário M20.
```

Se a resposta da cena 8 não mostrar os códigos, use `Escolho o preço de R$ 3,46.`

**Por trás:** `save_menu_decision`.

**No terminal:** `aprovar`. Deve aparecer "cenário M20".

**Explique:** "A escolha é dela, entre os cenários ou um preço próprio acima do
piso, e passa pela mesma aprovação."

### Cena 10 · Retomada e fechamento (1 min 30 s)

**Cole:**

```text
A escolha foi aprovada. Como ficou meu cardápio?
```

**Esperado:** frango acebolado na frigideira a **R$ 3,46** por porção, CMV de
R$ 2,42, taxa de R$ 0,35, sobra de **R$ 0,69** e saldo de R$ 80,00.

**No terminal:** `historico`. Devem aparecer 6 `APPROVED`.

**Fechamento:** "Seis decisões, todas propostas pelo agente e aplicadas só
depois da atestação. A sobra de R$ 0,69 não é lucro: embalagem, gás e trabalho
não estão na planilha." Volte aos slides e avance para o slide 15.

## Se algo sair do roteiro

| Situação | O que fazer e dizer |
| --- | --- |
| Duas propostas pendentes | `aprovar` lista as duas. Aprove a que corresponde à fala e cole `Aprovei uma; refaça só a outra.` "Cada proposta fica presa à revisão do estado; aprovar uma deixa a outra desatualizada." |
| `STALE_REVISION` | Cole `A proposta ficou desatualizada; refaça só ela.` |
| `AUTHORIZATION_EXPIRED` (passaram 10 min) | Cole `A proposta expirou antes da aprovação; refaça.` Ignore a frase "use outra pasta nova": a pasta está íntegra. |
| O agente pergunta algo a mais | Responda com os mesmos dados do roteiro, em uma frase. |
| O agente propõe algo que ela não disse | Não aprove. "A atestação existe para isso." |
| Resposta diferente do esperado | Leia o que o estado mostra. Não complete de memória. |
| Desktop trava ou o modelo não responde | Diga o que aconteceu. Siga pelo CLI no mesmo atendimento: `uv run --locked --no-sync python -X utf8 -m dona_maria.onboarding chat --directory "artifacts/private/demo-24nov" --query "<fala>"` |
| Plugins ausentes no Desktop | Feche o Desktop, `hermes gateway restart` e reabra pelo comando `desktop`. |

### Se o tempo apertar

- **Em 8:00 e ainda antes da cena 7:** encurte as explicações das cenas 6 e 7
  para uma frase.
- **Em 11:30 e ainda antes da cena 9:** pule a cena 10. Termine com `historico`
  e a frase de fechamento.
- **Em 13:00 sem preço:** pare a demo, diga em que cena parou e mostre o
  resultado de 19/11 no slide 11 ou no vídeo do ensaio. Nunca force a passagem
  ao vivo.

## Perguntas prováveis durante a demo

| Pergunta | Resposta curta |
| --- | --- |
| O modelo pode aprovar sozinho? | Não. Não existe tool de aprovação; a CLI roda em outro processo e exige a atestação. |
| E se a operadora atestar algo que a cozinheira não disse? | O protótipo não autentica a cozinheira; é o primeiro próximo passo (identidade). A atestação registra quem confirmou o quê. |
| De onde vem o custo do frango? | `R$ 28,00 ÷ 2.000 g = R$ 0,014/g`, das duas abas da planilha. |
| Por que R$ 0,00 de compra se o CMV é R$ 9,68? | Desembolso é o que falta comprar; CMV é o que o prato consome, inclusive do estoque. |
| Por que a pesquisa às vezes falha? | Exa anônimo, sem chave e sem fallback para busca livre, por decisão de segurança. |
| As falas são reais? | Não; são de demonstração. O sistema as registra como declarações (`USER_PROVIDED`), não como medições. |

Para a jornada de validação técnica completa (14 etapas), use o modo
**Jornada completa** do guia interativo.
