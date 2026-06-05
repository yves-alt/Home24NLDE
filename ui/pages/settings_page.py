import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def render():
    st.markdown('<div class="section-header">Settings & Import</div>', unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["API Key", "Import TM", "Import Glossary", "ML Index"])

    with tab1:
        st.markdown("**OpenAI API Key**")
        st.markdown(
            '<div class="alert-info">Key is loaded from <code>.env</code> or Streamlit secrets. '
            'Never hardcoded. Never committed.</div>',
            unsafe_allow_html=True,
        )

        current = st.session_state.get("api_key", os.getenv("OPENAI_API_KEY", ""))
        if current:
            masked = f"sk-...{current[-6:]}" if len(current) > 10 else "****"
            st.success(f"Key loaded: `{masked}`")
        else:
            st.warning("No API key found. Add `OPENAI_API_KEY=...` to your `.env` file.")

        new_key = st.text_input("Override key (session only)", type="password", placeholder="sk-proj-...")
        if st.button("Use this key", type="primary"):
            if new_key:
                st.session_state["api_key"] = new_key
                from engines.translation_engine import get_engine
                get_engine(new_key)
                st.success("Key set for this session.")

        model = st.selectbox(
            "OpenAI model",
            ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
            index=0,
            help="gpt-4o-mini is fastest and cheapest; used only when TM/glossary have no match.",
        )
        st.session_state["openai_model"] = model

    with tab2:
        st.markdown("**Import Translation Memory from XLSX**")
        st.caption("Expects columns: `Source (de-DE)`, `Target (nl-NL)`, `Usage Count`")

        tm_file = st.file_uploader("TM Excel file", type=["xlsx"], key="tm_upload")
        if tm_file:
            if st.button("Import TM", type="primary"):
                tmp = f"/tmp/tm_import_{tm_file.name}"
                with open(tmp, "wb") as f:
                    f.write(tm_file.read())

                progress = st.progress(0.0)
                status = st.empty()
                status.text("Importing TM…")

                try:
                    from importers.tm_importer import import_tm_from_excel
                    result = import_tm_from_excel(tmp, progress_callback=lambda p: progress.progress(p))
                    progress.progress(1.0)
                    status.empty()
                    st.success(f"Imported **{result['inserted']:,}** TM entries ({result['skipped']} skipped).")

                    with st.spinner("Building glossary from TM…"):
                        from importers.glossary_importer import build_glossary_from_tm
                        g = build_glossary_from_tm()
                    st.success(f"Auto-built glossary: **{g['inserted']:,}** terms.")

                    with st.spinner("Seeding critical vocabulary…"):
                        from importers.seed_glossary import seed_glossary
                        seed_glossary()
                    st.success("Critical DE→NL vocabulary seeded.")

                except Exception as e:
                    st.error(f"Import failed: {e}")

    with tab3:
        st.markdown("**Import Glossary from Excel**")
        st.caption("Expects columns: source term (DE), target term (NL), optional category.")

        g_file = st.file_uploader("Glossary Excel file", type=["xlsx"], key="glossary_upload")
        if g_file:
            if st.button("Import Glossary", type="primary"):
                tmp = f"/tmp/glossary_import_{g_file.name}"
                with open(tmp, "wb") as f:
                    f.write(g_file.read())
                try:
                    from importers.glossary_importer import import_glossary_from_excel
                    result = import_glossary_from_excel(tmp)
                    st.success(f"Imported **{result['inserted']:,}** glossary terms.")
                except Exception as e:
                    st.error(f"Import failed: {e}")

    with tab4:
        st.markdown("**TF-IDF Semantic Index**")
        st.caption("Build the semantic index to enable TF-IDF matching (step 3 of pipeline).")

        from engines.semantic_matcher import get_semantic_matcher
        matcher = get_semantic_matcher()
        if matcher.is_ready:
            st.success("Semantic index is built and ready.")
        else:
            st.warning("Index not built yet. Click below to build it.")

        if st.button("Build Semantic Index", type="primary"):
            progress = st.progress(0.0)
            with st.spinner("Building TF-IDF index from TM…"):
                matcher.build_index(progress_callback=lambda p: progress.progress(p))
            progress.progress(1.0)
            st.success("Semantic index ready.")
