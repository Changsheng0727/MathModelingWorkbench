import { cpSync, existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(scriptDir, "..");
const repoRoot = resolve(frontendDir, "..");
const exportedDir = resolve(frontendDir, "out");
const staticDir = resolve(repoRoot, "app", "static");

if (!existsSync(exportedDir)) {
  throw new Error(`Next.js export output not found: ${exportedDir}`);
}

mkdirSync(staticDir, { recursive: true });
for (const item of readdirSync(staticDir)) {
  rmSync(resolve(staticDir, item), { recursive: true, force: true });
}
cpSync(exportedDir, staticDir, { recursive: true });

console.log(`Copied Next.js static export to ${staticDir}`);
