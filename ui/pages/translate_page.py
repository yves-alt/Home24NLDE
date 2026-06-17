"""Translate workbook page — driven by the DutchLocalizationEngine.

Upload → detect sheet/columns → build a TranslationPlan → translate every
non-empty cell through the deterministic-first pipeline → multi-pass
self-correction → editable preview with warnings → quality gate → export
(Excel always keeps `name`; CSV can drop it). Human edits are saved as
HUMAN_REVIEW and propagated to identical source segments.
"""

import io
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd
import streamlit as st


# ── Single source of truth for columns ────────────────────────────────

TRANSLATABLE_COLUMNS_NL = frozenset({
    "name", "colorDetail", "deliveryScope", "otherMeasurements", "qualityDetail",
    "textileCompositionCover1", "variantName", "materialDetail", "textileComposition",
    "warningsAndSafetyInformation",
})

PROTECTED_COLUMNS = frozenset({"articleNumber", "sku", "id", "ean", "gtin"})

HOME24_DETECTION_COLUMNS = TRANSLATABLE_COLUMNS_NL | PROTECTED_COLUMNS | frozenset({
    "internalDimensionDrawer", "externalDimension", "weightNetto", "weightBrutto",
    "colorName", "descriptionBullet1", "descriptionBullet2",
})


def _norm(h: str) -> str:
    return h.strip().replace("​", "").replace("\xa0", " ").lower()


def _resolve_columns(raw_headers: list[str]) -> tuple[list[str], list[str]]:
    trans_norm = {_norm(c): c for c in TRANSLATABLE_COLUMNS_NL}
    prot_norm = {_norm(c): c for c in PROTECTED_COLUMNS}
    translatable, protected = [], []
    for h in raw_headers:
        n = _norm(h)
        if n in trans_norm:
            translatable.append(h)
        elif n in prot_norm:
            protected.append(h)
    return translatable, protected


@dataclass
class TranslationPlan:
    sheet_name: str
    translatable_cols: list = field(default_factory=list)
    protected_cols: list = field(default_factory=list)
    cell_counts: dict = field(default_factory=dict)

    @property
    def total_expected(self) -> int:
        return sum(self.cell_counts.values())


def _detect_best_sheet(file_bytes: bytes) -> tuple[str | None, list[tuple[str, int, list[str]]]]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    scored: list[tuple[str, int, list[str]]] = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not first_row:
            scored.append((sheet_name, 0, []))
            continue
        raw = [str(c).strip() for c in first_row if c is not None and str(c).strip()]
        det_norm = {_norm(c): c for c in HOME24_DETECTION_COLUMNS}
        matched = sorted({det_norm[_norm(h)] for h in raw if _norm(h) in det_norm})
        scored.append((sheet_name, len(matched), matched))
    wb.close()
    scored.sort(key=lambda x: x[1], reverse=True)

    if len(scored) == 1:
        return scored[0][0], scored
    best_score = scored[0][1]
    if best_score == 0:
        return None, scored
    top = [s for s in scored if s[1] == best_score]
    return (top[0][0], scored) if len(top) == 1 else (None, scored)


# ── Session state ──────────────────────────────────────────────────────

_STATE_KEYS = [
    "t_step", "t_filename", "t_file_bytes", "t_cells", "t_original_targets",
    "t_xl_bytes", "t_csv_bytes", "t_stats", "t_headers", "t_data_rows",
    "t_version", "t_detected_sheet", "t_detection_scored", "t_plan",
    "t_coverage", "t_gate",
]


