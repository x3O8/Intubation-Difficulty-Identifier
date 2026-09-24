from __future__ import annotations
import json, uuid
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from airway import LIMITATION
from airway.db import initialize, transaction
from airway.ingest import import_mapping, materialize_confirmed, delete_case, now, propose_sequential_triplets
from airway.reports import export_case
from airway.review import save_revision
from airway.ui.components import point_editor, state_badge
from airway.video import sha256_file
from airway.analysis import analyze_clip, review_intervals
from airway.aggregate import summarize_case_measurements
from airway.prototype import relative_opening_band

DB=Path("data/airway.sqlite3")
initialize(DB)
st.set_page_config(page_title="Airway Evidence Review",page_icon="◌",layout="wide")

# ---------------------------------------------------------------------------
# DESIGN SYSTEM — CSS injection (DESIGN.md: warm apothecary journal)
# ---------------------------------------------------------------------------
# Font imports
st.markdown("""<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400&family=Playfair+Display:ital,wght@0,400;1,300;1,400&display=swap" rel="stylesheet">""", unsafe_allow_html=True)

# Design system tokens and global styles
st.markdown("""<style>
:root {
    --color-terracotta-seal: #b05a36;
    --gradient-terracotta-seal: linear-gradient(116deg, rgb(176, 90, 54), rgb(212, 166, 142));
    --color-parchment: #fef9ef;
    --color-aged-paper: #f5eee1;
    --color-warm-taupe: #d1c9bf;
    --color-ink: #2a2b2f;
    --color-charcoal: #333333;
    --color-graphite: #515151;
    --color-ash: #808988;
    --font-display: 'Playfair Display', Georgia, 'Times New Roman', serif;
    --font-body: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --font-mono: 'JetBrains Mono', 'Consolas', monospace;
    --radius-cards: 24px;
    --radius-buttons: 40px;
    --radius-pills: 9999px;
    --radius-inputs: 9999px;
    --shadow-lg: rgba(0, 0, 0, 0.15) 0px 0px 20px 0px;
    --shadow-xl: rgba(42, 43, 47, 0.1) 12px 32px 80px 0px;
}
.stApp, .main, [data-testid="stAppViewContainer"] {
    background-color: var(--color-parchment) !important;
}
.block-container { padding-top: 2rem; max-width: 1280px; }
html, body, .stApp,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] span {
    font-family: var(--font-body) !important;
    letter-spacing: -0.023em;
    color: var(--color-ink);
}
[data-testid="stSidebar"] {
    background: var(--color-aged-paper) !important;
    border-right: 1px solid var(--color-warm-taupe) !important;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span {
    font-family: var(--font-body) !important;
    color: var(--color-ink);
}
[data-testid="stSidebar"] hr { border-color: var(--color-warm-taupe); opacity: 0.5; }
h1, h2, h3 {
    font-family: var(--font-display) !important;
    color: var(--color-ink) !important;
}
h1 { font-weight: 400 !important; }
h2 { font-weight: 400 !important; font-size: 1.8rem !important; }
h3 { font-weight: 400 !important; font-size: 1.3rem !important; }
hr { border-color: var(--color-warm-taupe) !important; opacity: 0.6; }
.stCaption, [data-testid="stCaptionContainer"] {
    color: var(--color-graphite) !important;
    font-size: 13px !important;
}
</style>""", unsafe_allow_html=True)

