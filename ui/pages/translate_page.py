import io
from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd
import streamlit as st

TARGET_SHEET = "Tabelle1"

ALLOWED_COLUMNS = [
    "articleNumber",
    "name",
    "colorDetail",
    "deliveryScope",
    "otherMeasurements",
    "qualityDetail",
    "textileCompositionCover1",
    "variantName",
]
TRANSLATE_COLUMNS = [c for c in ALLOWED_COLUMNS if c != "articleNumber"]

_STATE_KEYS = [
    "t_step", "t_filename", "t_file_bytes", "t_preview_rows",
    "t_original_preview", "t_xl_bytes", "t_csv_bytes", "t_stats",
    "t_headers", "t_data_rows", "t_version",
]


def _init_state():
    for key in _STATE_KEYS:
        if key not in st.session_state:
            st.session_state[key] = None
    if st.session_state["t_step"] is None:
        st.session_state["t_step"] = "upload"
    if st.session_state["t_version"] is None:
        st.session_state["t_version"] = 0


def render():
    from auth.session import require_permission
    require_permission("translate")

    st.markdown('<div class="section-header">Translate Workbook</div>', unsafe_allow_html=True)
    _init_state()

    if st.session_state["t_step"] == "upload":
        _render_upload()
    else:
        _render_preview()


# ── Upload ─────────────────────────────────────────────────────────────


def _render_upload():
    from auth.credentials import get_openai_key

    if not get_openai_key():
        st.markdown(
            '<div class="alert-warning">OpenAI API key not configured. TM-only mode active.</div>',
            unsafe_allow_html=True,
        )

    uploaded = st.file_uploader(
        "Upload German Excel file",
        type=["xlsx", "xls"],
        help="Must contain a sheet named 'Tabelle1'.",
    )

    if not uploaded:
        st.markdown(
            '<div class="alert-info">Upload a German Excel file to begin. '
            "The app processes sheet <strong>Tabelle1</strong> automatically "
            "and translates the expected Home24 columns.</div>",
            unsafe_allow_html=True,
        )
        return

    st.success(f"File ready: **{uploaded.name}**")

    if st.button("Translate", type="primary", use_container_width=True):
        _run_translation(uploaded.getvalue(), uploaded.name)


# ── Translation ────────────────────────────────────────────────────────


