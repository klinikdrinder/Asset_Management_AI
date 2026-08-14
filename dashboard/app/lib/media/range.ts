// Pure, dependency-free parsing of a single-range HTTP Range header
// (`bytes=start-end`, `bytes=start-`, or `bytes=-suffixLength`). Multi-range
// requests (`bytes=0-10,20-30`) are treated as invalid since browsers never
// send them for media/video seeking. Google Drive performs the actual byte
// slicing and 206/416 response; this module only decides whether the
// incoming header is well-formed enough to forward.

const RANGE_PATTERN = /^bytes=(\d*)-(\d*)$/;

export type ParsedRange = { start: number | null; end: number | null };

export function parseRangeHeader(header: string | null | undefined): ParsedRange | null {
  if (!header) return null;
  const match = RANGE_PATTERN.exec(header.trim());
  if (!match) return null;
  const [, startRaw, endRaw] = match;
  if (!startRaw && !endRaw) return null;
  const start = startRaw ? Number(startRaw) : null;
  const end = endRaw ? Number(endRaw) : null;
  if (start !== null && (!Number.isFinite(start) || start < 0)) return null;
  if (end !== null && (!Number.isFinite(end) || end < 0)) return null;
  if (start !== null && end !== null && start > end) return null;
  return { start, end };
}

export function isValidRangeHeader(header: string | null | undefined): boolean {
  return header == null || header === "" || parseRangeHeader(header) !== null;
}
