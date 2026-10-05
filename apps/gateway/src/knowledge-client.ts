/** Automatic RAG retrieval through the Python knowledge service. */

export interface KnowledgeHit {
	content: string;
	filename: string;
	section: string;
	score: number;
	chunk_id: number | null;
	lexical_score?: number;
	vector_score?: number | null;
}

interface RetrieveResponse {
	hits?: KnowledgeHit[];
}

const KNOWLEDGE_URL = (process.env.ROBOTCLAW_KNOWLEDGE_URL ?? "http://127.0.0.1:8790").replace(/\/+$/, "");
const TOP_K = Math.max(1, Math.min(10, Number.parseInt(process.env.ROBOTCLAW_RAG_TOP_K ?? "3", 10) || 3));
const TIMEOUT_MS = Math.max(200, Number.parseInt(process.env.ROBOTCLAW_RAG_TIMEOUT_MS ?? "2500", 10) || 2500);

export async function retrieveKnowledge(query: string, parentSignal?: AbortSignal): Promise<KnowledgeHit[]> {
	const controller = new AbortController();
	const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
	const abort = () => controller.abort();
	parentSignal?.addEventListener("abort", abort, { once: true });
	try {
		const response = await fetch(`${KNOWLEDGE_URL}/retrieve`, {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify({ query, top_k: TOP_K }),
			signal: controller.signal,
		});
		if (!response.ok) return [];
		const payload = (await response.json()) as RetrieveResponse;
		return Array.isArray(payload.hits) ? payload.hits : [];
	} catch {
		return [];
	} finally {
		clearTimeout(timeout);
		parentSignal?.removeEventListener("abort", abort);
	}
}

export function formatKnowledgeContext(hits: readonly KnowledgeHit[]): string | null {
	if (hits.length === 0) return null;
	const blocks = hits.map((hit, index) => {
		const section = hit.section ? ` / ${hit.section}` : "";
		const chunk = hit.chunk_id === null ? "" : ` / chunk ${hit.chunk_id}`;
		const content = hit.content.length > 1500 ? `${hit.content.slice(0, 1500)}\n…` : hit.content;
		return `### 资料 ${index + 1}：${hit.filename}${section}${chunk}\n${content}`;
	});
	return [
		"以下内容由 RobotClaw 知识库自动检索，仅作为当前问题的参考证据。",
		"优先依据证据回答；证据不足时明确说明，不要补造接口、命令或版本信息。",
		"回答使用知识时，请在相关段落末标注 `[知识库：文件名 / 章节]`。",
		"",
		...blocks,
	].join("\n");
}
