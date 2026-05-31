from __future__ import annotations

import argparse
import json
from typing import Any

from .services import (
    delete_knowledge_file,
    ingest_file,
    list_knowledge_files,
    preview_split_file,
    rebuild_vectorstore_from_knowledge_dir,
)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="知识库文件切分、入库与删除 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="列出当前知识库文件")

    preview_parser = subparsers.add_parser("preview", help="预览单个文件的切分结果")
    preview_parser.add_argument("file_path", help="本地文件路径")
    preview_parser.add_argument("--source-name", default="", help="预览时使用的源文件名")

    ingest_parser = subparsers.add_parser("ingest", help="导入文件到知识库并重建向量库")
    ingest_parser.add_argument("file_path", help="本地文件路径")
    ingest_parser.add_argument("--source-name", default="", help="入库后的文件名")
    ingest_parser.add_argument(
        "--replace-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="同名文件是否覆盖，默认覆盖",
    )

    delete_parser = subparsers.add_parser("delete", help="从知识库删除文件并重建向量库")
    delete_parser.add_argument("target_name", help="知识库中的相对文件名，例如 mapping.md")

    subparsers.add_parser("rebuild", help="基于 data/knowledge 全量重建向量库")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list":
        items = list_knowledge_files()
        _print_json({"total": len(items), "items": items})
        return

    if args.command == "preview":
        result = preview_split_file(
            args.file_path,
            source_name=str(args.source_name or "").strip() or None,
        )
        _print_json(result)
        return

    if args.command == "ingest":
        result = ingest_file(
            args.file_path,
            source_name=str(args.source_name or "").strip() or None,
            replace_existing=bool(args.replace_existing),
        )
        _print_json(result)
        return

    if args.command == "delete":
        result = delete_knowledge_file(args.target_name)
        _print_json(result)
        return

    if args.command == "rebuild":
        result = rebuild_vectorstore_from_knowledge_dir()
        _print_json(result)
        return

    parser.error(f"未知命令: {args.command}")


if __name__ == "__main__":
    main()
