# Apresentação técnica — Sabor da Maria

- [Slides Reveal.js](slides/index.html): 15 slides, 20 minutos, notas em português.
- [Guia para Lucas Rolim](guia-apresentacao-lucas.md): fala, decisão, trade-off,
  transição e corte para cada slide; perguntas difíceis ligadas ao código.
- [Demo Hermes](demo-hermes.md): 5–10 minutos, Desktop, planilha real e aprovação no terminal.
- [Verificação do percurso REAL](verification-local-real.md): testes atuais e pendências humanas.
- [Verificação e limites S20](verification-s20.md): resultados reais e integração.

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
Sem CDN, fontes remotas, imagens decorativas ou dependência de build Node.
Tipografia do sistema; animação fade curta respeita redução de movimento.
Para imprimir, acrescente `?print-pdf` à URL e use a impressão do navegador.

## Referência de organização

Estrutura editorial inspirada no
[deck do workshop](https://github.com/glaucia86/grok-bot-engineering-workshop/blob/main/docs/speaker/slides/index.html)
e no [guia da Glaucia](https://github.com/glaucia86/grok-bot-engineering-workshop/blob/main/docs/speaker/guia-glaucia.md):
tempos, notas, fala, checkpoint e cortes. O conteúdo técnico e o visual foram
escritos para este projeto; não foram importados exemplos ou métricas do workshop.
Funcionamento das notas: [documentação oficial Reveal.js](https://revealjs.com/speaker-view/).

## Antes da entrevista

Ensaie com o perfil definitivo, leia o relatório S20 e confira o status S19.
Não apresente a demo como evidência de autonomia geral. A pesquisa real faz parte do percurso completo;
se falhar, registre a limitação sem apresentar uma receita própria como essa prova.
Nenhuma publicação em GitHub Pages foi feita ou é necessária para apresentar.
