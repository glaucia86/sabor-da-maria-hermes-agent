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

Ainda não há `pyproject.toml`, dependências resolvidas ou testes da aplicação.
Os comandos abaixo são **propostas da SPEC §6.5**, pendentes de configuração
e comprovação; não representam verificações já disponíveis:

```text
uv run pytest tests/unit tests/integration
uv run ruff check .
uv run ruff format --check .
```

Documente o comando real do harness somente após implementar e verificar sua
interface. Execute as verificações pertinentes à alteração e registre comando,
versões, resultados reais e limitações no handoff. Para evals, use `PASS`,
`FAIL`, `NOT_RUN` ou `ERROR`, incluindo número de execuções e fontes.
Falha de instalação ou teste não executado nunca equivale a aprovação.

## Harness operacional

O verificador local usa somente biblioteca padrão e tem testes separados da
aplicação. Execute a partir da raiz:

```text
python -X utf8 -B -m unittest discover -s .harness/tests -v
python -X utf8 -B .harness/check.py
```

Esses comandos verificam integridade dos registros, índice, Source IDs e
dependências; não provam domínio, Hermes/MCP ou Agent Evals. Consulte
[.harness/verification.md](../.harness/verification.md) para resultados reais e
[.harness/tools.md](../.harness/tools.md) para limites e regeneração do índice.
