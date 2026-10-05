import { defineConfig } from "vitest/config";

export default defineConfig({
	test: {
		// RobotClaw-owned unit tests only. The imported pi-web-ui suite is kept
		// under vendor/pi-web-ui/tests as upstream reference.
		include: ["tests/unit/**/*.test.ts"],
		environment: "node",
		silent: true,
		onConsoleLog: () => false,
	},
});
