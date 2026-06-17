import streamlit as st
from engines.qa_engine import get_qa_engine
from engines.nl.product_name_engine import get_product_name_engine
from engines.nl.residue_gate import get_residue_gate
from engines.nl.terminology import get_terminology
from auth.session import require_permission


def render():
    require_permission("qa")

    st.markdown('<div class="section-header">QA & Validation</div>', unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["QA Validator", "Name Engine", "Residue Gate", "Terminology"])

    with tab1:
        st.markdown("Test the Dutch QA engine on any translation.")
        col1, col2 = st.columns(2)
        with col1:
            source = st.text_area("German source", height=100, placeholder="Duschmatte")
        with col2:
            translation = st.text_area("Dutch translation (to validate)", height=100, placeholder="Douchematt")

        if st.button("Validate", type="primary"):
            qa = get_qa_engine()
            result = qa.validate(translation, source)

            if result.issues:
                st.markdown(f"**{len(result.issues)} issue(s) found:**")
                for issue in result.issues:
                    severity = "warning" if issue.auto_fixable else "error"
                    icon = "✓" if issue.auto_fixable else "✗"
                    st.markdown(
                        f'<div class="alert-{"success" if issue.auto_fixable else "warning"}">'
                        f'<strong>[{issue.issue_type}]</strong> '
                        f'<code>{issue.original}</code> → <code>{issue.suggestion or "(flag only)"}</code> '
                        f'{"(auto-fixed)" if issue.auto_fixable else "(manual review)"}</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown(f"**Corrected:** `{result.corrected}`")
            else:
                st.markdown(
                    '<div class="alert-success">No QA issues found. Translation looks clean.</div>',
                    unsafe_allow_html=True,
                )

    with tab2:
        st.markdown("Validate and optimize Dutch product names (40-char limit, no brackets/"
                    "commas, no forbidden endings).")
        name = st.text_input("Product name (NL)", placeholder="Mini keuken Levin met keramische")
        if st.button("Optimize Name"):
            engine = get_product_name_engine()
            issues = engine.validate(name)
            result = engine.optimize(name)

            for issue in issues:
                st.warning(issue)
            for w in result.warnings:
                st.info(w)
            if result.name != name:
                st.success(f"**Before:** {name} ({len(name)} chars)\n\n"
                           f"**After:** {result.name} ({len(result.name)} chars)")
            else:
                st.success("Name is valid.")

    with tab3:
        st.markdown("Auto-fix German residue and detect anything that survives "
                    "(export blockers).")
        text = st.text_area("Dutch text to check", height=80, placeholder="Sofa mit Milchglas")
        if st.button("Check Residue"):
            gate = get_residue_gate()
            report = gate.autofix(text)
            if report.was_fixed:
                st.success(f"**Auto-fixed:** {report.text}")
            if report.remaining:
                st.error(f"Unresolved German (would block export): {', '.join(report.remaining)}")
            elif not report.was_fixed:
                st.success("No German residue detected.")

    with tab4:
        st.markdown("Test the deterministic Home24 terminology brain on any German text.")
        term = get_terminology()
        st.caption(f"{len(term._entries)} terminology rules active.")
        text = st.text_area("German text", height=80, placeholder="Tischleuchte mit Milchglas, Eiche Nordic Dekor")
        if st.button("Apply terminology"):
            out, hits = term.apply(text)
            st.success(f"**Result ({hits} replacement(s)):** {out}")
            remaining = term.remaining_german(out)
            if remaining:
                st.warning(f"Still German: {', '.join(remaining)} — would route to GPT.")
