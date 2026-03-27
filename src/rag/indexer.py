"""
RAG Indexer — 약관·기준 문서를 청크로 분할하고 벡터스토어에 적재.

책임:
  1. 소스 문서 탐색  : POLICY_DOCS_PATH + docs/insurance_standards/ 의 .md/.txt 파일
  2. 청크 분할       : 고정 크기(RAG_CHUNK_SIZE) + 오버랩(RAG_CHUNK_OVERLAP)
                       → Markdown 섹션(##) 경계 우선, 그 외 문자 수 기준 분할
  3. 메타데이터 추출 : source(파일명), doc_type, section(섹션 제목), chunk_index
  4. 벡터스토어 적재 : VectorStoreManager.add_documents() 호출

공개 API:
  build_index(force=False)  — 전체 문서 인덱싱 (force=True 시 기존 인덱스 재구성)
  index_file(path)          — 단일 파일 인덱싱
  DocumentChunk             — 청크 결과 dataclass

사용 방법:
  from src.rag.indexer import build_index
  stats = build_index()           # 최초 1회 실행 (이미 있으면 스킵)
  stats = build_index(force=True) # 재인덱싱

CLI:
  python -m src.rag.indexer          # 기본 실행 (이미 인덱싱됐으면 스킵)
  python -m src.rag.indexer --force  # 강제 재인덱싱
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config.settings import (
    POLICY_DOCS_PATH,
    PROJECT_ROOT,
    RAG_CHUNK_OVERLAP,
    RAG_CHUNK_SIZE,
)
from src.rag.vectorstore import VectorStoreManager

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 인덱싱 대상 소스 경로 목록
# ══════════════════════════════════════════════════════════════════

# 약관 원본 (data/policies/)
_POLICY_DOCS_DIR = POLICY_DOCS_PATH

# 보험 기준 문서 (docs/insurance_standards/)
_STANDARDS_DIR = PROJECT_ROOT / "docs" / "insurance_standards"

# 룰 정의서 (docs/03_룰정의서.md)
_RULE_BOOK_PATH = PROJECT_ROOT / "docs" / "03_룰정의서.md"

# 지원 확장자
_SUPPORTED_EXTS = {".md", ".txt"}


# ══════════════════════════════════════════════════════════════════
# 결과 타입
# ══════════════════════════════════════════════════════════════════

@dataclass
class DocumentChunk:
    """단일 청크 — 텍스트 + 메타데이터 + ID."""
    id: str                       # "{file_stem}-{chunk_index:04d}"
    text: str
    metadata: dict = field(default_factory=dict)
    # metadata 표준 키:
    #   source      : str  파일명 (예: "standard_policy.md")
    #   source_path : str  절대 경로
    #   doc_type    : str  "policy" | "standard" | "rulebook"
    #   section     : str  소속 Markdown 섹션 제목 (없으면 "")
    #   chunk_index : int  파일 내 청크 순서 (0-based)
    #   char_count  : int  청크 문자 수


@dataclass
class IndexStats:
    """build_index() 실행 결과 요약."""
    total_files: int = 0
    total_chunks: int = 0
    skipped_files: int = 0       # 이미 인덱싱된 파일 (force=False 시)
    failed_files: list[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
# 청크 분할 로직
# ══════════════════════════════════════════════════════════════════

def _split_by_markdown_sections(text: str) -> list[tuple[str, str]]:
    """
    Markdown 헤딩(## / ###) 기준으로 섹션 분리.
    반환: list of (section_title, section_body)
    헤딩이 없으면 [('' , 전체 텍스트)] 반환.
    """
    pattern = re.compile(r'^(#{1,3})\s+(.+)$', re.MULTILINE)
    matches = list(pattern.finditer(text))

    if not matches:
        return [("", text)]

    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        title = m.group(2).strip()
        start = m.end()
        end   = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body  = text[start:end].strip()
        if body:
            sections.append((title, body))

    # 첫 헤딩 이전 내용이 있으면 프리앰블로 추가
    if matches[0].start() > 0:
        preamble = text[:matches[0].start()].strip()
        if preamble:
            sections.insert(0, ("", preamble))

    return sections


def _chunk_text(
    text: str,
    chunk_size: int = RAG_CHUNK_SIZE,
    overlap: int = RAG_CHUNK_OVERLAP,
) -> list[str]:
    """
    고정 크기 + 오버랩 방식으로 텍스트를 청크 목록으로 분할.
    문장 경계('. ' / '.\n' / '\n\n')를 가능한 한 존중한다.
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
            break

        # 자연 경계 탐색: 뒤에서부터 '\n\n', '\n', '. ' 순서로
        cut = end
        for boundary in ("\n\n", "\n", ". ", " "):
            pos = text.rfind(boundary, start, end)
            if pos > start:
                cut = pos + len(boundary)
                break

        chunk = text[start:cut].strip()
        if chunk:
            chunks.append(chunk)

        start = cut - overlap if cut - overlap > start else cut

    return chunks


def split_document(
    text: str,
    file_stem: str,
    doc_type: str,
    chunk_size: int = RAG_CHUNK_SIZE,
    overlap: int = RAG_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """
    문서 전체를 섹션 분리 → 청크 분할 → DocumentChunk 목록 반환.

    Args:
        text:       문서 원문
        file_stem:  파일명 (확장자 제외, ID 접두사 및 메타데이터용)
        doc_type:   "policy" | "standard" | "rulebook"
        chunk_size: 청크 최대 문자 수
        overlap:    인접 청크 오버랩 문자 수
    """
    sections = _split_by_markdown_sections(text)
    chunks: list[DocumentChunk] = []
    chunk_index = 0

    for section_title, section_body in sections:
        sub_chunks = _chunk_text(section_body, chunk_size, overlap)
        for sub in sub_chunks:
            # 고유 ID: 파일 stem + 전체 청크 순서
            chunk_id = f"{file_stem}-{chunk_index:04d}"
            chunks.append(DocumentChunk(
                id=chunk_id,
                text=sub,
                metadata={
                    "source": f"{file_stem}",
                    "doc_type": doc_type,
                    "section": section_title,
                    "chunk_index": chunk_index,
                    "char_count": len(sub),
                },
            ))
            chunk_index += 1

    return chunks


# ══════════════════════════════════════════════════════════════════
# 파일 해시 — 변경 감지용
# ══════════════════════════════════════════════════════════════════

def _file_hash(path: Path) -> str:
    """파일 내용의 MD5 해시 (변경 감지에 사용)."""
    return hashlib.md5(path.read_bytes()).hexdigest()


def _doc_type_from_path(path: Path) -> str:
    """파일 경로 기반으로 doc_type 문자열 결정."""
    parts = {p.name for p in path.parents}
    if "policies" in parts:
        return "policy"
    if "insurance_standards" in parts:
        return "standard"
    return "rulebook"


# ══════════════════════════════════════════════════════════════════
# 파일 인덱싱
# ══════════════════════════════════════════════════════════════════

def index_file(
    path: Path,
    vsm: VectorStoreManager,
    chunk_size: int = RAG_CHUNK_SIZE,
    overlap: int = RAG_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """
    단일 파일을 읽어 청크로 분할하고 벡터스토어에 upsert 한다.

    Args:
        path:       인덱싱할 파일 경로
        vsm:        VectorStoreManager 인스턴스
        chunk_size: 청크 크기
        overlap:    오버랩

    Returns:
        추가된 DocumentChunk 목록 (길이 = 추가 청크 수)
    """
    if path.suffix.lower() not in _SUPPORTED_EXTS:
        logger.debug("지원하지 않는 확장자 스킵: %s", path)
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="cp949")
        except Exception as e:
            logger.warning("파일 읽기 실패 (%s): %s", path, e)
            return []
    except Exception as e:
        logger.warning("파일 읽기 실패 (%s): %s", path, e)
        return []

    doc_type = _doc_type_from_path(path)
    chunks   = split_document(
        text, path.stem, doc_type, chunk_size, overlap
    )

    if not chunks:
        logger.debug("청크 없음 (빈 파일?): %s", path)
        return []

    # 메타데이터에 source_path, file_hash 추가
    file_hash = _file_hash(path)
    for ch in chunks:
        ch.metadata["source_path"] = str(path)
        ch.metadata["file_hash"]   = file_hash

    vsm.add_documents(
        texts=[ch.text for ch in chunks],
        metadatas=[ch.metadata for ch in chunks],
        ids=[ch.id for ch in chunks],
    )
    logger.info("인덱싱 완료: %s → %d청크", path.name, len(chunks))
    return chunks


# ══════════════════════════════════════════════════════════════════
# 전체 인덱싱
# ══════════════════════════════════════════════════════════════════

def _collect_source_files() -> list[Path]:
    """인덱싱 대상 파일 목록 수집 (중복 없이, 존재하는 경로만)."""
    sources: list[Path] = []

    for directory in [_POLICY_DOCS_DIR, _STANDARDS_DIR]:
        if directory.exists():
            for ext in _SUPPORTED_EXTS:
                sources.extend(sorted(directory.glob(f"*{ext}")))

    if _RULE_BOOK_PATH.exists():
        sources.append(_RULE_BOOK_PATH)

    # 중복 제거 (절대경로 기준)
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in sources:
        ap = p.resolve()
        if ap not in seen:
            seen.add(ap)
            unique.append(p)

    return unique


def build_index(
    vsm: Optional[VectorStoreManager] = None,
    force: bool = False,
    chunk_size: int = RAG_CHUNK_SIZE,
    overlap: int = RAG_CHUNK_OVERLAP,
) -> IndexStats:
    """
    모든 소스 문서를 청크로 분할해 벡터스토어에 적재한다.

    Args:
        vsm:        VectorStoreManager 인스턴스. None 이면 settings 기반 생성.
        force:      True 이면 기존 인덱스를 삭제하고 재구성.
                    False 이면 이미 인덱싱된 파일(file_hash 일치)은 스킵.
        chunk_size: 청크 크기 (기본: settings.RAG_CHUNK_SIZE)
        overlap:    오버랩 (기본: settings.RAG_CHUNK_OVERLAP)

    Returns:
        IndexStats — 처리 결과 요약
    """
    if vsm is None:
        vsm = VectorStoreManager()

    if force:
        logger.info("force=True: 기존 인덱스 삭제 후 재구성")
        vsm.clear()

    source_files = _collect_source_files()
    if not source_files:
        logger.warning(
            "인덱싱 대상 파일이 없습니다. "
            "data/policies/ 또는 docs/insurance_standards/ 에 .md/.txt 파일을 추가하세요."
        )
        return IndexStats()

    # 이미 인덱싱된 file_hash 집합 조회 (force=False 시 스킵 판단용)
    existing_hashes: set[str] = set()
    if not force and vsm.count() > 0:
        try:
            # 전체 메타데이터에서 file_hash 수집
            col = vsm._get_collection(vsm._default_collection_name)
            all_meta = col.get(include=["metadatas"])["metadatas"] or []
            existing_hashes = {m.get("file_hash", "") for m in all_meta if m}
        except Exception as e:
            logger.debug("기존 hash 조회 실패 (무시): %s", e)

    stats = IndexStats(total_files=len(source_files))

    for path in source_files:
        try:
            if not force and _file_hash(path) in existing_hashes:
                logger.debug("스킵 (변경 없음): %s", path.name)
                stats.skipped_files += 1
                continue

            added = index_file(path, vsm, chunk_size, overlap)
            stats.total_chunks += len(added)

        except Exception as e:
            logger.error("인덱싱 실패 (%s): %s", path.name, e)
            stats.failed_files.append(str(path))

    logger.info(
        "build_index 완료 — 파일 %d개 (스킵 %d개, 실패 %d개), 총 청크 %d개",
        stats.total_files,
        stats.skipped_files,
        len(stats.failed_files),
        stats.total_chunks,
    )
    return stats


# ══════════════════════════════════════════════════════════════════
# 인덱스 존재 확인 + 자동 빌드
# ══════════════════════════════════════════════════════════════════

def ensure_index() -> bool:
    """
    벡터스토어 인덱스가 존재하는지 확인하고, 없으면 자동 빌드.

    임베딩 모델이 로컬에 캐시되어 있지 않으면 자동 빌드를 건너뛴다
    (470MB+ 다운로드로 앱 기동이 블로킹되는 것을 방지).

    Returns:
        True if index exists (or was just built), False if no source docs.
    """
    try:
        vsm = VectorStoreManager()
        if vsm.count() > 0:
            logger.debug("RAG 인덱스 존재 (%d 청크)", vsm.count())
            return True

        # 임베딩 모델 캐시 여부 확인 — 미캐시 시 빌드 건너뛰기
        if not vsm._embedder.is_model_available():
            logger.warning(
                "RAG 인덱스 미생성이나 임베딩 모델이 로컬 캐시에 없어 "
                "자동 빌드를 건너뜁니다. 'run.sh index' 로 수동 빌드하세요."
            )
            return False

        logger.info("RAG 인덱스 미생성 — 자동 빌드 시작")
        stats = build_index(vsm=vsm)
        if stats.total_chunks > 0:
            logger.info("RAG 인덱스 자동 빌드 완료 (%d 청크)", stats.total_chunks)
            return True
        else:
            logger.warning("RAG 인덱스 빌드 실패: 소스 문서 없음")
            return False
    except Exception as exc:
        logger.warning("RAG 인덱스 확인 실패 (무시): %s", exc)
        return False


# ══════════════════════════════════════════════════════════════════
# CLI 진입점
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = argparse.ArgumentParser(description="RAG 인덱서 — 보험 문서 벡터스토어 적재")
    parser.add_argument(
        "--force", action="store_true",
        help="기존 인덱스 삭제 후 전체 재인덱싱"
    )
    parser.add_argument(
        "--chunk-size", type=int, default=RAG_CHUNK_SIZE,
        help=f"청크 크기 (기본: {RAG_CHUNK_SIZE})"
    )
    parser.add_argument(
        "--overlap", type=int, default=RAG_CHUNK_OVERLAP,
        help=f"청크 오버랩 (기본: {RAG_CHUNK_OVERLAP})"
    )
    args = parser.parse_args()

    stats = build_index(force=args.force, chunk_size=args.chunk_size, overlap=args.overlap)
    print(f"\n인덱싱 결과:")
    print(f"  대상 파일 : {stats.total_files}개")
    print(f"  스킵      : {stats.skipped_files}개 (변경 없음)")
    print(f"  실패      : {len(stats.failed_files)}개")
    print(f"  총 청크   : {stats.total_chunks}개")
    if stats.failed_files:
        print(f"  실패 목록 : {stats.failed_files}")