# Component styles
st.markdown("""<style>
.hero-card {
    background: var(--color-aged-paper);
    border: 1px solid var(--color-warm-taupe);
    border-radius: var(--radius-cards);
    padding: 2.5rem 2.2rem 2rem;
    margin-bottom: 1.5rem;
}
.hero-card .eyebrow {
    font-family: var(--font-mono);
    font-size: 11px;
    text-transform: uppercase;
    color: var(--color-terracotta-seal);
    font-weight: 600;
    letter-spacing: 0.04em;
    margin-bottom: 0.5rem;
}
.hero-card h1 {
    font-family: var(--font-display) !important;
    font-size: 2.6rem;
    font-weight: 400;
    line-height: 1.1;
    color: var(--color-ink) !important;
    margin: 0 0 0.6rem 0;
}
.hero-card h1 em { font-weight: 300; font-style: italic; }
.hero-card .subtitle {
    font-family: var(--font-body);
    font-size: 16px;
    font-weight: 400;
    color: var(--color-graphite);
    line-height: 1.5;
    letter-spacing: -0.37px;
}
.stButton > button, .stFormSubmitButton > button {
    border-radius: var(--radius-buttons) !important;
    font-family: var(--font-body) !important;
    font-weight: 600 !important;
    letter-spacing: -0.023em !important;
    transition: all 0.2s ease !important;
}
.stButton > button[kind="primary"], .stFormSubmitButton > button {
    background: var(--color-terracotta-seal) !important;
    color: white !important;
    border: none !important;
}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button:hover {
    background: #9a4e2f !important;
    box-shadow: var(--shadow-lg) !important;
}
.stButton > button[kind="secondary"] {
    background: transparent !important;
    border: 1.5px solid var(--color-terracotta-seal) !important;
    color: var(--color-terracotta-seal) !important;
}
.stButton > button[kind="secondary"]:hover {
    background: rgba(176, 90, 54, 0.06) !important;
}
.stDownloadButton > button {
    border-radius: var(--radius-buttons) !important;
    font-family: var(--font-body) !important;
    font-weight: 600 !important;
    border: 1.5px solid var(--color-terracotta-seal) !important;
    color: var(--color-terracotta-seal) !important;
    background: transparent !important;
}
.stDownloadButton > button:hover {
    background: rgba(176, 90, 54, 0.06) !important;
}
div[data-testid="stMetric"] {
    background: var(--color-aged-paper);
    border: 1px solid var(--color-warm-taupe);
    border-radius: var(--radius-cards);
    padding: 1.2rem 1.4rem;
}
div[data-testid="stMetric"] label {
    font-family: var(--font-body) !important;
    color: var(--color-graphite) !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.02em;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-family: var(--font-display) !important;
    color: var(--color-ink) !important;
    font-weight: 400 !important;
}
</style>""", unsafe_allow_html=True)

# UI element styles
st.markdown("""<style>
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 2px solid var(--color-warm-taupe);
}
.stTabs [data-baseweb="tab"] {
    font-family: var(--font-body) !important;
    font-weight: 600;
    font-size: 14px;
    letter-spacing: -0.023em;
    color: var(--color-graphite);
    border-bottom: 3px solid transparent;
    padding: 0.7rem 1.2rem;
    transition: all 0.2s ease;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--color-ink); }
.stTabs [aria-selected="true"] {
    color: var(--color-terracotta-seal) !important;
    border-bottom-color: var(--color-terracotta-seal) !important;
}
.stTabs [data-baseweb="tab-highlight"] { background-color: var(--color-terracotta-seal) !important; }
.stTabs [data-baseweb="tab-border"] { background-color: var(--color-warm-taupe) !important; }
.streamlit-expanderHeader {
    font-family: var(--font-body) !important;
    font-weight: 600 !important;
    font-size: 15px !important;
    color: var(--color-ink) !important;
}
[data-testid="stExpander"] {
    border: 1px solid var(--color-warm-taupe) !important;
    border-radius: var(--radius-cards) !important;
    background: var(--color-parchment) !important;
}
.stTextInput > div > div, .stNumberInput > div > div,
.stSelectbox > div > div, .stMultiSelect > div > div,
.stTextArea > div > div {
    border-radius: 12px !important;
    border-color: var(--color-ash) !important;
}
.stTextInput > div > div:focus-within, .stNumberInput > div > div:focus-within,
.stSelectbox > div > div:focus-within, .stMultiSelect > div > div:focus-within,
.stTextArea > div > div:focus-within {
    border-color: var(--color-terracotta-seal) !important;
    box-shadow: 0 0 0 3px rgba(176, 90, 54, 0.15) !important;
}
[data-testid="stForm"] {
    border: 1px solid var(--color-warm-taupe) !important;
    border-radius: var(--radius-cards) !important;
    background: var(--color-aged-paper) !important;
    padding: 1.5rem !important;
}
div[data-testid="stAlert"] { border-radius: 16px !important; font-family: var(--font-body) !important; }
.stDataFrame { border-radius: 12px !important; overflow: hidden; }
.stCheckbox label span, .stRadio label span { font-family: var(--font-body) !important; }
.stLinkButton > a { color: var(--color-terracotta-seal) !important; font-weight: 600 !important; }
.stProgress > div > div > div { background: var(--gradient-terracotta-seal) !important; }
[data-testid="stSidebar"] .stSelectbox > label {
    font-family: var(--font-body) !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    color: var(--color-graphite) !important;
}
.stSlider [data-baseweb="slider"] [role="slider"] {
    background: var(--color-terracotta-seal) !important;
}
.sidebar-brand {
    padding: 1.2rem 1rem 0.8rem;
    border-bottom: 1px solid var(--color-warm-taupe);
    margin-bottom: 0.8rem;
}
.sidebar-brand h2 {
    font-family: var(--font-display) !important;
    font-size: 1.5rem !important;
    font-weight: 400 !important;
    color: var(--color-ink) !important;
    margin: 0 !important;
    line-height: 1.2 !important;
}
.sidebar-brand .brand-sub {
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--color-ash);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-top: 0.3rem;
}
.nav-section {
    font-family: var(--font-mono);
    font-size: 10px;
    text-transform: uppercase;
    color: var(--color-ash);
    letter-spacing: 0.06em;
    padding: 1rem 1rem 0.3rem;
    font-weight: 400;
}
</style>""", unsafe_allow_html=True)

