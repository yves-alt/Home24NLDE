import streamlit as st
from auth.session import login, is_authenticated


def render_login():
    """Full-page login form. Returns True once the user is authenticated."""
    if is_authenticated():
        return True

    _, col, _ = st.columns([1, 1.6, 1])

    with col:
        st.markdown(
            """
            <div style="text-align:center; padding: 2.5rem 0 1.5rem 0;">
                <div style="font-size: 1.5rem; font-weight: 700; color: #1E3A5F; letter-spacing: -0.03em;">
                    Home24 DE → NL
                </div>
                <div style="font-size: 0.8rem; color: #94A3B8; margin-top: 4px;
                            text-transform: uppercase; letter-spacing: 0.1em;">
                    Localization Platform
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form", clear_on_submit=False):
            st.markdown(
                '<div style="font-weight:600; color:#1E293B; margin-bottom:0.25rem;">Sign in</div>',
                unsafe_allow_html=True,
            )
            email = st.text_input("Email", placeholder="you@home24.de", label_visibility="collapsed")
            password = st.text_input("Password", type="password", placeholder="Password", label_visibility="collapsed")
            submitted = st.form_submit_button("Sign in", use_container_width=True, type="primary")

        if submitted:
            if not email or not password:
                st.warning("Please enter your email and password.")
            elif login(email, password):
                st.rerun()
            else:
                st.error("Invalid email or password.")

        st.markdown(
            '<div style="text-align:center; color:#CBD5E1; font-size:0.7rem; margin-top:2rem;">Home24 internal tool</div>',
            unsafe_allow_html=True,
        )

    return is_authenticated()
