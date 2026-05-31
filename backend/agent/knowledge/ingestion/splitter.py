"""文档切分器。

优先按 Markdown 标题结构切分，再用字符窗口二次切块，并保留 chunk_id、标题路径和来源文件等 metadata。
"""

from __future__ import annotations

import re
from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ....core.config import CHUNK_OVERLAP, CHUNK_SIZE, SHOW_CHUNK_CONTENT


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
FENCED_CODE_PATTERN = re.compile(r"^(```|~~~)")


def debug_print_first_level_split(
    first_level_title: str | None,
    original_length: int,
    second_level_titles: list[str],
    packed_sections: list[Document],
) -> None:
    lines = [
        "=== First Level Split ===",
        f"first_level_title = {first_level_title}",
        f"original_length = {original_length}",
        f"second_level_titles = {second_level_titles}",
        f"packed_count = {len(packed_sections)}",
    ]
    for idx, section in enumerate(packed_sections, start=1):
        preview = section.page_content.strip().splitlines()[0] if section.page_content.strip() else ""
        lines.append(f"[{idx}] packed_length = {len(section.page_content)} preview = {preview}")
        if SHOW_CHUNK_CONTENT:
            lines.append(section.page_content)
    lines.append("-" * 50)
    print("\n".join(lines))


def debug_print_second_level_split(
    parent_title: str | None,
    second_level_title: str | None,
    original_length: int,
    third_level_titles: list[str],
    packed_sections: list[Document],
) -> None:
    lines = [
        "=== Second Level Split ===",
        f"parent_title = {parent_title}",
        f"second_level_title = {second_level_title}",
        f"original_length = {original_length}",
        f"third_level_titles = {third_level_titles}",
        f"packed_count = {len(packed_sections)}",
    ]
    for idx, section in enumerate(packed_sections, start=1):
        preview = section.page_content.strip().splitlines()[0] if section.page_content.strip() else ""
        lines.append(f"[{idx}] packed_length = {len(section.page_content)} preview = {preview}")
        if SHOW_CHUNK_CONTENT:
            lines.append(section.page_content)
    lines.append("-" * 50)
    print("\n".join(lines))


def is_heading_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("## ") or stripped.startswith("### ")


def parse_heading_line(line: str) -> tuple[int, str] | None:
    match = HEADING_PATTERN.match(line.strip())
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def is_fenced_code_line(line: str) -> bool:
    return bool(FENCED_CODE_PATTERN.match(line.strip()))


def is_heading_only_content(content: str) -> bool:
    non_empty_lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(non_empty_lines) != 1:
        return False
    parsed = parse_heading_line(non_empty_lines[0])
    if parsed is None:
        return False
    return True


def choose_section_heading_level(document: Document) -> int | None:
    levels = set()
    in_fenced_code = False
    for line in document.page_content.splitlines():
        if is_fenced_code_line(line):
            in_fenced_code = not in_fenced_code
            continue
        if in_fenced_code:
            continue
        parsed = parse_heading_line(line)
        if parsed is None:
            continue
        level, _ = parsed
        levels.add(level)
    if 1 in levels:
        return 1
    if 2 in levels:
        return 2
    return None


