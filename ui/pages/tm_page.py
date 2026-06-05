import streamlit as st
import pandas as pd
from database.database import get_connection
from engines.tm_matcher import get_matcher
from auth.session import require_permission


def render():
    require_permission("tm")
    st.markdown('<div class="section-header">Translation Memory</div>', unsafe_allow_html=True)

    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM translation_memory").fetchone()[0]
        cats = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM translation_memory GROUP BY category ORDER BY cnt DESC"
        ).fetchall()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total TM Entries", f"{total:,}")
    with col2:
        with get_connection() as conn:
            high_freq = conn.execute("SELECT COUNT(*) FROM translation_memory WHERE frequency > 10").fetchone()[0]
        st.metric("High Frequency (>10)", f"{high_freq:,}")
    with col3:
        st.metric("Categories", len(cats))

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["Search TM", "Browse", "Test Matcher"])

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
                col1, col2, col3 = st.columns(3)
                col1.metric("Match Type", match.match_type.value)
                col2.metric("Score", f"{match.score:.0%}")
                col3.metric("Frequency", match.frequency)
                st.success(f"**{test_input}** → **{match.target}**")
            else:
                st.warning("No TM match found — would fall back to AI.")
