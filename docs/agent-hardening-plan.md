# Plano de implementação — domínio agnóstico, UX acessível e segurança

> Base: `main` no commit `fcdf98bb4329c15de1f7b948764f6a542d70f568`.
> Escopo: desafio Senior AI Engineer / Hermes Agent. Esta especificação não comprova implementação.

## Objetivo
Evoluir o Sabor da Maria sem regras específicas para arroz com frango, escondidinho ou qualquer outro prato. Preservar o motor determinístico de compras, viabilidade, aceite e preço e separar conversação amigável da infraestrutura interna.

## Evidências no código
- `src/dona_maria/candidates.py` tipa como `WebSource` a origem de medidas, ingredientes, rendimento, método, requisitos e revisões de categoria. Isso impossibilita atribuir corretamente receitas fornecidas pela usuária ou adaptações simuladas.
- `.hermes.md` já orienta mensagens simples e ocultação de detalhes técnicos; implementar avaliação que confira a experiência real, em vez de presumir que a instrução basta.
- `src/dona_maria/business_state.py` aceita `workspace_id` nas leituras. A conexão STDIO local não equivale a autenticação/autorização multiusuário.
- `evals/README.md` contém roteiros assistidos e resultados históricos. Não contar resultados históricos como validação da nova versão.

## P0 — Domínio e proveniência agnósticos
1. Inspecionar `candidates.py`, `planning.py`, `persistence.py`, `business_state.py`, `mcp_server.py`, `ingredients.py`, `quotes.py` e os consumidores reais dos contratos antes de editar.
2. Projetar proveniência discriminada para WEB, informação fornecida pela pessoa, simulação explicitamente declarada e medição apenas reportada. Separar origem de estado de validação; não inferir que um relato de medição é comprovação independente.
3. Suportar as fontes pertinentes a cada ingrediente, medida, método, rendimento, requisito e revisão. Validar referências e URLs apenas para origens WEB e exigir evidência verificável nos campos humanos. Não fabricar horário, `turn_ref` ou fonte.
4. Permitir receitas próprias e adaptações genéricas, mantendo fontes web originais e rastreabilidade de revisões, sem falsificar autoria ou criar exceção por nome de receita. Preserve invariantes de equivalência de ingredientes e de unidades; ausência de custo não vira zero.
5. Compatibilidade de leitura para registros antigos; definir e testar estratégia de migração/versionamento se for necessária. Preservar idempotência, `expected_revision`, versões, hashes/fingerprints e invalidação de decisões afetadas.
6. Propagar marcações de simulação nas avaliações e explicações. Nenhuma simulação comprova segurança alimentar ou produtividade real.
7. Não liberar aceite/cálculo quando faltarem insumos ou custos essenciais; documentar política genérica para água/insumos de custo desconhecido, separando custo conhecido e custo completo.

## P0 — Experiência da cozinheira
1. Interface normal em português claro e adulto. Sem `MCP`, `SQLite`, `workspace_id`, `revision`, schemas, tool names ou stack traces, salvo pedido explícito de diagnóstico autorizado.
2. Não exigir que a cozinheira forneça IDs: desenvolver um binding de contexto **confiável do lado do host/servidor** para o perfil de atendimento. Não alegar que prompt sozinho autentica ou vincula contexto. Se o host não suportar, registrar limitação e alternativa local de demonstração, sem expor o UUID na conversa.
3. Perguntar uma coisa relevante por vez, sem repetir fatos persistidos. Separar interesse, confirmação de lote, aceite de prato, compra e escolha de preço.
4. Mapear erros e estados de negócio para linguagem cotidiana sem falsificar confirmação de gravação. Em caso de falha, oferecer próximo passo útil.
5. Revisar `.hermes.md`, skill e referências, sem duplicação de regras conflitantes; preservar capacidade de diagnóstico restrito ao operador.

## P0 — Segurança com limites explícitos
1. Tratar mensagem, receita web, planilha e dados persistidos como entrada não confiável. Instruções embutidas nesses dados **não** autorizam ferramentas, confirmação, alteração de política ou exfiltração.
2. Fazer inventário das ferramentas habilitadas no perfil Hermes e documentar configuração de privilégio mínimo. Remover shell, execução arbitrária, SQL genérico, acesso amplo a arquivos e ferramentas administrativas do **perfil de atendimento**, mantendo apenas ferramentas de domínio e web necessárias. Não supor que texto do SOUL.md impõe permissões reais.
3. Validar parâmetros, tamanho, caminhos, URLs, permissões e efeitos no backend. Nenhuma ferramenta deve receber consulta SQL arbitrária nem pathname vindo da pessoa/modelo.
4. Identificar e evitar exfiltração por saída, logs, URLs e chamadas externas. Sanitizar diagnósticos sem perder auditoria técnica segura.
5. Registrar que STDIO local e UUID não oferecem isolamento multiusuário. Definir autenticação/autorização de recursos para evolução futura; não afirmar cross-tenant isolation implementado sem teste real. Diferenciar ataques por prompt de comprometimento do host.

## Testes exigidos
- Unidade/integração: WEB original; receita declarada pela usuária; adaptação de qualquer prato; simulação; medição reportada; proveniência falsa/incompleta; estado legado; versão/idempotência/concorrência; custos faltantes; bloqueios de aceite.
- Evals conversacionais: abertura sem IDs; linguagem natural; perguntas progressivas; recuperação de fatos; erro explicado sem stack/nomes técnicos; escolha de preço separada de estimativa de sobra.
- Adversariais: instrução maliciosa em web/XLSX; pedido de revelar .env, SQLite, código e segredos; pedir shell/SQL; troca de workspace; URL para enviar inventário; forçar orçamento/aceite; conteúdo persistido com instruções. Asserts de **tool calls e efeitos**, não só texto da resposta.
- Usar fixtures e bancos temporários isolados. Não executar bootstrap em bancos existentes, não tocar em `artifacts/private` de uso real.
- Rodar testes existentes + novos, lint/type checks previstos e registrar comandos/resultados. Não alegar execução não realizada.

## Ordem de trabalho sugerida
1. Inventário de contratos e risco de compatibilidade, com diff mínimo projetado.
2. Contratos de proveniência + persistência + testes.
3. UX/configuração efetiva do agente + evals.
4. Segurança de ferramentas e testes adversariais.
5. Demonstração ponta a ponta e documentação de limites.

## Critérios de aceite
- Nenhuma regra específica por título de receita.
- Uma adaptação com dados humanos/simulados nunca é atribuída à fonte web.
- Um cliente não técnico realiza a jornada sem ver identificadores internos.
- O perfil de atendimento não dispõe de execução arbitrária de código/SQL/arquivos.
- Falhas e tentativas de injection não criam compras, aceites, preços ou vazamentos.
- Dados antigos continuam legíveis; revisões/decisões mantêm coerência.
- Evidências de testes atuais e limitações residuais constam no README.

## Entrega
Commits pequenos na branch atual; resumo de arquivos alterados, decisões e trade-offs; resultados reais dos testes; roteiro de demo de 5–10 min. Abrir PR em draft para `main` só depois de haver implementação e revisão básica, sem merge automático.
