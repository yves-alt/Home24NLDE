import streamlit as st


def render_metric_row(metrics: list[dict]):
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            delta_html = f'<div class="metric-delta">↑ {m["delta"]}</div>' if m.get("delta") else ""
            st.markdown(
                f"""<div class="metric-card">
                    <div class="metric-value">{m["value"]}</div>
                    <div class="metric-label">{m["label"]}</div>
                    {delta_html}
                </div>""",
                unsafe_allow_html=True,
            )


def render_source_badge(source_type: str) -> str:
    map_ = {
        "TM_EXACT": ("TM Exact", "badge-tm"),
        "TM_FUZZY": ("TM Fuzzy", "badge-fuzzy"),
        "TM_PATTERN": ("TM Pattern", "badge-fuzzy"),
        "GLOSSARY": ("Glossary", "badge-glossary"),
        "CONTEXT": ("Context", "badge-glossary"),
        "AI": ("AI", "badge-ai"),
        "EMPTY": ("—", ""),
    }
    label, css = map_.get(source_type, (source_type, ""))
    return f'<span class="badge {css}">{label}</span>'
