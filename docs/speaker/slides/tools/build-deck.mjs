// Gera index.html a partir do template, expandindo somente os ícones Lucide.
// Os diagramas são imagens versionadas em assets/diagrams; não os sobrescreva.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

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

const template = readFileSync(join(root, "src", "index.template.html"), "utf8");
const html = template
  .replace(/\{\{icon ([a-z0-9-]+)(?: ([^}]*))?\}\}/g, (_, name, classes = "") => lucide(name, classes.trim()));

writeFileSync(
  join(root, "index.html"),
  `<!-- Gerado por tools/build-deck.mjs a partir de src/index.template.html. Edite o template e rode npm run build. -->\n${html}`,
);
console.log("index.html gerado; diagramas preservados em assets/diagrams.");
