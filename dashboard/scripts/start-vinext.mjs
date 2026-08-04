import path from "node:path";
import { loadEnv } from "vite";
import { StaticFileCache } from "../node_modules/vinext/dist/server/static-file-cache.js";
import { startProdServer } from "vinext/server/prod-server";

Object.assign(process.env, loadEnv("production", process.cwd(), ""));
process.env.NODE_ENV = "production";

function option(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

// vinext 0.0.50 builds StaticFileCache keys with Windows separators, while URL
// lookups use forward slashes. Disable only that metadata cache on Windows so
// the built-in traversal-safe filesystem fallback serves dist/client assets.
if (process.platform === "win32") StaticFileCache.create = async () => null;

const port = Number(option("--port", process.env.PORT ?? "3000"));
const host = option("--hostname", "0.0.0.0");
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error("Invalid port");

await startProdServer({ port, host, outDir: path.resolve("dist") });
