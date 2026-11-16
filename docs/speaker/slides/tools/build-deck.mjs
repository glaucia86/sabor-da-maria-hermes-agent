// Gera index.html a partir de src/index.template.html:
//   {{icon nome classes}}  -> SVG Lucide inline
//   {{diagram nome}}       -> SVG estilo Excalidraw (rough.js, seed fixa)
// Também grava cada diagrama em assets/diagrams/ para uso fora do deck.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import rough from "roughjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const gen = rough.generator();

const INK = "#1e1e1e";
const TONES = {
  blue: ["#a5d8ff", "#1971c2"],
  green: ["#b2f2bb", "#2f9e44"],
  yellow: ["#ffec99", "#e8a400"],
  red: ["#ffc9c9", "#e03131"],
  violet: ["#d0bfff", "#6741d9"],
  orange: ["#ffd8a8", "#e8590c"],
  gray: ["#e9ecef", "#495057"],
};

let seed = 7;
const nextSeed = () => (seed = (seed * 48271) % 2147483647);
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// Espelho editável de cada diagrama no formato de clipboard do Excalidraw,
// que o tldraw (Ctrl+V) e o Excalidraw convertem em formas nativas.
let scene = null;
let elementId = 0;
function el(type, props) {
  if (!scene) return;
  elementId += 1;
  scene.push({
    id: `sdm-${elementId}`,
    type,
    angle: 0,
    strokeColor: INK,
    backgroundColor: "transparent",
    fillStyle: "hachure",
    strokeWidth: 2,
    strokeStyle: "solid",
    roughness: 1,
    opacity: 100,
    groupIds: [],
    frameId: null,
    roundness: null,
    seed: elementId,
    version: 1,
    versionNonce: elementId,
    isDeleted: false,
    boundElements: null,
    updated: 1,
    link: null,
    locked: false,
    ...props,
  });
}
function textEl(x, cy, text, size, color = INK, align = "center") {
  const width = Math.round(text.length * size * 0.55);
  const height = Math.round(size * 1.25);
  el("text", {
    x: align === "center" ? x - width / 2 : align === "right" ? x - width : x,
    y: cy - height / 2,
    width,
    height,
    text,
    originalText: text,
    fontSize: size,
    fontFamily: 1,
    textAlign: align,
    verticalAlign: "middle",
    containerId: null,
    lineHeight: 1.25,
    autoResize: true,
    strokeColor: color,
  });
}
function shapeEl(type, x, y, w, h, tone, { dash = false, fill } = {}) {
  el(type, {
    x,
    y,
    width: w,
    height: h,
    strokeColor: TONES[tone][1],
    backgroundColor: fill ?? TONES[tone][0],
    fillStyle: fill ? "solid" : "hachure",
    strokeStyle: dash ? "dashed" : "solid",
    roundness: type === "rectangle" ? { type: 3 } : null,
  });
}

function draw(drawable, { dash = false } = {}) {
  return gen
    .toPaths(drawable)
    .map(
      (p) =>
        `<path d="${p.d.replace(/-?\d+\.\d+/g, (n) => String(Math.round(Number(n) * 10) / 10))}" stroke="${p.stroke}" stroke-width="${p.strokeWidth}" fill="${p.fill ?? "none"}"` +
        `${dash && p.fill === undefined ? ' stroke-dasharray="10 8"' : ""} stroke-linecap="round" stroke-linejoin="round"/>`,
    )
    .join("");
}

function shapeOpts(tone, extra = {}) {
  const [fill, stroke] = TONES[tone];
  return {
    seed: nextSeed(),
    roughness: 1.1,
    bowing: 0.8,
    stroke,
    strokeWidth: 1.8,
    fill,
    fillStyle: "hachure",
    hachureGap: 7,
    hachureAngle: -41,
    fillWeight: 1.1,
    ...extra,
  };
}

