# Testes e verificação

Consulte ao implementar comportamento, escolher o nível de teste ou verificar
uma alteração. Os comandos públicos estão no [README](../README.md#validar)
e no [workflow de CI](../.github/workflows/ci.yml). Quando disponíveis, o plano
em `doc-specs/implementation-slices.md` e a SPEC em `doc-specs/spec.md`
fornecem contexto local de desenvolvimento; não são necessários para executar
a suíte pública.

## TDD e pontos de teste

Escreva um teste comportamental, observe uma falha relevante, implemente o
mínimo e refatore. Priorize erros de negócio, fronteiras e integração;
evite testes de getters ou schemas que apenas reproduzam a implementação.

| Nível | Ferramenta e objetivo |
| --- | --- |
| Unitário | pytest para regras, guards, valores e transições |
| Propriedades | Hypothesis para invariantes financeiros com Decimal finito |
| Integração | pytest, SQLite temporário e MCP stdio real nos pontos da fatia |
| Agent Evals | Host/modelo real, traces e assertions determinísticas no banco |

Testes determinísticos verificam números, estado e efeitos. Evals verificam
diálogo e comportamento probabilístico; uma fala prudente não compensa uma
decisão indevida persistida. Leia apenas os casos pertinentes à mudança.

## Isolamento e evidências

- Use banco temporário por teste e relógio controlável para expiração.
- Preserve a planilha original como fixture somente leitura; crie variantes
  em diretórios temporários.
- Identifique receitas sintéticas como fixtures: elas não provam pesquisa real.
- Sanitize traces e relatórios; não use segredos ou bancos pessoais.
- Cubra diretamente guards, arredondamento e rollback afetados. Não existe
  percentual mínimo de cobertura atribuído ao desafio.

## Comandos e resultados

Instale pelo lock e execute a partir da raiz, com Python 3.13 como ambiente
de referência:

```text
uv sync --locked --python 3.13
uv run --locked --no-sync python -X utf8 -B -m pytest tests/unit tests/integration -q
uv run --locked --no-sync ruff check src tests/unit tests/integration
uv run --locked --no-sync ruff format --check src tests/unit tests/integration
```

A suíte cobre importação e diagnósticos, leitura sem mutação, candidatas,
viabilidade, aceite, cotações e confirmação, orçamento agregado, custos por
origem, precificação, invalidação e retomada. Hypothesis exercita invariantes
de alocação, pacotes, permutação e confirmação. Integrações usam SQLite
temporário e MCP stdio real, incluindo replay, rollback e reinício.

Para listar os casos atuais sem executá-los:

```text
uv run --locked --no-sync python -X utf8 -B -m pytest tests/unit tests/integration --collect-only -q
```

Coleta não comprova execução. Pytest não executa Agent Evals nem comprova
pesquisa web real ou qualidade do diálogo no Hermes. A planilha original não
é distribuída; a suíte usa fixtures sintéticas e indica como ignorada a
conferência adicional do anexo quando ele não está disponível.

Execute as verificações pertinentes à alteração e registre comando,
versões, resultados reais e limitações no handoff. Para evals, use `PASS`,
`FAIL`, `NOT_RUN` ou `ERROR`, incluindo número de execuções e fontes.
Falha de instalação ou teste não executado nunca equivale a aprovação.

## Harness operacional e Agent Evals locais (opcionais)

O Harness e seus registros não integram o checkout público. Se o bundle local
estiver disponível, seu verificador usa somente biblioteca padrão e tem
testes separados da aplicação. Execute a partir da raiz somente nesse caso:

```text
python -X utf8 -B -m unittest discover -s tests/harness -v
python -X utf8 -B tools/harness_check.py
```

Esses comandos verificam integridade dos registros, índice, Source IDs e
dependências; não provam domínio, Hermes/MCP ou Agent Evals. Os registros
locais `.harness/verification.md` e `.harness/tools.md`, quando disponíveis,
descrevem resultados, limites e regeneração do índice.

A CI usa somente a suíte pública com fixtures sintéticas em temporários,
sem depender dos documentos ignorados. Agent Evals exigem host/modelo real,
cenário e evidências de chamadas e estado; seus roteiros e registros locais
não são uma reprodução pública. Registre resultados sanitizados e mantenha
traces privados fora da entrega. Um eval anterior aprovado não valida uma
alteração nova de orientação.
