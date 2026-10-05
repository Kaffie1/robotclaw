from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from robotclaw_knowledge.retrieval import KnowledgeIndex


class RetrievalTest(unittest.TestCase):
	def test_returns_matching_robot_document(self) -> None:
		with tempfile.TemporaryDirectory() as directory:
			index_file = Path(directory) / "index.json"
			index_file.write_text(
				json.dumps(
					{
						"records": [
							{
								"page_content": "底盘通过 battery_info 话题发布电池信息。",
								"metadata": {"filename": "chassis.md", "section_title": "电池信息", "chunk_id": 1},
							},
							{
								"page_content": "地图服务负责加载静态地图。",
								"metadata": {"filename": "map.md", "section_title": "地图"},
							},
						]
					},
					ensure_ascii=False,
				),
				encoding="utf-8",
			)
			index = KnowledgeIndex(index_file)
			hits = index.search("底盘没有电池信息", top_k=1)
			self.assertEqual(len(hits), 1)
			self.assertEqual(hits[0].filename, "chassis.md")

	def test_hybrid_search_can_use_stored_embeddings(self) -> None:
		with tempfile.TemporaryDirectory() as directory:
			index_file = Path(directory) / "index.json"
			index_file.write_text(
				json.dumps(
					{
						"records": [
							{
								"page_content": "无明显关键词的相关资料",
								"metadata": {"filename": "related.md"},
								"embedding": [1.0, 0.0],
							},
							{
								"page_content": "另一份资料",
								"metadata": {"filename": "other.md"},
								"embedding": [0.0, 1.0],
							},
						]
					}
				),
				encoding="utf-8",
			)
			index = KnowledgeIndex(index_file)
			hits = index.search("完全不同的查询", top_k=1, query_embedding=[1.0, 0.0])
			self.assertEqual(hits[0].filename, "related.md")
			self.assertEqual(hits[0].vector_score, 1.0)


if __name__ == "__main__":
	unittest.main()
