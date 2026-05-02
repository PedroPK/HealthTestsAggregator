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
from src.pdf_exporter import generate_pdf_report, generate_pdf_bytes
from src.reference import load_references, get_reference

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

    st.caption(
        "🔒 Arquivos processados inteiramente em memória e descartados ao "
        "encerrar a sessão. Nenhum dado é salvo no servidor."
    )

    if uploaded_files and st.button("🔍 Processar", use_container_width=True):
        import io as _io, zipfile as _zipfile
        from src.parser import parse_pdf_bytes

        MAX_UPLOAD_MB = 50

        # Validate file sizes before any processing
        for uf in uploaded_files:
            if uf.size > MAX_UPLOAD_MB * 1024 * 1024:
                st.error(
                    f"❌ '{uf.name}' excede o limite de {MAX_UPLOAD_MB} MB. "
                    "Reduza o tamanho do arquivo e tente novamente."
                )
                st.stop()

        # Expand uploaded files into (label, pdf_bytes) pairs — entirely in memory
        tasks: list[tuple[str, bytes]] = []
        for uf in uploaded_files:
            raw = uf.read()
            if uf.name.lower().endswith(".zip"):
                with _zipfile.ZipFile(_io.BytesIO(raw)) as zf:
                    for entry in zf.infolist():
                        if entry.filename.lower().endswith(".pdf"):
                            fname = Path(entry.filename).name
                            tasks.append((fname, zf.read(entry.filename)))
            else:
                tasks.append((uf.name, raw))

        status_text = st.empty()
        progress_bar = st.progress(0)
        all_docs = []
        n = len(tasks)

        for i, (label, pdf_bytes) in enumerate(tasks):
            pct = int(i / n * 100)
            status_text.markdown(
                f"Extraindo dados dos PDFs... **{pct}%** &nbsp;·&nbsp; `{label}`"
            )
            progress_bar.progress(pct)
            doc = parse_pdf_bytes(pdf_bytes, label)
            all_docs.append(doc)

        progress_bar.progress(100)
        status_text.markdown("Extraindo dados dos PDFs... **100%**")
        progress_bar.empty()
        status_text.empty()

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
                pdf_data = generate_pdf_bytes(st.session_state.df)
            st.download_button(
                "⬇️ Baixar PDF",
                pdf_data,
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

tab1, tab2, tab3, tab4 = st.tabs(["📊 Evolução por Exame", "📋 Tabela Completa", "ℹ️ Dados Brutos", "🔬 Análise por Exame"])

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

# ── Tab 4: Análise por Exame com Valores de Referência ───────────────────────
with tab4:
    st.subheader("🔬 Análise por Exame")

    _config_path = Path(__file__).parent.parent / "config" / "reference_ranges.yaml"
    refs = load_references()
    if not _config_path.exists():
        st.error(
            "⚠️ Arquivo de valores de referência não encontrado.  \n"
            f"Esperado em: `{_config_path}`  \n\n"
            "Execute no terminal para configurar:\n"
            "```\npython update_references.py\n```"
        )

    exam_names = sorted(df["exam_name"].unique().tolist())
    exams_with_ref = {e for e in exam_names if get_reference(e, refs) is not None}

    selected_exam = st.selectbox(
        "Selecione o exame",
        options=exam_names,
        format_func=lambda x: f"✓  {x}" if x in exams_with_ref else f"○  {x}",
    )

    exam_df = df[df["exam_name"] == selected_exam].sort_values("date")
    numeric = exam_df.dropna(subset=["value_numeric"])
    ref = get_reference(selected_exam, refs)

    if numeric.empty:
        st.warning("Este exame não possui valores numéricos para exibição gráfica.")
    else:
        # ── Compute display y-range ──────────────────────────────────────────
        data_min = numeric["value_numeric"].min()
        data_max = numeric["value_numeric"].max()
        data_span = max(data_max - data_min, abs(data_max) * 0.1, 1.0)
        y_low  = data_min - data_span * 0.35
        y_high = data_max + data_span * 0.35
        if ref:
            if ref.min is not None:
                y_low  = min(y_low,  ref.min - data_span * 0.15)
            if ref.max is not None:
                y_high = max(y_high, ref.max + data_span * 0.15)

        fig = go.Figure()

        # ── Reference zones or lines ─────────────────────────────────────────
        if ref and ref.zones:
            for zone in ref.zones:
                z_min = max(zone.min if zone.min is not None else y_low,  y_low)
                z_max = min(zone.max if zone.max is not None else y_high, y_high)
                if z_max <= z_min:
                    continue
                fig.add_hrect(
                    y0=z_min, y1=z_max,
                    fillcolor=zone.color,
                    opacity=0.18,
                    layer="below",
                    line_width=0,
                    annotation_text=zone.label,
                    annotation_position="top right",
                    annotation_font=dict(size=11, color="#555555"),
                )
        elif ref:
            if ref.min is not None:
                fig.add_hline(
                    y=ref.min, line_dash="dash", line_color="#2ca02c", line_width=1.5,
                    annotation_text=f"Mín: {ref.min}",
                    annotation_position="bottom right",
                    annotation_font=dict(color="#2ca02c"),
                )
            if ref.max is not None:
                fig.add_hline(
                    y=ref.max, line_dash="dash", line_color="#d62728", line_width=1.5,
                    annotation_text=f"Máx: {ref.max}",
                    annotation_position="top right",
                    annotation_font=dict(color="#d62728"),
                )

        # ── Data trace ───────────────────────────────────────────────────────
        unit_label = (
            ref.unit if ref
            else (exam_df["unit"].dropna().iloc[0] if not exam_df["unit"].dropna().empty else "")
        )
        fig.add_trace(go.Scatter(
            x=numeric["date"],
            y=numeric["value_numeric"],
            mode="lines+markers",
            name=selected_exam,
            marker=dict(size=9, color="#1f77b4", line=dict(width=1.5, color="white")),
            line=dict(width=2.5, color="#1f77b4"),
            hovertemplate=(
                "<b>%{x|%d/%m/%Y}</b><br>"
                f"Valor: %{{y}} {unit_label}<br>"
                "<extra></extra>"
            ),
        ))

        fig.update_layout(
            title=dict(text=f"<b>{selected_exam}</b>", font=dict(color="#111111", size=16)),
            xaxis_title="Data",
            yaxis_title=unit_label,
            height=480,
            hovermode="x unified",
            plot_bgcolor="#f8fbff",
            paper_bgcolor="white",
            xaxis=dict(
                title_font=dict(color="#111111"),
                tickfont=dict(color="#111111"),
                gridcolor="#dddddd",
            ),
            yaxis=dict(
                title_font=dict(color="#111111"),
                tickfont=dict(color="#111111"),
                gridcolor="#dddddd",
                range=[y_low, y_high],
            ),
            margin=dict(t=60, r=130, b=60, l=70),
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Reference info card ──────────────────────────────────────────────
        if ref:
            note_str = f" · {ref.note}" if ref.note else ""
            st.info(
                f"**Referência ({ref.canonical_name}):** {ref.summary()}{note_str}  "
                f"{'· ' + str(len(ref.zones)) + ' faixas configuradas' if ref.zones else ''}"
            )
        else:
            st.caption(
                "⚙️ Nenhum valor de referência configurado para este exame. "
                "Execute `python update_references.py` para adicionar."
            )

        # ── Data table ───────────────────────────────────────────────────────
        with st.expander(f"📋 Todos os registros ({len(exam_df)})"):
            st.dataframe(
                exam_df[
                    ["date", "value_raw", "unit", "reference_range", "lab", "source_file"]
                ].assign(date=exam_df["date"].dt.strftime("%d/%m/%Y"))
                .rename(columns={
                    "date": "Data",
                    "value_raw": "Valor",
                    "unit": "Unidade",
                    "reference_range": "Ref. PDF",
                    "lab": "Laboratório",
                    "source_file": "Arquivo",
                }),
                use_container_width=True,
            )
