# Apresentação técnica — Sabor da Maria

- [Slides Reveal.js](slides/index.html): 14 slides (~15 minutos) + 5 de apêndice, notas em português.
- [Guia para Lucas Rolim](guia-apresentacao-lucas.md): fala de cada slide, ritmo,
  cortes e perguntas difíceis ligadas ao código.
- [Demo Hermes](demo-hermes.md): 5–10 minutos, Desktop, planilha real e aprovação no terminal.
- [Verificação do percurso REAL](verification-local-real.md): testes atuais e pendências humanas.
- [Verificação e limites S20](verification-s20.md): resultados reais e integração.

## Publicação no GitHub Pages

Após o primeiro deploy, acesse a
[apresentação online](https://glaucia86.github.io/sabor-da-maria-hermes-agent/).
O workflow [Publish presentation](../../.github/workflows/pages.yml) publica
`docs/speaker/slides` quando essa pasta ou o workflow muda na `main`.
Também permite disparo manual pela aba Actions, selecionando a `main`.
Em Settings → Pages, mantenha a origem como **GitHub Actions**.
Os arquivos gerados são publicados como versionados; ao editar as fontes,
execute o build abaixo e inclua os artefatos atualizados na alteração.

## Abrir localmente

Na raiz do checkout:

```sh
python -m http.server 8765 --bind 127.0.0.1 --directory docs/speaker/slides
```

Abra [a apresentação local](http://127.0.0.1:8765). Sirva somente a pasta dos
slides; não sirva a raiz do projeto nem `artifacts/private`. Encerre com Ctrl+C.
Setas/espaço navegam; **F** ativa tela cheia; **S** abre as notas da apresentadora;
**Esc** mostra a visão geral. Permita popup apenas para esse endereço local se
necessário. O plugin de notas exige HTTP local; abrir por `file://` não é o
percurso recomendado. Confirme a janela de notas antes de compartilhar tela.

Reveal.js **5.2.1**, CSS, JavaScript e plugin de notas ficam em
`slides/vendor/reveal-5.2.1/`, com [licença MIT](slides/vendor/reveal-5.2.1/LICENSE).
Sem CDN nem recursos remotos: `index.html`, `assets/deck.css`, os diagramas e a
fonte são versionados, então apresentar não exige Node nem internet.
Animação fade curta respeita redução de movimento.
Para imprimir, acrescente `?print-pdf` à URL e use a impressão do navegador.

## Editar o deck

O `index.html` é gerado. Edite `slides/src/index.template.html` (conteúdo e notas),
`slides/src/deck.css` (tema Tailwind) ou `slides/tools/build-deck.mjs` (diagramas) e rode:

```sh
cd docs/speaker/slides
npm ci
npm run build
```

- **Tailwind CSS v4** compila `src/deck.css` em `assets/deck.css`; o CSS do Reveal
  entra numa camada própria para não sobrepor as utilidades.
- **Ícones [Lucide](https://lucide.dev)** (ISC) entram inline no HTML com
  `{{icon nome classes}}`.
- **Diagramas estilo Excalidraw** são desenhados com [rough.js](https://roughjs.com)
  (MIT, seed fixa) e a fonte Excalifont ([OFL](slides/assets/fonts/Excalifont-OFL.txt)).
  Use `{{diagram nome}}` no template; cópias avulsas ficam em `slides/assets/diagrams/`.

### Editar um diagrama no tldraw ou no Excalidraw

Cada diagrama também é exportado como `slides/assets/diagrams/<nome>.excalidraw.json`
(formato de clipboard do Excalidraw). Copie todo o conteúdo do arquivo e cole com
**Ctrl+V** no [tldraw](https://www.tldraw.com) ou no [Excalidraw](https://excalidraw.com):
as caixas, textos e setas viram formas nativas e editáveis. Edições feitas lá não
voltam para o deck; para mudar os slides, ajuste `tools/build-deck.mjs`.

Para a extensão tldraw do VS Code, abra `slides/assets/diagrams/<nome>.tldr`.
Esses arquivos foram gerados uma vez a partir dos `.excalidraw.json` e não são
recriados pelo `npm run build`.

## Referência de organização

Estrutura editorial inspirada no
[deck do workshop](https://github.com/glaucia86/grok-bot-engineering-workshop/blob/main/docs/speaker/slides/index.html)
e no [guia da Glaucia](https://github.com/glaucia86/grok-bot-engineering-workshop/blob/main/docs/speaker/guia-glaucia.md):
tempos, notas, fala, checkpoint e cortes. O conteúdo técnico e o visual foram
escritos para este projeto; não foram importados exemplos ou métricas do workshop.
Funcionamento das notas: [documentação oficial Reveal.js](https://revealjs.com/speaker-view/).

## Antes da entrevista

Ensaie a jornada completa com o perfil definitivo e a planilha original.
Não apresente a demo como evidência de autonomia geral. A pesquisa real faz parte do percurso completo;
se falhar, registre a limitação sem apresentar uma receita própria como essa prova.
A apresentação local continua disponível independentemente do GitHub Pages.
