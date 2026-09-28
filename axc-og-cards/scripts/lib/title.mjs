// Rough estimate of wrapped line count for a bold title at a given font size,
// used to shrink the title until it fits within maxLines. Satori performs the
// real wrapping at render time; this only picks the font size.
export function estimateLineCount(text, fontSize, maxWidth) {
  const CHAR_WIDTH_FACTOR = 0.56;
  const charsPerLine = Math.max(1, Math.floor(maxWidth / (fontSize * CHAR_WIDTH_FACTOR)));
  const words = text.split(/\s+/).filter(Boolean);
  let lines = 1;
  let lineLen = 0;
  for (const word of words) {
    const wordLen = word.length + 1;
    if (lineLen + wordLen > charsPerLine && lineLen > 0) {
      lines++;
      lineLen = wordLen;
    } else {
      lineLen += wordLen;
    }
  }
  return lines;
}

export function fitTitleFontSize(title, maxWidth, maxLines) {
  const MAX_SIZE = 68;
  const MIN_SIZE = 38;
  const STEP = 2;
  for (let size = MAX_SIZE; size >= MIN_SIZE; size -= STEP) {
    if (estimateLineCount(title, size, maxWidth) <= maxLines) return size;
  }
  return MIN_SIZE;
}

export function formatMonthYear(date) {
  if (!date) return "";
  // UTC, not the machine's zone: a date-only value like 2024-05-01 parses as UTC
  // midnight and would otherwise print as "April 2024" west of UTC.
  return date.toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
}
