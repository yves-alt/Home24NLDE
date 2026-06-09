import streamlit as st
import pandas as pd
from database.database import get_connection
from engines.tm_matcher import get_matcher
from auth.session import require_permission, current_user


def render():
    require_permission("tm")
    st.markdown('<div class="section-header">Translation Memory</div>', unsafe_allow_html=True)

    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM translation_memory").fetchone()[0]
        cats = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM translation_memory GROUP BY category ORDER BY cnt DESC"
        ).fetchall()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total TM Entries", f"{total:,}")
    with c2:
        with get_connection() as conn:
            high_freq = conn.execute("SELECT COUNT(*) FROM translation_memory WHERE frequency > 10").fetchone()[0]
        st.metric("High Frequency (>10)", f"{high_freq:,}")
    with c3:
        st.metric("Categories", len(cats))

    st.markdown("---")

    # Show Import TM tab only to admin
    user = current_user()
    is_admin = user and user.role == "admin"

    if is_admin:
        tab1, tab2, tab3, tab4 = st.tabs(["Search TM", "Browse", "Test Matcher", "Import TM"])
    else:
        tab1, tab2, tab3 = st.tabs(["Search TM", "Browse", "Test Matcher"])
        tab4 = None

    with tab1:
        query = st.text_input("Search source segment", placeholder="e.g. Duschmatte, Sofa, Mehrfarbig")
        if query:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT source_segment, target_segment, frequency, category, confidence "
                    "FROM translation_memory WHERE normalized_source LIKE ? "
                    "ORDER BY frequency DESC LIMIT 50",
                    (f"%{query.lower()}%",),
                ).fetchall()
            if rows:
                df = pd.DataFrame([dict(r) for r in rows])
                st.dataframe(df, use_container_width=True, height=400)
            else:
                st.info("No matches found.")

    with tab2:
        cat_options = ["all"] + [r["category"] for r in cats]
        selected_cat = st.selectbox("Filter by category", cat_options)
        min_freq = st.slider("Minimum frequency", 0, 100, 0)

        sql = "SELECT source_segment, target_segment, frequency, category FROM translation_memory WHERE 1=1"
        params = []
        if selected_cat != "all":
            sql += " AND category=?"
            params.append(selected_cat)
        if min_freq > 0:
            sql += " AND frequency >= ?"
            params.append(min_freq)
        sql += " ORDER BY frequency DESC LIMIT 200"

        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        df = pd.DataFrame([dict(r) for r in rows])
        st.dataframe(df, use_container_width=True, height=500)

    with tab3:
        st.markdown("Test the TM matching pipeline on any German term.")
        test_input = st.text_input("German term to test", placeholder="e.g. Singleküche")
        if test_input:
            matcher = get_matcher()
            match = matcher.match(test_input)
            if match:
                c1, c2, c3 = st.columns(3)
                c1.metric("Match Type", match.match_type.value)
                c2.metric("Score", f"{match.score:.0%}")
                c3.metric("Frequency", match.frequency)
                st.success(f"**{test_input}** → **{match.target}**")
            else:
                st.warning("No TM match found — would fall back to AI.")

    if is_admin and tab4 is not None:
        with tab4:
            _render_import_tab()


def _render_import_tab():
    st.markdown("### Import Translation Memory")
    st.markdown(
        "Upload an Excel (.xlsx) or CSV (.csv) TM export. "
        "Existing entries are **never deleted** — duplicates update their frequency, "
        "new entries are inserted."
    )
    st.markdown(
        "**Expected columns:** `source` / `de-de` / `deutsch` (German) "
        "and `target` / `nl-nl` / `dutch` (Dutch). "
        "Column names are matched case-insensitively."
    )

    uploaded = st.file_uploader(
        "TM file",
        type=["xlsx", "xls", "csv"],
        key="tm_import_file",
        help="Export from SDL Trados, memoQ, or any tool that produces source/target pairs.",
    )

    if not uploaded:
        return

    st.markdown(f"**Selected file:** {uploaded.name}  ({uploaded.size:,} bytes)")

    if st.button("Import Translation Memory", type="primary", use_container_width=True):
        _run_import(uploaded)

    st.markdown("---")
    st.markdown("#### Rebuild TM cache")
    st.caption("Force-reload the in-memory TM index. Use if the TM was updated outside the app.")
    if st.button("Rebuild TM index", use_container_width=True):
        matcher = get_matcher()
        matcher.reload()
        with get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM translation_memory").fetchone()[0]
        st.success(f"TM index rebuilt. {count:,} entries loaded.")


def _run_import(uploaded):
    from importers.tm_importer import import_tm_from_bytes

    file_bytes = uploaded.getvalue()
    progress = st.progress(0.0)
    status = st.empty()

    try:
        status.text("Parsing file…")

        def cb(p):
            progress.progress(min(p, 1.0))
            status.text(f"Processing… {p:.0%}")

        stats = import_tm_from_bytes(file_bytes, uploaded.name, progress_callback=cb)
        progress.progress(1.0)
        status.empty()

        st.success(
            f"Import complete — "
            f"**{stats['inserted']:,} new entries** inserted, "
            f"**{stats['updated']:,} updated** (frequency bump), "
            f"**{stats['duplicates']:,} duplicates** skipped, "
            f"**{stats['invalid']:,} invalid rows** ignored "
            f"(out of {stats['total']:,} total rows)."
        )

        # Refresh stats
        with get_connection() as conn:
            new_total = conn.execute("SELECT COUNT(*) FROM translation_memory").fetchone()[0]
        st.info(f"TM now contains **{new_total:,}** entries. Pipeline will use them immediately.")

    except ValueError as e:
        status.empty()
        st.error(f"Import failed: {e}")
    except Exception as e:
        status.empty()
        st.error(f"Unexpected error during import: {e}")