# Sidebar vertical navigation tabs CSS
st.markdown("""<style>
/* Hide sidebar scrollbars */
[data-testid="stSidebar"] > div:first-child {
    overflow-y: hidden !important;
    overflow-x: hidden !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
    padding-top: 1rem !important;
    padding-bottom: 1rem !important;
}
/* Hide widget label (empty box above options) */
[data-testid="stSidebar"] [data-testid="stRadio"] > label,
[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stWidgetLabel"] {
    display: none !important;
}
/* Hide standard radio circles */
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label > div:first-child {
    display: none !important;
}
/* Style option labels as clean segmented vertical tabs */
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label {
    display: flex !important;
    align-items: center !important;
    padding: 0.65rem 0.9rem !important;
    border-radius: 10px !important;
    margin-bottom: 0.4rem !important;
    cursor: pointer !important;
    background: var(--color-parchment) !important;
    border: 1px solid var(--color-warm-taupe) !important;
    transition: all 0.15s ease !important;
    width: 100% !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:hover {
    background: #f2e9dc !important;
    border-color: var(--color-terracotta-seal) !important;
}
/* Active selected tab styling */
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked),
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] [aria-checked="true"] {
    background: rgba(176, 90, 54, 0.10) !important;
    border: 1.5px solid var(--color-terracotta-seal) !important;
    border-left: 4px solid var(--color-terracotta-seal) !important;
    box-shadow: 0 2px 4px rgba(176, 90, 54, 0.08) !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label [data-testid="stMarkdownContainer"] p {
    font-family: var(--font-body) !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    color: var(--color-charcoal) !important;
    margin: 0 !important;
    letter-spacing: -0.015em !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) [data-testid="stMarkdownContainer"] p {
    color: var(--color-terracotta-seal) !important;
    font-weight: 600 !important;
}
</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# SIDEBAR — branded navigation
# ---------------------------------------------------------------------------
PAGES = {
    "Research workspace":   "🩺  Clinical Review",
    "Cases":                "📋  Patient Intake",
}

with st.sidebar:
    st.markdown("""
    <div class="sidebar-brand">
        <h2>Airway <em>Studio</em></h2>
        <div class="brand-sub">Evidence Review · v0.1</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="nav-section">Workflow</div>', unsafe_allow_html=True)
    page = st.radio(
        "Navigate",
        list(PAGES.keys()),
        format_func=lambda k: PAGES[k],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("Local processing · No network access")
    st.caption("Research prototype — not for clinical decisions")

# ---------------------------------------------------------------------------
# HERO
# ---------------------------------------------------------------------------
st.markdown("""
<div class="hero-card">
    <div class="eyebrow">Airway Research Studio</div>
    <h1>Video Evidence, Measurement <em>Review</em></h1>
    <div class="subtitle">Traceable research findings from local video analysis. No data leaves this machine.</div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# PAGE ROUTING (all backend logic preserved identically)
# ---------------------------------------------------------------------------
if page=='Research workspace':
    from airway.ui.research_workspace import workspace
    workspace(DB)
    st.stop()

def rows(query,args=()):
    with transaction(DB) as conn: return [dict(x) for x in conn.execute(query,args)]

if page=="Inventory & assignment":
    st.header("Inventory and Assignment")
    vids=rows("SELECT v.id video_uuid,v.relative_path,v.sha256,v.bytes,v.decode_status,a.participant_id,a.status assignment_status,a.camera_view,a.maneuver FROM videos v JOIN assignments a ON a.video_id=v.id AND a.active=1 ORDER BY v.relative_path")
    a,b,c,d=st.columns(4); a.metric("Inventoried clips",len(vids)); b.metric("Confirmed",sum(x["assignment_status"]=="confirmed" for x in vids)); c.metric("Provisional",sum(x["assignment_status"]=="provisional" for x in vids)); d.metric("Unassigned",sum(x["assignment_status"]=="unassigned" for x in vids))
    if vids: st.dataframe(pd.DataFrame(vids),use_container_width=True,height=410)
    else: st.info("Run the inventory command first. No source files are modified.")
    st.subheader("Owner-declared three-video sets")
    st.caption("Use this only when the inventory is ordered as three consecutive clips per patient. It creates provisional sets from sequence only—never from facial matching—and you can relabel views before analysis.")
    if st.button("Create provisional patient sets from adjacent triples",disabled=not vids or any(x["assignment_status"]!="unassigned" for x in vids)):
        try:
            grouped=propose_sequential_triplets(DB)
            st.success(f"Created {grouped['patients']} provisional three-video patient sets. {grouped['remainder_unassigned']} clip(s) remain unassigned because they do not complete a triple.")
        except Exception as e: st.error(str(e))
    st.subheader("Import owner/reviewer mapping")
    up=st.file_uploader("CSV with relative_path or video_uuid, participant_id, assignment_status, camera_view, maneuver",type="csv")
    reviewer=st.text_input("Reviewer",value="local_reviewer")
    if up and st.button("Validate and import mapping"):
        target=Path("data/imports")/f"mapping-{uuid.uuid4()}.csv"; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(up.getvalue())
        try: st.success(f"Imported {len(import_mapping(target,DB,reviewer))} reviewed assignment revisions.")
        except Exception as e: st.error(str(e))
    confirmed=rows("SELECT id FROM participants WHERE status='confirmed' AND deleted_at IS NULL")
    if confirmed:
        pid=st.selectbox("Confirmed participant",[x["id"] for x in confirmed])
        if st.button("Copy and verify confirmed originals"):
            st.json(materialize_confirmed(pid,DB))

elif page=="Cases":
    st.header("Patient Cases")
    mode=st.radio("Case type",["Three-video patient assessment","Confirmed participant","Single-clip technical review"],horizontal=True)
    confirmed=rows("SELECT id FROM participants WHERE status='confirmed' AND deleted_at IS NULL ORDER BY id")
    if not confirmed: st.warning("Combined participant cases require owner-confirmed mappings. Single-clip technical review remains available after inventory.")
    pid=st.selectbox("Confirmed participant",[x["id"] for x in confirmed],index=None,placeholder="Select confirmed participant") if confirmed and mode=="Confirmed participant" else None
    technical_clips=rows("SELECT id,relative_path FROM videos ORDER BY relative_path") if mode in ("Single-clip technical review","Three-video patient assessment") else []
    if mode=="Three-video patient assessment":
        technical_clip=st.multiselect("Select the three clips for one patient",technical_clips,format_func=lambda x:x["relative_path"],max_selections=3)
    else:
        technical_clip=st.selectbox("Clip",technical_clips,format_func=lambda x:x["relative_path"]) if technical_clips else None
    label=st.text_input("Case label",value="Airway video review")
    ready=bool(pid) if mode=="Confirmed participant" else (len(technical_clip)==3 if mode=="Three-video patient assessment" else bool(technical_clip))
    if st.button("Create case",disabled=not ready):
        cid=str(uuid.uuid4())
        with transaction(DB) as conn:
            conn.execute("INSERT INTO cases(id,participant_id,label,created_at) VALUES(?,?,?,?)",(cid,pid,label,now()))
            if mode=="Three-video patient assessment":
                for selected in technical_clip: conn.execute("INSERT INTO segments(id,case_id,video_id,reason) VALUES(?,?,?,?)",(str(uuid.uuid4()),cid,selected["id"],"three_video_patient_assessment"))
            elif technical_clip: conn.execute("INSERT INTO segments(id,case_id,video_id,reason) VALUES(?,?,?,?)",(str(uuid.uuid4()),cid,technical_clip["id"],"single_clip_technical_review"))
        (Path("data/participants")/(pid or "unassigned")/"cases"/cid/"frames").mkdir(parents=True,exist_ok=True)
        st.success(f"Created case {cid}")
    st.dataframe(pd.DataFrame(rows("SELECT * FROM cases WHERE deleted_at IS NULL ORDER BY created_at DESC")),use_container_width=True)

elif page=="Analyze":
    st.header("Technical Analysis")
    cases=rows("SELECT id,label,participant_id FROM cases WHERE deleted_at IS NULL")
    if not cases: st.info("Create a case first.")
    else:
        case=st.selectbox("Case",cases,format_func=lambda x:f"{x['label']} · {x['id'][:8]}")
        if case["participant_id"]:
            clips=rows("SELECT v.* ,a.camera_view,a.maneuver FROM videos v JOIN assignments a ON a.video_id=v.id AND a.active=1 WHERE a.participant_id=? AND a.status='confirmed'",(case["participant_id"],))
        else:
            clips=rows("SELECT v.*,'unknown' camera_view,'unknown' maneuver FROM videos v JOIN segments s ON s.video_id=v.id WHERE s.case_id=?",(case["id"],))
        st.dataframe(pd.DataFrame(clips)[["relative_path","decode_status","camera_view","maneuver"]] if clips else pd.DataFrame(),use_container_width=True)
        clip=st.selectbox("Clip to analyze",clips,format_func=lambda x:x["relative_path"]) if clips else None
        sample_hz=st.number_input("Sampling frequency (Hz)",min_value=1.0,max_value=30.0,value=10.0,step=1.0)
        st.caption("Analysis uses actual presentation timestamps, applies metadata orientation once, and creates a fresh VIDEO tracker for this clip. No network access is used.")
        if st.button("Run pretrained landmark analysis",disabled=not clip):
            bar=st.progress(0.0,text="Analyzing sampled frames…")
            try:
                result=analyze_clip(case["id"],clip["id"],sample_hz=sample_hz,db_path=DB,progress=lambda p:bar.progress(p,text="Analyzing sampled frames…"))
                bar.progress(1.0,text="Analysis complete"); st.session_state["last_run"]=result["run_id"]; st.success(f"Analyzed {result['summary']['sampled_frames']} frames; single-face tracking coverage {result['summary']['tracking_coverage']:.1%}."); st.json(result["summary"])
            except Exception as e: st.error(f"Analysis failed: {e}")
        if len(clips)==3 and st.button("Run all three clips",disabled=not clips):
            bar=st.progress(0.0,text="Analyzing three clips…")
            completed=[]
            try:
                for index,selected in enumerate(clips):
                    completed.append(analyze_clip(case["id"],selected["id"],sample_hz=sample_hz,db_path=DB,progress=lambda p,i=index:bar.progress((i+p)/3,text=f"Analyzing clip {i+1} of 3…")))
                bar.progress(1.0,text="All three clips complete"); st.success("All three clips were analyzed. Review each clip's overlays and intervals before accepting its measurements.")
            except Exception as e: st.error(f"Three-video analysis stopped: {e}")
        active=rows("SELECT metric_id,state,value,unit,video_id,reason_codes_json FROM measurements WHERE case_id=? AND active=1 AND metric_id IN ('visible_lip_aperture','mouth_width','lip_aperture_mouth_width_ratio','lip_aperture_eye_span_ratio','prototype_relative_opening_index','relative_head_yaw','relative_head_pitch','relative_head_roll','tracking_coverage') ORDER BY metric_id",(case["id"],))
        if active:
            prototype=[x for x in active if x["metric_id"]=="prototype_relative_opening_index" and x["state"]=="available"]
            if prototype:
                st.subheader("Proof-of-concept visual indicator")
                st.metric("Relative visible mouth opening",relative_opening_band(prototype[0]["value"]) or "Unavailable")
                st.caption("Display-only heuristic from a dimensionless lip-aperture/mouth-width ratio. It is not centimetres, a physical measurement, or a clinical threshold.")
            st.subheader("Evidence checklist")
            st.caption("A checked item means its technical and review prerequisites were met. This checklist reports video evidence only; it does not predict intubation difficulty.")
            metric_labels={
                "visible_lip_aperture":"Visible lip aperture",
                "mouth_width":"Mouth width",
                "lip_aperture_mouth_width_ratio":"Lip aperture / mouth-width ratio",
                "lip_aperture_eye_span_ratio":"Lip aperture / eye-span ratio",
                "prototype_relative_opening_index":"Relative visual opening band",
                "relative_head_yaw":"Relative head yaw",
                "relative_head_pitch":"Relative head pitch",
                "relative_head_roll":"Relative head roll",
                "tracking_coverage":"Single-face tracking coverage",
            }
            for item in active:
                label=metric_labels.get(item["metric_id"],item["metric_id"].replace("_"," ").title())
                checked=item["state"]=="available"
                value="" if item["value"] is None else f" — {item['value']:.3f} {item['unit'] or ''}".rstrip()
                st.checkbox(f"{label}{value}",value=checked,disabled=True,key=f"evidence_{case['id']}_{item['video_id']}_{item['metric_id']}")
                if not checked:
                    reasons=", ".join(json.loads(item["reason_codes_json"] or "[]")) or item["state"]
                    st.caption(f"Not satisfied: {reasons}")
            expected_video_ids=[clip["id"] for clip in clips]
            cross_video=summarize_case_measurements(active,expected_video_ids)
            st.subheader("Combined three-video evidence")
            st.caption("Each clip is analyzed independently first. The values below are a transparent median and range across the latest reviewed clip-level values; no clip is discarded or silently replaced.")
            st.metric("Clips with reviewed measurements",f"{cross_video['clips_with_reviewed_measurements']} / {cross_video['clips_expected']}")
            if cross_video["prototype_relative_opening_band_from_median_ratio"]:
                st.metric("Combined relative visual opening",cross_video["prototype_relative_opening_band_from_median_ratio"])
            summary_rows=[]
            for metric,summary in cross_video["metrics"].items():
                summary_rows.append({"Metric":metric.replace("_"," ").title(),"Reviewed clips":summary["reviewed_clips"],"Median":round(summary["median"],3),"Range":f"{summary['minimum']:.3f}–{summary['maximum']:.3f}","Unit":summary["unit"] or ""})
            if summary_rows:
                st.dataframe(pd.DataFrame(summary_rows),use_container_width=True,hide_index=True)
            else:
                st.info("Review each clip's interval to generate a combined cross-video summary.")
            st.warning("Clinical verdict unavailable: this video-evidence checklist has not been validated to determine whether intubation will be difficult. A qualified clinician must perform the complete airway assessment.")
            with st.expander("Technical measurement records"):
                st.dataframe(pd.DataFrame(active),use_container_width=True)

elif page=="Review":
    st.header("Human Review")
    cases=rows("SELECT id,label FROM cases WHERE deleted_at IS NULL")
    if not cases: st.info("Create and analyze a case first.")
    else:
        case=st.selectbox("Case",cases,format_func=lambda x:f"{x['label']} · {x['id'][:8]}")
        runs=rows("SELECT r.*,v.relative_path FROM analysis_runs r JOIN videos v ON v.id=r.video_id WHERE r.case_id=? ORDER BY r.started_at DESC",(case["id"],))
        run=st.selectbox("Analysis run",runs,format_func=lambda x:f"{x['relative_path']} · {x['state']} · {x['id'][:8]}") if runs else None
        ms=rows("SELECT * FROM measurements WHERE case_id=? AND active=1 ORDER BY metric_id",(case["id"],))
        if ms: st.dataframe(pd.DataFrame(ms)[["metric_id","state","value","unit","reason_codes_json"]],use_container_width=True)
        if run and run["state"]=="completed":
            arts=rows("SELECT * FROM analysis_artifacts WHERE run_id=?",(run["id"],)); raw_art=next((x for x in arts if x["kind"]=="per_frame_json"),None)
            raw=json.loads(Path(raw_art["path"]).read_text(encoding="utf-8")) if raw_art else {"frames":[]}; frames=raw["frames"]
            overlays=[f for f in frames if f.get("overlay_path") and Path(f["overlay_path"]).exists()]
            if overlays:
                chosen=st.select_slider("Inspect overlay timestamp (ms)",options=overlays,format_func=lambda x:f"{x['timestamp_ms']:.0f}")
                st.image(chosen["overlay_path"],caption=f"Sparse mesh and verified anchors at {chosen['timestamp_ms']:.0f} ms")
            times=[f["timestamp_ms"] for f in frames]
            if times:
                neutral=st.slider("Neutral interval (ms)",float(min(times)),float(max(times)),(float(min(times)),float(min(max(times),min(times)+500.0))))
                maneuver=st.slider("Maneuver interval (ms)",float(min(times)),float(max(times)),(float(min(times)),float(max(times))))
                camera=st.radio("Did the camera remain fixed?",["uncertain","yes","no"],horizontal=True)
                exclusion_text=st.text_input("Excluded intervals (start-end ms, comma separated)",placeholder="2100-2500, 4100-4300")
                reviewer_interval=st.text_input("Reviewer name",value="local_reviewer",key="reviewer_interval")
                if st.button("Accept reviewed intervals and calculate summaries"):
                    try:
                        exclusions=[]
                        for part in filter(None,(x.strip() for x in exclusion_text.split(","))): exclusions.append([float(x) for x in part.split("-",1)])
                        result=review_intervals(run["id"],reviewer_interval,neutral,maneuver,exclusions,camera,db_path=DB); st.success("Reviewed summaries saved; previous summaries and reports were invalidated without deleting history."); st.json(result)
                    except Exception as e: st.error(str(e))
        st.divider(); st.subheader("Optional manual correction")
        metric=st.selectbox("Review metric",["visible_lip_aperture","mouth_width"])
        state=st.selectbox("Evidence state",["needs_review","available","unavailable"])
        reason=st.text_input("Specific reason or limitation",value="")
        neutral=st.number_input("Neutral timestamp (ms)",min_value=0.0,value=0.0)
        points=point_editor(f"{case['id']}_{metric}") if metric in ("visible_lip_aperture","interincisor_opening") else []
        reviewer=st.text_input("Reviewer name",value="local_reviewer",key="reviewer_review")
        if st.button("Commit review revision"):
            payload={"metric_id":metric,"state":state,"reason":reason,"neutral_timestamp_ms":neutral,"endpoints":points,"coordinate_space":"orientation_corrected_source_pixels"}
            rid=save_revision(case["id"],reviewer,payload,db_path=DB)
            st.success(f"Saved review revision {rid}. Dependent active measurements and report snapshots were invalidated; prior records remain preserved.")

elif page=="Report & export":
    st.header("Report and Export")
    cases=rows("SELECT id,label,participant_id FROM cases WHERE deleted_at IS NULL")
    if not cases: st.info("No cases available.")
    else:
        case=st.selectbox("Case",cases,format_func=lambda x:f"{x['label']} · {x['id'][:8]}")
        if st.button("Generate reproducible snapshot"):
            out=Path("data/participants")/(case["participant_id"] or "unassigned")/"cases"/case["id"]/"exports"
            result=export_case(case["id"],out,DB); st.session_state["exports"]={k:str(v) for k,v in result.items()}
        if st.session_state.get("exports"):
            st.json(st.session_state["exports"])
            for kind in ("html","json","csv","frames_csv"):
                p=Path(st.session_state["exports"][kind]); st.download_button(f"Download {kind.upper()}",p.read_bytes(),p.name)
    st.info(LIMITATION)

elif page=="Delete":
    st.header("Safe Data Deletion")
    st.warning("Deletion affects only the selected managed case. Files in Downloads are never targeted. Browser-downloaded exports are outside this application's control.")
    cases=rows("SELECT id,label,participant_id FROM cases WHERE deleted_at IS NULL")
    if cases:
        case=st.selectbox("Case",cases,format_func=lambda x:f"{x['label']} · {x['id']}")
        confirm=st.text_input("Type the complete case UUID to confirm")
        if st.button("Delete managed case",type="primary",disabled=confirm!=case["id"]):
            st.success("Deleted." if delete_case(case["id"],DB) else "Case was already absent.")
    else: st.info("No managed cases to delete.")
