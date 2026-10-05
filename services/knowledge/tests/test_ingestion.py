from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from robotclaw_knowledge.ingestion import (
	load_documents,
	rebuild_index,
	split_documents,
)
from robotclaw_knowledge.retrieval import KnowledgeIndex


class IngestionTest(unittest.TestCase):
	def test_markdown_chunking_preserves_heading_metadata(self) -> None:
		with tempfile.TemporaryDirectory() as directory:
			root = Path(directory)
			doc = root / "robot.md"
			doc.write_text(
				"\n".join(
					[
						"# 机器人软件SOP说明",
						"",
						"开场说明。",
						"",
						"## 底盘检查",
						"",
						"确认 battery_info 是否发布。",
						"",
						"## 定位检查",
						"",
						"确认 map 和 location 状态。",
					]
				),
				encoding="utf-8",
			)

			chunks = split_documents(load_documents(root), chunk_size=80, chunk_overlap=0)

			self.assertGreaterEqual(len(chunks), 2)
			self.assertEqual(chunks[0].metadata["filename"], "robot.md")
			self.assertEqual(chunks[0].metadata["parent_title"], "机器人软件SOP说明")
			self.assertEqual(chunks[0].metadata["section_title"], "底盘检查")
			self.assertEqual(chunks[0].metadata["chunk_id"], 0)

	def test_rebuild_index_writes_retrieval_compatible_json(self) -> None:
		with tempfile.TemporaryDirectory() as directory:
			root = Path(directory) / "knowledge"
			root.mkdir()
			(root / "chassis.md").write_text("# 底盘\n\n## 电池信息\n\n底盘通过 battery_info 发布电池信息。", encoding="utf-8")
			index_file = Path(directory) / "index.json"

			result = rebuild_index(root, index_file, chunk_size=120, chunk_overlap=0, embed=False)

			self.assertEqual(result["documents"], 1)
			self.assertTrue(index_file.exists())
			payload = json.loads(index_file.read_text(encoding="utf-8"))
			self.assertEqual(payload["embedding_signature"], {})
			self.assertEqual(payload["records"][0]["metadata"]["filename"], "chassis.md")

			index = KnowledgeIndex(index_file)
			hits = index.search("底盘没有电池信息", top_k=1)
			self.assertEqual(hits[0].filename, "chassis.md")


if __name__ == "__main__":
	unittest.main()
