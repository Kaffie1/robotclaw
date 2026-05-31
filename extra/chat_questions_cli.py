from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import unicodedata


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHAT_DATA_DIR = PROJECT_ROOT / "data" / "chat"
DEFAULT_SOURCE_FILE = CHAT_DATA_DIR / "collected_questions.txt"
NORMALIZED_OUTPUT_PATH = CHAT_DATA_DIR / "normalized_questions.json"
FREQUENCY_OUTPUT_PATH = CHAT_DATA_DIR / "question_frequency.json"

_MULTISPACE_RE = re.compile(r"\s+")
_TRAILING_PUNCT_RE = re.compile(r"[\s,，.。!！?？;；:：~～、]+$")


def normalize_question(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.strip().lower()
    normalized = _MULTISPACE_RE.sub(" ", normalized)
    normalized = _TRAILING_PUNCT_RE.sub("", normalized)
    return normalized


def load_questions_from_chat_dir(source_file: Path) -> list[dict[str, str]]:
    if not source_file.exists() or not source_file.is_file():
        return []
    records: list[dict[str, str]] = []
    for raw_line in source_file.read_text(encoding="utf-8").splitlines():
        question = str(raw_line or "").strip()
        if not question:
            continue
        records.append(
            {
                "source_file": str(source_file.relative_to(CHAT_DATA_DIR)),
                "raw_question": question,
                "normalized_question": normalize_question(question),
            }
        )
    return records


def source_file_relative(path: Path) -> Path:
    try:
        return path.relative_to(PROJECT_ROOT)
    except ValueError:
        return path


def write_outputs(records: list[dict[str, str]], *, source_file: Path) -> dict:
    CHAT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    normalized_payload = {
        "total_questions": len(records),
        "items": records,
    }
    NORMALIZED_OUTPUT_PATH.write_text(
        json.dumps(normalized_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    counter = Counter(item["normalized_question"] for item in records if item["normalized_question"])
    frequency_items = [
        {"normalized_question": question, "count": count}
        for question, count in counter.most_common()
    ]
    frequency_payload = {
        "total_unique_questions": len(frequency_items),
        "items": frequency_items,
    }
    FREQUENCY_OUTPUT_PATH.write_text(
        json.dumps(frequency_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "source_file": str(source_file_relative(source_file)),
        "total_questions": len(records),
        "total_unique_questions": len(frequency_items),
        "normalized_output": str(NORMALIZED_OUTPUT_PATH.relative_to(PROJECT_ROOT)),
        "frequency_output": str(FREQUENCY_OUTPUT_PATH.relative_to(PROJECT_ROOT)),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="手动归一化 data/chat 下采集到的问题文本")
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize_parser = subparsers.add_parser("normalize", help="归一化 collected_questions.txt 并输出频次统计")
    normalize_parser.add_argument(
        "--source-file",
        default=str(DEFAULT_SOURCE_FILE),
        help="问题采集源文件，默认 data/chat/collected_questions.txt",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "normalize":
        source_file = Path(str(args.source_file or "")).expanduser().resolve()
        try:
            source_file.relative_to(CHAT_DATA_DIR.resolve())
        except ValueError as exc:
            parser.error("source-file 必须位于 data/chat 目录下")
            raise SystemExit(2) from exc
        records = load_questions_from_chat_dir(source_file)
        summary = write_outputs(records, source_file=source_file)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    parser.error(f"未知命令: {args.command}")


if __name__ == "__main__":
    main()