def split_document_by_heading_level(document: Document, selected_level: int | None) -> List[Document]:
    if selected_level is None:
        metadata = dict(document.metadata)
        metadata["selected_heading_level"] = None
        return [Document(page_content=document.page_content, metadata=metadata)]

    sections: List[Document] = []
    preamble_lines: List[str] = []
    current_lines: List[str] = []
    current_section_title: str | None = None
    current_parent_title: str | None = None
    active_parent_title: str | None = None
    first_section_started = False
    in_fenced_code = False

    def flush_current() -> None:
        nonlocal current_lines, current_section_title, current_parent_title
        content = "\n".join(current_lines).strip()
        if content:
            metadata = dict(document.metadata)
            metadata["selected_heading_level"] = selected_level
            metadata["section_title"] = current_section_title
            if current_parent_title:
                metadata["parent_title"] = current_parent_title
            sections.append(Document(page_content=content, metadata=metadata))
        current_lines = []
        current_section_title = None
        current_parent_title = None

    for line in document.page_content.splitlines():
        if is_fenced_code_line(line):
            in_fenced_code = not in_fenced_code
            parsed = None
        elif in_fenced_code:
            parsed = None
        else:
            parsed = parse_heading_line(line)
        if parsed is not None:
            level, title = parsed
            if level == 1:
                active_parent_title = title

            if level == selected_level:
                if first_section_started:
                    flush_current()
                else:
                    first_section_started = True
                current_section_title = title
                current_parent_title = active_parent_title if selected_level > 1 else None
                current_lines = []
                if preamble_lines:
                    current_lines.extend(preamble_lines)
                    preamble_lines = []
                current_lines.append(line)
                continue

        if first_section_started:
            current_lines.append(line)
        else:
            preamble_lines.append(line)

    if first_section_started:
        flush_current()
    else:
        metadata = dict(document.metadata)
        metadata["selected_heading_level"] = None
        metadata.pop("parent_title", None)
        metadata.pop("section_title", None)
        return [Document(page_content=document.page_content, metadata=metadata)]

    return sections


def split_document_by_heading_structure(document: Document) -> List[Document]:
    selected_level = choose_section_heading_level(document)
    return split_document_by_heading_level(document, selected_level)


def append_unit_text(current_content: str, unit_content: str) -> str:
    if not current_content:
        return unit_content
    return f"{current_content}\n\n{unit_content}"


def pack_document_on_heading_boundaries(
    document: Document,
    child_level: int,
    *,
    chunk_size: int,
    preserve_parent_metadata: bool,
    promote_single_child_metadata: bool = False,
) -> List[Document]:
    if document.metadata.get("selected_heading_level") != child_level - 1:
        return [document]

    child_sections = split_document_by_heading_level(document, child_level)
    meaningful_sections = [
        section for section in child_sections if section.metadata.get("section_title") is not None
    ]
    if len(meaningful_sections) <= 1:
        return [document]

    packed_sections: List[Document] = []
    current_content = ""
    current_child_sections: List[Document] = []

    def flush_current() -> None:
        nonlocal current_content, current_child_sections
        if current_content.strip():
            if preserve_parent_metadata:
                if promote_single_child_metadata and len(current_child_sections) == 1:
                    metadata = dict(current_child_sections[0].metadata)
                else:
                    metadata = dict(document.metadata)
            else:
                metadata = dict(document.metadata)
            packed_sections.append(Document(page_content=current_content.strip(), metadata=metadata))
        current_content = ""
        current_child_sections = []

    for section in meaningful_sections:
        section_content = section.page_content.strip()
        if not section_content:
            continue
        current_content = append_unit_text(current_content, section_content)
        current_child_sections.append(section)
        if len(current_content) > chunk_size:
            flush_current()

    flush_current()
    return packed_sections or [document]


def split_oversized_first_level_section(document: Document, *, chunk_size: int) -> List[Document]:
    if document.metadata.get("selected_heading_level") != 1:
        return [document]

    packed_sections = pack_document_on_heading_boundaries(
        document,
        2,
        chunk_size=chunk_size,
        preserve_parent_metadata=True,
        promote_single_child_metadata=True,
    )
    debug_print_first_level_split(
        document.metadata.get("section_title"),
        len(document.page_content),
        [
            section.metadata.get("section_title")
            for section in split_document_by_heading_level(document, 2)
            if section.metadata.get("section_title") is not None
        ],
        packed_sections,
    )
    return packed_sections or [document]


def split_oversized_second_level_section(document: Document, *, chunk_size: int) -> List[Document]:
    if document.metadata.get("selected_heading_level") != 2:
        return [document]

    packed_sections = pack_document_on_heading_boundaries(
        document,
        3,
        chunk_size=chunk_size,
        preserve_parent_metadata=True,
    )
    debug_print_second_level_split(
        document.metadata.get("parent_title"),
        document.metadata.get("section_title"),
        len(document.page_content),
        [
            section.metadata.get("section_title")
            for section in split_document_by_heading_level(document, 3)
            if section.metadata.get("section_title") is not None
        ],
        packed_sections,
    )
    return packed_sections


