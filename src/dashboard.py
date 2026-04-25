"""
Streamlit dashboard for interactive blood test history visualization.

Run with:
    streamlit run src/dashboard.py
"""

import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from src.parser import parse_input
from src.aggregator import build_dataframe, pivot_table, list_exams
from src.pdf_exporter import generate_pdf_report

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="HealthTests Aggregator",
    page_icon="🩸",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .reportview-container { background: #f8fbff; }
    h1 { color: #1a6ba0; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "df" not in st.session_state:
    st.session_state.df = None
if "documents" not in st.session_state:
    st.session_state.documents = []

# ---------------------------------------------------------------------------
# Sidebar: file upload
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🩸 HealthTests\nAggregator")
    st.markdown("---")
    st.subheader("📂 Carregar Exames")

    uploaded_files = st.file_uploader(
        "Selecione PDF(s) ou ZIP(s)",
        type=["pdf", "zip"],
        accept_multiple_files=True,
    )

    if uploaded_files and st.button("🔍 Processar", use_container_width=True):
        with st.spinner("Extraindo dados dos PDFs..."):
            import tempfile, os
            all_docs = []
            for uf in uploaded_files:
                suffix = Path(uf.name).suffix.lower()
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(uf.read())
                    tmp_path = tmp.name
                try:
                    docs = parse_input(tmp_path)
                    all_docs.extend(docs)
                finally:
                    os.unlink(tmp_path)

            st.session_state.documents = all_docs
            df = build_dataframe(all_docs)
            st.session_state.df = df

        errors = [e for d in all_docs for e in d.parse_errors]
        if errors:
            with st.expander(f"⚠️ {len(errors)} avisos de parse"):
                for e in errors:
                    st.text(e)

        total = sum(len(d.results) for d in all_docs)
        st.success(f"✅ {len(all_docs)} arquivo(s) · {total} registros encontrados")

    st.markdown("---")

    # Export buttons (only when data is loaded)
    if st.session_state.df is not None and not st.session_state.df.empty:
        st.subheader("📤 Exportar")

        if st.button("📄 Gerar PDF Consolidado", use_container_width=True):
            with st.spinner("Gerando PDF..."):
                from pathlib import Path
                out = Path("output") / "historico_exames.pdf"
                generate_pdf_report(st.session_state.df, out)
            with open(out, "rb") as f:
                st.download_button(
                    "⬇️ Baixar PDF",
                    f,
                    file_name="historico_exames.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

        # Excel export
        pivot = pivot_table(st.session_state.df)
        if not pivot.empty:
            import io
            buf = io.BytesIO()
            pivot.to_excel(buf, sheet_name="Histórico")
            buf.seek(0)
            st.download_button(
                "⬇️ Baixar Excel",
                buf,
                file_name="historico_exames.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

st.title("🩸 Histórico Consolidado de Exames de Sangue")

if st.session_state.df is None or st.session_state.df.empty:
    st.info("👈 Carregue seus arquivos PDF ou ZIP no painel lateral para começar.")

    st.markdown("""
    ### Como usar
    1. Clique em **Selecione PDF(s) ou ZIP(s)** no painel lateral
    2. Adicione seus laudos de exame de sangue
    3. Clique em **Processar**
    4. Explore o histórico no dashboard
    5. Exporte como **PDF consolidado** ou **Excel**

    ### Suporte
    - **A+ Medicina Diagnóstica** (laudos individuais e Laudos Evolutivos)
    - **Laboratório Marcelo Magalhães**
    - Outros laboratórios (parser genérico)
    """)
    st.stop()

df = st.session_state.df

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total de Registros", len(df))
with col2:
    st.metric("Tipos de Exame", df["exam_name"].nunique())
with col3:
    dates = df["date"].dt.date.unique()
    st.metric("Datas de Coleta", len(dates))
with col4:
    labs = df["lab"].nunique()
    st.metric("Laboratórios", labs)

st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab1, tab2, tab3 = st.tabs(["📊 Evolução por Exame", "📋 Tabela Completa", "ℹ️ Dados Brutos"])

# ── Tab 1: Exam evolution chart ──────────────────────────────────────────────
with tab1:
    exams = list_exams(df)

    col_sel, col_lab = st.columns([3, 1])
    with col_sel:
        selected_exams = st.multiselect(
            "Selecione os exames para visualizar",
            options=exams,
            default=exams[:min(5, len(exams))],
        )
    with col_lab:
        lab_filter = st.multiselect(
            "Laboratório",
            options=df["lab"].unique().tolist(),
            default=df["lab"].unique().tolist(),
        )

    filtered = df[df["lab"].isin(lab_filter)]

    if selected_exams:
        fig = go.Figure()
        for exam in selected_exams:
            exam_df = filtered[filtered["exam_name"] == exam].sort_values("date")
            if exam_df.empty:
                continue
            numeric = exam_df.dropna(subset=["value_numeric"])
            if numeric.empty:
                continue

            unit = numeric["unit"].dropna().iloc[0] if not numeric["unit"].dropna().empty else ""
            fig.add_trace(go.Scatter(
                x=numeric["date"],
                y=numeric["value_numeric"],
                mode="lines+markers",
                name=f"{exam} ({unit})" if unit else exam,
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "Data: %{x|%d/%m/%Y}<br>"
                    "Valor: %{y}<br>"
                    "<extra></extra>"
                ),
            ))

        fig.update_layout(
            title="Evolução dos Exames ao Longo do Tempo",
            xaxis_title="Data",
            yaxis_title="Valor",
            hovermode="x unified",
            height=520,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.18,
                xanchor="center",
                x=0.5,
                font=dict(size=12, color="#111111"),
                bgcolor="#ffffff",
                bordercolor="#888888",
                borderwidth=1,
            ),
            margin=dict(t=50, b=160),
            plot_bgcolor="#f8fbff",
            paper_bgcolor="white",
            xaxis=dict(
                title_font=dict(color="#111111"),
                tickfont=dict(color="#111111"),
                linecolor="#888888",
                gridcolor="#dddddd",
            ),
            yaxis=dict(
                title_font=dict(color="#111111"),
                tickfont=dict(color="#111111"),
                linecolor="#888888",
                gridcolor="#dddddd",
            ),
            title_font=dict(color="#111111"),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Selecione ao menos um exame acima.")

# ── Tab 2: Pivot table ────────────────────────────────────────────────────────
with tab2:
    pivot = pivot_table(df)
    if not pivot.empty:
        st.dataframe(pivot, use_container_width=True, height=500)
    else:
        st.warning("Nenhum dado para exibir.")

# ── Tab 3: Raw data ───────────────────────────────────────────────────────────
with tab3:
    st.dataframe(
        df.assign(date=df["date"].dt.strftime("%d/%m/%Y")),
        use_container_width=True,
        height=500,
    )

    # Parse errors
    errors = [e for d in st.session_state.documents for e in d.parse_errors]
    if errors:
        with st.expander(f"⚠️ Erros de parse ({len(errors)})"):
            for e in errors:
                st.text(e)
