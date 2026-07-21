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

from engines.nl.column_classifier import (
    ColumnKind, classify_columns, normalize_header,
    KNOWN_TRANSLATABLE_COLUMNS, PROTECTED_METADATA_COLUMNS,
)


def _ensure_xlsx_bytes(raw_bytes: bytes) -> bytes:
    """Return bytes that openpyxl can open.

    Handles two .xls cases transparently:
    - ZIP magic (PK) — file is really XLSX with a wrong extension, returned as-is.
    - BIFF magic (D0CF) — true legacy XLS, converted sheet-by-sheet via xlrd+pandas.
    """
    if raw_bytes[:4] == b"PK\x03\x04":
        return raw_bytes
    sheets = pd.read_excel(
        io.BytesIO(raw_bytes), sheet_name=None, header=None,
        engine="xlrd", dtype=object, keep_default_na=False,
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sname, df in sheets.items():
            df.to_excel(writer, sheet_name=sname, index=False, header=False)
    return buf.getvalue()


# ── Single source of truth for columns ────────────────────────────────
# The static lists below cover the columns with dedicated behavior; anything
# else is classified dynamically (engines/nl/column_classifier.py) so a
# non-empty column is never silently skipped — see _resolve_columns.

TRANSLATABLE_COLUMNS_NL = KNOWN_TRANSLATABLE_COLUMNS
PROTECTED_COLUMNS = PROTECTED_METADATA_COLUMNS

HOME24_DETECTION_COLUMNS = TRANSLATABLE_COLUMNS_NL | PROTECTED_COLUMNS | frozenset({
    "internalDimensionDrawer", "externalDimension", "weightNetto", "weightBrutto",
    "colorName", "descriptionBullet1", "descriptionBullet2",
})


def _norm(h: str) -> str:
    return normalize_header(h)


def _resolve_columns(raw_headers: list, data_rows: list, ambiguous_actions: dict | None = None):
    """Classify every non-empty column and route it to translatable / protected
    / ambiguous-needing-review. `ambiguous_actions` carries the user's choice
    (from the upload-review UI) for columns the classifier couldn't place with
    confidence — defaults to "protect" (never translate silently, never drop).
    """
    ambiguous_actions = ambiguous_actions or {}
    classification = classify_columns(raw_headers, data_rows)
    translatable, protected, ambiguous = [], [], []
    for c in classification:
        if c.kind == ColumnKind.PROTECTED_METADATA:
            protected.append(c.header)
        elif c.kind in (ColumnKind.PRODUCT_NAME, ColumnKind.KNOWN_CONTENT, ColumnKind.UNKNOWN_CONTENT):
            translatable.append(c.header)
        elif c.kind == ColumnKind.TECHNICAL_DATA:
            protected.append(c.header)  # not translated; passes through unchanged like protected metadata
        elif c.kind == ColumnKind.AMBIGUOUS:
            ambiguous.append(c)
            action = ambiguous_actions.get(c.header, "protect")
            if action == "translate":
                translatable.append(c.header)
            else:
                protected.append(c.header)  # "protect" and "skip" both mean: pass through unchanged
        # EMPTY columns contribute nothing either way.
    return translatable, protected, ambiguous


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
    "t_coverage", "t_gate", "t_pass_summary", "t_reconciliation",
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
    if uploaded.name.lower().endswith(".xls") and not uploaded.name.lower().endswith(".xlsx"):
        file_bytes = _ensure_xlsx_bytes(file_bytes)
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

    raw_headers, data_rows = _load_sheet_rows(file_bytes, selected_sheet)
    if raw_headers is None:
        return

    ambiguous_actions = _render_ambiguous_column_review(raw_headers, data_rows, selected_sheet)

    if st.button("Translate", type="primary", use_container_width=True):
        _run_translation(file_bytes, uploaded.name, selected_sheet, scored,
                         raw_headers, data_rows, ambiguous_actions)


def _load_sheet_rows(file_bytes, sheet_name):
    """Return (raw_headers, data_rows) for a sheet, or (None, None) on error."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as e:
        st.error(f"Cannot open file: {e}")
        return None, None
    if sheet_name not in wb.sheetnames:
        st.error(f"Sheet '{sheet_name}' not found.")
        wb.close()
        return None, None
    all_rows = list(wb[sheet_name].iter_rows(values_only=True))
    wb.close()
    if len(all_rows) < 2:
        st.error(f"Sheet '{sheet_name}' has no data rows.")
        return None, None
    raw_headers = [str(c) if c is not None else "" for c in all_rows[0]]
    data_rows = [
        {raw_headers[i]: row[i] for i in range(min(len(raw_headers), len(row)))}
        for row in all_rows[1:]
    ]
    return raw_headers, data_rows


def _render_ambiguous_column_review(raw_headers, data_rows, sheet_name) -> dict:
    """Show any AMBIGUOUS column (not in the known/protected lists, and not
    clearly technical or descriptive by sampling) for an explicit per-column
    choice, so nothing non-empty is ever silently skipped. Returns
    {header: "translate"|"protect"|"skip"} from the widgets' current state."""
    _, _, ambiguous = _resolve_columns(raw_headers, data_rows)
    if not ambiguous:
        return {}

    st.markdown("---")
    st.markdown("### Columns needing review")
    st.caption(
        "These columns aren't in the known Home24 list, and sampling their values didn't "
        "clearly show technical data (IDs/URLs/dates) or German product copy either. "
        "Choose how to handle each — nothing is translated or dropped without a decision."
    )
    actions: dict[str, str] = {}
    for c in ambiguous:
        preview = " · ".join(str(v) for v in c.sample_values[:3]) or "(no sample values)"
        choice = st.radio(
            f"**{c.header}** — e.g. _{preview}_",
            options=["protect", "translate", "skip"],
            format_func={
                "protect": "Keep unchanged (protected)",
                "translate": "Translate as generic Dutch text",
                "skip": "Skip (leave blank in output)",
            }.get,
            index=0, horizontal=True, key=f"ambig_{sheet_name}_{c.header}",
        )
        actions[c.header] = choice
    return actions


# ── Translation ────────────────────────────────────────────────────────

def _run_translation(file_bytes, filename, sheet_name, scored, raw_headers, data_rows, ambiguous_actions):
    translatable_cols, protected_cols, ambiguous = _resolve_columns(raw_headers, data_rows, ambiguous_actions)
    if not translatable_cols:
        st.error(f"No translatable columns found. Expected any of: {', '.join(sorted(TRANSLATABLE_COLUMNS_NL))}")
        return

    cell_counts = {
        col: sum(1 for r in data_rows if r.get(col) is not None and str(r.get(col, "")).strip())
        for col in translatable_cols
    }
    plan = TranslationPlan(sheet_name, translatable_cols, protected_cols, cell_counts)

    from engines.nl.localization_engine import get_localization_engine
    from engines.nl.consistency_engine import harmonize
    from engines.nl.glossary_validator import validate_cells as validate_glossary_compliance
    engine = get_localization_engine(use_gpt=True)
    engine.clear_glossary_cache()

    cells = []
    progress = st.progress(0.0)
    status = st.empty()
    total = sum(cell_counts.values()) or 1
    done = 0

    with st.spinner("Loading translation memory and translating…"):
        status.text(f"Pass 1 — Initial translation: {total} cell(s)…")
        for col in translatable_cols:
            for row_idx, row in enumerate(data_rows):
                val = row.get(col)
                if val is None or not str(val).strip():
                    continue
                cells.append(engine.translate_cell(row_idx + 1, col, val))
                done += 1
                if done % 10 == 0:
                    progress.progress(min(done / total, 1.0))
                    status.text(f"Pass 1 — Initial translation: '{col}' — {done}/{total} cell(s)…")
        progress.progress(1.0)
        status.text("Pass 2 — Self-correction…")
        cells, correct_stats = engine.self_correct(cells)
        status.text("Pass 3 — Glossary compliance validation…")
        glossary_stats = validate_glossary_compliance(cells, filename=filename)
        status.text("Pass 4 — Consistency harmonization…")
        consistency_report = harmonize(cells, filename=filename)

    coverage, reconciliation = _build_coverage(cells, plan, data_rows)
    coverage_errors = [
        f"'{c['Column']}': {c['Translated']} translated, {c['Source cells']} expected"
        for c in coverage if not c["_ok"] and c["Source cells"] > 0
    ]
    if not reconciliation["_reconciles"]:
        coverage_errors.append(
            f"Reconciliation mismatch: {reconciliation['Successful']} successful + "
            f"{reconciliation['Failed']} failed exceeds {reconciliation['Expected translations']} expected"
        )
    gate = engine.quality_report(cells, coverage_errors=coverage_errors)

    st.session_state.update({
        "t_file_bytes": file_bytes, "t_filename": filename, "t_headers": raw_headers,
        "t_data_rows": data_rows, "t_cells": cells,
        "t_original_targets": {(c.row, c.column): c.target for c in cells},
        "t_stats": _build_stats(cells), "t_xl_bytes": None, "t_csv_bytes": None,
        "t_version": 0, "t_step": "preview", "t_detected_sheet": sheet_name,
        "t_detection_scored": scored, "t_plan": plan, "t_coverage": coverage,
        "t_reconciliation": reconciliation, "t_gate": gate,
        "t_pass_summary": _build_pass_summary(total, correct_stats, glossary_stats, consistency_report, gate),
    })
    for k in [k for k in st.session_state if k.startswith("preview_editor_")]:
        del st.session_state[k]
    st.rerun()


def _build_pass_summary(total_cells: int, correct_stats, glossary_stats, consistency_report, gate) -> list:
    return [
        f"Pass 1 — Initial Translation: completed ({total_cells} cell(s))",
        f"Pass 2 — Self-Correction: {correct_stats.cells_fixed} cell(s) fixed across "
        f"{correct_stats.passes_run} loop(s), {correct_stats.gpt_retries} GPT retr(y/ies)",
        f"Pass 3 — Glossary Compliance: {glossary_stats['corrected']} correction(s), "
        f"{glossary_stats['flagged']} flagged for review",
        f"Pass 4 — Consistency Harmonization: {consistency_report.cells_harmonized} value(s) harmonized "
        f"across {len(consistency_report.rewrites)} recurring source(s)",
        f"Pass 5 — Quality Gate: {gate.status.replace('_', ' ').title()} "
        f"({len(gate.critical_issues)} critical, {len(gate.warning_issues)} warning)",
    ]


# ── Coverage / stats ─────────────────────────────────────────────────────

def _build_coverage(cells, plan, data_rows=None) -> tuple:
    """Per-column coverage table, plus a full reconciliation summary (§22):
    non-empty source cells, protected cells, expected/successful/failed/
    review-required translations must add up — a mismatch is a CRITICAL gate
    issue via coverage_errors, not a silently-accepted gap."""
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

    expected_total = plan.total_expected
    failed = sum(1 for c in cells if c.gpt_failed)
    review_required = sum(1 for c in cells if any("requires review" in w.lower() for w in c.warnings))
    successful = sum(1 for c in cells if (c.target or "").strip() and not c.gpt_failed)
    protected_cell_count = 0
    if data_rows is not None:
        protected_cell_count = sum(
            1 for r in data_rows for col in plan.protected_cols
            if r.get(col) is not None and str(r.get(col, "")).strip()
        )
    reconciliation = {
        "Non-empty source cells": expected_total,
        "Protected cells (untouched)": protected_cell_count,
        "Expected translations": expected_total,
        "Successful": successful,
        "Failed": failed,
        "Review required": review_required,
        "_reconciles": successful + failed <= expected_total,
    }
    return rows, reconciliation


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
    reconciliation = st.session_state.get("t_reconciliation")
    gate = st.session_state.get("t_gate")
    plan = st.session_state.get("t_plan")
    data_rows = st.session_state.get("t_data_rows") or []

    st.markdown(f"**File:** {filename} &nbsp;·&nbsp; **Sheet:** {detected_sheet}")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("TM (exact+adapted)", stats.get("tm_exact", 0) + stats.get("tm_adapted", 0))
    c2.metric("Terminology", stats.get("terminology", 0))
    c3.metric("Human/Glossary", stats.get("human_glossary", 0))
    c4.metric("AI (gpt-4o)", stats.get("ai_hits", 0))
    c5.metric("Needs review", stats.get("needs_review", 0))

    pass_summary = st.session_state.get("t_pass_summary")
    if pass_summary:
        with st.expander("Pipeline passes", expanded=False):
            for line in pass_summary:
                st.text(line)

    _render_gate(gate, cells, data_rows, plan)

    if reconciliation:
        with st.expander("Translation coverage reconciliation", expanded=not reconciliation.get("_reconciles", True)):
            recon_df = pd.DataFrame(
                [{"Metric": k, "Count": v} for k, v in reconciliation.items() if not k.startswith("_")]
            )
            st.dataframe(recon_df, use_container_width=True, hide_index=True)
            if not reconciliation.get("_reconciles", True):
                st.error("Reconciliation does not add up — see the coverage gap above. Export is blocked.")

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


def _categorize_issue(issue_text: str) -> str:
    low = issue_text.lower()
    if "name compression" in low or "name rule" in low:
        return "Product names"
    if "german residue" in low:
        return "Residue"
    if "glossary" in low:
        return "Glossary"
    if "information loss" in low or "model integrity" in low or "<br>" in low:
        return "Information loss"
    return "Other"


def _row_context(row: int, data_rows: list, headers: list) -> dict:
    if not data_rows or row - 1 >= len(data_rows) or row < 1:
        return {}
    data = data_rows[row - 1]
    article = next((data.get(h) for h in headers if normalize_header(h) == "articlenumber"), None)
    jira = next((data.get(h) for h in _jira_key_headers(headers)), None)
    return {"articleNumber": article, "Jira Key": jira}


def _render_gate(gate, cells=None, data_rows=None, plan=None):
    if not gate:
        return

    status_map = {
        "PASSED": ("success", "PASSED — no critical or warning issues found."),
        "PASSED_WITH_WARNINGS": ("warning", f"PASSED WITH REVIEW WARNINGS — "
                                            f"{len(gate.warning_issues)} warning(s), export allowed."),
        "FAILED_CRITICAL": ("error", f"FAILED — CRITICAL ISSUES — {len(gate.critical_issues)} critical "
                                     f"issue(s) plus {len(gate.coverage_errors)} coverage error(s). "
                                     "Export is blocked until every CRITICAL item is resolved."),
    }
    kind, message = status_map.get(gate.status, ("error", gate.status))
    getattr(st, kind)(f"**Quality gate: {message}**")

    for err in gate.coverage_errors:
        st.error(f"Coverage: {err}")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Critical", len(gate.critical_issues))
    m2.metric("Warning", len(gate.warning_issues))
    m3.metric("Info (non-blocking)", len(gate.info_events))
    m4.metric("Compressed names", sum(1 for c in (cells or []) if c.compression_event))
    m5.metric("Failed cells", sum(1 for c in (cells or []) if c.gpt_failed))

    if not gate.issues and not gate.info_events:
        return

    with st.expander(f"Review panel ({len(gate.issues)} issue(s), {len(gate.info_events)} info event(s))",
                     expanded=gate.status != "PASSED"):
        fc1, fc2 = st.columns(2)
        severity_filter = fc1.selectbox("Severity", ["All", "Critical", "Warning", "Info"])
        category_filter = fc2.selectbox(
            "Category", ["All", "Product names", "Residue", "Glossary", "Information loss", "Other"]
        )

        headers = st.session_state.get("t_headers") or []
        rows = []
        for i in gate.issues:
            severity = i.severity.value
            category = _categorize_issue(i.issue)
            if severity_filter != "All" and severity.title() != severity_filter:
                continue
            if category_filter != "All" and category != category_filter:
                continue
            ctx = _row_context(i.row, data_rows, headers)
            rows.append({
                "Severity": severity, "Category": category, "Row": i.row, "Column": i.column,
                "articleNumber": ctx.get("articleNumber", ""), "Jira Key": ctx.get("Jira Key", ""),
                "Source": i.source, "Output": i.output, "Issue": i.issue,
                "Recommendation": i.proposed_fix,
            })
        if severity_filter in ("All", "Info"):
            for ev in gate.info_events:
                if category_filter not in ("All", "Product names"):
                    continue
                ctx = _row_context(ev.row, data_rows, headers)
                rows.append({
                    "Severity": "INFO", "Category": "Product names", "Row": ev.row, "Column": ev.column,
                    "articleNumber": ctx.get("articleNumber", ""), "Jira Key": ctx.get("Jira Key", ""),
                    "Source": ev.source, "Output": ev.compressed_name,
                    "Issue": f"name compression ({ev.strategy})", "Recommendation": ev.recommendation,
                })

        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No items match the selected filters.")

    if plan and cells:
        unknown_cols = [c for c in plan.translatable_cols if c not in TRANSLATABLE_COLUMNS_NL]
        if unknown_cols:
            with st.expander(f"Unknown columns translated via generic profile ({', '.join(unknown_cols)})"):
                unk_rows = [c.to_preview() for c in cells if c.column in unknown_cols]
                if unk_rows:
                    st.dataframe(pd.DataFrame(unk_rows), use_container_width=True, hide_index=True)


def _render_download():
    xl_bytes = st.session_state.get("t_xl_bytes")
    csv_bytes = st.session_state.get("t_csv_bytes")
    if not (xl_bytes or csv_bytes):
        return
    filename = st.session_state.get("t_filename") or "file.xlsx"
    stem = Path(filename).stem
    st.markdown("---")
    st.markdown("### Download translated files")

    st.caption("Excel keeps every column, including `name`. The CSV always excludes "
              "`name` and `Jira Key` (§24).")
    csv_bytes = _csv_for_download()

    dc1, dc2 = st.columns(2)
    with dc1:
        if xl_bytes:
            st.download_button("Download NL Excel (.xlsx)", data=xl_bytes,
                               file_name=f"NL-{stem}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True, type="primary")
    with dc2:
        if csv_bytes:
            st.download_button("Download NL CSV (.csv)", data=csv_bytes,
                               file_name=f"NL-{stem}.csv", mime="text/csv",
                               use_container_width=True)


def _jira_key_headers(headers: list) -> list:
    """Every header spelling that normalizes to 'Jira Key' ('JiraKey', 'jira_key', …)."""
    target = normalize_header("Jira Key")
    return [h for h in headers if normalize_header(h) == target]


def _csv_exclude_columns(headers: list) -> list:
    """§24: CSV always excludes `name` and every Jira Key header spelling."""
    return _jira_key_headers(headers) + ["name"]


def _csv_for_download() -> bytes | None:
    headers = st.session_state.get("t_headers")
    data_rows = st.session_state.get("t_data_rows")
    cells = st.session_state.get("t_cells")
    if not (headers and data_rows is not None and cells):
        return st.session_state.get("t_csv_bytes")
    translation_map = _translation_map(cells)
    from exporters.csv_export import generate_csv_bytes
    return generate_csv_bytes(headers, data_rows, translation_map, exclude_columns=_csv_exclude_columns(headers))


def _translation_map(cells) -> dict:
    tmap: dict[int, dict[str, str]] = {}
    for c in cells:
        tmap.setdefault(c.row - 1, {})[c.column] = c.target
    return tmap


_SEVERITY_RANK = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}


def _severity_map(gate) -> dict:
    """{(1-based row, column): 'CRITICAL'|'WARNING'|'INFO'} for Excel review
    highlighting — the highest severity wins when a cell has multiple issues."""
    if not gate:
        return {}
    result: dict[tuple, str] = {}
    for i in gate.issues:
        key = (i.row, i.column)
        sev = i.severity.value
        if _SEVERITY_RANK[sev] > _SEVERITY_RANK.get(result.get(key, "INFO"), 0):
            result[key] = sev
    for ev in gate.info_events:
        key = (ev.row, ev.column)
        result.setdefault(key, "INFO")
    return result


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
    coverage, reconciliation = _build_coverage(cells, plan, data_rows) if plan else ([], {})
    coverage_errors = [
        f"'{c['Column']}': {c['Translated']} translated, {c['Source cells']} expected"
        for c in coverage if not c["_ok"] and c["Source cells"] > 0
    ]
    gate = engine.quality_report(cells, coverage_errors=coverage_errors)
    st.session_state["t_gate"] = gate
    st.session_state["t_coverage"] = coverage
    st.session_state["t_reconciliation"] = reconciliation
    st.session_state["t_stats"] = _build_stats(cells)

    if not gate.passed:
        st.session_state["t_xl_bytes"] = None
        st.session_state["t_csv_bytes"] = None
        st.session_state["t_version"] = (st.session_state.get("t_version") or 0) + 1
        n_critical = len(gate.critical_issues) + len(gate.coverage_errors)
        st.error(f"Export blocked: {n_critical} CRITICAL issue(s) remain. Fix the "
                 "highlighted cells and click Validate again.")
        st.rerun()
        return

    if corrections:
        _save_corrections(corrections)

    translation_map = _translation_map(cells)
    try:
        from exporters.xlsx_export import export_workbook_translated_bytes
        xl_bytes = export_workbook_translated_bytes(
            file_bytes, translation_map, headers, sheet_name=sheet_name,
            severity_map=_severity_map(gate),
        )
    except Exception as e:
        st.error(f"Excel export failed: {e}")
        return
    try:
        from exporters.csv_export import generate_csv_bytes
        csv_bytes = generate_csv_bytes(headers, data_rows, translation_map, exclude_columns=_csv_exclude_columns(headers))
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
