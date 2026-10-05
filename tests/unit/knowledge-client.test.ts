import { describe, expect, it } from "vitest";
import { formatKnowledgeContext } from "../../apps/gateway/src/knowledge-client.js";

describe("knowledge context", () => {
	it("keeps source metadata and citation instructions out of the user prompt", () => {
		const context = formatKnowledgeContext([
			{
				content: "电池信息由 /zj_humanoid/robot/battery_info 发布。",
				filename: "chassis接口.md",
				section: "Topic 总览",
				score: 12,
				chunk_id: 3,
			},
		]);
		expect(context).toContain("chassis接口.md / Topic 总览 / chunk 3");
		expect(context).toContain("[知识库：文件名 / 章节]");
	});

	it("returns null when retrieval has no evidence", () => {
		expect(formatKnowledgeContext([])).toBeNull();
	});
});
