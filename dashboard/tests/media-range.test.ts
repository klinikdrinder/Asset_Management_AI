import test from "node:test";
import assert from "node:assert/strict";
import { isValidRangeHeader, parseRangeHeader } from "../app/lib/media/range";

test("a missing Range header is valid (means: send the whole file)", () => {
  assert.equal(isValidRangeHeader(null), true);
  assert.equal(isValidRangeHeader(undefined), true);
  assert.equal(isValidRangeHeader(""), true);
  assert.equal(parseRangeHeader(null), null);
});

test("well-formed single-range headers parse correctly", () => {
  assert.deepEqual(parseRangeHeader("bytes=0-1023"), { start: 0, end: 1023 });
  assert.deepEqual(parseRangeHeader("bytes=500-"), { start: 500, end: null });
  assert.deepEqual(parseRangeHeader("bytes=-500"), { start: null, end: 500 });
  assert.equal(isValidRangeHeader("bytes=0-1023"), true);
});

test("malformed Range headers are rejected rather than forwarded blindly", () => {
  for (const header of ["bytes=", "bytes=abc-def", "0-1023", "bytes=1023-0", "bytes=-", "chars=0-10"]) {
    assert.equal(parseRangeHeader(header), null, header);
    assert.equal(isValidRangeHeader(header), false, header);
  }
});

test("multi-range requests are rejected (browsers never send them for media seeking)", () => {
  assert.equal(parseRangeHeader("bytes=0-10,20-30"), null);
});

test("negative numbers are rejected", () => {
  assert.equal(parseRangeHeader("bytes=-1--5"), null);
});
