# Apresentação técnica — Sabor da Maria

- [Slides Reveal.js](slides/index.html): 15 slides (~17 minutos) + 5 de apêndice, notas em português.
- [Guia para Lucas Rolim](guia-apresentacao-lucas.md): fala de cada slide, ritmo,
  cortes e perguntas difíceis ligadas ao código.
- [Demo Hermes](demo-hermes.md): demo rápida de 8 minutos, somente leitura, no perfil REAL preparado.
- [Guia interativo da Dona Maria](../demo/hermes-desktop-walkthrough.html): prompts
  naturais da demonstração, também acessível pelo slide 11.
- [Verificação do percurso REAL](verification-local-real.md): testes atuais e pendências humanas.
- [Jornada E2E assistida no Desktop](../verification-desktop-e2e.md): ensaio `SIMULATION` concluído e intervenções operacionais.
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
python -m http.server 8765 --bind 127.0.0.1 --directory docs
```

Abra [a apresentação local](http://127.0.0.1:8765/speaker/slides/). Sirva somente
a pasta `docs`, para que o link do slide 11 abra o guia interativo; não sirva a
raiz do projeto nem `artifacts/private`. Encerre com Ctrl+C.
No GitHub Pages, que publica apenas a pasta dos slides, o mesmo link abre o
arquivo do guia no GitHub.
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

## Sistema visual e condução

O tema usa Manrope variável local ([OFL](slides/assets/fonts/Manrope-OFL.txt)),
fundo carvão, texto marfim e vermelho para destacar decisões. Cores, tipografia,
espaçamento e componentes ficam em `slides/src/deck.css`; os rodapés distinguem
os 15 slides principais do material de apoio. A apresentação mantém os arquivos
locais do Reveal.js e funciona offline.

Em `#/13`, a linha do tempo apresenta cinco etapas propostas, sem inventar
prazos ou tratar trabalho futuro como concluído. As setas destacam uma etapa
por vez, mantendo a sequência inteira visível. A impressão não duplica o slide
para cada destaque; animações são desativadas com redução de movimento.

## Editar o deck

O `index.html` é gerado. Edite `slides/src/index.template.html` (conteúdo e notas),
`slides/src/deck.css` (tema Tailwind) e rode:

```sh
cd docs/speaker/slides
npm ci
npm run build
```

- **Tailwind CSS v4** compila `src/deck.css` em `assets/deck.css`; o CSS do Reveal
  entra numa camada própria para não sobrepor as utilidades.
- **Ícones [Lucide](https://lucide.dev)** (ISC) entram inline no HTML com
  `{{icon nome classes}}`.
- **Diagramas** são carregados por `<img>` diretamente dos SVGs em
  `slides/assets/diagrams/`, com texto alternativo no template.
  O build preserva esses arquivos; substitua o SVG para atualizar a imagem.

### Editar um diagrama no tldraw ou no Excalidraw

Abra `slides/assets/diagrams/<nome>.tldr` na extensão tldraw do VS Code.
Depois de editar, exporte o SVG atualizado para a mesma pasta, preservando
o nome usado no template. Para edições no Excalidraw, exporte também como SVG.
O `npm run build` não recria nem sobrescreve os diagramas ou seus arquivos editáveis.

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
