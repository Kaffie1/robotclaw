#!/usr/bin/env node
/** Select a Python runtime for the optional BGE vector retriever. */

import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import { delimiter } from "node:path";

const explicit = process.env.ROBOTCLAW_KNOWLEDGE_PYTHON?.trim();
const candidates = [explicit, "/opt/homebrew/Caskroom/miniforge/base/envs/langchain/bin/python", "python3"].filter(
	(value) => Boolean(value),
);

const python = candidates.find((candidate) => !candidate.startsWith("/") || existsSync(candidate));
if (!python) {
	console.error("No Python runtime found for the RobotClaw knowledge service.");
	process.exit(1);
}

const child = spawn(
	python,
	[
		"-m",
		"robotclaw_knowledge.server",
		"--host",
		"127.0.0.1",
		"--port",
		process.env.ROBOTCLAW_KNOWLEDGE_PORT ?? "8790",
		"--index",
		process.env.ROBOTCLAW_KNOWLEDGE_INDEX ?? "data/vectorstore/index.json",
	],
	{
		stdio: "inherit",
		env: {
			...process.env,
			PYTHONPATH: ["services/knowledge/src", process.env.PYTHONPATH].filter(Boolean).join(delimiter),
		},
	},
);

for (const signal of ["SIGINT", "SIGTERM"]) {
	process.on(signal, () => child.kill(signal));
}

child.on("exit", (code) => {
	process.exit(code ?? 0);
});
