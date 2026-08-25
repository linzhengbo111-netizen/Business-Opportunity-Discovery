/**
 * Print the rendered stage-definition prompt block from the TypeScript
 * source of truth (src/lib/project_phase.ts).
 *
 * Used by scripts/check_stage_parity.sh to diff the TS block against the
 * Python one (crawler/project_phase.py), guaranteeing both AI paths get
 * byte-identical stage definitions.
 *
 * Run: node_modules/.bin/jiti scripts/print_stage_block.ts
 */

import { stagePromptBlock } from "../src/lib/project_phase";

process.stdout.write(stagePromptBlock());
