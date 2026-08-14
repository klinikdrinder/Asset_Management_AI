import "server-only";

import { spawn } from "node:child_process";

// Fallback video poster generation. Used only when Drive does not return a
// usable thumbnailLink for a video asset. Downloads a small leading byte
// range (enough to contain an early keyframe) and pipes it into ffmpeg to
// extract a single JPEG frame - never the whole file, and never buffered
// beyond that small range.
//
// ffmpeg is an optional runtime dependency: when it is not installed on the
// host, this degrades to "no poster" (the grid keeps its existing play
// overlay/category glyph) rather than failing the request or poisoning any
// cache entry.
const FRAME_TIMEOUT_MS = 15_000;

let ffmpegAvailable: boolean | null = null;

export async function isFfmpegAvailable(): Promise<boolean> {
  if (ffmpegAvailable !== null) return ffmpegAvailable;
  ffmpegAvailable = await new Promise<boolean>((resolve) => {
    const child = spawn("ffmpeg", ["-version"], { stdio: "ignore" });
    child.on("error", () => resolve(false));
    child.on("exit", (code) => resolve(code === 0));
  });
  return ffmpegAvailable;
}

export async function extractPosterFrame(videoBytes: Buffer): Promise<Buffer | null> {
  if (!(await isFfmpegAvailable())) return null;
  return new Promise((resolve) => {
    const child = spawn("ffmpeg", [
      "-y",
      "-ss", "0.5",
      "-i", "pipe:0",
      "-frames:v", "1",
      "-q:v", "4",
      "-f", "image2",
      "pipe:1",
    ], { stdio: ["pipe", "pipe", "ignore"] });

    const chunks: Buffer[] = [];
    const timer = setTimeout(() => { child.kill("SIGKILL"); resolve(null); }, FRAME_TIMEOUT_MS);
    child.stdout.on("data", (chunk: Buffer) => chunks.push(chunk));
    child.on("error", () => { clearTimeout(timer); resolve(null); });
    child.on("exit", (code) => {
      clearTimeout(timer);
      if (code !== 0 || !chunks.length) { resolve(null); return; }
      resolve(Buffer.concat(chunks));
    });
    child.stdin.on("error", () => { /* ffmpeg closed stdin early once it has a frame; ignore EPIPE */ });
    child.stdin.write(videoBytes);
    child.stdin.end();
  });
}
