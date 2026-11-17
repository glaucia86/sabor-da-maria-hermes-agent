# Demonstração no Hermes Desktop — 5 a 10 minutos

Use a planilha real, o modelo escolhido no seu Hermes e pesquisa real.
O roteiro orienta a demonstração; não cria fatos, respostas ou decisões.
Conversa no Desktop, revisão local em terminal separado. Se você exercer os
papéis de cozinheira e operadora, explique essa alternância ao avaliador.

## Antes de iniciar o relógio

Complete as [dez etapas de preparação](../../README.md#executar) e faça um
ensaio completo. Confira versão/commit do backend, perfil, contexto, catálogo
efetivo (seis MCP e duas de pesquisa) e ausência de detalhes privados na conversa.
A [jornada E2E assistida](../verification-desktop-e2e.md) foi concluída em
`SIMULATION`; ela não homologa o perfil REAL com a planilha original. Registre
o resultado real em [verificações](verification-local-real.md).

Tenha a planilha original local, modelo autenticado, pesquisa Exa confirmada
por `check-research`, termos públicos autorizados e um segundo terminal na raiz
do projeto. Não projete
credenciais, configurações completas ou logs privados. Declare o que foi
preparado antes da sessão; não apresente uma pesquisa anterior como busca ao vivo.
Se reutilizar um atendimento já ensaiado, declare também as decisões existentes.
Para demonstrar do início, prepare outra pasta, sem apagar o histórico anterior.

## Roteiro

Os prompts de cada etapa, em linguagem natural e na trilha REAL, estão no
[guia interativo](../demo/hermes-desktop-walkthrough.html), também acessível
pelo slide 11 da apresentação.

| Tempo | Ação | Evidência esperada |
| --- | --- | --- |
| 0:00–1:00 | Pedir consulta da despensa e informar o objetivo de lançamento. | Ingredientes reais e orçamento de R$ 80, sem pedir UUID à cozinheira. |
| 1:00–2:30 | Solicitar pesquisa e comentar uma candidata. | Fonte real; preferência registrada como interesse, sem aceite prematuro. |
| 2:30–4:30 | Responder sobre equipamentos, técnicas, tempo e armazenamento. | Perguntas relevantes; impedimento real provoca adaptação ou outra candidata. |
| 4:30–6:00 | Conferir ingredientes, quantidade planejada e complementos. | Lacunas explícitas, preços/origens e desembolso agregado dentro do orçamento. |
| 6:00–8:30 | Manifestar o aceite, revisar propostas no terminal e pedir preços. | Aceite válido, CMV, taxa e três cenários; a pessoa escolhe o preço. |
| 8:30–10:00 | Revisar a escolha e retomar o estado. | Preço escolhido persistido, sem baixa de estoque físico ou compra automática. |

As aprovações acontecem nos pontos em que surgirem propostas, não somente ao
final. Use `review list`, `inspect` e `approve` conforme o README. Leia cada
resumo antes de digitar `ATESTO <hash>`; nunca automatize o stdin nem peça ao
agente para atestar. Se uma proposta expirar, revise uma proposta atual.
Volte ao Desktop somente depois de `ok: true` no terminal; uma consulta anterior
ao commit ainda mostra a proposta como `PENDING`. O aceite exige interesse
registrado antes; se o agente pular essa etapa, peça a proposta de interesse.

## Se algo impedir a demonstração

- Modelo ou rede indisponível: informe a falha e mostre o diagnóstico local.
- Pesquisa sem resultado adequado: tente outros termos já liberados ou revise
  os termos no canal local; não invente URL ou substitua por busca livre.
- Equipamento, quantidade ou custo desconhecido: mostre a pergunta/bloqueio.
  Não complete com uma hipótese para caber no tempo.
- Tempo insuficiente: apresente o estado alcançado e conclua a jornada depois;
  não afirme que o cardápio e o preço foram aprovados.

Uma execução sintética ou receita própria pode explicar o núcleo, mas não
substitui a prova de pesquisa real exigida pelo desafio. Grave o vídeo somente
após o ensaio no perfil final; slides não equivalem a demonstração executada.
