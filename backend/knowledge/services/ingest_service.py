"""知识文档导入服务。"""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from ..ingestion.loader import load_documents
from ..ingestion.splitter import split_documents
from ..retrieval.common import iter_knowledge_files, knowledge_docs_dir
from ..vectorstore import build_vectorstore, upsert_vectorstore_documents


def preview_split_file(file_path: str, source_name: str | None = None) -> dict:
    docs = load_documents(file_path, source_name=source_name)
    chunks = split_documents(docs)
    return {
        "documents": len(docs),
        "chunks": len(chunks),
        "file_path": file_path,
        "source_name": source_name or file_path,
        "chunk_lengths": [len(chunk.page_content) for chunk in chunks],
    }


def rebuild_vectorstore_from_knowledge_dir() -> dict:
    docs = []
    files = iter_knowledge_files()
    total_files = len(files)
    print(f"[knowledge] rebuild started files={total_files}", flush=True)
    for index, path in enumerate(files, start=1):
        loaded_docs = load_documents(path)
        docs.extend(loaded_docs)
        relative_path = path.relative_to(knowledge_docs_dir())
        print(
            f"[knowledge] parsed file {index}/{total_files}: {relative_path} "
            f"documents={len(loaded_docs)} total_documents={len(docs)}",
            flush=True,
        )
    chunks = split_documents(docs)
    print(f"[knowledge] split completed chunks={len(chunks)}", flush=True)
    build_vectorstore(chunks, replace_existing=True)
    print(f"[knowledge] vectorstore rebuilt chunks={len(chunks)}", flush=True)
    return {
        "files": len(files),
        "documents": len(docs),
        "chunks": len(chunks),
        "knowledge_dir": str(knowledge_docs_dir()),
    }


def list_knowledge_files() -> list[dict]:
    root = knowledge_docs_dir()
    items: list[dict] = []
    for path in iter_knowledge_files():
        stat = path.stat()
        items.append(
            {
                "filename": str(path.relative_to(root)),
                "path": str(path),
                "size": int(stat.st_size),
            }
        )
    return items


def _resolve_knowledge_target(target_name: str) -> Path:
    normalized_name = str(target_name or "").strip()
    if not normalized_name:
        raise RuntimeError("知识文件名不能为空")
    root = knowledge_docs_dir().resolve()
    target_path = (root / normalized_name).resolve()
    if root != target_path and root not in target_path.parents:
        raise RuntimeError(f"非法知识文件路径：{normalized_name}")
    return target_path


def ingest_file(
    file_path: str,
    source_name: str | None = None,
    replace_existing: bool = True,
) -> dict:
    source = Path(file_path)
    target_filename = source_name or source.name
    target_path = _resolve_knowledge_target(target_filename)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists() and not replace_existing:
        raise RuntimeError(f"知识文件已存在：{target_filename}")

    shutil.copy2(source, target_path)
    stats = rebuild_vectorstore_from_knowledge_dir()
    stats.update(
        {
            "target_filename": target_filename,
            "target_path": str(target_path),
            "replace_existing": replace_existing,
        }
    )
    return stats


def _default_target_filename(source: Path) -> str:
    root = knowledge_docs_dir().resolve()
    resolved_source = source.resolve()
    if root == resolved_source or root in resolved_source.parents:
        return str(resolved_source.relative_to(root))
    return source.name


def upsert_file(
    file_path: str,
    source_name: str | None = None,
    replace_existing: bool = True,
) -> dict:
    source = Path(file_path)
    target_filename = source_name or _default_target_filename(source)
    target_path = _resolve_knowledge_target(target_filename)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists() and not replace_existing:
        raise RuntimeError(f"知识文件已存在：{target_filename}")

    if source.resolve() != target_path.resolve():
        shutil.copy2(source, target_path)

    metadata_filename = target_path.name
    docs = load_documents(target_path, source_name=metadata_filename)
    chunks = split_documents(docs)
    from ..vectorstore import load_vectorstore

    try:
        before_records = load_vectorstore().records
    except RuntimeError:
        before_records = []

    source_key = str(target_path.resolve())
    removed_chunks = sum(
        1
        for record in before_records
        if str((record.metadata or {}).get("source", "")) == source_key
        or str((record.metadata or {}).get("filename", "")) == metadata_filename
    )
    handle = upsert_vectorstore_documents(
        chunks,
        source_path=target_path,
        filename=metadata_filename,
    )
    return {
        "target_filename": target_filename,
        "target_path": str(target_path),
        "replace_existing": replace_existing,
        "documents": len(docs),
        "new_chunks": len(chunks),
        "removed_chunks": removed_chunks,
        "total_chunks": len(handle.records),
        "knowledge_dir": str(knowledge_docs_dir()),
    }


def ingest_uploaded_file(
    *,
    filename: str,
    raw_bytes: bytes,
    source_name: str | None = None,
    replace_existing: bool = True,
) -> dict:
    suffix = Path(filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".tmp") as tmp:
        tmp.write(raw_bytes)
        tmp_path = Path(tmp.name)
    try:
        preview = preview_split_file(str(tmp_path), source_name=source_name or filename)
        stats = ingest_file(
            str(tmp_path),
            source_name=source_name or filename,
            replace_existing=replace_existing,
        )
        stats.update(
            {
                "preview_documents": preview["documents"],
                "preview_chunks": preview["chunks"],
                "preview_chunk_lengths": preview["chunk_lengths"],
            }
        )
        return stats
    finally:
        tmp_path.unlink(missing_ok=True)


def delete_knowledge_file(target_name: str) -> dict:
    target_path = _resolve_knowledge_target(target_name)
    if not target_path.exists() or not target_path.is_file():
        raise RuntimeError(f"知识文件不存在：{target_name}")
    target_path.unlink()
    stats = rebuild_vectorstore_from_knowledge_dir()
    stats.update(
        {
            "deleted_filename": str(target_path.relative_to(knowledge_docs_dir())),
            "deleted_path": str(target_path),
        }
    )
    return stats
