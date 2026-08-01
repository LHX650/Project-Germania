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
        background: var(--pg-canvas);
        color: var(--pg-ink);
    }

    .block-container {
        max-width: 1520px;
        padding: 1.65rem 2.5rem 2rem;
    }

    [data-testid="stSidebar"] {
        background: #0b2238;
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
        background: #2f72ff;
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

    .status-dot-green {
        background: #4ecb8d;
        box-shadow: 0 0 0 4px rgba(78, 203, 141, 0.12);
    }

    .project-header {
        align-items: center;
        background: #0b2b46;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 1rem;
        box-shadow: 0 12px 30px rgba(13, 35, 57, 0.12);
        display: flex;
        justify-content: space-between;
        margin-bottom: 2rem;
        min-height: 8.25rem;
        overflow: hidden;
        padding: 1.7rem 2rem;
        position: relative;
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

    .badge-connected {
        background: rgba(78, 203, 141, 0.14);
        border: 1px solid rgba(78, 203, 141, 0.38);
        color: #bff4d8;
    }

    .page-heading {
        margin: 0 0 1.15rem;
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

    .data-provenance {
        align-items: center;
        background: #edf4ff;
        border: 1px solid #d3e2f7;
        border-radius: 0.7rem;
        color: #40546c;
        display: flex;
        flex-wrap: wrap;
        font-size: 0.78rem;
        gap: 0.6rem 1.4rem;
        margin-bottom: 0.35rem;
        padding: 0.7rem 0.9rem;
    }

    .data-provenance strong {
        color: #17314d;
        margin-right: 0.25rem;
    }

    [data-testid="stMetric"] {
        background: var(--pg-surface);
        border: 1px solid var(--pg-border);
        border-radius: 0.8rem;
        min-height: 6.5rem;
        padding: 0.8rem 0.95rem;
    }

    [data-testid="stMetric"] [data-testid="stMetricLabel"] {
        color: var(--pg-muted);
        font-size: 0.78rem;
        font-weight: 600;
    }

    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: var(--pg-ink);
        letter-spacing: -0.025em;
    }

    [data-testid="stDataFrame"] {
        border: 1px solid var(--pg-border);
        border-radius: 0.75rem;
        overflow: hidden;
    }

    .insight-card {
        background: var(--pg-surface);
        border: 1px solid #d7e3f2;
        border-radius: 0.85rem;
        box-shadow: 0 6px 18px rgba(17, 48, 79, 0.05);
        margin-bottom: 1rem;
        min-height: 9.2rem;
        padding: 1rem 1.1rem;
    }

    .insight-card-label,
    .score-label {
        color: var(--pg-blue);
        font-size: 0.64rem;
        font-weight: 800;
        letter-spacing: 0.12em;
    }

    .insight-card-title {
        color: var(--pg-ink);
        font-weight: 750;
        margin-top: 0.45rem;
    }

    .insight-card-value {
        color: #102f50;
        font-size: 2rem;
        font-weight: 800;
        line-height: 1.1;
        margin-top: 0.45rem;
    }

    .insight-card-meta {
        color: var(--pg-muted);
        font-size: 0.75rem;
        margin-top: 0.5rem;
    }

    .score-panel {
        align-items: center;
        background: #123653;
        border-radius: 0.85rem;
        display: flex;
        justify-content: space-between;
        margin: 1.2rem 0 0.75rem;
        padding: 1.1rem 1.3rem;
    }

    .score-title {
        color: #f1f6fb;
        font-size: 1.05rem;
        font-weight: 700;
        margin-top: 0.3rem;
    }

    .score-value {
        color: #ffffff;
        font-size: 2.2rem;
        font-weight: 850;
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
        background: #edf4ff;
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

        .data-provenance {
            align-items: flex-start;
            flex-direction: column;
        }
    }

    @media (max-width: 420px) {
        .block-container {
            padding: 0.8rem 0.7rem 1.2rem;
        }

        .project-header {
            gap: 0.85rem;
            margin-bottom: 1.25rem;
            min-height: auto;
            padding: 1rem;
        }

        .project-header h1 {
            font-size: 1.55rem;
        }

        .project-header p,
        .page-heading p {
            font-size: 0.86rem;
        }

        .project-badges {
            gap: 0.35rem;
        }

        .badge {
            font-size: 0.64rem;
            padding: 0.35rem 0.55rem;
        }

        .page-heading h2 {
            font-size: 1.45rem;
        }

        [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
        }

        [data-testid="stHorizontalBlock"] > div,
        [data-testid="column"] {
            flex: 1 1 100% !important;
            min-width: 100% !important;
            width: 100% !important;
        }

        [data-testid="stMetric"] {
            min-height: 5.8rem;
        }

        .insight-card {
            min-height: auto;
        }

        .score-panel {
            align-items: flex-start;
            flex-direction: column;
            gap: 0.75rem;
        }

        .score-value {
            font-size: 1.9rem;
        }
    }
</style>
"""


def apply_global_styles() -> None:
    """Inject the shared responsive dashboard CSS."""

    st.markdown(GLOBAL_STYLES, unsafe_allow_html=True)
