/**
 * Whether two excerpts are about the same part of a message: most of the
 * words of the shorter one are in the other (a part read again may be
 * quoted a little differently). Mirrors the server's api/assistant.is_about.
 */

function words(text: string): Set<string> {
  return new Set(text.toLocaleLowerCase().match(/[\p{L}\p{N}_]+/gu) ?? []);
}

export function sameExcerpt(a: string, b: string): boolean {
  const left = words(a);
  const right = words(b);
  if (left.size === 0 || right.size === 0) {
    return false;
  }
  const shared = [...left].filter((word) => right.has(word)).length;
  return shared / Math.min(left.size, right.size) >= 0.5;
}
