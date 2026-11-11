# Testes e verificação

Consulte ao implementar comportamento, escolher o nível de teste ou verificar
uma alteração. Fontes canônicas: seção **Testes / Verification** da fatia no
[plano](../doc-specs/implementation-slices.md) e seções pertinentes de
**6. Estratégia de automação de testes** na [SPEC](../doc-specs/spec.md).

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

O recorte S00 possui manifesto, lock e testes locais comprovados em Windows
com Python 3.13.15. Instale pelo lock com
`uv sync --locked --cache-dir .venv/uv-cache` e execute a partir da raiz:

```text
uv run --locked --cache-dir .venv/uv-cache python -X utf8 -m pytest tests/unit tests/integration -q -s
.venv/Scripts/python.exe -m ruff check src tests/unit tests/integration
.venv/Scripts/python.exe -m ruff format --check src tests/unit tests/integration
```

São 20 casos de leitura segura/MCP stdio, sem provas de Hermes, web ou regras
dos próximos slices; detalhes em [s00-smoke.md](s00-smoke.md). Hypothesis e
Agent Evals permanecem pendentes dos comportamentos correspondentes.

Execute as verificações pertinentes à alteração e registre comando,
versões, resultados reais e limitações no handoff. Para evals, use `PASS`,
`FAIL`, `NOT_RUN` ou `ERROR`, incluindo número de execuções e fontes.
Falha de instalação ou teste não executado nunca equivale a aprovação.

## Harness operacional

O verificador local usa somente biblioteca padrão e tem testes separados da
aplicação. Execute a partir da raiz:

```text
python -X utf8 -B -m unittest discover -s tests/harness -v
python -X utf8 -B tools/harness_check.py
```

Esses comandos verificam integridade dos registros, índice, Source IDs e
dependências; não provam domínio, Hermes/MCP ou Agent Evals. Consulte
[.harness/verification.md](../.harness/verification.md) para resultados reais e
[.harness/tools.md](../.harness/tools.md) para limites e regeneração do índice.

A [CI](ci.md) usa somente a suíte pública com fixtures sintéticas em
temporários, sem depender dos documentos ignorados. A verificação do bundle
real continua local. Os comandos anteriores em .harness/ permanecem como
entradas de compatibilidade para a implementação e suíte públicas.
