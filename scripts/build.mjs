// Bundles src/ into app.js and refreshes the cache-busting hashes in index.html.
// Usage: npm run build
import { build } from "esbuild";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

await build({
  entryPoints: ["src/main.js"],
  outfile: "app.js",
  bundle: true,
  format: "iife",
  minify: true,
  target: ["es2020", "safari16"],
  legalComments: "eof",
  logLevel: "info",
});

const hash = file => createHash("sha256").update(readFileSync(file)).digest("hex").slice(0, 10);
let html = readFileSync("index.html", "utf8");
for (const file of ["app.js", "styles.css"]) {
  const pattern = new RegExp(`(${file.replace(".", "\\.")})\\?v=[^"]*`);
  if (!pattern.test(html)) throw new Error(`index.html does not reference ${file}`);
  html = html.replace(pattern, `$1?v=${hash(file)}`);
}
writeFileSync("index.html", html);
console.log("index.html updated");
