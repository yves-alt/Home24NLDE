import streamlit as st
import pandas as pd
from engines.qa_engine import get_qa_engine
from engines.name_optimizer import get_name_optimizer
from engines.residue_detector import get_residue_detector
from engines.naturalness_rewriter import get_rewriter


def render():
    st.markdown('<div class="section-header">QA & Validation</div>', unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["QA Validator", "Name Optimizer", "Residue Detector", "Naturalness Rules"])

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
        st.markdown("Validate and optimize Dutch product names.")
        name = st.text_input("Product name (NL)", placeholder="Pantrykeuken Levin met keramische")
        if st.button("Optimize Name"):
            optimizer = get_name_optimizer()
            issues = optimizer.validate(name)
            optimized, actions = optimizer.optimize(name)

            if issues:
                for issue in issues:
                    st.warning(issue)
            if actions:
                st.info("Actions taken: " + "; ".join(actions))
            if optimized != name:
                st.success(f"**Before:** {name}\n\n**After:** {optimized}")
            else:
                st.success("Name is valid.")

    with tab3:
        st.markdown("Detect German residue in a Dutch translation.")
        text = st.text_area("Dutch text to check", height=80, placeholder="Sofa mit Schaumstoff")
        if st.button("Check Residue"):
            detector = get_residue_detector()
            result = detector.detect_and_clean(text, auto_fix=True)
            if result.german_residues:
                st.warning(f"German residues found: {', '.join(result.german_residues)}")
                st.success(f"**Cleaned:** {result.text}")
            elif result.hybrids:
                st.warning(f"Hybrid words found: {', '.join(result.hybrids)}")
            else:
                st.success("No residue detected.")

    with tab4:
        rewriter = get_rewriter()
        rules = rewriter.get_rules()
        st.markdown(f"**{len(rules)} naturalness rules active**")
        df = pd.DataFrame(list(rules.items()), columns=["German", "Dutch"])
        st.dataframe(df, use_container_width=True, height=400)

        with st.expander("Add naturalness rule"):
            col1, col2 = st.columns(2)
            g = col1.text_input("German pattern")
            d = col2.text_input("Dutch replacement")
            if st.button("Add Rule"):
                if g and d:
                    rewriter.add_rule(g, d)
                    st.success(f"Added: {g} → {d}")