function roundedPath(x, y, w, h, r = 14) {
  return `M${x + r} ${y} L${x + w - r} ${y} Q${x + w} ${y} ${x + w} ${y + r} L${x + w} ${y + h - r} Q${x + w} ${y + h} ${x + w - r} ${y + h} L${x + r} ${y + h} Q${x} ${y + h} ${x} ${y + h - r} L${x} ${y + r} Q${x} ${y} ${x + r} ${y} Z`;
}

// Linhas iniciadas por "`" são nomes de tools (fonte mono).
function label(cx, cy, lines, { size = 20, sub = 15.5, color = INK } = {}) {
  const heights = lines.map((l, i) => (i === 0 ? size : sub) * 1.28);
  let y = cy - heights.reduce((a, b) => a + b, 0) / 2;
  return lines
    .map((raw, i) => {
      const mono = raw.startsWith("`");
      const text = esc(mono ? raw.slice(1) : raw);
      const fs = i === 0 ? size : sub;
      y += heights[i];
      const family = mono ? ' font-family="Cascadia Code, Consolas, ui-monospace, monospace"' : "";
      const fill = i === 0 ? color : "#343a40";
      textEl(cx, y - heights[i] / 2, mono ? raw.slice(1) : raw, Math.round(i === 0 ? fs : fs * 0.9), fill);
      return `<text x="${cx}" y="${y - heights[i] * 0.26}" font-size="${mono ? Math.round(fs * 0.76) : fs}" text-anchor="middle" fill="${fill}"${family}>${text}</text>`;
    })
    .join("");
}

function box(x, y, w, h, tone, lines, opts = {}) {
  const o = shapeOpts(tone, opts.solid ? { fillStyle: "solid", fill: "#ffffff" } : {});
  if (opts.dash) o.strokeLineDash = [10, 8];
  shapeEl("rectangle", x, y, w, h, tone, { dash: opts.dash });
  return draw(gen.path(roundedPath(x, y, w, h), o), opts) + label(x + w / 2, y + h / 2, lines, opts);
}

// Contêiner sem hachura: caixa do Hermes e fronteiras tracejadas.
function frame(x, y, w, h, tone, { dash = false, fill } = {}) {
  shapeEl("rectangle", x, y, w, h, tone, { dash, fill: fill ?? "transparent" });
  const o = fill ? shapeOpts(tone, { fillStyle: "solid", fill }) : { ...shapeOpts(tone), fill: undefined };
  if (dash) o.strokeLineDash = [10, 8];
  return draw(gen.path(roundedPath(x, y, w, h, 18), o), { dash });
}

function ellipse(cx, cy, w, h, tone, lines, opts = {}) {
  shapeEl("ellipse", cx - w / 2, cy - h / 2, w, h, tone);
  return draw(gen.ellipse(cx, cy, w, h, shapeOpts(tone))) + label(cx, cy, lines, opts);
}

function diamond(cx, cy, w, h, tone, lines, opts = {}) {
  shapeEl("diamond", cx - w / 2, cy - h / 2, w, h, tone);
  const pts = [
    [cx, cy - h / 2],
    [cx + w / 2, cy],
    [cx, cy + h / 2],
    [cx - w / 2, cy],
  ];
  return draw(gen.polygon(pts, shapeOpts(tone))) + label(cx, cy, lines, { size: 18, sub: 14.5, ...opts });
}

function cylinder(x, y, w, h, tone, lines) {
  const ry = 14;
  const o = shapeOpts(tone);
  shapeEl("rectangle", x, y, w, h, tone);
  const body = `M${x} ${y + ry} L${x} ${y + h - ry} Q${x} ${y + h + ry} ${x + w / 2} ${y + h + ry * 0.2} Q${x + w} ${y + h + ry} ${x + w} ${y + h - ry} L${x + w} ${y + ry}`;
  return (
    draw(gen.path(`${body} Q${x + w} ${y - ry} ${x + w / 2} ${y - ry * 0.2} Q${x} ${y - ry} ${x} ${y + ry} Z`, o)) +
    draw(gen.ellipse(x + w / 2, y + ry, w, ry * 2, { ...shapeOpts(tone), fillStyle: "solid", fill: TONES[tone][0] })) +
    label(x + w / 2, y + h / 2 + ry / 2, lines)
  );
}

