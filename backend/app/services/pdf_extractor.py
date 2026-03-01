"""
PageTutor AI — PDF Page Extractor + Page Index
===============================================
Extracts text page-by-page using pdfplumber.
Stores the index in SQLite (page_indices table) — NO vector DB needed.

For long corpus/long context:
- Each page is processed independently (avoids context limits)
- Page index stores per-page text + summary in SQLite
- Downstream LLM tasks use the page index instead of raw PDF
"""

import logging
import os
import sqlite3
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  Raw text extraction using pdfplumber
# ─────────────────────────────────────────────────────────────

def extract_pages(pdf_path: str) -> list:
    """
    Extract text from every page of a PDF.

    Returns: list of (page_num:int, text:str) sorted by page_num.
    Page numbers are 1-indexed.
    """
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                try:
                    text = page.extract_text() or ""
                    text = text.strip()
                    if text:
                        pages.append((i, text))
                except Exception as e:
                    logger.warning(f"Page {i} extraction error: {e}")
        logger.info(f"Extracted {len(pages)} text pages from {os.path.basename(pdf_path)}")
        return pages
    except ImportError:
        logger.error("pdfplumber not installed — run: pip install pdfplumber")
        return []
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return []


def count_tokens_approx(text: str) -> int:
    """Approximate token count (1 token ≈ 4 chars)."""
    return max(1, len(text) // 4)


# ─────────────────────────────────────────────────────────────
#  Page Index — SQLite (no vector DB)
# ─────────────────────────────────────────────────────────────

def _get_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def build_page_index(
    document_id: str,
    pdf_path: str,
    db_path: str,
    page_summaries: Optional[list] = None,
) -> list:
    """
    Store per-page text + optional LLM summary in the page_indices table.

    Args:
        document_id: UUID of the document
        pdf_path:    Path to the PDF file on disk
        db_path:     Path to the SQLite DB
        page_summaries: Optional list of (page_num, summary_text)

    Returns: list of (page_num, text) tuples
    """
    pages = extract_pages(pdf_path)
    if not pages:
        return []

    summary_map = {}
    if page_summaries:
        for pnum, psum in page_summaries:
            summary_map[pnum] = psum

    conn = _get_db(db_path)
    try:
        # Remove stale entries (re-indexing the same document)
        conn.execute(
            "DELETE FROM page_indices WHERE document_id = ?", (document_id,)
        )
        conn.commit()

        rows = []
        for page_num, text in pages:
            row_id = str(uuid.uuid4())
            token_count = count_tokens_approx(text)
            summary = summary_map.get(page_num, "")
            rows.append((row_id, document_id, page_num, text[:5000], summary, token_count, 0.0, 0, 1))

        conn.executemany(
            """INSERT INTO page_indices
               (id, document_id, page_number, topic, summary, token_count, importance_score, chunk_index, chunk_total)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        logger.info(f"Page index built: {len(rows)} pages for doc {document_id[:8]}")
        return pages
    finally:
        conn.close()


def get_page_texts_from_index(document_id: str, db_path: str) -> list:
    """
    Load (page_num, text) from the page index (SQLite).
    Falls back to empty list if nothing indexed yet.
    """
    conn = _get_db(db_path)
    try:
        cur = conn.execute(
            "SELECT page_number, topic FROM page_indices WHERE document_id = ? ORDER BY page_number",
            (document_id,),
        )
        rows = cur.fetchall()
        return [(r[0], r[1] or "") for r in rows if r[1]]
    except Exception as e:
        logger.error(f"get_page_texts_from_index error: {e}")
        return []
    finally:
        conn.close()


def get_page_count(document_id: str, db_path: str) -> int:
    """Return number of indexed pages for a document."""
    conn = _get_db(db_path)
    try:
        cur = conn.execute(
            "SELECT COUNT(*) FROM page_indices WHERE document_id = ?", (document_id,)
        )
        return cur.fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()


def find_pdf_path(document_id: str, db_path: str, upload_dir: str) -> Optional[str]:
    """
    Look up the stored s3_key from the documents table and construct
    the local file path. Returns None if not found.
    """
    conn = _get_db(db_path)
    try:
        cur = conn.execute(
            "SELECT s3_key FROM documents WHERE id = ?", (document_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        s3_key = row[0]
        # Local path pattern: uploads/pdfs/<s3_key>
        path = os.path.join(upload_dir, s3_key) if not os.path.isabs(s3_key) else s3_key
        if os.path.exists(path):
            return path
        # Try relative to backend root
        for base in (upload_dir, "uploads/pdfs", "uploads"):
            candidate = os.path.join(base, os.path.basename(s3_key))
            if os.path.exists(candidate):
                return candidate
        logger.warning(f"PDF not found on disk: {s3_key}")
        return None
    finally:
        conn.close()
