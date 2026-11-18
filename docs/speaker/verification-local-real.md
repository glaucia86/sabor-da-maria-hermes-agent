# Verificação do percurso local REAL — 16/11/2026

> [!NOTE]
> **Registro histórico.** O estado atual está em [Evidências e limites do README](../../README.md#validar), na [jornada REAL no Desktop](../verification-desktop-real.md) e na [jornada SIMULATION](../verification-desktop-e2e.md), todas de 17/11/2026. Última suíte completa: 948 aprovados e 2 ignorados.

Esta revisão muda o percurso principal para planilha real, modelo escolhido
localmente no Hermes e Desktop. Os registros históricos em
[verification-s20.md](verification-s20.md) permanecem históricos.

## Implementação

- `setup-real` importa o XLSX fornecido sem alterar o original, prepara REAL e
  migrações com backups. Não cria fatos de cozinha, receitas ou decisões.
- Mesmo arquivo/diretório reaproveitam o banco; troca de origem ou modo é recusada.
- Perfil novo, pesquisa explícita (DDGS nesta revisão; o onboarding atual usa
  Exa anônimo), termos aprovados pelo operador e contexto com orientações/skill.
  Nenhuma credencial pessoal é copiada.
- `desktop` verifica a preparação, exige modelo e abre perfil/cwd próprios.
- O diagnóstico compara o rótulo de versão/commit; a checagem integral do commit
  continua no plugin, dentro do runtime efetivo. Rótulo não é prova de execução.
- README e guia descrevem aprovação no terminal e retomada do mesmo banco.

## Evidências desta revisão

Os testes de onboarding usam XLSX temporários e contexto REAL para verificar o
contrato de importação. Isso **não equivale a executar a planilha original**.
O teste de integração do lançamento substitui somente o processo externo Hermes
por um adaptador controlado; não abre interface nem usa credenciais/rede.

| Verificação | Estado |
| --- | --- |
| Onboarding: importação, retomada, proteção de contexto, termos e lançamento | PASS: 15 testes, 28,51 s, após o refinamento final do guard de versão/commit. |
| Regressão unitária e integração | PASS: 804 aprovados e 2 ignorados, 698,08 s. Executada antes do último refinamento do guard, coberto pela rodada direcionada acima. |
| Ruff dos arquivos novos/alterados de onboarding | PASS: `onboarding.py` e `test_onboarding.py`. |
| Ruff geral | Quatro F401 em imports sob TYPE_CHECKING de `approvals.py`, alteração preexistente preservada. |
| Ruff format geral | PASS, 75 arquivos. |
| Diagramas Mermaid | Parse e render PASS; inspeção visual executada. |
| Slides | PASS: 15 slides/15 notas, 20 minutos, 30 verificações em 1366×768 e 1920×1080; teclado, fullscreen, hash/reload e notas reais; sem erro JS, HTTP ou requisição externa. Inspeção visual dos slides de arquitetura e encerramento. |
| Links locais | PASS: 84 links/âncoras em sete documentos. |
| Cópia preparada para Pages | HTML atualizado no worktree separado; workflow e oito assets validados. Sem publicação. |
| Instalação limpa em outra máquina/SO | NOT_RUN. |
| Planilha original no percurso REAL | NOT_RUN nesta revisão; anexo binário não disponível. Em 17/11, a planilha foi versionada e usada na [jornada REAL](../verification-desktop-real.md). |
| Desktop, modelo autenticado e pesquisa ao vivo | NOT_RUN nesta revisão. Em 17/11: [jornada REAL](../verification-desktop-real.md) com a planilha original até a viabilidade `PENDING` (PARCIAL, sem aceite nem preço) e [jornada `SIMULATION`](../verification-desktop-e2e.md) completa. |

Comandos executados no Windows, com o Python 3.13 da aplicação:

```powershell
.venv/Scripts/python.exe -X utf8 -B -m pytest tests/unit tests/integration -q --basetemp artifacts/private/real-onboarding-regression-1 --junitxml artifacts/private/real-onboarding-regression-1.xml
.venv/Scripts/python.exe -X utf8 -B -m pytest tests/integration/test_onboarding.py -q --basetemp artifacts/private/onboarding-final-targeted --junitxml artifacts/private/onboarding-final-targeted.xml
.venv/Scripts/python.exe -m ruff check src/dona_maria/onboarding.py tests/integration/test_onboarding.py
.venv/Scripts/python.exe -m ruff check src tests/conftest.py tests/unit tests/integration evals scripts
.venv/Scripts/python.exe -m ruff format --check src tests/conftest.py tests/unit tests/integration evals scripts
git diff --check
```

Os dois skips são anexo original ausente e criação de symlink sem privilégio
no Windows (1314). O lint geral não está verde: seus quatro F401 pertencem a
imports preexistentes em `approvals.py`, preservados fora do escopo desta mudança.
`git diff --check` passou. Os checks visuais usam scripts e evidências privados,
sem acrescentar dependências ao projeto. A pasta
temporária padrão do pytest apresentou erro de acesso no Windows, inclusive
fora do sandbox; usar uma pasta nova evitou reutilizar ou apagar dados anteriores.

## Gate humano antes da demonstração

Executar o percurso do README na versão/perfil final. Registrar SO, versão e
commit do backend, modelo/provedor, catálogo antes/depois da retomada, busca e
extração reais, decisões aprovadas, preço escolhido e persistência. Inspecionar
também cartões e mensagens automáticas do Desktop quanto a detalhes privados.
Não publicar credenciais, planilha, banco ou transcrição pessoal como evidência.

Uma limitação de pesquisa, modelo ou interface deve permanecer explícita.
Testes de núcleo não homologam Desktop; histórico CLI não comprova a nova jornada.
Nenhum commit, push, PR, merge ou publicação faz parte desta verificação.
