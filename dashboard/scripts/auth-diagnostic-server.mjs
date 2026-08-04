import http from "node:http";
import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";

const logDirectory = path.resolve(".logs");
const safe = (value, fallback = "none") => String(value ?? fallback).toLowerCase().replace(/[^a-z0-9_.:-]/g, "_").slice(0, 100);
const server = http.createServer((request, response) => {
  if (request.method !== "POST" || request.url !== "/auth-callback" || request.socket.remoteAddress !== "127.0.0.1") { response.writeHead(404).end(); return; }
  let body = "";
  request.setEncoding("utf8");
  request.on("data", (chunk) => { if (body.length < 8_192) body += chunk; });
  request.on("end", async () => {
    try {
      const input = JSON.parse(body);
      const output = { timestamp: safe(input.timestamp), stage: safe(input.stage), reason: safe(input.reason), status: Number(input.status) || 0, cookieNames: Array.isArray(input.cookieNames) ? input.cookieNames.filter((name) => /^sb-[a-z0-9-]+-auth-token/.test(name)).map((name) => safe(name)) : [], errorCode: safe(input.errorCode), errorClass: safe(input.errorClass), errorMessage: safe(input.errorMessage), redirectPath: String(input.redirectPath || "none").startsWith("/") ? String(input.redirectPath).split("?")[0] : "none" };
      await mkdir(logDirectory, { recursive: true });
      await appendFile(path.join(logDirectory, "auth-callback.log"), `${JSON.stringify(output)}\n`, "utf8");
      response.writeHead(204).end();
    } catch { response.writeHead(400).end(); }
  });
});
server.listen(3001, "127.0.0.1", () => console.log("AUTH_DIAGNOSTIC_SERVER_READY"));