def split_oversized_third_level_section(document: Document, *, chunk_size: int) -> List[Document]:
    if document.metadata.get("selected_heading_level") != 3:
        return [document]

    return pack_document_on_heading_boundaries(
        document,
        4,
        chunk_size=chunk_size,
        preserve_parent_metadata=True,
    )


def split_document_preserving_code_blocks(document: Document) -> List[Document]:
    lines = document.page_content.splitlines()
    segments: List[Document] = []
    normal_buffer: List[str] = []
    code_buffer: List[str] = []
    in_code_block = False

    def flush_normal() -> None:
        nonlocal normal_buffer
        content = "\n".join(normal_buffer).strip()
        if content:
            segments.append(Document(page_content=content, metadata=dict(document.metadata)))
        normal_buffer = []

    def flush_code() -> None:
        nonlocal code_buffer
        content = "\n".join(code_buffer).strip()
        if content:
            if segments and is_heading_only_content(segments[-1].page_content):
                heading_segment = segments.pop()
                content = append_unit_text(heading_segment.page_content.strip(), content)
            metadata = dict(document.metadata)
            metadata["contains_code_block"] = True
            segments.append(Document(page_content=content, metadata=metadata))
        code_buffer = []

    for line in lines:
        if is_fenced_code_line(line):
            if in_code_block:
                code_buffer.append(line)
                flush_code()
                in_code_block = False
            else:
                flush_normal()
                in_code_block = True
                code_buffer.append(line)
            continue

        if in_code_block:
            code_buffer.append(line)
            continue

        normal_buffer.append(line)

    if in_code_block:
        flush_code()
    else:
        flush_normal()

    return segments


def merge_chunk_metadata(base_metadata: dict, extra_metadata: dict) -> dict:
    merged = dict(base_metadata)
    if extra_metadata.get("contains_code_block"):
        merged["contains_code_block"] = True
    base_section = (
        base_metadata.get("selected_heading_level"),
        base_metadata.get("parent_title"),
        base_metadata.get("section_title"),
    )
    extra_section = (
        extra_metadata.get("selected_heading_level"),
        extra_metadata.get("parent_title"),
        extra_metadata.get("section_title"),
    )
    if base_section != extra_section:
        merged["selected_heading_level"] = None
        merged.pop("parent_title", None)
        merged.pop("section_title", None)
    return merged


def should_split_before_unit(current_metadata: dict | None, next_metadata: dict) -> bool:
    if current_metadata is None:
        return False

    current_section = (
        current_metadata.get("selected_heading_level"),
        current_metadata.get("parent_title"),
        current_metadata.get("section_title"),
    )
    next_section = (
        next_metadata.get("selected_heading_level"),
        next_metadata.get("parent_title"),
        next_metadata.get("section_title"),
    )

    has_current_section = any(value is not None for value in current_section)
    has_next_section = any(value is not None for value in next_section)

    if has_current_section and has_next_section and current_section != next_section:
        return True
    return False


def pack_split_units(units: List[Document], *, chunk_size: int = CHUNK_SIZE) -> List[Document]:
    packed_chunks: List[Document] = []
    current_content = ""
    current_metadata: dict | None = None

    def flush_current() -> None:
        nonlocal current_content, current_metadata
        if current_content and current_metadata is not None:
            packed_chunks.append(Document(page_content=current_content.strip(), metadata=dict(current_metadata)))
        current_content = ""
        current_metadata = None

    for unit in units:
        unit_content = unit.page_content.strip()
        if not unit_content:
            continue

        if current_metadata is None:
            current_content = unit_content
            current_metadata = dict(unit.metadata)
            if unit.metadata.get("contains_code_block") and len(current_content) > chunk_size:
                flush_current()
            continue

        if should_split_before_unit(current_metadata, unit.metadata):
            flush_current()
            current_content = unit_content
            current_metadata = dict(unit.metadata)
            if unit.metadata.get("contains_code_block") and len(current_content) > chunk_size:
                flush_current()
            continue

        current_content = append_unit_text(current_content, unit_content)
        current_metadata = merge_chunk_metadata(current_metadata, unit.metadata)
        if len(current_content) > chunk_size:
            flush_current()

    flush_current()
    return packed_chunks


