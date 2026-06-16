import streamlit as st


def apply_global_styles(max_width: int | None = 1500) -> None:
    max_width_rule = f"max-width: {max_width}px;" if max_width else ""

    st.markdown(
        f"""
<style>
.block-container {{
    {max_width_rule}
    padding-top: 2rem;
    padding-bottom: 2rem;
}}

.main-title {{
    font-size: 2.1rem;
    font-weight: 800;
    color: #0f1f3d;
    margin-bottom: 0.3rem;
}}

.sub-title {{
    font-size: 1rem;
    color: #667085;
    margin-bottom: 1.8rem;
}}

.card {{
    background-color: white;
    border: 1px solid #e5eaf2;
    border-radius: 16px;
    padding: 1.4rem;
    box-shadow: 0 4px 14px rgba(15, 31, 61, 0.06);
}}

.step-wrap {{
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    margin-top: 1rem;
}}

.step-item {{
    flex: 1;
    text-align: center;
}}

.step-circle {{
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: #eaf2ff;
    color: #2563eb;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    margin: 0 auto 0.6rem auto;
    border: 1px solid #bfdbfe;
}}

.step-title {{
    text-align: center;
    font-weight: 800;
    color: #1f2937;
    margin-top: 0.6rem;
    margin-bottom: 0.25rem;
}}

.step-desc {{
    text-align: center;
    font-size: 0.85rem;
    color: #667085;
}}

.summary-box {{
    background: #f8fbff;
    border: 1px solid #dbeafe;
    border-radius: 14px;
    padding: 1.1rem;
    margin-bottom: 1rem;
}}

.keyword {{
    display: inline-block;
    background: #f3e8ff;
    color: #7e22ce;
    padding: 0.3rem 0.7rem;
    border-radius: 999px;
    margin-right: 0.4rem;
    margin-bottom: 0.4rem;
    font-size: 0.85rem;
    font-weight: 600;
}}

.start-area {{
    max-width: 520px;
    margin: 1.5rem auto 0 auto;
}}

div.stButton > button {{
    height: 3.2rem;
    border-radius: 12px;
    font-weight: 800;
    font-size: 1rem;
}}
</style>
""",
        unsafe_allow_html=True,
    )
