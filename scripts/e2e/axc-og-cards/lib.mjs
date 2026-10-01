// Shared helpers for the axc-og-cards end-to-end harness: logging with secret
// redaction, running processes with everything captured, file snapshots, and
// the pass/fail/warn check collector used by the case validators.
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createWriteStream, appendFileSync, readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import path from "node:path";

const secrets = () => [process.env.OPENROUTER_API_KEY].filter((s) => s && s.length >= 8);

export function redact(text) {
  let out = String(text);
  for (const secret of secrets()) out = out.split(secret).join("***REDACTED***");
  return out;
}

export function createLogger(logFile) {
  const write = (level, msg) => {
    const line = `[${new Date().toISOString()}] [${level}] ${redact(msg)}`;
    console.log(line);
    appendFileSync(logFile, line + "\n");
  };
  return {
    info: (m) => write("INFO ", m),
    step: (m) => write("STEP ", m),
    warn: (m) => write("WARN ", m),
    error: (m) => write("ERROR", m),
    check: (c) => write(c.status.toUpperCase().padEnd(5), `${c.name}${c.detail ? ` -- ${c.detail}` : ""}`),
  };
}

const shellQuote = (s) => (/^[\w@%+=:,./-]+$/.test(s) ? s : `'${String(s).replace(/'/g, `'\\''`)}'`);
export const commandLine = (command, args) => [command, ...args].map(shellQuote).join(" ");

// Runs a command, logging the exact command line and capturing stdout/stderr.
// `onStdoutLine` sees each complete stdout line (used to log agent progress
// live); `streamFile` receives the raw stdout untouched.
export function runProcess(command, args, { cwd, env, logger, streamFile, onStdoutLine, timeoutMs = 0 }) {
  return new Promise((resolve) => {
    const started = Date.now();
    logger.info(`$ ${commandLine(command, args)}`);
    logger.info(`  cwd: ${cwd}`);
    const child = spawn(command, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
    const file = streamFile ? createWriteStream(streamFile) : null;
    let stdout = "";
    let stderr = "";
    let pending = "";
    let timedOut = false;
    const timer = timeoutMs > 0 ? setTimeout(() => { timedOut = true; child.kill("SIGKILL"); }, timeoutMs) : null;

    child.stdout.on("data", (d) => {
      const text = d.toString();
      stdout += text;
      file?.write(text);
      if (onStdoutLine) {
        pending += text;
        let i;
        while ((i = pending.indexOf("\n")) !== -1) {
          onStdoutLine(pending.slice(0, i));
          pending = pending.slice(i + 1);
        }
      }
    });
    child.stderr.on("data", (d) => { stderr += d.toString(); });
    child.on("error", (err) => { stderr += `spawn error: ${err.message}\n`; });
    child.on("close", (code, signal) => {
      if (timer) clearTimeout(timer);
      if (pending && onStdoutLine) onStdoutLine(pending);
      file?.end();
      resolve({ code: code ?? (signal ? 1 : 0), signal, stdout, stderr, timedOut, durationMs: Date.now() - started });
    });
  });
}

const sha = (buf) => createHash("sha256").update(buf).digest("hex");

function walk(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir)) {
    const p = path.join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

// Map of relative path -> sha256 for every file under the given paths.
export function snapshot(root, relPaths) {
  const map = new Map();
  for (const rel of relPaths) {
    const abs = path.join(root, rel);
    if (!existsSync(abs)) continue;
    const files = statSync(abs).isDirectory() ? walk(abs) : [abs];
    for (const f of files) map.set(path.relative(root, f), sha(readFileSync(f)));
  }
  return map;
}

// Collects named checks. "warn" is for things worth a human's eye that don't
// prove the skill is broken (e.g. wording of an approval request).
export function makeChecks() {
  const list = [];
  const add = (status, name, detail = "") => list.push({ status, name, detail: String(detail) });
  return {
    list,
    ok: (name, cond, detail) => add(cond ? "pass" : "fail", name, detail),
    warn: (name, cond, detail) => add(cond ? "pass" : "warn", name, detail),
    fail: (name, detail) => add("fail", name, detail),
  };
}

export const money = (n) => `$${Number(n).toFixed(4)}`;