def _init_state():
    for key in _STATE_KEYS:
        st.session_state.setdefault(key, None)
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
    from database.database import get_connection

    if not get_openai_key():
        st.markdown(
            '<div class="alert-warning">OpenAI API key not configured. The engine '
            "runs in deterministic mode (TM + terminology); cells that need GPT will "
            "be flagged and block export until resolved.</div>",
            unsafe_allow_html=True,
        )

    try:
        with get_connection() as conn:
            tm_count = conn.execute("SELECT COUNT(*) FROM translation_memory").fetchone()[0]
        if tm_count == 0:
            st.warning("No Translation Memory imported yet. Import a TM file to improve quality.")
        else:
            st.info(f"Translation Memory active: **{tm_count:,} entries**")
    except Exception:
        pass

    uploaded = st.file_uploader("Upload German Excel file", type=["xlsx", "xls"])
    if not uploaded:
        st.markdown(
            '<div class="alert-info">Upload a German Excel file to begin. '
            "The sheet is detected automatically from the Home24 column structure.</div>",
            unsafe_allow_html=True,
        )
        return

    file_bytes = uploaded.getvalue()
    try:
        detected_sheet, scored = _detect_best_sheet(file_bytes)
    except Exception as e:
        st.error(f"Cannot open file: {e}")
        return

    st.success(f"File ready: **{uploaded.name}**")

    if detected_sheet:
        _, score, matched = next((s for s in scored if s[0] == detected_sheet), (None, 0, []))
        if len(scored) > 1:
            st.info(f"Sheet detected: **{detected_sheet}** — {score} Home24 column(s): {', '.join(matched)}")
        selected_sheet = detected_sheet
    else:
        labels = [f"{n} (score: {s})" if s else n for n, s, _ in scored]
        idx = st.selectbox("Select the sheet to translate:", options=range(len(scored)),
                           format_func=lambda i: labels[i])
        selected_sheet = scored[idx][0]

    if st.button("Translate", type="primary", use_container_width=True):
        _run_translation(file_bytes, uploaded.name, selected_sheet, scored)


# ── Translation ────────────────────────────────────────────────────────

def _run_translation(file_bytes, filename, sheet_name, scored):
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as e:
        st.error(f"Cannot open file: {e}")
        return
    if sheet_name not in wb.sheetnames:
        st.error(f"Sheet '{sheet_name}' not found.")
        wb.close()
        return
    all_rows = list(wb[sheet_name].iter_rows(values_only=True))
    wb.close()

    if len(all_rows) < 2:
        st.error(f"Sheet '{sheet_name}' has no data rows.")
        return

    raw_headers = [str(c) if c is not None else "" for c in all_rows[0]]
    translatable_cols, protected_cols = _resolve_columns(raw_headers)
    if not translatable_cols:
        st.error(f"No translatable columns found. Expected any of: {', '.join(sorted(TRANSLATABLE_COLUMNS_NL))}")
        return

    data_rows = [
        {raw_headers[i]: row[i] for i in range(min(len(raw_headers), len(row)))}
        for row in all_rows[1:]
    ]
    cell_counts = {
        col: sum(1 for r in data_rows if r.get(col) is not None and str(r.get(col, "")).strip())
        for col in translatable_cols
    }
    plan = TranslationPlan(sheet_name, translatable_cols, protected_cols, cell_counts)

    from engines.nl.localization_engine import get_localization_engine
    engine = get_localization_engine(use_gpt=True)
    engine.clear_glossary_cache()

    cells = []
    progress = st.progress(0.0)
    status = st.empty()
    total = sum(cell_counts.values()) or 1
    done = 0

    with st.spinner("Loading translation memory and translating…"):
        for col in translatable_cols:
            status.text(f"Translating '{col}' — {cell_counts.get(col, 0)} cells…")
            for row_idx, row in enumerate(data_rows):
                val = row.get(col)
                if val is None or not str(val).strip():
                    continue
                cells.append(engine.translate_cell(row_idx + 1, col, val))
                done += 1
                if done % 10 == 0:
                    progress.progress(min(done / total, 1.0))
        progress.progress(1.0)
        status.text("Running multi-pass self-correction…")
        cells = engine.self_correct(cells)

    coverage = _build_coverage(cells, plan)
    coverage_errors = [
        f"'{c['Column']}': {c['Translated']} translated, {c['Source cells']} expected"
        for c in coverage if not c["_ok"] and c["Source cells"] > 0
    ]
    gate = engine.quality_report(cells, coverage_errors=coverage_errors)

    st.session_state.update({
        "t_file_bytes": file_bytes, "t_filename": filename, "t_headers": raw_headers,
        "t_data_rows": data_rows, "t_cells": cells,
        "t_original_targets": {(c.row, c.column): c.target for c in cells},
        "t_stats": _build_stats(cells), "t_xl_bytes": None, "t_csv_bytes": None,
        "t_version": 0, "t_step": "preview", "t_detected_sheet": sheet_name,
        "t_detection_scored": scored, "t_plan": plan, "t_coverage": coverage, "t_gate": gate,
    })
    for k in [k for k in st.session_state if k.startswith("preview_editor_")]:
        del st.session_state[k]
    st.rerun()


