import streamlit as st
import pandas as pd
from database.database import get_connection, get_stats


def render():
    st.markdown('<div class="section-header">Dashboard</div>', unsafe_allow_html=True)

    db_stats = get_stats()

    metrics = [
        {"label": "TM Entries", "value": f"{db_stats['tm_entries']:,}"},
        {"label": "Glossary Terms", "value": f"{db_stats['glossary_terms']:,}"},
        {"label": "Files Exported", "value": f"{db_stats['files_exported']:,}"},
        {"label": "QA Corrections", "value": f"{db_stats['qa_corrections']:,}"},
    ]

    cols = st.columns(4)
    for col, m in zip(cols, metrics):
        with col:
            st.markdown(
                f'<div class="metric-card"><div class="metric-value">{m["value"]}</div>'
                f'<div class="metric-label">{m["label"]}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Recent Exports**")
        with get_connection() as conn:
            exports = conn.execute(
                "SELECT filename, rows_processed, tm_hits, ai_hits, qa_corrections, processing_time, exported_at "
                "FROM export_log ORDER BY exported_at DESC LIMIT 10"
            ).fetchall()
        if exports:
            df = pd.DataFrame([dict(r) for r in exports])
            st.dataframe(df, use_container_width=True, height=300)
        else:
            st.info("No exports yet.")

    with col2:
        st.markdown("**TM by Category**")
        with get_connection() as conn:
            cats = conn.execute(
                "SELECT category, COUNT(*) as entries, SUM(frequency) as total_freq "
                "FROM translation_memory GROUP BY category ORDER BY entries DESC"
            ).fetchall()
        if cats:
            df = pd.DataFrame([dict(r) for r in cats])
            st.dataframe(df, use_container_width=True, height=300)
        else:
            st.info("No TM data yet. Import the Translation Memory first.")

    st.markdown("---")

    st.markdown("**Recent QA Issues**")
    with get_connection() as conn:
        qa = conn.execute(
            "SELECT filename, row_num, issue_type, original, corrected, auto_fixed, logged_at "
            "FROM qa_log ORDER BY logged_at DESC LIMIT 20"
        ).fetchall()
    if qa:
        df = pd.DataFrame([dict(r) for r in qa])
        st.dataframe(df, use_container_width=True, height=300)
    else:
        st.info("No QA issues logged yet.")
