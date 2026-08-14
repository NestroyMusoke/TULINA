import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";

const root = resolve("dist");
const port = Number.parseInt(process.env.PORT ?? "8080", 10);
const types = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".ico", "image/x-icon"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".webmanifest", "application/manifest+json"],
]);

function safeAsset(pathname) {
  const relative = normalize(decodeURIComponent(pathname)).replace(/^([/\\])+/, "");
  const candidate = resolve(join(root, relative));
  return candidate === root || candidate.startsWith(`${root}${sep}`) ? candidate : null;
}

async function existingFile(pathname) {
  const candidate = safeAsset(pathname);
  if (!candidate) return null;
  try {
    return (await stat(candidate)).isFile() ? candidate : null;
  } catch {
    return null;
  }
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://localhost");
  if (url.pathname === "/healthz") {
    response.writeHead(200, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
    response.end('{"status":"ok","service":"tulina-web"}');
    return;
  }
  if (!request.method || !["GET", "HEAD"].includes(request.method)) {
    response.writeHead(405, { Allow: "GET, HEAD" });
    response.end();
    return;
  }
  const asset = (await existingFile(url.pathname)) ?? join(root, "index.html");
  const extension = extname(asset);
  const immutable = url.pathname.startsWith("/assets/") && asset !== join(root, "index.html");
  response.writeHead(200, {
    "Content-Type": types.get(extension) ?? "application/octet-stream",
    "Cache-Control": immutable ? "public, max-age=31536000, immutable" : "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
  });
  if (request.method === "HEAD") response.end();
  else createReadStream(asset).pipe(response);
});

server.listen(port, "0.0.0.0", () => {
  process.stdout.write(`${JSON.stringify({ severity: "INFO", service: "tulina-web", event: "SERVER_READY", port })}\n`);
});