# ── Coverage / stats ─────────────────────────────────────────────────────

def _build_coverage(cells, plan) -> list[dict]:
    translated = Counter(c.column for c in cells if (c.target or "").strip())
    unchanged = Counter(c.column for c in cells if c.source == c.target)
    rows = []
    for col in plan.translatable_cols:
        expected = plan.cell_counts.get(col, 0)
        tr = translated.get(col, 0)
        rows.append({
            "Column": col, "Source cells": expected, "Translated": tr,
            "Unchanged": unchanged.get(col, 0),
            "Coverage": f"{tr}/{expected}" if expected else "—",
            "_ok": tr >= expected,
        })
    return rows


def _build_stats(cells) -> dict:
    origins = Counter(c.origin for c in cells)
    return {
        "total_cells": len(cells),
        "tm_exact": origins.get("TM_EXACT", 0),
        "tm_adapted": origins.get("TM_ADAPTED", 0),
        "terminology": origins.get("TERMINOLOGY", 0),
        "human_glossary": origins.get("HUMAN", 0) + origins.get("GLOSSARY", 0),
        "ai_hits": origins.get("GPT", 0),
        "needs_review": sum(1 for c in cells if c.gpt_failed),
    }


# ── Preview ──────────────────────────────────────────────────────────────

def _render_preview():
    filename = st.session_state.get("t_filename") or "file.xlsx"
    stats = st.session_state.get("t_stats") or {}
    cells = st.session_state.get("t_cells") or []
    version = st.session_state.get("t_version") or 0
    detected_sheet = st.session_state.get("t_detected_sheet") or "—"
    coverage = st.session_state.get("t_coverage")
    gate = st.session_state.get("t_gate")

    st.markdown(f"**File:** {filename} &nbsp;·&nbsp; **Sheet:** {detected_sheet}")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("TM (exact+adapted)", stats.get("tm_exact", 0) + stats.get("tm_adapted", 0))
    c2.metric("Terminology", stats.get("terminology", 0))
    c3.metric("Human/Glossary", stats.get("human_glossary", 0))
    c4.metric("AI (gpt-4o)", stats.get("ai_hits", 0))
    c5.metric("Needs review", stats.get("needs_review", 0))

    _render_gate(gate)

    if coverage:
        has_gap = any(not r["_ok"] and r["Source cells"] > 0 for r in coverage)
        cov_df = pd.DataFrame([{k: v for k, v in r.items() if k != "_ok"} for r in coverage])
        if has_gap:
            st.markdown('<div class="alert-error">Coverage gap — some cells were not '
                        "translated. Export is blocked.</div>", unsafe_allow_html=True)
        st.markdown("**Column coverage**")
        st.dataframe(cov_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("### Translation preview")
    st.caption("Edit the **Dutch translation** column directly, then click **Validate** to "
               "apply edits, save corrections, and (re)generate files.")

    editor_key = f"preview_editor_{version}"
    preview_rows = [c.to_preview() for c in cells]
    preview_df = pd.DataFrame(preview_rows) if preview_rows else pd.DataFrame(
        columns=["Row", "Column", "German source", "Dutch translation", "Confidence", "Origin", "Warnings"])

    edited_df = st.data_editor(
        preview_df,
        column_config={
            "Row": st.column_config.NumberColumn("Row", disabled=True, width="small"),
            "Column": st.column_config.TextColumn("Column", disabled=True, width="small"),
            "German source": st.column_config.TextColumn("German source", disabled=True, width="large"),
            "Dutch translation": st.column_config.TextColumn("Dutch translation", disabled=False, width="large"),
            "Confidence": st.column_config.TextColumn("Confidence", disabled=True, width="small"),
            "Origin": st.column_config.TextColumn("Origin", disabled=True, width="small"),
            "Warnings": st.column_config.TextColumn("Warnings", disabled=True, width="medium"),
        },
        hide_index=True, use_container_width=True, height=560, key=editor_key,
    )

    st.markdown("---")
    col_btn, col_reset = st.columns([3, 1])
    with col_btn:
        validate_clicked = st.button("Validate modifications and generate new files",
                                     type="primary", use_container_width=True)
    with col_reset:
        if st.button("Start over", use_container_width=True):
            _reset_state()
            st.rerun()

    if validate_clicked:
        rows = edited_df.to_dict("records")
        for r in rows:
            r["Row"] = int(r["Row"])
        _validate_and_generate(rows)
        return

    _render_download()


def _render_gate(gate):
    if not gate:
        return
    if gate.passed:
        st.success("Quality gate passed — no German residue, no lost data, no name violations.")
        return
    st.error(f"**Quality gate failed: {gate.issue_count} issue(s). Export is blocked until "
             "all are resolved.**")
    for err in gate.coverage_errors:
        st.error(f"Coverage: {err}")
    if gate.issues:
        with st.expander(f"Quality issues ({len(gate.issues)})", expanded=True):
            issue_df = pd.DataFrame([{
                "Row": i.row, "Column": i.column, "Issue": i.issue,
                "Source": i.source, "Output": i.output, "Proposed fix": i.proposed_fix,
            } for i in gate.issues])
            st.dataframe(issue_df, use_container_width=True, hide_index=True)


def _render_download():
    xl_bytes = st.session_state.get("t_xl_bytes")
    csv_bytes = st.session_state.get("t_csv_bytes")
    if not (xl_bytes or csv_bytes):
        return
    filename = st.session_state.get("t_filename") or "file.xlsx"
    stem = Path(filename).stem
    st.markdown("---")
    st.markdown("### Download translated files")

    exclude_name = st.checkbox("Generate CSV without the `name` column", value=False,
                               help="Excel always keeps the name column; the CSV can omit it.")
    csv_bytes = _csv_for_download(exclude_name)

    dc1, dc2 = st.columns(2)
    with dc1:
        if xl_bytes:
            st.download_button("Download NL Excel (.xlsx)", data=xl_bytes,
                               file_name=f"NL-{stem}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True, type="primary")
    with dc2:
        if csv_bytes:
            suffix = "_no-name" if exclude_name else ""
            st.download_button("Download NL CSV (.csv)", data=csv_bytes,
                               file_name=f"NL-{stem}{suffix}.csv", mime="text/csv",
                               use_container_width=True)


def _csv_for_download(exclude_name: bool) -> bytes | None:
    headers = st.session_state.get("t_headers")
    data_rows = st.session_state.get("t_data_rows")
    cells = st.session_state.get("t_cells")
    if not (headers and data_rows is not None and cells):
        return st.session_state.get("t_csv_bytes")
    translation_map = _translation_map(cells)
    from exporters.csv_export import generate_csv_bytes
    exclude = ["name"] if exclude_name else None
    return generate_csv_bytes(headers, data_rows, translation_map, exclude_columns=exclude)


def _translation_map(cells) -> dict:
    tmap: dict[int, dict[str, str]] = {}
    for c in cells:
        tmap.setdefault(c.row - 1, {})[c.column] = c.target
    return tmap


# ── Validate & generate ──────────────────────────────────────────────────

def _validate_and_generate(edited_rows: list):
    filename = st.session_state.get("t_filename") or "file.xlsx"
    file_bytes = st.session_state.get("t_file_bytes")
    headers = st.session_state.get("t_headers") or []
    data_rows = st.session_state.get("t_data_rows") or []
    sheet_name = st.session_state.get("t_detected_sheet") or "Sheet1"
    plan = st.session_state.get("t_plan")
    cells = st.session_state.get("t_cells") or []
    original_targets = st.session_state.get("t_original_targets") or {}

    cell_index = {(c.row, c.column): c for c in cells}

    # Apply edits and detect human corrections.
    corrections = []
    correction_lookup: dict[str, str] = {}
    for r in edited_rows:
        key = (r["Row"], r["Column"])
        cell = cell_index.get(key)
        if not cell:
            continue
        new_val = (r.get("Dutch translation") or "").strip()
        if new_val and new_val != cell.target:
            cell.target = new_val
            cell.origin = "HUMAN"
            cell.confidence_label = "HUMAN_REVIEW"
            cell.confidence = 1.0
            cell.gpt_failed = False
            cell.warnings = []
            corrections.append({"source": cell.source, "new_target": new_val, "column": cell.column})
            correction_lookup[cell.source] = new_val

    # Propagate corrections to identical source segments in this file.
    if correction_lookup:
        for c in cells:
            if c.source in correction_lookup and c.target != correction_lookup[c.source]:
                c.target = correction_lookup[c.source]
                c.origin = "HUMAN"
                c.confidence_label = "HUMAN_REVIEW"

    # Re-run quality gate on the edited cells.
    from engines.nl.localization_engine import get_localization_engine
    engine = get_localization_engine(use_gpt=True)
    coverage = _build_coverage(cells, plan) if plan else []
    coverage_errors = [
        f"'{c['Column']}': {c['Translated']} translated, {c['Source cells']} expected"
        for c in coverage if not c["_ok"] and c["Source cells"] > 0
    ]
    gate = engine.quality_report(cells, coverage_errors=coverage_errors)
    st.session_state["t_gate"] = gate
    st.session_state["t_coverage"] = coverage
    st.session_state["t_stats"] = _build_stats(cells)

    if not gate.passed:
        st.session_state["t_xl_bytes"] = None
        st.session_state["t_csv_bytes"] = None
        st.session_state["t_version"] = (st.session_state.get("t_version") or 0) + 1
        st.error(f"Export blocked: {gate.issue_count} quality issue(s) remain. Fix the "
                 "highlighted cells and click Validate again.")
        st.rerun()
        return

    if corrections:
        _save_corrections(corrections)

    translation_map = _translation_map(cells)
    try:
        from exporters.xlsx_export import export_workbook_translated_bytes
        xl_bytes = export_workbook_translated_bytes(file_bytes, translation_map, headers, sheet_name=sheet_name)
    except Exception as e:
        st.error(f"Excel export failed: {e}")
        return
    try:
        from exporters.csv_export import generate_csv_bytes
        csv_bytes = generate_csv_bytes(headers, data_rows, translation_map)
    except Exception as e:
        st.error(f"CSV export failed: {e}")
        return

    st.session_state["t_original_targets"] = {(c.row, c.column): c.target for c in cells}
    st.session_state["t_xl_bytes"] = xl_bytes
    st.session_state["t_csv_bytes"] = csv_bytes
    st.session_state["t_version"] = (st.session_state.get("t_version") or 0) + 1

    msg = "Files generated successfully."
    if corrections:
        msg = f"Files generated. {len(corrections)} human correction(s) saved to glossary and TM."
    st.success(msg)
    st.rerun()


# ── Human correction persistence (learning loop) ────────────────────────

def _save_corrections(corrections: list):
    from database.database import get_connection
    now = datetime.now().isoformat()
    for c in corrections:
        src = c["source"].lower().strip()
        tgt = c["new_target"]
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO glossary "
                    "(source_term, target_term, category, confidence, source_type, active) "
                    "VALUES (?,?,?,1.0,'HUMAN_REVIEW',1)",
                    (src, tgt, c["column"]),
                )
        except Exception:
            pass
        try:
            with get_connection() as conn:
                existing = conn.execute(
                    "SELECT id FROM translation_memory WHERE normalized_source=? LIMIT 1", (src,)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE translation_memory SET target_segment=?, normalized_target=?, "
                        "confidence=1.0, modified_at=?, created_by='HUMAN_REVIEW' WHERE id=?",
                        (tgt, tgt.lower().strip(), now, existing["id"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO translation_memory "
                        "(source_segment, target_segment, normalized_source, normalized_target, "
                        "confidence, created_at, modified_at, created_by) "
                        "VALUES (?,?,?,?,1.0,?,?,'HUMAN_REVIEW')",
                        (c["source"], tgt, src, tgt.lower().strip(), now, now),
                    )
        except Exception:
            pass

    # Refresh engine caches so corrections apply immediately to later files.
    try:
        from engines.nl.localization_engine import get_localization_engine
        from engines.nl.adaptive_tm import get_adaptive_tm
        get_localization_engine().clear_glossary_cache()
        get_adaptive_tm().reload()
    except Exception:
        pass


def _reset_state():
    for key in _STATE_KEYS:
        st.session_state[key] = None
    st.session_state["t_step"] = "upload"
    st.session_state["t_version"] = 0
    for k in [k for k in st.session_state if k.startswith("preview_editor_")]:
        del st.session_state[k]
