# Correção da pesquisa no Hermes 0.23.1

Reprodução em Windows, commit `3b421578588243f920886e6fe79a6faa87ea026e`.

## Causa e correção

O registro direto no perfil funcionava. No gateway compartilhado, `_load_application`
encontrava `dona_maria` já carregado de outra origem e lançava `ValueError`
(`SOURCE_CONFLICT`). A mensagem genérica ocultava a causa; o toolset não era
registrado e `session.create` recusava `culinary_research` antes da inferência.

`plugins.isolation: host` resolveu o conflito mantendo a recusa de versões
estranhas: cada perfil usa seu próprio processo de plugins. Nenhuma dependência
ou arquivo da instalação Hermes foi alterado. O plugin agora informa somente
estágio, categoria de exceção e motivo fixo. O traceback permanece suprimido.

`agent.disabled_toolsets: [desktop_ui]` remove os previews do catálogo do modelo.
O teste real de `get_tool_definitions` confirmou somente as duas ferramentas
de pesquisa ao habilitar pesquisa + Desktop e excluir `desktop_ui`.

O Doctor é uma reprodução diferente: copia o plugin para um home temporário,
sem settings; `_load_application(None)` lança `ValueError`
(`SOURCE_NOT_CONFIGURED`). Não foi criado fallback que libere pesquisa sem binding.

`verify-profile` agora consulta o registro no gateway via `plugins.list`, exigindo
política habilitada com dois hooks, pesquisa com duas ferramentas e o toolset.
Contagens não homologam uma conversa: o teste de runtime separado cobre o despacho.

## Evidência executada

- 77 testes direcionados aprovados: pesquisa, diagnósticos, política, onboarding,
  preflight e integração opcional com Hermes instalado.
- Após excluir `desktop_ui`, os dois testes afetados foram repetidos: 2 aprovados.
- Ruff check e format check gerais aprovados; `git diff --check` sem erros.
- Teste real de registro com módulo estrangeiro sintético no processo pai:
  o host registrou as duas ferramentas sem substituir o módulo do pai.
- `post_api_request` exercitado com `NormalizedResponse`/`ToolCall` reais do Hermes,
  atravessando o transporte do host; controle positivo de pesquisa autorizado.
- `pre_tool_call` bloqueou `desktop_preview`, `drive_preview` e `web_search`.
  Os caminhos de execução compartilhado/concorrente (`invoke_tool`) e sequencial
  do Desktop foram exercitados; nenhum callback sentinela foi chamado.
- CLI real em perfil e SQLite sintéticos: `search_culinary_sources` e
  `extract_culinary_source` retornaram `ok: true`. Tentativas anteriores retornaram
  `DATA_SOURCE_UNAVAILABLE`; nenhuma ativou busca livre. DDGS, provedor desta
  verificação, é uma dependência externa e sucesso pontual não garante
  disponibilidade contínua. O onboarding atual usa Exa anônimo, com o mesmo limite.
- Correção aplicada ao perfil de atendimento existente: plugin copiado,
  isolamento `host`, `desktop_ui` desabilitado e plugins recarregados.
  Registro no gateway aprovado; hash do SQLite de negócio idêntico antes/depois.
  O preflight real confirmou configuração, skill, conexão MCP e registro no gateway.

Os comandos direcionados usaram `uv run --locked --no-sync python -X utf8 -B -m
pytest`, com `--basetemp` dentro de `artifacts/private` e `-p no:cacheprovider`
devido a permissões dos diretórios temporários/cache do Windows.
Para incluir o runtime instalado no teste opcional:

```powershell
$env:DONA_MARIA_HERMES_TEST_PROFILE='sabor-research-regression-20261117-v4'
uv run --locked --no-sync python -X utf8 -B -m pytest tests/integration/test_hermes_installed_runtime.py -q
```

Use apenas um perfil sintético com prefixo `sabor-research-regression-`, plugins
do checkout, binding sintético e isolamento `host`. O teste não chama LLM nem
faz pesquisa externa. Sem a variável, ele é explicitamente ignorado na CI pública.

## Limite da homologação Desktop

A automação de interface retornou `Computer Use native pipe is unavailable`;
o canal alternativo também não encontrou o host. Nenhuma janela foi fechada.
Os testes comprovam os hooks nos executores reais, **não** uma jornada visual
concluída no Desktop. A verificação visual requer nova conversa no perfil corrigido,
busca/extração mediadas e confirmação das recusas sem execução de previews.

Logs, credenciais, perfis de teste e bancos permanecem privados, fora do Git.
Não houve commit, push ou merge. Não foi executada a suíte completa de domínio,
pois esta alteração está restrita à integração e ao preflight.

## Arquivos alterados

- `src/dona_maria/hermes_research/__init__.py`: diagnóstico sanitizado, sem retirar a recusa.
- `src/dona_maria/onboarding.py`: isolamento, exclusão Desktop e preflight do gateway.
- `src/dona_maria/hermes_gateway_check.py`: validação do registro efetivo.
- `config/hermes.config.example.yaml` e `config/hermes.s17.example.yaml`: configurações restritas.
- `tests/unit/test_hermes_research_plugin.py` e `tests/unit/test_hermes_gateway_check.py`: regressões.
- `tests/integration/test_onboarding.py`, `test_hermes_installed_runtime.py` e
  `hermes_runtime_probe.py`: preflight, conflito no processo pai e executores Desktop reais.
- `docs/setup.md` e este relatório: atualização sem reimportação e limites da evidência.
