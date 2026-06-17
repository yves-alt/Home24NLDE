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

    tab1, tab2, tab3 = st.tabs(["Import TM", "Import Glossary", "Engine"])

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
        st.markdown("**Localization engine status**")
        st.caption("Deterministic-first pipeline: human/glossary → terminology phrases → "
                   "adaptive TM → terminology → gpt-4o (only when German remains).")

        from database.database import get_connection
        from engines.nl.gpt_client import get_gpt_client
        from engines.nl.terminology import get_terminology
        from engines.nl.adaptive_tm import get_adaptive_tm

        try:
            with get_connection() as conn:
                tm_count = conn.execute("SELECT COUNT(*) FROM translation_memory").fetchone()[0]
                gl_count = conn.execute("SELECT COUNT(*) FROM glossary WHERE active=1").fetchone()[0]
        except Exception:
            tm_count = gl_count = 0

        gpt = get_gpt_client()
        c1, c2, c3 = st.columns(3)
        c1.metric("TM entries", f"{tm_count:,}")
        c2.metric("Active glossary terms", f"{gl_count:,}")
        c3.metric("GPT model", gpt.model if gpt.available else "—")

        if gpt.available:
            st.success(f"GPT refinement active (model: {gpt.model}).")
        else:
            st.warning("No OpenAI key — deterministic mode only. Cells needing GPT are "
                       "flagged and block export.")

        st.markdown(f"Terminology rules loaded: **{len(get_terminology()._entries)}**")

        if st.button("Reload TM cache", type="primary"):
            with st.spinner("Reloading translation memory…"):
                get_adaptive_tm().reload()
            st.success("Translation memory cache reloaded.")
