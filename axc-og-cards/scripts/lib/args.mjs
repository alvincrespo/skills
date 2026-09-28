function parseSlugList(flag, value) {
  const list = (value ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  if (list.length === 0) {
    throw new Error(`${flag} requires a comma-separated list of slugs (got none). Aborting rather than silently matching zero posts.`);
  }
  return list;
}

export function parseArgs(argv) {
  const args = { yes: false, only: null, regen: null, renderOnly: false, config: "og-cards.config.json" };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--yes") args.yes = true;
    else if (arg === "--render-only") args.renderOnly = true;
    else if (arg === "--config") {
      args.config = argv[++i];
      if (!args.config) throw new Error("--config requires a path.");
    } else if (arg.startsWith("--config=")) args.config = arg.slice(9);
    else if (arg === "--only") args.only = parseSlugList("--only", argv[++i]);
    else if (arg === "--regen") args.regen = parseSlugList("--regen", argv[++i]);
    else if (arg.startsWith("--only=")) args.only = parseSlugList("--only", arg.slice(7));
    else if (arg.startsWith("--regen=")) args.regen = parseSlugList("--regen", arg.slice(8));
  }
  return args;
}