def split_document_recursively(
    document: Document,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", ".", " ", ""],
    )
    return splitter.split_documents([document])


def split_markdown_documents(
    documents: List[Document],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> List[Document]:
    del chunk_overlap

    def merge_sections_for_chunk(sections: List[Document]) -> Document:
        if len(sections) == 1:
            return sections[0]

        content = "\n\n".join(
            section.page_content.strip() for section in sections if section.page_content.strip()
        ).strip()
        metadata = dict(sections[0].metadata)
        section_identity = (
            metadata.get("selected_heading_level"),
            metadata.get("parent_title"),
            metadata.get("section_title"),
        )
        if any(
            (
                section.metadata.get("selected_heading_level"),
                section.metadata.get("parent_title"),
                section.metadata.get("section_title"),
            ) != section_identity
            for section in sections[1:]
        ):
            metadata["selected_heading_level"] = None
            metadata.pop("parent_title", None)
            metadata.pop("section_title", None)
        return Document(page_content=content, metadata=metadata)

    def pack_sections_by_chunk_size(sections: List[Document]) -> List[Document]:
        chunks: List[Document] = []
        pending_sections: List[Document] = []
        pending_length = 0

        def flush_pending() -> None:
            nonlocal pending_sections, pending_length
            if not pending_sections:
                return
            chunks.append(merge_sections_for_chunk(pending_sections))
            pending_sections = []
            pending_length = 0

        for section in sections:
            if not section.page_content.strip():
                continue
            should_downgrade = (
                len(section.page_content.strip()) > chunk_size
                and (section.metadata.get("selected_heading_level") or 0) < 4
            )
            if should_downgrade:
                selected_level = section.metadata.get("selected_heading_level")
                child_level = selected_level + 1 if selected_level is not None else None
            else:
                child_level = None

            if child_level is not None:
                grandchild_sections = split_document_by_heading_level(section, child_level)
                has_meaningful_grandchildren = any(
                    grandchild.metadata.get("selected_heading_level") == child_level
                    and grandchild.metadata.get("section_title") is not None
                    for grandchild in grandchild_sections
                )
                if has_meaningful_grandchildren:
                    flush_pending()
                    chunks.extend(split_by_heading_downgrade(section))
                    continue

            if pending_sections and len(section.page_content.strip()) > chunk_size:
                flush_pending()

            section_length = len(section.page_content.strip()) + (2 if pending_sections else 0)
            pending_sections.append(section)
            pending_length += section_length
            if pending_length > chunk_size:
                flush_pending()

        flush_pending()
        return chunks

    def split_by_heading_downgrade(document: Document) -> List[Document]:
        selected_level = document.metadata.get("selected_heading_level")
        if selected_level is None:
            if len(document.page_content.strip()) <= chunk_size:
                return [document]
            return split_document_recursively(
                document,
                chunk_size=chunk_size,
                chunk_overlap=0,
            )
        if len(document.page_content.strip()) <= chunk_size:
            return [document]
        if selected_level >= 4:
            return [document]

        child_level = selected_level + 1
        child_sections = split_document_by_heading_level(document, child_level)
        meaningful_sections = [
            section
            for section in child_sections
            if section.metadata.get("selected_heading_level") == child_level
            and section.metadata.get("section_title") is not None
        ]
        if len(meaningful_sections) <= 1:
            return [document]

        return pack_sections_by_chunk_size(meaningful_sections)

    chunks: List[Document] = []
    for document in documents:
        top_sections = split_document_by_heading_structure(document)
        split_sections: List[Document] = []
        for section in top_sections:
            split_sections.extend(split_by_heading_downgrade(section))
        chunks.extend(pack_sections_by_chunk_size(split_sections))

    for idx, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = idx
    return chunks


def split_documents(documents: List[Document]) -> List[Document]:
    chunks = split_markdown_documents(
        documents,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    for idx, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = idx
    return chunks