function arrow(points, { tone = "gray", text, at, dash = false, both = false } = {}) {
  const stroke = tone === "ink" ? INK : TONES[tone][1];
  const o = { seed: nextSeed(), roughness: 0.9, bowing: 1.2, stroke, strokeWidth: 1.9 };
  if (dash) o.strokeLineDash = [9, 7];
  const head = (tip, from) => {
    const ang = Math.atan2(tip[1] - from[1], tip[0] - from[0]);
    const len = 15;
    const wing = (d) => [tip[0] - len * Math.cos(ang + d), tip[1] - len * Math.sin(ang + d)];
    return draw(gen.linearPath([wing(0.42), tip, wing(-0.42)], { ...o, seed: nextSeed(), strokeLineDash: undefined }));
  };
  let out = draw(gen.linearPath(points, o), { dash });
  out += head(points.at(-1), points.at(-2));
  if (both) out += head(points[0], points[1]);
  const [x0, y0] = points[0];
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  el("arrow", {
    x: x0,
    y: y0,
    width: Math.max(...xs) - Math.min(...xs),
    height: Math.max(...ys) - Math.min(...ys),
    points: points.map(([px, py]) => [px - x0, py - y0]),
    strokeColor: stroke,
    strokeStyle: dash ? "dashed" : "solid",
    startArrowhead: both ? "arrow" : null,
    endArrowhead: "arrow",
    startBinding: null,
    endBinding: null,
    lastCommittedPoint: null,
  });
  if (text) {
    const [tx, ty] = at ?? points[0];
    textEl(tx, ty - 5, text, 15, stroke);
    out += `<text x="${tx}" y="${ty}" font-size="15" text-anchor="middle" fill="${stroke}">${esc(text)}</text>`;
  }
  return out;
}

function note(x, y, text, { tone = "gray", size = 15, anchor = "start" } = {}) {
  textEl(x, y - size * 0.35, text, size, TONES[tone][1], anchor === "middle" ? "center" : anchor === "end" ? "right" : "left");
  return `<text x="${x}" y="${y}" font-size="${size}" text-anchor="${anchor}" fill="${TONES[tone][1]}">${esc(text)}</text>`;
}

function svg(name, width, height, title, body) {
  return (
    `<svg class="diagram" data-diagram="${name}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="dg-${name}">` +
    `<title id="dg-${name}">${esc(title)}</title>` +
    `<g font-family="Excalifont, 'Segoe Print', cursive">${body}</g></svg>`
  );
}

