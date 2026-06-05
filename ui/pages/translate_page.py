import os
import time
from pathlib import Path

import streamlit as st
import pandas as pd

from importers.excel_importer import load_workbook
from engines.translation_engine import get_engine, TranslationSource
from engines.consistency_engine import get_consistency_engine
from database.database import get_connection


def render():
    st.markdown('<div class="section-header">Translate Workbook</div>', unsafe_allow_html=True)

    api_key = st.session_state.get("api_key", os.getenv("OPENAI_API_KEY", ""))
    if not api_key:
        st.markdown(
            '<div class="alert-warning">No API key set. TM-only mode active (no AI fallback). Set key in Settings.</div>',
            unsafe_allow_html=True,
        )

    uploaded = st.file_uploader("Upload German Excel file", type=["xlsx", "xls"],
                                 help="Upload any Home24 product export. Supports 300+ rows and multi-sheet files.")

    if not uploaded:
        st.markdown(
            '<div class="alert-info">Upload a German Excel file to start. The system will detect columns automatically.</div>',
            unsafe_allow_html=True,
        )
        return

    # Save temp file
    tmp_path = f"/tmp/{uploaded.name}"
    with open(tmp_path, "wb") as f:
        f.write(uploaded.read())

    # Load workbook
    try:
        wb = load_workbook(tmp_path)
    except Exception as e:
        st.error(f"Failed to open file: {e}")
        return

    st.success(f"Loaded **{wb.filename}** — {wb.total_rows} rows across {len(wb.sheets)} sheet(s)")

    # Sheet & column configuration
    with st.expander("Column configuration", expanded=True):
        sheet_configs = {}
        for sheet in wb.sheets:
            st.markdown(f"**Sheet: {sheet.name}**")
            col1, col2 = st.columns(2)
            src_options = sheet.headers
            tgt_options = ["(auto-detect / add new column)"] + sheet.headers

            src_default = sheet.source_col if sheet.source_col is not None else 0
            with col1:
                src_idx = st.selectbox(f"German (source) column", options=range(len(src_options)),
                                        format_func=lambda i: src_options[i],
                                        index=src_default, key=f"src_{sheet.name}")
            with col2:
                tgt_idx = st.selectbox(f"Dutch (target) column", options=range(len(tgt_options)),
                                        format_func=lambda i: tgt_options[i],
                                        index=0, key=f"tgt_{sheet.name}")
            sheet_configs[sheet.name] = {
                "source_col": src_idx,
                "target_col": None if tgt_idx == 0 else tgt_idx - 1,
            }

    # Translation settings
    col_a, col_b = st.columns(2)
    with col_a:
        fuzzy_threshold = st.slider("Fuzzy match threshold", 0.5, 1.0, 0.75, 0.05,
                                     help="Minimum similarity to accept a fuzzy TM match")
    with col_b:
        max_rows = st.number_input("Max rows to translate (0 = all)", min_value=0, value=0, step=50)

    if st.button("Start Translation", type="primary", use_container_width=True):
        _run_translation(wb, tmp_path, sheet_configs, api_key, fuzzy_threshold, max_rows)


def _run_translation(wb, tmp_path, sheet_configs, api_key, fuzzy_threshold, max_rows):
    engine = get_engine(api_key)
    consistency = get_consistency_engine()
    consistency.reset()
    consistency.lock_batch_from_glossary()

    overall_progress = st.progress(0.0)
    status_text = st.empty()
    results_container = st.container()

    all_sheet_results = {}
    total_sheets = len(wb.sheets)

    for s_idx, sheet in enumerate(wb.sheets):
        cfg = sheet_configs.get(sheet.name, {})
        src_col_idx = cfg.get("source_col", sheet.source_col or 0)
        tgt_col_idx = cfg.get("target_col", sheet.target_col)

        src_col_name = sheet.headers[src_col_idx] if src_col_idx < len(sheet.headers) else str(src_col_idx)

        rows = sheet.rows
        if max_rows and max_rows > 0:
            rows = rows[:max_rows]

        items = []
        for i, row in enumerate(rows):
            val = row.get(src_col_name) or (list(row.values())[src_col_idx] if src_col_idx < len(row) else None)
            if val and str(val).strip():
                items.append((i, str(val).strip()))

        status_text.text(f"Translating sheet '{sheet.name}' ({len(items)} segments)...")

        sheet_progress = st.progress(0.0)

        def on_progress(p, sp=sheet_progress):
            sp.progress(p)
            overall_progress.progress((s_idx + p) / total_sheets)

        batch_result = engine.translate_batch(items, context_rows=rows, filename=wb.filename,
                                               progress_callback=on_progress)
        sheet_progress.progress(1.0)

        result_rows = []
        res_map = {items[i][0]: batch_result.results[i] for i in range(len(items))}

        for i, row in enumerate(rows):
            row_out = dict(row)
            row_out.pop("_raw", None)
            res = res_map.get(i)
            if res:
                row_out["NL Translation"] = res.target
                row_out["Source Type"] = res.source_type.value
                row_out["Confidence"] = res.confidence_label
                row_out["Score"] = f"{res.confidence_score:.0%}"
                row_out["Review"] = "⚠" if res.needs_review else ""
                row_out["QA Issues"] = len(res.qa_issues)
                row_out["_result"] = res
            result_rows.append(row_out)

        all_sheet_results[sheet.name] = {
            "results": [{"target": r.target, "source_type": r.source_type.value,
                          "confidence_label": r.confidence_label,
                          "confidence_score": r.confidence_score,
                          "needs_review": r.needs_review,
                          "qa_issues": r.qa_issues, "row_idx": i} for i, r in res_map.items()],
            "result_rows": result_rows,
            "target_col_idx": tgt_col_idx,
            "source_col_idx": src_col_idx,
            "stats": {
                "total_rows": len(items),
                "tm_hits": batch_result.tm_hits,
                "fuzzy_hits": batch_result.fuzzy_hits,
                "glossary_hits": batch_result.glossary_hits,
                "tfidf_hits": batch_result.tfidf_hits,
                "ai_hits": batch_result.ai_hits,
                "low_confidence": len(batch_result.low_confidence_rows),
                "api_savings": batch_result.api_savings_pct,
                "qa_corrections": batch_result.qa_corrections,
                "consistency_score": batch_result.consistency_score,
                "token_usage": batch_result.total_tokens,
                "processing_time": batch_result.processing_time,
            },
        }

    overall_progress.progress(1.0)
    status_text.text("Translation complete.")

    st.session_state["last_results"] = all_sheet_results
    st.session_state["last_source_file"] = tmp_path

    with results_container:
        _render_results(all_sheet_results, tmp_path)


