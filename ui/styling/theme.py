CUSTOM_CSS = """
<style>
/* ─── Base ─── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* ─── Hide Streamlit chrome ─── */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

/* ─── App background ─── */
.stApp {
    background: #F8FAFC;
}

/* ─── Top nav bar ─── */
.top-nav {
    background: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    padding: 0 2rem;
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 999;
    margin-bottom: 1.5rem;
}

.nav-logo {
    font-size: 1.1rem;
    font-weight: 700;
    color: #1E3A5F;
    letter-spacing: -0.02em;
}

.nav-badge {
    background: #EBF5FB;
    color: #1E3A5F;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* ─── Sidebar ─── */
.css-1d391kg, [data-testid="stSidebar"] {
    background: #FFFFFF;
    border-right: 1px solid #E2E8F0;
}

[data-testid="stSidebar"] .stMarkdown h3 {
    color: #64748B;
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-top: 1.2rem;
    margin-bottom: 0.4rem;
}

/* ─── Cards ─── */
.card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
}

.card-sm {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 1rem 1.25rem;
}

/* ─── Metric cards ─── */
.metric-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    text-align: center;
}

.metric-value {
    font-size: 2rem;
    font-weight: 700;
    color: #1E3A5F;
    line-height: 1;
}

.metric-label {
    font-size: 0.75rem;
    color: #94A3B8;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-top: 0.3rem;
}

.metric-delta {
    font-size: 0.8rem;
    color: #22C55E;
    margin-top: 0.2rem;
}

/* ─── Status badges ─── */
.badge {
    display: inline-block;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.72rem;
    font-weight: 600;
}

.badge-tm { background: #DCFCE7; color: #15803D; }
.badge-fuzzy { background: #FEF9C3; color: #854D0E; }
.badge-ai { background: #FCE7F3; color: #9D174D; }
.badge-glossary { background: #EDE9FE; color: #5B21B6; }

/* ─── Progress bar ─── */
.stProgress > div > div > div > div {
    background-color: #3B82F6;
    border-radius: 99px;
}

/* ─── Buttons ─── */
.stButton > button {
    border-radius: 8px;
    font-weight: 500;
    font-size: 0.875rem;
    transition: all 0.15s;
    border: 1px solid #E2E8F0;
}

.stButton > button[kind="primary"] {
    background: #1E3A5F;
    color: #FFFFFF;
    border-color: #1E3A5F;
}

.stButton > button[kind="primary"]:hover {
    background: #15304F;
    border-color: #15304F;
}

/* ─── File uploader ─── */
[data-testid="stFileUploader"] {
    border: 2px dashed #CBD5E1;
    border-radius: 12px;
    padding: 1.5rem;
    background: #F8FAFC;
    transition: border-color 0.2s;
}

[data-testid="stFileUploader"]:hover {
    border-color: #3B82F6;
}

/* ─── Tables ─── */
.stDataFrame {
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    overflow: hidden;
}

/* ─── Tabs ─── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 2px solid #E2E8F0;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    font-weight: 500;
    font-size: 0.875rem;
    padding: 0.5rem 1rem;
    color: #64748B;
}

.stTabs [aria-selected="true"] {
    color: #1E3A5F;
    border-bottom: 2px solid #1E3A5F;
}

/* ─── Section headers ─── */
.section-header {
    font-size: 1.1rem;
    font-weight: 600;
    color: #1E293B;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #F1F5F9;
}

/* ─── Alert boxes ─── */
.alert-success {
    background: #F0FDF4;
    border: 1px solid #BBF7D0;
    border-left: 4px solid #22C55E;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    color: #15803D;
    font-size: 0.875rem;
}

.alert-warning {
    background: #FFFBEB;
    border: 1px solid #FDE68A;
    border-left: 4px solid #F59E0B;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    color: #92400E;
    font-size: 0.875rem;
}

.alert-info {
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-left: 4px solid #3B82F6;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    color: #1D4ED8;
    font-size: 0.875rem;
}
</style>
"""
