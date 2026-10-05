#!/usr/bin/env node
/** Run RobotClaw knowledge CLI with the same Python selection as the service. */

import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { delimiter } from "node:path";

const explicit = process.env.ROBOTCLAW_KNOWLEDGE_PYTHON?.trim();
const candidates = [explicit, "/opt/homebrew/Caskroom/miniforge/base/envs/langchain/bin/python", "python3"].filter(
	(value) => Boolean(value),
);
const python = candidates.find((candidate) => !candidate.startsWith("/") || existsSync(candidate));
if (!python) {
	console.error("No Python runtime found for the RobotClaw knowledge CLI.");
	process.exit(1);
}

const result = spawnSync(python, ["-m", "robotclaw_knowledge.ingestion", ...process.argv.slice(2)], {
	stdio: "inherit",
	env: {
		...process.env,
		PYTHONPATH: ["services/knowledge/src", process.env.PYTHONPATH].filter(Boolean).join(delimiter),
	},
});

process.exit(result.status ?? 1);
