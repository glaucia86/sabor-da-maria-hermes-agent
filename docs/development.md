# Desenvolvimento por fatias

Consulte ao executar uma fatia, alterar código ou preparar seu handoff.
Este guia complementa o [AGENTS.md](../AGENTS.md); o procedimento canônico
está no [plano](../doc-specs/implementation-slices.md), em **Context Retrieval
Contract**, **Condições comuns** e no contrato da fatia. Retomada global e
comandos do Harness: [.harness/README.md](../.harness/README.md).

## Recuperação de contexto

1. Use RULES.md como roteador, confira [.harness/handoff.md](../.harness/handoff.md),
   o contrato de contexto, a fatia pedida e somente os handoffs necessários.
2. Extraia os Source IDs e localizadores indicados pela fatia.
3. Busque cada definição literalmente, por exemplo:
   `rg -n -F -- 'INV-007' doc-specs/spec.md`.
4. Confira se o resultado é a definição canônica, e não uma menção no índice.
5. Leia apenas o bloco necessário e as convenções que o afetam. Use o PRD
   quando houver dúvida de origem ou regra de negócio.
6. Acrescente referências somente por necessidade concreta; registre o motivo
   no handoff. Não reabra decisões GRILL sem conflito ou evidência.

Não use histórico de conversa como substituto dos contratos. Se o contexto
não comportar a mudança, reduza o incremento e registre o ponto de retomada.

## Convenções de código

- Prefira interfaces Python explícitas e tipadas.
- Valide entradas e saídas com Pydantic 2.x conforme a SPEC; não trate
  validação estrutural como prova da veracidade de fatos externos.
- Mantenha regras de negócio independentes de Hermes, MCP e rede.
- Evite dependências e abstrações desnecessárias.
- Consulte [testes](testing.md) ao implementar comportamento e
  [arquitetura](architecture.md) quando alterar responsabilidades.

Ainda não há manifesto nem configuração de lint no repositório. Não apresente
ferramentas propostas como já instaladas ou comandos futuros como comprovados.

## Entrega e continuidade

Ao executar uma fatia autorizada, atualize o handoff dessa fatia no plano com:

- Status real, comportamento entregue e caminhos alterados.
- Contratos, versões, entradas e saídas disponíveis para a próxima fatia.
- Comandos executados, resultados observados e evidências de testes/evals.
- Referências extras e justificativas, limitações e decisões pendentes.
- Próximo passo exato e dependências necessárias.

Use apenas evidências privadas ou sanitizadas para identificadores de
workspace/operação. Não inclua segredos nem transcrições integrais.
Não faça commit, push ou abra PR automaticamente.

O Handoff por fatia permanece no plano. Registre continuidade global em
.harness/handoff.md, eventos em .harness/progress.md e comandos/resultados em
.harness/verification.md, sem duplicar todos os status. Se as fontes do índice
mudaram, revise e regenere com `python -X utf8 -B .harness/check.py --refresh-index`;
depois execute `python -X utf8 -B .harness/check.py`. O JSON é derivado, não aprovação.
