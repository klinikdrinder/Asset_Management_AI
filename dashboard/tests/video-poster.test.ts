import test from "node:test";
import assert from "node:assert/strict";
import { extractPosterFrame, isFfmpegAvailable } from "../app/lib/media/video-poster";

test("ffmpeg availability check never throws, regardless of whether ffmpeg is installed", async () => {
  const available = await isFfmpegAvailable();
  assert.equal(typeof available, "boolean");
});

test("when ffmpeg is unavailable, poster extraction degrades to null instead of failing the request", async () => {
  if (await isFfmpegAvailable()) return; // this host has ffmpeg - the fallback path isn't exercised here
  const frame = await extractPosterFrame(Buffer.from("not a real video"));
  assert.equal(frame, null);
});
