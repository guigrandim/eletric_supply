"""
Dashboard interativo — Materiais Elétricos em Compras Públicas (Compras.gov.br)

Lê diretamente do banco estrela (assets/data/database.db) produzido pelos
notebooks 02_extracao_e_bd.ipynb e 03_limpeza_eda.ipynb. Não recalcula
hipóteses/EDA — isso vive nos notebooks. Este app cobre o requisito de
"visualização que permita acompanhar e explorar as informações obtidas".

Acessado via navegação a partir de Home.py — rodar com: streamlit run Home.py
"""

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

CAMINHO_BANCO = Path(__file__).parents[1] / "assets" / "data" / "database.db"


@st.cache_data
def carregar_dados():
    """Carrega e junta o schema estrela num único DataFrame achatado para o dashboard."""
    conexao = sqlite3.connect(CAMINHO_BANCO)
    query = """
    SELECT
        f.id_compra_item, f.codigo_item_catalogo, f.ni_fornecedor, f.codigo_uasg,
        f.quantidade, f.preco_unitario, f.data_compra,
        m.nome_classe, m.nome_grupo, m.nome_pdm, m.descricao_item,
        fo.nome_fornecedor,
        u.nome_uasg, u.municipio, u.estado, u.nome_orgao, u.poder, u.esfera
    FROM fato_precos_praticados f
    LEFT JOIN dim_material m ON f.codigo_item_catalogo = m.codigo_item
    LEFT JOIN dim_fornecedor fo ON f.ni_fornecedor = fo.ni_fornecedor
    LEFT JOIN dim_uasg u ON f.codigo_uasg = u.codigo_uasg
    """
    df = pd.read_sql_query(query, conexao)
    conexao.close()

    df["data_compra"] = pd.to_datetime(df["data_compra"], errors="coerce")
    df["valor_total"] = df["quantidade"] * df["preco_unitario"]
    return df


def projecao_naive_sazonal(serie_trimestral, n_trimestres=4):
    """
    Repete o valor do mesmo trimestre do ano anterior (método vencedor no
    backtest do notebook 03, seção 4.7: MAPE 15,5% vs. 51,4% do XGBoost).
    Para trimestres além do 4º do horizonte, "ano anterior" já é um valor
    projetado (não há dado real ainda) — a projeção encadeia sobre si mesma.
    Faixa de confiança = ±1 desvio padrão histórico da série completa.
    """
    serie_estendida = serie_trimestral.copy()
    datas_futuras = pd.date_range(
        serie_trimestral.index[-1] + pd.DateOffset(months=3), periods=n_trimestres, freq="QS"
    )
    for data in datas_futuras:
        serie_estendida.loc[data] = serie_estendida.iloc[-4]
    projecao = serie_estendida.loc[datas_futuras]
    desvio = serie_trimestral.std()
    return projecao, desvio


df = carregar_dados()
data_min, data_max = df["data_compra"].min(), df["data_compra"].max()

st.title("Materiais Elétricos — Compras Públicas")
st.caption(
    "Fonte: API do Portal de Dados Abertos (dadosabertos.compras.gov.br) — "
    "grupos CATMAT 59 (Componentes Elétricos) e 61 (Condutores e Equip. de Energia)"
)

# ── Sidebar: filtros ─────────────────────────────────────────────────────
st.sidebar.header("Filtros")

periodo = st.sidebar.date_input(
    "Período", value=(data_min, data_max), min_value=data_min, max_value=data_max
)
estados = st.sidebar.multiselect("Estado (UASG)", sorted(df["estado"].dropna().unique()))
classes = st.sidebar.multiselect("Classe de material", sorted(df["nome_classe"].dropna().unique()))
fornecedores = st.sidebar.multiselect("Fornecedor", sorted(df["nome_fornecedor"].dropna().unique()))

df_filtrado = df.copy()
if isinstance(periodo, tuple) and len(periodo) == 2:
    inicio, fim = pd.to_datetime(periodo[0]), pd.to_datetime(periodo[1])
    df_filtrado = df_filtrado[df_filtrado["data_compra"].between(inicio, fim)]
if estados:
    df_filtrado = df_filtrado[df_filtrado["estado"].isin(estados)]
if classes:
    df_filtrado = df_filtrado[df_filtrado["nome_classe"].isin(classes)]
if fornecedores:
    df_filtrado = df_filtrado[df_filtrado["nome_fornecedor"].isin(fornecedores)]

if df_filtrado.empty:
    st.warning("Nenhum registro para os filtros selecionados.")
    st.stop()

# ── KPIs ─────────────────────────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Valor total", f"R$ {df_filtrado['valor_total'].sum():,.0f}")
col2.metric("Compras", f"{len(df_filtrado):,}")
col3.metric("Fornecedores únicos", f"{df_filtrado['ni_fornecedor'].nunique():,}")
col4.metric("UASGs únicas", f"{df_filtrado['codigo_uasg'].nunique():,}")
col5.metric("Ticket médio", f"R$ {df_filtrado['valor_total'].mean():,.2f}")

