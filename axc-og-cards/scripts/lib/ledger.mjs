import { readFile, writeFile, access } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";

export async function exists(p) {
  try {
    await access(p, fsConstants.F_OK);
    return true;
  } catch {
    return false;
  }
}

export async function loadLedger(file) {
  if (!(await exists(file))) return [];
  const raw = await readFile(file, "utf8");
  return raw.trim() ? JSON.parse(raw) : [];
}

export async function saveLedger(file, ledger) {
  await writeFile(file, JSON.stringify(ledger, null, 2) + "\n", "utf8");
}

// Sums recorded spend. An entry without a numeric cost means real money was
// spent that we can't account for, so refuse to produce a total at all.
export function ledgerTotal(ledger, file = "the ledger") {
  let total = 0;
  for (const entry of ledger) {
    if (typeof entry.cost !== "number" || Number.isNaN(entry.cost)) {
      throw new Error(
        `Ledger entry for "${entry.slug}" (${entry.timestamp}) has no numeric cost. Refusing to continue until this is fixed by hand: ${file}`
      );
    }
    total += entry.cost;
  }
  return total;
}
