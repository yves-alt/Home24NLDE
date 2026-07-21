import streamlit as st
import pandas as pd
from engines.glossary_engine import get_glossary_manager
from auth.session import require_permission, can


def render():
    require_permission("glossary")

    st.markdown('<div class="section-header">Glossary Manager</div>', unsafe_allow_html=True)

    gm = get_glossary_manager()
    stats = gm.get_stats()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Terms", stats["total"])
    col2.metric("Active", stats["active"])
    col3.metric("TM-sourced", stats["by_type"].get("TM", 0))
    col4.metric("Manual", stats["by_type"].get("MANUAL", 0))

    st.markdown("---")

    tab1, tab2, tab3, tab4 = st.tabs(["Browse & Edit", "Add Term", "Export", "Import Official Glossary"])

    with tab1:
        col_a, col_b, col_c = st.columns([3, 2, 1])
        with col_a:
            search = st.text_input("Search", placeholder="Search source or target term...")
        with col_b:
            cats = ["all"] + gm.get_categories()
            cat_filter = st.selectbox("Category", cats)
        with col_c:
            active_only = st.checkbox("Active only", value=True)

        if search:
            rows = gm.search(search, category=cat_filter if cat_filter != "all" else None)
        else:
            rows = gm.get_all(category=cat_filter if cat_filter != "all" else None, active_only=active_only)

        if rows:
            df = pd.DataFrame(rows)[["id", "source_term", "target_term", "category", "frequency", "confidence", "source_type", "active"]]
            st.dataframe(df, use_container_width=True, height=450)

            with st.expander("Edit / Deactivate term"):
                term_id = st.number_input("Term ID", min_value=1, step=1)
                new_target = st.text_input("New Dutch translation")
                new_cat = st.text_input("New category")
                col_x, col_y, col_z = st.columns(3)
                if col_x.button("Update term"):
                    if gm.update_term(int(term_id), new_target, new_cat):
                        st.success("Updated.")
                        st.rerun()
                if col_y.button("Deactivate"):
                    if gm.toggle_term(int(term_id), False):
                        st.success("Deactivated.")
                        st.rerun()
                if col_z.button("Delete", type="primary"):
                    if gm.delete_term(int(term_id)):
                        st.success("Deleted.")
                        st.rerun()
        else:
            st.info("No glossary terms found.")

    with tab2:
        with st.form("add_term_form"):
            col1, col2 = st.columns(2)
            source = col1.text_input("German term (DE)")
            target = col2.text_input("Dutch translation (NL)")
            category = st.selectbox("Category", ["general", "kitchen", "bathroom", "bedroom", "living",
                                                   "outdoor", "lighting", "storage", "textile", "color", "material"])
            submitted = st.form_submit_button("Add Term", type="primary")

        if submitted:
            if source and target:
                if gm.add_term(source, target, category, "MANUAL"):
                    st.success(f"Added: **{source}** → **{target}**")
                else:
                    st.error("Failed to add term (may already exist).")
            else:
                st.warning("Both source and target required.")

    with tab3:
        st.markdown("Export the full glossary as Excel.")
        if st.button("Export Glossary to Excel", type="primary"):
            import os
            from pathlib import Path
            path = "data/exports/DE_NL_Furniture_Glossary.xlsx"
            Path("data/exports").mkdir(parents=True, exist_ok=True)
            gm.export_to_excel(path)
            st.success(f"Exported to `{path}`")
            with open(path, "rb") as f:
                st.download_button("Download Glossary", f, file_name="DE_NL_Furniture_Glossary.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with tab4:
        _render_official_glossary_import()


def _render_official_glossary_import():
    st.markdown("### Import the official DE→NL glossary")
    st.markdown(
        "Upload the authoritative DE→NL furniture glossary (two columns: German term, "
        "Dutch term — a sheet named like *Clean Technical Glossary* is auto-detected, "
        "otherwise the first sheet is used). Rows are classified automatically:\n\n"
        "- **`Label:` rows** → the terminology brain's colon-label layer.\n"
        "- **2-word `ProductType ModelName` rows** (the model name reappears unchanged "
        "in the Dutch term) → Translation Memory, so the adaptive TM can generalize the "
        "pattern to other products with the same type.\n"
        "- **everything else** → general glossary vocabulary.\n\n"
        "Re-importing is safe — existing entries are never duplicated, and the terminology "
        "brain picks up changes immediately without an app restart."
    )
    uploaded = st.file_uploader("Official glossary file", type=["xlsx"], key="official_glossary_file")
    if not uploaded:
        return
    st.markdown(f"**Selected file:** {uploaded.name}  ({uploaded.size:,} bytes)")
    if st.button("Import Official Glossary", type="primary", use_container_width=True):
        from importers.glossary_importer import import_official_glossary

        progress = st.progress(0.0)
        status = st.empty()

        def cb(p):
            progress.progress(min(p, 1.0))
            status.text(f"Processing… {p:.0%}")

        try:
            stats = import_official_glossary(uploaded.getvalue(), progress_callback=cb)
            progress.progress(1.0)
            status.empty()
            st.success(
                f"Import complete — **{stats['total']:,} rows** processed: "
                f"**{stats['labels_inserted']:,} label(s)**, "
                f"**{stats['general_inserted']:,} general term(s)**, "
                f"**{stats['tm_pairs_inserted']:,} product+model pattern(s)** added to Translation Memory "
                f"({stats['tm_pairs_updated']:,} updated). "
                f"Skipped: **{stats['de_eq_nl_skipped']:,}** identical DE=NL rows, "
                f"**{stats['duplicates_skipped']:,}** duplicate source terms (first occurrence kept)."
            )
            if stats["conflicts"]:
                with st.expander(f"Duplicate source terms — first kept, rest dropped ({len(stats['conflicts'])})"):
                    df = pd.DataFrame(stats["conflicts"], columns=["Source term", "Kept target", "Dropped target"])
                    st.dataframe(df, use_container_width=True, height=300)
        except Exception as e:
            status.empty()
            st.error(f"Import failed: {e}")