const DIAGRAMS = {
  arquitetura: () =>
    svg(
      "arquitetura",
      1200,
      565,
      "Arquitetura: Dona Maria conversa com o Hermes Agent (context file, skill, plugin de política e plugin de pesquisa); o Hermes chama 6 tools via MCP stdio; o domínio Python valida e grava no SQLite. O plugin de pesquisa acessa a web com termos liberados. Fora do alcance do modelo, o operador usa a CLI de aprovação e o setup-real para importar a planilha.",
      [
        ellipse(85, 245, 150, 96, "red", ["Dona Maria", "conversa"]),
        frame(185, 95, 295, 315, "gray", { fill: "#f8f9fa" }),
        label(332, 124, ["Hermes Agent"], { size: 22 }),
        box(205, 148, 255, 52, "violet", ["Plugin de pesquisa", "2 tools · termos liberados"], { size: 17, sub: 14 }),
        box(205, 210, 255, 52, "blue", [".hermes.md + skill", "papel, linguagem, condução"], { size: 17, sub: 14 }),
        box(205, 272, 255, 52, "blue", ["Plugin de política", "allowlist + hooks"], { size: 17, sub: 14 }),
        box(205, 334, 255, 52, "gray", ["Modelo LLM", "escolhido no perfil"], { size: 17, sub: 14 }),
        box(530, 18, 200, 72, "violet", ["Web (DDGS)", "receitas e ofertas"]),
        arrow([[460, 172], [530, 62]], { tone: "violet", text: "busca mediada", at: [565, 150] }),
        box(530, 200, 190, 100, "green", ["MCP stdio", "6 tools", "contexto fixo"]),
        box(770, 145, 215, 210, "yellow", ["Domínio Python", "Pydantic + Decimal", "inventory · planning", "quotes · pricing", "approvals"]),
        cylinder(1030, 175, 155, 150, "blue", ["SQLite", "estado · histórico", "auditoria"]),
        arrow([[160, 245], [185, 245]], { tone: "ink", both: true }),
        arrow([[480, 250], [530, 250]], { tone: "ink", both: true }),
        arrow([[720, 250], [770, 250]], { tone: "ink", both: true }),
        arrow([[985, 250], [1030, 250]], { tone: "ink", both: true }),
        frame(530, 405, 660, 150, "orange", { dash: true }),
        note(550, 432, "Canal local do operador · fora do alcance do modelo", { tone: "orange", size: 16 }),
        ellipse(605, 500, 120, 66, "orange", ["Operador"]),
        box(695, 455, 230, 88, "orange", ["CLI de aprovação", "list · inspect · atestar"]),
        box(950, 455, 225, 88, "orange", ["setup-real", "importa o XLSX"]),
        arrow([[665, 500], [695, 500]], { tone: "orange" }),
        arrow([[810, 455], [850, 355]], { tone: "orange", text: "revalida e aplica", at: [910, 388] }),
        arrow([[1110, 455], [1110, 330]], { tone: "orange", text: "snapshot", at: [1150, 382] }),
        arrow([[85, 293], [85, 500], [545, 500]], { tone: "red", dash: true, text: "manifesta a decisão", at: [300, 490] }),
      ].join(""),
    ),

  "fluxo-despensa": () =>
    svg(
      "fluxo-despensa",
      1200,
      470,
      "Fluxo 1: o operador importa despensa_dona_maria.xlsx com setup-real; o custo unitário é o preço pago dividido pela quantidade comprada. O snapshot fica no SQLite. O Hermes consulta get_inventory_snapshot, pesquisa receitas com search_culinary_sources e extrai a fonte com extract_culinary_source, ou registra uma receita própria. As candidatas são apresentadas e Dona Maria dá feedback.",
      [
        box(20, 40, 240, 110, "blue", ["despensa_dona_maria", ".xlsx · Despensa + Precos", "37 ingredientes"], { size: 19, sub: 15 }),
        box(322, 40, 240, 110, "orange", ["setup-real (operador)", "custo = pago ÷ comprado", "ausente não vira zero"]),
        cylinder(630, 40, 225, 110, "blue", ["SQLite", "snapshot imutável"]),
        box(926, 40, 254, 110, "green", ["`get_inventory_snapshot", "o que existe", "e quanto custou"]),
        arrow([[260, 95], [322, 95]], { tone: "ink" }),
        arrow([[562, 95], [630, 95]], { tone: "ink" }),
        arrow([[855, 95], [926, 95]], { tone: "ink" }),
        arrow([[1053, 150], [1053, 300]], { tone: "violet", text: "termos liberados", at: [1000, 235] }),
        box(926, 300, 254, 110, "violet", ["`search_culinary_sources", "busca RECIPE", "na web"]),
        box(624, 300, 254, 110, "violet", ["`extract_culinary_source", "extrai por ID", "fonte + hash + horário"]),
        box(322, 300, 254, 110, "blue", ["Hermes apresenta", "candidatas com fonte", "e o que já tem"]),
        ellipse(140, 355, 240, 120, "red", ["Dona Maria", "gosta de cozinhar?", "vê impedimento?"], { size: 19, sub: 14.5 }),
        arrow([[926, 355], [878, 355]], { tone: "ink" }),
        arrow([[624, 355], [576, 355]], { tone: "ink" }),
        arrow([[322, 355], [262, 355]], { tone: "ink" }),
        box(330, 185, 240, 64, "gray", ["ou: receita própria", "sem URL · origem humana"], { dash: true, size: 17, sub: 14 }),
        arrow([[450, 249], [450, 300]], { tone: "gray", dash: true }),
        note(140, 450, "segue para o Fluxo 2", { tone: "red", anchor: "middle", size: 16 }),
      ].join(""),
    ),

  "fluxo-viabilidade": () =>
    svg(
      "fluxo-viabilidade",
      1200,
      470,
      "Fluxo 2: os requisitos da receita (equipamento, técnica, operação e ingredientes) são conferidos contra fatos confirmados. CONFIRMED segue; UNKNOWN vira pergunta e o fato informado passa por propose_user_change e aprovação local; BLOCKED exige rever o plano. Depois, evaluate_recipe_feasibility e evaluate_purchase_plan, que soma faltantes de todos os pratos, considera pacote inteiro e encargos e só conta ofertas confirmadas. Se cabe em R$ 80, está pronto para o aceite; senão, OVER_BUDGET.",
      [
        box(20, 30, 190, 110, "blue", ["Receita escolhida", "em discussão"]),
        box(250, 30, 250, 110, "blue", ["Requisitos do preparo", "equipamento · técnica", "operação · ingredientes"]),
        diamond(650, 85, 220, 130, "yellow", ["Fato", "confirmado?"]),
        box(800, 18, 200, 58, "green", ["CONFIRMED"]),
        box(800, 100, 200, 58, "red", ["BLOCKED", "rever o plano"], { size: 18, sub: 14 }),
        box(550, 195, 200, 72, "yellow", ["UNKNOWN", "perguntar à Dona Maria"], { size: 18, sub: 14.5 }),
        box(250, 195, 250, 72, "orange", ["`propose_user_change", "+ aprovação local"]),
        arrow([[210, 85], [250, 85]], { tone: "ink" }),
        arrow([[500, 85], [540, 85]], { tone: "ink" }),
        arrow([[760, 85], [800, 47]], { tone: "green" }),
        arrow([[760, 85], [800, 129]], { tone: "red" }),
        arrow([[650, 150], [650, 195]], { tone: "yellow" }),
        arrow([[550, 231], [500, 231]], { tone: "orange" }),
        arrow([[375, 195], [375, 140]], { tone: "orange", text: "fato registrado", at: [440, 175] }),
        arrow([[1000, 47], [1085, 47], [1085, 300]], { tone: "green" }),
        box(925, 300, 260, 120, "green", ["`evaluate_recipe_feasibility", "ELIGIBLE · PENDING", "BLOCKED"]),
        box(480, 290, 400, 140, "green", ["`evaluate_purchase_plan", "faltantes de todos os pratos", "pacote inteiro + encargos", "só ofertas confirmadas (24 h)"]),
        diamond(320, 360, 210, 130, "yellow", ["cabe em", "R$ 80?"]),
        box(20, 290, 175, 62, "green", ["Pronto", "para o aceite"], { size: 18, sub: 14.5 }),
        box(20, 378, 175, 62, "red", ["OVER_BUDGET", "rever compras"], { size: 18, sub: 14.5 }),
        arrow([[925, 360], [880, 360]], { tone: "green" }),
        arrow([[480, 360], [425, 360]], { tone: "ink" }),
        arrow([[215, 360], [195, 322]], { tone: "green", text: "sim", at: [222, 330] }),
        arrow([[215, 360], [195, 408]], { tone: "red", text: "não", at: [222, 405] }),
      ].join(""),
    ),

  "fluxo-aprovacao": () =>
    svg(
      "fluxo-aprovacao",
      1200,
      470,
      "Fluxo 3: Dona Maria manifesta uma decisão; o Hermes chama propose_user_change; a proposta fica pendente com resumo, hash e prazo de 10 minutos, sem alterar o negócio. No canal local, o operador lista e inspeciona o conteúdo exato e registra a atestação. A aplicação revalida revisão, prazo e regras: se ok, grava efeito e auditoria na mesma transação; se não, recusa sem efeito parcial. O Hermes consulta get_business_state e explica o resultado.",
      [
        ellipse(110, 90, 190, 104, "red", ["Dona Maria", "manifesta a decisão"], { size: 19, sub: 14.5 }),
        box(250, 40, 255, 100, "green", ["`propose_user_change", "chamada pelo Hermes"]),
        box(555, 40, 265, 100, "blue", ["Proposta pendente", "resumo + hash · 10 min", "negócio inalterado"]),
        frame(860, 12, 328, 448, "orange", { dash: true }),
        note(1024, 40, "Operador local · fora do modelo", { tone: "orange", anchor: "middle", size: 16 }),
        box(885, 62, 280, 95, "orange", ["CLI: list · inspect", "confere o conteúdo exato"]),
        box(885, 215, 280, 82, "orange", ["Atestação explícita", "da manifestação dela"]),
        diamond(690, 345, 230, 140, "yellow", ["Revalida", "revisão · prazo · regras"]),
        box(285, 268, 250, 80, "green", ["Efeito + auditoria", "na mesma transação"]),
        box(285, 370, 250, 72, "red", ["Recusa", "sem efeito parcial"]),
        box(20, 268, 225, 80, "blue", ["`get_business_state", "Hermes explica"]),
        arrow([[205, 90], [250, 90]], { tone: "ink" }),
        arrow([[505, 90], [555, 90]], { tone: "ink" }),
        arrow([[820, 100], [885, 108]], { tone: "orange" }),
        arrow([[1025, 157], [1025, 215]], { tone: "orange" }),
        arrow([[885, 256], [768, 318]], { tone: "orange" }),
        arrow([[575, 345], [535, 312]], { tone: "green", text: "ok", at: [570, 318] }),
        arrow([[575, 345], [535, 400]], { tone: "red", text: "falha", at: [580, 390] }),
        arrow([[285, 308], [245, 308]], { tone: "ink" }),
      ].join(""),
    ),

  "fluxo-preco": () =>
    svg(
      "fluxo-preco",
      1200,
      455,
      "Fluxo 4: com aceite vigente, calculate_pricing_scenarios calcula o CMV por porção (soma da quantidade usada vezes o custo da origem, dividida pelo rendimento) e gera piso e cenários M10, M20 e M30. Exemplo com CMV de R$ 10,00: piso R$ 11,12, M10 R$ 12,50, M20 R$ 14,29, M30 R$ 16,67. Dona Maria escolhe um cenário ou um preço próprio não abaixo do piso; a escolha vira proposta com aprovação local e se torna o preço vigente.",
      [
        box(20, 30, 200, 100, "green", ["Aceite vigente", "pré-condição"]),
        box(265, 30, 290, 100, "green", ["`calculate_pricing_scenarios", "grava o cálculo", "não escolhe o preço"]),
        box(600, 30, 360, 100, "yellow", ["CMV por porção", "soma(qtd usada × custo da origem)", "÷ rendimento do lote"]),
        arrow([[220, 80], [265, 80]], { tone: "ink" }),
        arrow([[555, 80], [600, 80]], { tone: "ink" }),
        draw(gen.linearPath([[780, 130], [780, 172], [127, 172], [127, 176]], { seed: nextSeed(), roughness: 0.9, stroke: INK, strokeWidth: 1.9 })),
        draw(gen.linearPath([[367, 172], [367, 176]], { seed: nextSeed(), roughness: 0.6, stroke: INK, strokeWidth: 1.9 })),
        draw(gen.linearPath([[607, 172], [607, 176]], { seed: nextSeed(), roughness: 0.6, stroke: INK, strokeWidth: 1.9 })),
        arrow([[127, 176], [127, 210]], { tone: "ink" }),
        arrow([[367, 176], [367, 210]], { tone: "ink" }),
        arrow([[607, 176], [607, 210]], { tone: "ink" }),
        arrow([[780, 172], [847, 172], [847, 210]], { tone: "ink" }),
        box(20, 210, 215, 125, "gray", ["Piso", "R$ 11,12", "sobra R$ 0,01"], { size: 21, sub: 17 }),
        box(260, 210, 215, 125, "blue", ["M10", "R$ 12,50", "sobra R$ 1,25"], { size: 21, sub: 17 }),
        box(500, 210, 215, 125, "blue", ["M20", "R$ 14,29", "sobra R$ 2,86"], { size: 21, sub: 17 }),
        box(740, 210, 215, 125, "blue", ["M30", "R$ 16,67", "sobra R$ 5,00"], { size: 21, sub: 17 }),
        note(487, 375, "exemplo com CMV de R$ 10,00 por porção · taxa de 10% sobre a venda", { anchor: "middle", size: 16 }),
        ellipse(1080, 200, 210, 112, "red", ["Dona Maria", "cenário ou preço", "próprio acima do piso"], { size: 19, sub: 14 }),
        arrow([[955, 272], [990, 230]], { tone: "red" }),
        box(978, 290, 205, 70, "orange", ["Proposta +", "aprovação local"], { size: 18, sub: 15 }),
        box(978, 385, 205, 58, "green", ["Preço vigente"]),
        arrow([[1080, 256], [1080, 290]], { tone: "orange" }),
        arrow([[1080, 360], [1080, 385]], { tone: "green" }),
      ].join(""),
    ),
};

