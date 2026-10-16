// Local preview server (the site uses fetch(), so it can't be opened as a file://).
// Usage: npm run serve  →  http://localhost:8080
import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const root = process.cwd();
const port = Number(process.env.PORT) || 8080;
const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".jpg": "image/jpeg",
  ".png": "image/png",
  ".bin": "application/octet-stream",
};

createServer((request, response) => {
  let path = normalize(join(root, decodeURIComponent(new URL(request.url, "http://x").pathname)));
  if (!path.startsWith(root)) return response.writeHead(403).end();
  try {
    if (statSync(path).isDirectory()) path = join(path, "index.html");
    const { size } = statSync(path);
    response.writeHead(200, { "content-type": types[extname(path)] || "application/octet-stream", "content-length": size });
    createReadStream(path).pipe(response);
  } catch {
    response.writeHead(404).end("Not found");
  }
}).listen(port, () => console.log(`Renaissance em http://localhost:${port}`));
