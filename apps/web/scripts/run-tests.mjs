#!/usr/bin/env node
// Node's native Web Storage global (behind --experimental-webstorage on some
// versions) shadows jsdom's window.localStorage in tests. Disabling it via
// --no-experimental-webstorage is only valid on Node versions that register
// the flag; older Node (e.g. CI's Node 20) rejects it with
// "is not allowed in NODE_OPTIONS". Check the current binary's allowlist
// instead of hardcoding a version cutoff.
import { spawnSync } from "node:child_process";

const flag = "--no-experimental-webstorage";
const nodeOptions = process.allowedNodeEnvironmentFlags.has(flag) ? flag : "";

const result = spawnSync("vitest", ["run"], {
  stdio: "inherit",
  shell: true,
  env: { ...process.env, NODE_OPTIONS: nodeOptions },
});

process.exit(result.status ?? 1);
