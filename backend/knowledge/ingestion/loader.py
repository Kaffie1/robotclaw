"""文档加载器。

根据文件后缀把 txt/md 直接读成 Document，把 pdf/docx 交给 MinerU 解析，再统一返回带 metadata 的 LangChain Document。
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import List
import uuid

import requests
from langchain_core.documents import Document

from ...shared.config import (
    MINERU_API_URL,
    MINERU_BACKEND,
    MINERU_BIN,
    MINERU_MODEL_SOURCE,
    MINERU_OUTPUT_DIR,
    MINERU_PTXAS_PATH,
    MINERU_SERVER_URL,
    MINERU_TIMEOUT_SECONDS,
)


SUPPORTED_FILE_SUFFIXES = {".txt", ".md", ".docx", ".pdf"}


def export_markdown_preview(source_path: Path, markdown_text: str, suffix: str) -> Path:
    output_dir = source_path.parent
    output_path = output_dir / f"{source_path.stem}.{suffix}.md"
    output_path.write_text(markdown_text, encoding="utf-8")
    return output_path


def clean_extracted_text(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    lines = text.splitlines()
    cleaned_lines: List[str] = []
    numeric_buffer: List[str] = []
    numeric_run_active = False

    def flush_numeric_buffer() -> None:
        nonlocal numeric_buffer, numeric_run_active
        if not numeric_buffer:
            numeric_run_active = False
            return

        if len(numeric_buffer) < 3:
            cleaned_lines.extend(numeric_buffer)
        numeric_buffer = []
        numeric_run_active = False

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            if numeric_run_active:
                continue
            flush_numeric_buffer()
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue

        if re.fullmatch(r"\d+", stripped):
            numeric_buffer.append(stripped)
            numeric_run_active = True
            continue

        flush_numeric_buffer()
        cleaned_lines.append(line)

    flush_numeric_buffer()

    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)
    return cleaned_text.strip()


def _find_mineru_markdown(output_dir: Path, source_stem: str) -> Path:
    exact_matches = list(output_dir.rglob(f"{source_stem}.md"))
    if exact_matches:
        return sorted(exact_matches, key=lambda path: len(path.parts))[0]

    markdown_files = [
        path
        for path in output_dir.rglob("*.md")
        if not path.name.endswith(("_content_list.md", "_middle.md", "_model.md"))
    ]
    if not markdown_files:
        raise RuntimeError(f"MinerU did not generate a markdown file under {output_dir}")
    return sorted(markdown_files, key=lambda path: (len(path.parts), path.name))[0]


def _keep_only_mineru_markdown(markdown_path: Path) -> None:
    output_dir = markdown_path.parent
    for item in output_dir.iterdir():
        if item == markdown_path:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink(missing_ok=True)


def _run_mineru_api(file_path: Path) -> tuple[str, Path]:
    if not MINERU_API_URL:
        raise RuntimeError("MINERU_API_URL is required for MinerU API conversion")

    run_output_dir = Path(MINERU_OUTPUT_DIR) / f"{file_path.stem}-{uuid.uuid4().hex[:8]}"
    run_output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = run_output_dir / f"{file_path.stem}.md"

    data = {
        "lang_list": "ch",
        "backend": MINERU_BACKEND,
        "parse_method": "auto",
        "formula_enable": "true",
        "table_enable": "true",
        "server_url": MINERU_SERVER_URL,
        "return_md": "true",
        "return_middle_json": "false",
        "return_model_output": "false",
        "return_content_list": "false",
        "return_images": "false",
        "response_format_zip": "false",
        "return_original_file": "false",
    }
    if not MINERU_SERVER_URL:
        data.pop("server_url")

    with file_path.open("rb") as file_obj:
        response = requests.post(
            f"{MINERU_API_URL.rstrip('/')}/file_parse",
            data=data,
            files={"files": (file_path.name, file_obj)},
            timeout=MINERU_TIMEOUT_SECONDS,
        )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results", {})
    if not isinstance(results, dict):
        raise RuntimeError(f"MinerU API returned invalid results payload: {payload}")

    md_content = ""
    for result in results.values():
        if isinstance(result, dict) and result.get("md_content"):
            md_content = str(result["md_content"])
            break
    if not md_content:
        raise RuntimeError(f"MinerU API returned empty markdown content: {payload}")

    markdown_path.write_text(md_content, encoding="utf-8")
    return md_content, markdown_path


def _run_local_mineru(file_path: Path) -> tuple[str, Path]:
    if MINERU_API_URL:
        return _run_mineru_api(file_path)

    run_output_dir = Path(MINERU_OUTPUT_DIR) / f"{file_path.stem}-{uuid.uuid4().hex[:8]}"
    run_output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["MINERU_MODEL_SOURCE"] = MINERU_MODEL_SOURCE
    env["TRITON_PTXAS_PATH"] = MINERU_PTXAS_PATH
    env["PATH"] = f"{Path(MINERU_PTXAS_PATH).parent}:{env.get('PATH', '')}"

    command = [
        MINERU_BIN,
        "-p",
        str(file_path),
        "-o",
        str(run_output_dir),
        "-b",
        MINERU_BACKEND,
    ]
    if MINERU_API_URL:
        command.extend(["--api-url", MINERU_API_URL])
    if MINERU_SERVER_URL:
        command.extend(["-u", MINERU_SERVER_URL])

    result = subprocess.run(
        command,
        env=env,
        text=True,
        capture_output=True,
        timeout=MINERU_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "MinerU local conversion failed.\n"
            f"command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    markdown_path = _find_mineru_markdown(run_output_dir, file_path.stem)
    markdown_text = markdown_path.read_text(encoding="utf-8")
    _keep_only_mineru_markdown(markdown_path)
    return markdown_text, markdown_path


def load_with_mineru(file_path: str, *, filetype: str, source_name: str | None = None) -> List[Document]:
    path = Path(file_path)
    doc_id = str(uuid.uuid4())
    filename = source_name or path.name

    print(f"[loader] Starting local MinerU conversion: {filename}")
    markdown_text, mineru_markdown_path = _run_local_mineru(path)
    text = clean_extracted_text(markdown_text)
    if not text:
        raise RuntimeError("MinerU returned empty content")

    print("[loader] MinerU converted text sample (first 800 chars):")
    print("-" * 40)
    print(text[:800])
    print("-" * 40)

    preview_path = export_markdown_preview(path, text, "mineru")
    print(f"[loader] MinerU markdown preview exported to: {preview_path}")
    print(f"[loader] MinerU raw markdown output: {mineru_markdown_path}")

    return [
        Document(
            page_content=text,
            metadata={
                "source": str(path),
                "filename": filename,
                "filetype": filetype,
                "loader": "mineru",
                "structure_strategy": "mineru",
                "doc_id": doc_id,
                "preview_path": str(preview_path),
                "mineru_output_path": str(mineru_markdown_path),
                "mineru_backend": MINERU_BACKEND,
            },
        )
    ]


def load_txt(file_path: str, source_name: str | None = None) -> List[Document]:
    path = Path(file_path)
    doc_id = str(uuid.uuid4())
    text = path.read_text(encoding="utf-8")
    filename = source_name or path.name
    return [
        Document(
            page_content=text,
            metadata={
                "source": str(path),
                "filename": filename,
                "filetype": "txt",
                "doc_id": doc_id,
            },
        )
    ]


def load_md(file_path: str, source_name: str | None = None) -> List[Document]:
    path = Path(file_path)
    doc_id = str(uuid.uuid4())
    text = path.read_text(encoding="utf-8")
    filename = source_name or path.name
    return [
        Document(
            page_content=text,
            metadata={
                "source": str(path),
                "filename": filename,
                "filetype": "md",
                "doc_id": doc_id,
            },
        )
    ]


def load_docx(file_path: str, source_name: str | None = None) -> List[Document]:
    return load_with_mineru(file_path, filetype="docx", source_name=source_name)


def load_pdf(file_path: str, source_name: str | None = None) -> List[Document]:
    return load_with_mineru(file_path, filetype="pdf", source_name=source_name)


def load_documents(file_path: str | Path, source_name: str | None = None) -> List[Document]:
    suffix = Path(file_path).suffix.lower()

    if suffix == ".txt":
        return load_txt(str(file_path), source_name=source_name)
    if suffix == ".md":
        return load_md(str(file_path), source_name=source_name)
    if suffix == ".docx":
        return load_docx(str(file_path), source_name=source_name)
    if suffix == ".pdf":
        return load_pdf(str(file_path), source_name=source_name)

    raise ValueError(f"Unsupported file type: {suffix}")