def _render_results(all_sheet_results, source_path):
    st.markdown("---")
    st.markdown('<div class="section-header">Results</div>', unsafe_allow_html=True)

    for sheet_name, data in all_sheet_results.items():
        stats = data["stats"]
        total = stats["total_rows"]
        if total == 0:
            continue

        with st.expander(f"Sheet: {sheet_name} ({total} rows)", expanded=True):
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            col1.metric("TM Exact", stats["tm_hits"])
            col2.metric("Fuzzy+TF-IDF", stats["fuzzy_hits"] + stats.get("tfidf_hits", 0))
            col3.metric("Glossary", stats["glossary_hits"])
            col4.metric("AI (GPT)", stats["ai_hits"])
            col5.metric("QA Fixes", stats["qa_corrections"])
            col6.metric("API Saved", f"{stats.get('api_savings', 0):.0%}")

            low_conf = stats.get("low_confidence", 0)
            if low_conf > 0:
                st.markdown(
                    f'<div class="alert-warning">⚠ {low_conf} row(s) flagged LOW_CONFIDENCE — review before publishing.</div>',
                    unsafe_allow_html=True,
                )

            result_rows = data.get("result_rows", [])
            display_cols = [c for c in (result_rows[0].keys() if result_rows else []) if not c.startswith("_")]
            df = pd.DataFrame(result_rows)[display_cols]
            st.dataframe(df, use_container_width=True, height=400)

            # Low confidence detail
            low_rows = [r for r in result_rows if r.get("Review") == "⚠"]
            if low_rows:
                with st.expander(f"Low confidence rows ({len(low_rows)})"):
                    lc_cols = ["NL Translation", "Source Type", "Confidence", "Score"]
                    lc_df = pd.DataFrame(low_rows)[[c for c in lc_cols if c in lc_df.columns if c in pd.DataFrame(low_rows).columns]]
                    st.dataframe(pd.DataFrame(low_rows)[[c for c in lc_cols if c in pd.DataFrame(low_rows).columns]], use_container_width=True)

    _render_export_section(all_sheet_results, source_path)


def _render_export_section(all_sheet_results, source_path):
    st.markdown("---")
    st.markdown('<div class="section-header">Export</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Export as XLSX", type="primary", use_container_width=True):
            try:
                from exporters.xlsx_export import export_workbook
                output_path = export_workbook(source_path, all_sheet_results)
                with open(output_path, "rb") as f:
                    st.download_button(
                        "Download NL XLSX",
                        f,
                        file_name=Path(output_path).name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                st.success(f"Saved: {output_path}")
            except Exception as e:
                st.error(f"Export failed: {e}")

    with col2:
        if st.button("Export as CSV", use_container_width=True):
            try:
                from exporters.csv_export import export_csv
                for sheet_name, data in all_sheet_results.items():
                    rows = data.get("result_rows", [])
                    clean_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
                    path = export_csv(clean_rows, Path(source_path).name)
                    with open(path, "rb") as f:
                        st.download_button(
                            f"Download {sheet_name} CSV",
                            f,
                            file_name=Path(path).name,
                            mime="text/csv",
                        )
            except Exception as e:
                st.error(f"CSV export failed: {e}")
