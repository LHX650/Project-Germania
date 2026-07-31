"""Responsive enterprise styling for Project Germania."""

from __future__ import annotations

import streamlit as st


GLOBAL_STYLES = """
<style>
    :root {
        --pg-navy: #0b1f33;
        --pg-blue: #1f5eff;
        --pg-cyan: #58b7d6;
        --pg-ink: #142336;
        --pg-muted: #607086;
        --pg-border: #dfe6ee;
        --pg-surface: #ffffff;
        --pg-canvas: #f4f7fa;
        --pg-amber: #c98012;
    }

    .stApp {
        background:
            radial-gradient(circle at 92% 4%, rgba(31, 94, 255, 0.08), transparent 24rem),
            var(--pg-canvas);
        color: var(--pg-ink);
    }

    .block-container {
        max-width: 1600px;
        padding: 1.8rem 3rem 2rem;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #081a2d 0%, #102a44 100%);
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }

    [data-testid="stSidebar"] * {
        color: #eaf1f8;
    }

    [data-testid="stSidebarNav"] {
        display: none;
    }

    [data-testid="stSidebar"] [role="radiogroup"] label {
        border: 1px solid transparent;
        border-radius: 0.65rem;
        margin-bottom: 0.3rem;
        padding: 0.45rem 0.65rem;
        transition: background 0.15s ease, border-color 0.15s ease;
    }

    [data-testid="stSidebar"] [role="radiogroup"] label:hover {
        background: rgba(255, 255, 255, 0.07);
        border-color: rgba(255, 255, 255, 0.12);
    }

    .sidebar-brand {
        align-items: center;
        display: flex;
        gap: 0.8rem;
        margin: 0.35rem 0 2rem;
    }

    .sidebar-brand-mark {
        align-items: center;
        background: linear-gradient(135deg, #2f72ff, #55bfd7);
        border-radius: 0.7rem;
        box-shadow: 0 8px 24px rgba(31, 94, 255, 0.24);
        display: flex;
        font-size: 0.75rem;
        font-weight: 800;
        height: 2.5rem;
        justify-content: center;
        letter-spacing: 0.08em;
        width: 2.5rem;
    }

    .sidebar-brand-name {
        font-size: 0.98rem;
        font-weight: 700;
    }

    .sidebar-brand-caption,
    .sidebar-status-meta {
        color: #91a7bd !important;
        font-size: 0.72rem;
        margin-top: 0.15rem;
    }

    .sidebar-section-label {
        color: #7f98b1 !important;
        font-size: 0.66rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        margin: 0.5rem 0 0.7rem;
        text-transform: uppercase;
    }

    .sidebar-status-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 0.75rem;
        margin-top: 2.2rem;
        padding: 0.85rem 1rem 1rem;
    }

    .sidebar-status-row {
        align-items: center;
        display: flex;
        font-size: 0.78rem;
        gap: 0.5rem;
    }

    .status-dot {
        border-radius: 999px;
        display: inline-block;
        height: 0.5rem;
        width: 0.5rem;
    }

    .status-dot-amber {
        background: #f2b84b;
        box-shadow: 0 0 0 4px rgba(242, 184, 75, 0.12);
    }

    .project-header {
        align-items: center;
        background: linear-gradient(120deg, #0a1f34 0%, #12385b 72%, #175070 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 1rem;
        box-shadow: 0 18px 50px rgba(13, 35, 57, 0.14);
        display: flex;
        justify-content: space-between;
        margin-bottom: 2rem;
        min-height: 9rem;
        overflow: hidden;
        padding: 1.7rem 2rem;
        position: relative;
    }

    .project-header::after {
        border: 1px solid rgba(108, 197, 222, 0.25);
        border-radius: 50%;
        content: "";
        height: 12rem;
        position: absolute;
        right: -3rem;
        top: -6rem;
        width: 12rem;
    }

    .project-eyebrow,
    .page-kicker,
    .foundation-label,
    .planned-card-label {
        color: var(--pg-blue);
        font-size: 0.67rem;
        font-weight: 800;
        letter-spacing: 0.14em;
    }

    .project-eyebrow {
        color: #75c7de;
    }

    .project-header h1 {
        color: #ffffff;
        font-size: clamp(1.8rem, 3vw, 2.55rem);
        letter-spacing: -0.03em;
        margin: 0.35rem 0 0.2rem;
    }

    .project-header p {
        color: #b7c8d8;
        margin: 0;
    }

    .project-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
        justify-content: flex-end;
        position: relative;
        z-index: 1;
    }

    .badge {
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 0.45rem 0.75rem;
    }

    .badge-phase {
        background: rgba(79, 139, 255, 0.18);
        border: 1px solid rgba(117, 166, 255, 0.45);
        color: #dce8ff;
    }

    .badge-pending {
        background: rgba(242, 184, 75, 0.12);
        border: 1px solid rgba(242, 184, 75, 0.35);
        color: #ffdc99;
    }

    .page-heading {
        margin: 0 0 1.3rem;
    }

    .page-heading h2 {
        color: var(--pg-ink);
        font-size: clamp(1.55rem, 2.4vw, 2.15rem);
        letter-spacing: -0.025em;
        margin: 0.3rem 0 0.35rem;
    }

    .page-heading p {
        color: var(--pg-muted);
        font-size: 0.98rem;
        margin: 0;
        max-width: 58rem;
    }

    .foundation-panel {
        align-items: center;
        background: var(--pg-surface);
        border: 1px solid var(--pg-border);
        border-radius: 0.9rem;
        display: flex;
        gap: 1.1rem;
        margin-bottom: 1rem;
        min-height: 8rem;
        padding: 1.25rem 1.4rem;
    }

    .foundation-icon {
        align-items: center;
        background: linear-gradient(145deg, #eaf1ff, #e8f7fb);
        border: 1px solid #cfddf1;
        border-radius: 0.8rem;
        color: var(--pg-blue);
        display: flex;
        flex: 0 0 3.4rem;
        font-size: 0.84rem;
        font-weight: 800;
        height: 3.4rem;
        justify-content: center;
    }

    .foundation-panel h3 {
        color: var(--pg-ink);
        font-size: 1.14rem;
        margin: 0.25rem 0 0.3rem;
    }

    .foundation-panel p {
        color: var(--pg-muted);
        margin: 0;
        max-width: 60rem;
    }

    .planned-card {
        background: rgba(255, 255, 255, 0.74);
        border: 1px solid var(--pg-border);
        border-radius: 0.8rem;
        margin-bottom: 0.8rem;
        min-height: 6.6rem;
        padding: 1rem 1.05rem;
    }

    .planned-card-title {
        color: var(--pg-ink);
        font-size: 0.96rem;
        font-weight: 700;
        margin: 0.35rem 0 0.4rem;
    }

    .planned-card-meta {
        color: var(--pg-muted);
        font-size: 0.76rem;
    }

    .dashboard-footer {
        align-items: center;
        border-top: 1px solid var(--pg-border);
        color: var(--pg-muted);
        display: flex;
        flex-wrap: wrap;
        font-size: 0.72rem;
        gap: 0.85rem 1.5rem;
        justify-content: space-between;
        margin-top: 2.8rem;
        padding: 1rem 0 0.2rem;
    }

    @media (max-width: 900px) {
        .block-container {
            padding: 1.2rem 1.1rem 1.5rem;
        }

        .project-header {
            align-items: flex-start;
            flex-direction: column;
            gap: 1.25rem;
            padding: 1.35rem;
        }

        .project-badges {
            justify-content: flex-start;
        }
    }

    @media (max-width: 640px) {
        .foundation-panel {
            align-items: flex-start;
        }

        .dashboard-footer {
            align-items: flex-start;
            flex-direction: column;
        }
    }
</style>
"""


def apply_global_styles() -> None:
    """Inject the shared responsive dashboard CSS."""

    st.markdown(GLOBAL_STYLES, unsafe_allow_html=True)
