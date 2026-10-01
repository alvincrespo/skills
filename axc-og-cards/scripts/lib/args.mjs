export const SPEND_MODES = ["strict", "auto", "yolo"];

const REMOVED_FLAGS = {
  "--yes": "--yes was replaced by --spend strict|auto|yolo.",
  "--only": "--only was replaced by passing post paths: og-cards.mjs path/to/post.md",
};

function isDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const d = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().startsWith(value);
}

function parsePositiveNumber(flag, value) {
  if (!/^\d+(\.\d+)?$/.test(value) || Number(value) <= 0) {
    throw new Error(`${flag} must be a positive number like 2 or 2.50, without a $ (got "${value}").`);
  }
  return Number(value);
}

// Parses the command line into an args object. Throws on anything ambiguous
// (unknown flags, missing values, flag combinations that don't make sense) so
// a typo can never turn into a silent dry run or a wider run than intended.
//
// `args.kind` is "status" (no target: report only, never spends) or "run".
export function parseArgs(argv) {
  const args = {
    config: "og-cards.config.json",
    paths: [],
    backfill: false,
    limit: null,
    since: null,
    before: null,
    regen: false,
    renderOnly: false,
    includeOverridden: false,
    spend: null,
    budget: null,
  };
  const given = new Set();

  for (let i = 0; i < argv.length; i++) {
    let arg = argv[i];
    if (!arg.startsWith("--")) {
      args.paths.push(arg);
      continue;
    }

    let inline = null;
    const eq = arg.indexOf("=");
    if (eq !== -1) {
      inline = arg.slice(eq + 1);
      arg = arg.slice(0, eq);
    }
    // A flag that takes a value; the value can't itself look like a flag.
    const value = () => {
      const v = inline ?? argv[++i];
      if (v === undefined || v === "" || v.startsWith("--")) throw new Error(`${arg} requires a value.`);
      return v;
    };

    given.add(arg);
    switch (arg) {
      case "--backfill": args.backfill = true; break;
      case "--regen": args.regen = true; break;
      case "--render-only": args.renderOnly = true; break;
      case "--include-overridden": args.includeOverridden = true; break;
      case "--config": args.config = value(); break;
      case "--spend": {
        const mode = value();
        if (!SPEND_MODES.includes(mode)) throw new Error(`--spend must be one of ${SPEND_MODES.join(", ")} (got "${mode}").`);
        args.spend = mode;
        break;
      }
      case "--budget": args.budget = parsePositiveNumber("--budget", value()); break;
      case "--limit": {
        const raw = value();
        if (!/^[1-9]\d*$/.test(raw)) throw new Error(`--limit must be a positive whole number (got "${raw}").`);
        args.limit = Number(raw);
        break;
      }
      case "--since":
      case "--before": {
        const raw = value();
        if (!isDate(raw)) throw new Error(`${arg} must be a date like 2024-05-01 (got "${raw}").`);
        args[arg.slice(2)] = raw;
        break;
      }
      default:
        throw new Error(REMOVED_FLAGS[arg] ?? `Unknown flag ${arg}.`);
    }
  }

  const hasTarget = args.paths.length > 0 || args.backfill;
  if (args.paths.length > 0 && args.backfill) {
    throw new Error("Pass post paths or --backfill, not both.");
  }
  if (!hasTarget) {
    const stray = ["--spend", "--budget", "--regen", "--render-only", "--limit", "--since", "--before", "--include-overridden"].filter((f) => given.has(f));
    if (stray.length > 0) {
      throw new Error(`${stray.join(", ")} needs a target: pass one or more post paths, or --backfill. With no target the command only reports status.`);
    }
  }
  if (args.regen && args.backfill) {
    throw new Error("--regen replaces existing illustrations, so it only works with named post paths, not --backfill.");
  }
  if (!args.backfill) {
    const stray = ["--limit", "--since", "--before"].filter((f) => given.has(f));
    if (stray.length > 0) throw new Error(`${stray.join(", ")} only works with --backfill.`);
  }

  args.kind = hasTarget ? "run" : "status";
  return args;
}
