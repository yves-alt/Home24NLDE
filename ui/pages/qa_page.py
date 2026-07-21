import streamlit as st
from engines.nl.product_name_engine import get_product_name_engine
from engines.nl.residue_gate import get_residue_gate
from engines.nl.terminology import get_terminology
from auth.session import require_permission

_TEST_COLUMNS = [
    "qualityDetail", "name", "materialDetail", "colorDetail", "deliveryScope",
    "otherMeasurements", "variantName", "textileComposition", "warningsAndSafetyInformation",
]


def render():
    require_permission("qa")

    st.markdown('<div class="section-header">QA & Validation</div>', unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["QA Validator", "Name Engine", "Residue Gate", "Terminology"])

    with tab1:
        st.markdown("Run a translation through the **real quality gate** — the same checks that "
                    "block export (German residue, model-name loss, information loss, name rules, "
                    "metadata leaks, `<br>` corruption).")
        col1, col2 = st.columns(2)
        with col1:
            source = st.text_area("German source", height=100, placeholder="Duschmatte")
        with col2:
            translation = st.text_area("Dutch translation (to validate)", height=100, placeholder="Douchematt")
        column = st.selectbox("Column profile", _TEST_COLUMNS)

        if st.button("Validate", type="primary"):
            from engines.nl.model_protector import get_model_protector
            from engines.nl.quality_gate import get_quality_gate
            from engines.nl.types import CellResult

            model_names = get_model_protector().protect(source).model_names if source else []
            cell = CellResult(
                row=1, column=column, source=source, target=translation,
                origin="HUMAN", confidence=1.0, confidence_label="TEST", model_names=model_names,
            )
            issues = get_quality_gate().check_cell(cell)

            if issues:
                st.markdown(f"**{len(issues)} issue(s) found — would block export:**")
                for issue in issues:
                    fix = f"<br>Suggested fix: <code>{issue.proposed_fix}</code>" if issue.proposed_fix else ""
                    st.markdown(
                        f'<div class="alert-warning"><strong>{issue.issue}</strong>{fix}</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    '<div class="alert-success">No QA issues found — this would pass the real export gate.</div>',
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
