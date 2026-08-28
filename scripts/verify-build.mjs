// Post-build guard: fail deploy if the client bundle is missing the Lark app_id.
// Catches machines building without .env — Vite inlines VITE_* vars at build time,
// so an empty VITE_LARK_APP_ID builds fine and silently breaks Lark login for everyone.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const assetsDir = "dist/client/assets";

const jsFiles = readdirSync(assetsDir).filter((f) => f.endsWith(".js"));
if (jsFiles.length === 0) {
  console.error("verify-build: no JS assets found in", assetsDir);
  process.exit(1);
}

let appIdCount = 0;
let errorCount = 0;
for (const f of jsFiles) {
  const content = readFileSync(join(assetsDir, f), "utf8");
  appIdCount += (content.match(/cli_aab/g) || []).length; // Lark app ids start with cli_aab
  errorCount += (content.match(/LARK_APP_ID is not configured/g) || []).length;
}

if (appIdCount === 0) {
  console.error("verify-build: VITE_LARK_APP_ID not inlined into bundle. Check .env / .env.production.");
  process.exit(1);
}
if (errorCount > 0) {
  console.error("verify-build: bundle contains the not-configured error path — app_id may be empty.");
  process.exit(1);
}
console.log(`verify-build: ok (app_id inlined x${appIdCount})`);
