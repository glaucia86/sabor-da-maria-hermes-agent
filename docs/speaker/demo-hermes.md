# Demonstração no Hermes Desktop — Demo rápida de 8 minutos

A demonstração da apresentação é **somente leitura**. Ela consulta um
atendimento REAL já preparado com a planilha original e mostra como o agente
lê o estado, preserva fontes e para quando falta informação. Durante os oito
minutos não há comandos no terminal, novas propostas nem aprovações.

Os prompts, os resultados esperados e os critérios de cada cena estão no
[guia interativo](../demo/hermes-desktop-walkthrough.html), no modo
**Demo rápida — 8 minutos**, também acessível pelo slide 11. A jornada com
propostas, aprovação local, aceite e preço continua no modo **Jornada completa —
14 etapas**. No ensaio, essa jornada levou mais de uma hora e serve para
validação técnica, não para a apresentação.

## Antes de iniciar o relógio

Prepare o atendimento REAL fora da sessão, pela Etapa 0 da jornada completa ou
pelo [percurso do README](../../README.md#executar). O roteiro pressupõe um
workspace REAL com pesquisa Exa já registrada, adaptação da receita, plano de
1 lote e 4 porções, cinco propostas aprovadas localmente e uma proposta
adicional criada antes, cuja situação atual é lida durante a demo.

Abra o Desktop no perfil REAL preparado. Confira o perfil e o catálogo efetivo,
com seis ferramentas MCP e duas de pesquisa, sem projetar credenciais,
configurações completas ou logs privados. Ao começar, declare ao avaliador o
que foi preparado antes da sessão.

## Roteiro

| Tempo | Cena | Evidência esperada |
| --- | --- | --- |
| 0:00–1:30 | Despensa REAL e orçamento | 37 ingredientes da planilha original, custos unitários e saldo a partir de R$ 80, com lacunas como pendência. |
| 1:30–3:00 | Fonte Exa registrada | Título, link e data da consulta da receita web, sem nova pesquisa. |
| 3:00–4:45 | Adaptação e plano | Receita original intacta, adaptação separada com origem por campo e plano de 1 lote e 4 porções. |
| 4:45–6:15 | Viabilidade pendente | Viabilidade `PENDING`, com as condições que faltam nomeadas e sem suposições. |
| 6:15–8:00 | Decisões e aprovação externa | Cinco decisões aplicadas, situação atual da proposta adicional e explicação da aprovação fora do modelo. |

O guia traz um cronômetro indicativo por cena. Use-o como referência de
ritmo, não como limite rígido.

## Limites de evidência

- A pesquisa mostrada é o registro de uma busca feita antes da sessão. Não a
  apresente como busca ao vivo.
- A viabilidade observada é `PENDING`. Não declare o prato elegível.
- A receita REAL não foi aceita nem precificada. Preço e cardápio finalizados
  existem apenas no [ensaio `SIMULATION`](../verification-desktop-e2e.md) de
  17/11/2026 e aparecem no slide seguinte como resultado documentado.
- Não presuma que a proposta adicional continua pendente. Propostas expiram dez
  minutos após a criação. Leia a situação no estado e diga o que ele mostrar.
- Se o agente pedir uma informação na cena 4, não responda com um fato: isso
  criaria uma proposta. Use o prompt alternativo do guia.

## Se algo impedir a demonstração

- Modelo ou rede indisponível: informe a falha e mostre o estado alcançado.
- O agente oferece registrar ou aprovar algo: recuse e repita que a demo é só
  consulta.
- Resultado diferente do esperado: descreva o que o estado mostra. Não complete
  com hipóteses para caber no tempo.

Para reproduzir a jornada com propostas e aprovações, siga a jornada completa
do guia e o [registro da jornada E2E](../verification-desktop-e2e.md). Slides
e demo somente leitura não equivalem a uma jornada REAL completa validada.
