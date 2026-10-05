import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildAttachmentMessages } from "../../apps/gateway/src/attachments.js";
import { initAttachmentStore } from "../../apps/gateway/src/attachment-store.js";

const PNG_1X1 =
	"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

function fakeSession(input: string[]) {
	return {
		model: { id: "test-model", name: "test-model", input },
		modelRuntime: {
			getProviders: () => [],
			hasConfiguredAuth: () => false,
			getModels: () => [],
			getModel: () => null,
			completeSimple: () => {
				throw new Error("vision bridge should not run in this test");
			},
		},
	} as never;
}

describe("attachments", () => {
	it("converts imageData attachments into Pi image content blocks", async () => {
		initAttachmentStore(mkdtempSync(join(tmpdir(), "robotclaw-attachments-")));
		const notices: unknown[] = [];

		const result = await buildAttachmentMessages(
			{
				cwd: process.cwd(),
				clientId: "unit-test",
				emit: (message) => notices.push(message),
				settings: {
					visionBridgeEnabled: true,
					visionBridgeModel: null,
					visionBridgePromptMode: "append",
					visionBridgePrompt: "",
				} as never,
				session: fakeSession(["text", "image"]),
				getLang: () => "zh",
			},
			[{ path: "", name: "verify.png", imageData: PNG_1X1, mimeType: "image/png" }],
		);

		expect(notices).toEqual([]);
		expect(result).toHaveLength(1);
		const message = result[0].message;
		expect(message.customType).toBe("file");
		expect(message.details).toMatchObject({ name: "verify.png", mode: "image", size: 70 });
		expect(message.content).toHaveLength(1);
		expect(message.content[0]).toMatchObject({
			type: "image",
			data: PNG_1X1,
			mimeType: "image/png",
			source: { type: "url" },
		});
	});
});