function lucide(name, classes = "") {
  const file = join(root, "node_modules", "lucide-static", "icons", `${name}.svg`);
  let svgText;
  try {
    svgText = readFileSync(file, "utf8");
  } catch {
    throw new Error(`Ícone Lucide inexistente: ${name}`);
  }
  return svgText
    .replace(/<!--[\s\S]*?-->\s*/, "")
    .replace(/\s*\n\s*/g, " ")
    .replace(/class="([^"]*)"/, (_, base) => `class="${[base, classes].filter(Boolean).join(" ")}" aria-hidden="true" focusable="false"`)
    .replace(/ width="24" height="24"/, "")
    .replace(/> </g, "><")
    .trim();
}

const scenes = {};
const rendered = Object.fromEntries(
  Object.entries(DIAGRAMS).map(([name, fn]) => {
    scene = [];
    elementId = 0;
    const markup = fn();
    scenes[name] = scene;
    scene = null;
    return [name, markup];
  }),
);
mkdirSync(join(root, "assets", "diagrams"), { recursive: true });
for (const [name, markup] of Object.entries(rendered)) {
  const standalone = markup.replace(
    "<g ",
    `<style>@font-face{font-family:Excalifont;src:url("../fonts/Excalifont-Regular.woff2") format("woff2")}</style><rect width="100%" height="100%" fill="#fdfbf6"/><g `,
  );
  writeFileSync(join(root, "assets", "diagrams", `${name}.svg`), `${standalone}\n`);
  writeFileSync(
    join(root, "assets", "diagrams", `${name}.excalidraw.json`),
    `${JSON.stringify({ type: "excalidraw/clipboard", elements: scenes[name], files: {} }, null, 1)}\n`,
  );
}

const template = readFileSync(join(root, "src", "index.template.html"), "utf8");
const html = template
  .replace(/\{\{diagram ([a-z-]+)\}\}/g, (_, name) => {
    if (!rendered[name]) throw new Error(`Diagrama inexistente: ${name}`);
    return rendered[name];
  })
  .replace(/\{\{icon ([a-z0-9-]+)(?: ([^}]*))?\}\}/g, (_, name, classes = "") => lucide(name, classes.trim()));

writeFileSync(
  join(root, "index.html"),
  `<!-- Gerado por tools/build-deck.mjs a partir de src/index.template.html. Edite o template e rode npm run build. -->\n${html}`,
);
console.log(`index.html gerado com ${Object.keys(rendered).length} diagramas.`);