st.divider()

# ── Série temporal ───────────────────────────────────────────────────────
st.subheader("Consumo ao longo do tempo")
granularidade = st.radio("Granularidade", ["Trimestral", "Mensal"], horizontal=True)
freq = "QS" if granularidade == "Trimestral" else "MS"

serie = (
    df_filtrado.dropna(subset=["data_compra"])
    .set_index("data_compra")
    .resample(freq)["valor_total"]
    .sum()
)
fig_serie = px.line(
    x=serie.index, y=serie.values, markers=True,
    labels={"x": "Período", "y": "Valor total (R$)"},
)
st.plotly_chart(fig_serie, width="stretch")

st.divider()

# ── Rankings ──────────────────────────────────────────────────────────────
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Top 10 fornecedores por valor")
    top_fornecedores = (
        df_filtrado.groupby("nome_fornecedor")["valor_total"].sum()
        .sort_values(ascending=True).tail(10)
    )
    st.plotly_chart(
        px.bar(top_fornecedores, orientation="h", labels={"value": "Valor total (R$)", "nome_fornecedor": ""}),
        width="stretch",
    )

with col_b:
    st.subheader("Top 10 classes de material por valor")
    top_classes = (
        df_filtrado.groupby("nome_classe")["valor_total"].sum()
        .sort_values(ascending=True).tail(10)
    )
    st.plotly_chart(
        px.bar(top_classes, orientation="h", labels={"value": "Valor total (R$)", "nome_classe": ""}),
        width="stretch",
    )

st.divider()

# ── Projeção ──────────────────────────────────────────────────────────────
serie_trimestral_full = (
    df.dropna(subset=["data_compra", "valor_total"])
    .set_index("data_compra")
    .resample("QS")["valor_total"].sum()
)

# remove o último trimestre se ele ainda estiver em andamento na extração dos dados
fim_do_trimestre = serie_trimestral_full.index[-1] + pd.DateOffset(months=3) - pd.DateOffset(days=1)
if data_max < fim_do_trimestre:
    serie_trimestral_full = serie_trimestral_full.iloc[:-1]

# projeta o suficiente para cobrir o restante do ano corrente + o ano civil seguinte inteiro
ano_seguinte = serie_trimestral_full.index[-1].year + 1
n_trimestres_projecao = (4 - serie_trimestral_full.index[-1].quarter) + 4

st.subheader(f"Projeção de consumo — ano civil {ano_seguinte}")
st.caption(
    "Projeção calculada sobre a base completa (não respeita os filtros acima), pois a "
    "metodologia foi validada no nível agregado do portfólio. Método: naive sazonal — "
    "venceu o XGBoost no backtest 2026 (MAPE 15,5% vs. 51,4%). Faixa de confiança = ±1 "
    "desvio padrão histórico. Os 2 últimos trimestres do horizonte encadeiam sobre "
    "trimestres já projetados (ainda não há dado real de referência para eles). "
    "Metodologia completa e limitações em notebooks/03_limpeza_eda.ipynb, seções 4.0–4.8."
)

projecao, desvio = projecao_naive_sazonal(serie_trimestral_full, n_trimestres=n_trimestres_projecao)
projecao_ano_seguinte = projecao[projecao.index.year == ano_seguinte]

st.metric(f"Projeção total {ano_seguinte}", f"R$ {projecao_ano_seguinte.sum():,.0f}")

fig_proj = go.Figure()
fig_proj.add_trace(go.Scatter(
    x=serie_trimestral_full.index, y=serie_trimestral_full.values,
    name="Histórico", mode="lines+markers",
))
fig_proj.add_trace(go.Scatter(
    x=projecao.index, y=projecao.values,
    name="Projeção", mode="lines+markers", line=dict(dash="dash"),
))
fig_proj.add_trace(go.Scatter(
    x=list(projecao.index) + list(projecao.index[::-1]),
    y=list(projecao.values + desvio) + list(projecao.values[::-1] - desvio),
    fill="toself", fillcolor="rgba(255,165,0,0.15)", line=dict(width=0),
    name="Faixa de confiança (±1 desvio padrão)", hoverinfo="skip",
))
fig_proj.update_layout(yaxis_title="Valor total (R$)", xaxis_title="Trimestre")
st.plotly_chart(fig_proj, width="stretch")

st.divider()

# ── Tabela detalhada ────────────────────────────────────────────────────
st.subheader("Dados filtrados")
st.dataframe(
    df_filtrado[[
        "data_compra", "descricao_item", "nome_fornecedor", "nome_uasg", "estado",
        "quantidade", "preco_unitario", "valor_total",
    ]].sort_values("data_compra", ascending=False),
    width="stretch",
    height=300,
)
