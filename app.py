import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(override=False)  # .env → os.environ; Streamlit secrets take precedence

import streamlit as st

st.set_page_config(
    page_title="Home24 DE→NL Localization",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.styling.theme import CUSTOM_CSS
from database.migrations import run_migrations

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Init DB on first run
if "db_initialized" not in st.session_state:
    run_migrations()
    st.session_state["db_initialized"] = True

# Sidebar navigation
with st.sidebar:
    st.markdown(
        """
        <div style="padding: 1rem 0 0.5rem 0;">
            <div style="font-size: 1rem; font-weight: 700; color: #1E3A5F; letter-spacing: -0.02em;">
                Home24 DE→NL
            </div>
            <div style="font-size: 0.7rem; color: #94A3B8; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.08em;">
                Localization Platform
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    st.markdown("### Navigation")

    pages = {
        "Dashboard": "dashboard",
        "Translate": "translate",
        "Translation Memory": "tm",
        "Glossary": "glossary",
        "QA Tools": "qa",
        "Settings": "settings",
    }

    if "page" not in st.session_state:
        st.session_state["page"] = "dashboard"

    for label, key in pages.items():
        icon_map = {
            "dashboard": "📊",
            "translate": "🔄",
            "tm": "📚",
            "glossary": "📖",
            "qa": "✅",
            "settings": "⚙️",
        }
        active = st.session_state["page"] == key
        if st.sidebar.button(
            f"{icon_map.get(key, '')}  {label}",
            key=f"nav_{key}",
            use_container_width=True,
            type="primary" if active else "secondary",
        ):
            st.session_state["page"] = key
            st.rerun()

    st.markdown("---")

    from database.database import get_stats
    try:
        stats = get_stats()
        st.markdown(
            f"""
            <div style="font-size: 0.7rem; color: #94A3B8; padding: 0 0.25rem;">
                <div>TM: <strong>{stats['tm_entries']:,}</strong> entries</div>
                <div>Glossary: <strong>{stats['glossary_terms']:,}</strong> terms</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception:
        pass

# Page routing
page = st.session_state.get("page", "dashboard")

if page == "dashboard":
    from ui.pages.dashboard_page import render
    render()
elif page == "translate":
    from ui.pages.translate_page import render
    render()
elif page == "tm":
    from ui.pages.tm_page import render
    render()
elif page == "glossary":
    from ui.pages.glossary_page import render
    render()
elif page == "qa":
    from ui.pages.qa_page import render
    render()
elif page == "settings":
    from ui.pages.settings_page import render
    render()
