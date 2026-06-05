import streamlit as st
from auth.credentials import get_openai_key
from auth.session import require_permission


def render():
    require_permission("settings")

    st.markdown('<div class="section-header">Settings & Import</div>', unsafe_allow_html=True)

    # Show key status without revealing the value
    key = get_openai_key()
    if key:
        st.markdown(
            '<div class="alert-success">OpenAI API key loaded from secrets.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="alert-warning">OpenAI API key not found. '
            'Add <code>OPENAI_API_KEY</code> to your <code>.env</code> file or Streamlit secrets.</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["Import TM", "Import Glossary", "ML Index"])

    with tab1:
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

    with tab2:
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

    with tab3:
        st.markdown("**TF-IDF Semantic Index**")
        st.caption("Build the semantic index to enable TF-IDF matching (step 4 of pipeline).")

        from engines.semantic_matcher import get_semantic_matcher
        matcher = get_semantic_matcher()
        if matcher.is_ready:
            st.success("Semantic index is built and ready.")
        else:
            st.warning("Index not built yet.")

        if st.button("Build Semantic Index", type="primary"):
            progress = st.progress(0.0)
            with st.spinner("Building TF-IDF index from TM…"):
                matcher.build_index(progress_callback=lambda p: progress.progress(p))
            progress.progress(1.0)
            st.success("Semantic index ready.")