def _run_translation(file_bytes: bytes, filename: str):
    try:
        wb_check = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as e:
        st.error(f"Cannot open file: {e}")
        return

    if TARGET_SHEET not in wb_check.sheetnames:
        st.error(
            f"Sheet '{TARGET_SHEET}' not found in this file.\n"
            f"Available sheets: {', '.join(wb_check.sheetnames)}"
        )
        wb_check.close()
        return

    ws = wb_check[TARGET_SHEET]
    all_rows = list(ws.iter_rows(values_only=True))
    wb_check.close()

    if len(all_rows) < 2:
        st.error(f"Sheet '{TARGET_SHEET}' has no data rows.")
        return

    headers = [str(c) if c is not None else "" for c in all_rows[0]]
    cols_to_translate = [c for c in TRANSLATE_COLUMNS if c in headers]

    if not cols_to_translate:
        st.error(
            f"No translatable columns found in '{TARGET_SHEET}'.\n"
            f"Expected: {', '.join(TRANSLATE_COLUMNS)}\n"
            f"Found: {', '.join(h for h in headers if h)}"
        )
        return

    data_rows = [
        {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
        for row in all_rows[1:]
    ]

    from engines.translation_engine import get_engine
    from engines.consistency_engine import get_consistency_engine

    engine = get_engine()
    consistency = get_consistency_engine()
    consistency.reset()
    consistency.lock_batch_from_glossary()

    preview_rows = []
    stats = {
        "tm_hits": 0, "fuzzy_hits": 0, "glossary_hits": 0,
        "phrase_hits": 0, "corpus_hits": 0, "ai_hits": 0,
        "qa_corrections": 0, "total_cells": 0,
    }

    overall_progress = st.progress(0.0)
    status_text = st.empty()
    total_cols = len(cols_to_translate)

    for col_idx, col_name in enumerate(cols_to_translate):
        status_text.text(f"Translating '{col_name}' ({col_idx + 1}/{total_cols})…")

        items = [
            (row_idx, str(row.get(col_name, "")).strip())
            for row_idx, row in enumerate(data_rows)
            if row.get(col_name) and str(row.get(col_name, "")).strip()
        ]

        if not items:
            overall_progress.progress((col_idx + 1) / total_cols)
            continue

        def _cb(p, ci=col_idx, tot=total_cols):
            overall_progress.progress((ci + p) / tot)

        batch = engine.translate_batch(
            items,
            context_rows=data_rows,
            filename=filename,
            progress_callback=_cb,
        )

        for i, (row_idx, source) in enumerate(items):
            res = batch.results[i]
            preview_rows.append({
                "Row": row_idx + 1,
                "Column": col_name,
                "German source": source,
                "Dutch translation": res.target,
                "Confidence": res.confidence_label,
                "Origin": res.source_type.value,
            })

        stats["tm_hits"] += batch.tm_hits
        stats["fuzzy_hits"] += batch.fuzzy_hits
        stats["glossary_hits"] += batch.glossary_hits
        stats["phrase_hits"] += batch.phrase_hits
        stats["corpus_hits"] += batch.corpus_hits
        stats["ai_hits"] += batch.ai_hits
        stats["qa_corrections"] += batch.qa_corrections
        stats["total_cells"] += len(items)

        overall_progress.progress((col_idx + 1) / total_cols)

    overall_progress.progress(1.0)
    status_text.text("Translation complete.")

    # Store state
    st.session_state["t_file_bytes"] = file_bytes
    st.session_state["t_filename"] = filename
    st.session_state["t_headers"] = headers
    st.session_state["t_data_rows"] = data_rows
    st.session_state["t_preview_rows"] = preview_rows
    st.session_state["t_original_preview"] = [dict(r) for r in preview_rows]
    st.session_state["t_stats"] = stats
    st.session_state["t_xl_bytes"] = None
    st.session_state["t_csv_bytes"] = None
    st.session_state["t_version"] = 0
    st.session_state["t_step"] = "preview"

    # Clear any leftover data_editor widget state
    for k in [k for k in st.session_state if k.startswith("preview_editor_")]:
        del st.session_state[k]

    st.rerun()


# ── Preview + export ───────────────────────────────────────────────────


def _render_preview():
    filename = st.session_state.get("t_filename") or "file.xlsx"
    stats = st.session_state.get("t_stats") or {}
    preview_rows = st.session_state.get("t_preview_rows") or []
    version = st.session_state.get("t_version") or 0

    st.markdown(f"**File:** {filename}")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("TM Exact", stats.get("tm_hits", 0))
    c2.metric("Fuzzy + Glossary", stats.get("fuzzy_hits", 0) + stats.get("glossary_hits", 0))
    c3.metric("Phrase / Corpus", stats.get("phrase_hits", 0) + stats.get("corpus_hits", 0))
    c4.metric("AI (GPT)", stats.get("ai_hits", 0))
    c5.metric("Total cells", stats.get("total_cells", 0))

    st.markdown("---")
    st.markdown("### Translation preview")
    st.caption("Edit the **Dutch translation** column directly. Click **Validate** to apply edits and generate files.")

    editor_key = f"preview_editor_{version}"
    preview_df = pd.DataFrame(preview_rows) if preview_rows else pd.DataFrame(
        columns=["Row", "Column", "German source", "Dutch translation", "Confidence", "Origin"]
    )

    edited_df = st.data_editor(
        preview_df,
        column_config={
            "Row": st.column_config.NumberColumn("Row", disabled=True, width="small"),
            "Column": st.column_config.TextColumn("Column", disabled=True, width="medium"),
            "German source": st.column_config.TextColumn("German source", disabled=True, width="large"),
            "Dutch translation": st.column_config.TextColumn("Dutch translation", disabled=False, width="large"),
            "Confidence": st.column_config.TextColumn("Confidence", disabled=True, width="small"),
            "Origin": st.column_config.TextColumn("Origin", disabled=True, width="small"),
        },
        hide_index=True,
        use_container_width=True,
        height=560,
        key=editor_key,
    )

    st.markdown("---")
    col_btn, col_reset = st.columns([3, 1])

    with col_btn:
        validate_clicked = st.button(
            "Validate modifications and generate new files",
            type="primary",
            use_container_width=True,
        )

    with col_reset:
        if st.button("Start over", use_container_width=True):
            _reset_state()
            st.rerun()

    if validate_clicked:
        current_rows = edited_df.to_dict("records")
        # Normalise Row to int (data_editor may return float)
        for r in current_rows:
            r["Row"] = int(r["Row"])
        _validate_and_generate(current_rows)
        return

    # Download section — always visible once files exist
    xl_bytes = st.session_state.get("t_xl_bytes")
    csv_bytes = st.session_state.get("t_csv_bytes")

    if xl_bytes or csv_bytes:
        st.markdown("---")
        st.markdown("### Download translated files")
        stem = Path(filename).stem
        dc1, dc2 = st.columns(2)
        with dc1:
            if xl_bytes:
                st.download_button(
                    "Download NL Excel (.xlsx)",
                    data=xl_bytes,
                    file_name=f"NL-{stem}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary",
                )
        with dc2:
            if csv_bytes:
                st.download_button(
                    "Download NL CSV (.csv)",
                    data=csv_bytes,
                    file_name=f"NL-{stem}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )


# ── Validate & generate ────────────────────────────────────────────────


def _validate_and_generate(current_rows: list):
    filename = st.session_state.get("t_filename") or "file.xlsx"
    file_bytes = st.session_state.get("t_file_bytes")
    original_preview = st.session_state.get("t_original_preview") or []
    headers = st.session_state.get("t_headers") or []
    data_rows = st.session_state.get("t_data_rows") or []

    # Detect human corrections
    original_map = {(r["Row"], r["Column"]): r["Dutch translation"] for r in original_preview}
    corrections = []
    correction_lookup = {}  # source_text → new_dutch

    for row in current_rows:
        key = (row["Row"], row["Column"])
        old_val = original_map.get(key, "")
        new_val = (row.get("Dutch translation") or "").strip()
        if new_val and new_val != old_val:
            corrections.append({
                "source": row["German source"],
                "old_target": old_val,
                "new_target": new_val,
                "column": row["Column"],
            })
            correction_lookup[row["German source"]] = new_val

    # Propagate corrections to all identical source segments in current file
    if correction_lookup:
        for row in current_rows:
            src = row.get("German source", "")
            if src in correction_lookup:
                row["Dutch translation"] = correction_lookup[src]

    # Save human corrections to glossary + TM
    if corrections:
        _save_corrections(corrections, correction_lookup)

    # Build translation_map {row_idx 0-based: {col: dutch}}
    translation_map: dict[int, dict[str, str]] = {}
    for row in current_rows:
        row_idx = row["Row"] - 1
        col = row["Column"]
        translation_map.setdefault(row_idx, {})[col] = row["Dutch translation"]

    # Generate Excel bytes
    try:
        from exporters.xlsx_export import export_workbook_translated_bytes
        xl_bytes = export_workbook_translated_bytes(file_bytes, translation_map, headers)
    except Exception as e:
        st.error(f"Excel export failed: {e}")
        return

    # Generate CSV bytes
    try:
        from exporters.csv_export import generate_csv_bytes
        csv_bytes = generate_csv_bytes(headers, data_rows, translation_map)
    except Exception as e:
        st.error(f"CSV export failed: {e}")
        return

    # Persist updated state
    st.session_state["t_preview_rows"] = current_rows
    st.session_state["t_original_preview"] = [dict(r) for r in current_rows]
    st.session_state["t_xl_bytes"] = xl_bytes
    st.session_state["t_csv_bytes"] = csv_bytes
    st.session_state["t_version"] = (st.session_state.get("t_version") or 0) + 1

    if corrections:
        st.success(f"Files generated. {len(corrections)} human correction(s) saved to glossary and TM.")
    else:
        st.success("Files generated successfully.")

    st.rerun()


# ── Human correction persistence ──────────────────────────────────────


def _save_corrections(corrections: list, correction_lookup: dict):
    from database.database import get_connection

    now = datetime.now().isoformat()

    for c in corrections:
        src_lower = c["source"].lower().strip()
        tgt = c["new_target"]

        # Glossary: INSERT OR REPLACE with HUMAN_REVIEW, confidence=1.0
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO glossary "
                    "(source_term, target_term, category, confidence, source_type, active) "
                    "VALUES (?,?,?,1.0,'HUMAN_REVIEW',1)",
                    (src_lower, tgt, c["column"]),
                )
        except Exception:
            pass

        # TM: update existing or insert new
        try:
            normalized_src = src_lower
            normalized_tgt = tgt.lower().strip()
            with get_connection() as conn:
                existing = conn.execute(
                    "SELECT id FROM translation_memory WHERE normalized_source=? LIMIT 1",
                    (normalized_src,),
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE translation_memory SET target_segment=?, normalized_target=?, "
                        "confidence=1.0, modified_at=?, created_by='HUMAN_REVIEW' WHERE id=?",
                        (tgt, normalized_tgt, now, existing["id"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO translation_memory "
                        "(source_segment, target_segment, normalized_source, normalized_target, "
                        "confidence, created_at, modified_at, created_by) "
                        "VALUES (?,?,?,?,1.0,?,?,'HUMAN_REVIEW')",
                        (c["source"], tgt, normalized_src, normalized_tgt, now, now),
                    )
        except Exception:
            pass

    # Update in-memory dedup cache so the same session benefits immediately
    try:
        from engines.translation_engine import get_engine
        eng = get_engine()
        for src, tgt in correction_lookup.items():
            eng._dedup_cache[src] = tgt
    except Exception:
        pass


# ── Reset ──────────────────────────────────────────────────────────────


def _reset_state():
    for key in _STATE_KEYS:
        st.session_state[key] = None
    st.session_state["t_step"] = "upload"
    st.session_state["t_version"] = 0
    for k in [k for k in st.session_state if k.startswith("preview_editor_")]:
        del st.session_state[k]
