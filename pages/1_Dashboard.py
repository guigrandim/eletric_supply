"""
Dashboard interativo — Materiais Elétricos em Compras Públicas (Compras.gov.br)

Lê diretamente do banco estrela (assets/data/database.db) produzido pelos
notebooks 02_extracao_e_bd.ipynb e 03_limpeza_eda.ipynb. Não recalcula
hipóteses/EDA — isso vive nos notebooks. Este app cobre o requisito de
"visualização que permita acompanhar e explorar as informações obtidas".

Acessado via navegação a partir de Home.py — rodar com: streamlit run Home.py
"""

#==================================
# Import Library
#==================================

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from scipy.stats import linregress

#==================================
# Configuration Page
#==================================

# st.set_page_config já foi chamado em Home.py — uma página filha chamando de
# novo dispara StreamlitAPIException, por isso não é repetido aqui.
CAMINHO_BANCO = Path(__file__).parents[1] / "assets" / "data" / "database.db"

#===================================
# Functions
#===================================

@st.cache_data
def carregar_dados():
    """
    Carrega o schema estrela do banco SQLite e junta as tabelas num único
    DataFrame achatado, pronto para os filtros e gráficos do dashboard.

    Responde às perguntas:
    "Quais compras de materiais elétricos foram registradas, com que
    fornecedor, UASG e classe de material?"
    "Qual o valor total de cada compra (quantidade x preço unitário)?"

    Parâmetros
    ----------
    Nenhum — lê diretamente de CAMINHO_BANCO (assets/data/database.db).

    Retorna
    -------
    df : pd.DataFrame
        Uma linha por item comprado, com colunas de fato (quantidade, preço
        unitário, data, valor_total) e dimensões achatadas (material,
        fornecedor, UASG).
    """
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


def aplicar_filtros_sidebar(df):
    """
    Renderiza os filtros da sidebar (período, estado, classe, fornecedor) e
    retorna a base filtrada de acordo com a seleção do usuário.

    Responde às perguntas:
    "Como restringir a análise a um recorte específico (período, estado,
    classe de material, fornecedor) sem alterar a base completa usada na
    Projeção e nas Recomendações?"

    Parâmetros
    ----------
    df : pd.DataFrame
        Base completa (carregar_dados()).

    Retorna
    -------
    pd.DataFrame
        Subconjunto de df de acordo com os filtros selecionados na sidebar.
    """
    # ── 1. Cabeçalho e opções de filtro ──────────────────────────────────
    st.sidebar.header("Filtros")
    data_min, data_max = df["data_compra"].min(), df["data_compra"].max()

    periodo = st.sidebar.date_input(
        "Período", value=(data_min, data_max), min_value=data_min, max_value=data_max
    )
    estados = st.sidebar.multiselect("Estado (UASG)", sorted(df["estado"].dropna().unique()))
    classes = st.sidebar.multiselect("Classe de material", sorted(df["nome_classe"].dropna().unique()))
    fornecedores = st.sidebar.multiselect("Fornecedor", sorted(df["nome_fornecedor"].dropna().unique()))

    # ── 2. Aplicação sequencial dos filtros selecionados ────────────────
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

    return df_filtrado


def grafico_serie_temporal(df_filtrado, freq):
    """
    Gera um gráfico de linha com o valor total comprado ao longo do tempo,
    na granularidade escolhida pelo usuário (trimestral ou mensal).

    Responde às perguntas:
    "Como o volume de compras evoluiu ao longo do tempo?"
    "Existem picos ou quedas visíveis no consumo?"

    Parâmetros
    ----------
    df_filtrado : pd.DataFrame
        Base já filtrada pelos filtros da sidebar.
    freq : str
        Frequência de reamostragem pandas ("QS" trimestral ou "MS" mensal).

    Retorna
    -------
    fig : plotly.graph_objects.Figure
        Gráfico de linha do valor total por período.
    """
    serie = (
        df_filtrado.dropna(subset=["data_compra"])
        .set_index("data_compra")
        .resample(freq)["valor_total"]
        .sum()
    )
    fig = px.line(
        x=serie.index, y=serie.values, markers=True,
        labels={"x": "Período", "y": "Valor total (R$)"},
    )
    return fig


def grafico_top_fornecedores(df_filtrado, top_n=10):
    """
    Gera um gráfico de barras horizontais com os fornecedores de maior valor
    total comprado.

    Responde às perguntas:
    "Quem são os principais fornecedores em valor?"
    "Há concentração de gasto em poucos fornecedores?"

    Parâmetros
    ----------
    df_filtrado : pd.DataFrame
        Base já filtrada pelos filtros da sidebar.
    top_n : int
        Quantidade de fornecedores a exibir (default 10).

    Retorna
    -------
    fig : plotly.graph_objects.Figure
        Gráfico de barras horizontais, valor total por fornecedor.
    """
    top_fornecedores = (
        df_filtrado.groupby("nome_fornecedor")["valor_total"].sum()
        .sort_values(ascending=True).tail(top_n)
    )
    fig = px.bar(
        top_fornecedores, orientation="h",
        labels={"value": "Valor total (R$)", "nome_fornecedor": ""},
    )
    return fig


def grafico_top_classes(df_filtrado, top_n=10):
    """
    Gera um gráfico de barras horizontais com as classes de material de
    maior valor total comprado.

    Responde às perguntas:
    "Quais classes de material concentram mais gasto?"
    "Onde estão as maiores oportunidades de negociação/consolidação?"

    Parâmetros
    ----------
    df_filtrado : pd.DataFrame
        Base já filtrada pelos filtros da sidebar.
    top_n : int
        Quantidade de classes a exibir (default 10).

    Retorna
    -------
    fig : plotly.graph_objects.Figure
        Gráfico de barras horizontais, valor total por classe de material.
    """
    top_classes = (
        df_filtrado.groupby("nome_classe")["valor_total"].sum()
        .sort_values(ascending=True).tail(top_n)
    )
    fig = px.bar(
        top_classes, orientation="h",
        labels={"value": "Valor total (R$)", "nome_classe": ""},
    )
    return fig


def preparar_serie_trimestral_projecao(df, data_max):
    """
    Prepara a série trimestral histórica usada como base da projeção:
    agrega valor total por trimestre e descarta o último trimestre se ele
    ainda estiver em andamento na data de corte da extração.

    Responde às perguntas:
    "Qual a base histórica correta para alimentar o modelo de projeção, sem
    distorcer o MAPE com um trimestre incompleto?"
    "Quantos trimestres é preciso projetar para cobrir o próximo ano civil
    inteiro, a partir de onde a série histórica termina?"

    Parâmetros
    ----------
    df : pd.DataFrame
        Base completa (carregar_dados()), não filtrada pela sidebar.
    data_max : pd.Timestamp
        Data mais recente presente na base (limite de corte da extração).

    Retorna
    -------
    serie_trimestral_full : pd.Series
        Série de valor total por trimestre, sem o trimestre incompleto.
    ano_seguinte : int
        Ano civil seguinte ao último trimestre completo — horizonte alvo.
    n_trimestres_projecao : int
        Quantidade de trimestres a projetar para cobrir `ano_seguinte` inteiro.
    """
    # ── 1. Agregação trimestral e remoção do trimestre em andamento ─────
    serie_trimestral_full = (
        df.dropna(subset=["data_compra", "valor_total"])
        .set_index("data_compra")
        .resample("QS")["valor_total"].sum()
    )
    fim_do_trimestre = serie_trimestral_full.index[-1] + pd.DateOffset(months=3) - pd.DateOffset(days=1)
    if data_max < fim_do_trimestre:
        serie_trimestral_full = serie_trimestral_full.iloc[:-1]

    # ── 2. Horizonte necessário para cobrir o ano civil seguinte inteiro ─
    ano_seguinte = serie_trimestral_full.index[-1].year + 1
    n_trimestres_projecao = (4 - serie_trimestral_full.index[-1].quarter) + 4

    return serie_trimestral_full, ano_seguinte, n_trimestres_projecao


def projecao_naive_sazonal(serie_trimestral, n_trimestres=4):
    """
    Projeta valores futuros repetindo o valor do mesmo trimestre do ano
    anterior — método vencedor no backtest do notebook 03 (seção 4.7): MAPE
    15,5% vs. 51,4% do XGBoost.

    Responde às perguntas:
    "Quanto a área de Suprimentos deve esperar gastar nos próximos
    trimestres?"
    "Qual a faixa de confiança dessa projeção?"

    Parâmetros
    ----------
    serie_trimestral : pd.Series
        Série de valor total agregado por trimestre (index datetime, freq QS).
    n_trimestres : int
        Quantidade de trimestres a projetar à frente do último trimestre da série.

    Retorna
    -------
    projecao : pd.Series
        Valores projetados, indexados pelas datas futuras. Para trimestres
        além do 4º do horizonte, "ano anterior" já é um valor projetado (não
        há dado real ainda) — a projeção encadeia sobre si mesma.
    desvio : float
        Desvio padrão histórico da série completa, usado como faixa de
        confiança heurística (±1 desvio).
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


def grafico_projecao(serie_trimestral_full, projecao, desvio):
    """
    Gera um gráfico de linha combinando o histórico trimestral com a
    projeção naive sazonal e sua faixa de confiança.

    Responde às perguntas:
    "Como a projeção se compara ao histórico recente?"
    "Qual a incerteza (faixa de confiança) em cada trimestre projetado?"

    Parâmetros
    ----------
    serie_trimestral_full : pd.Series
        Série histórica de valor total por trimestre (base completa).
    projecao : pd.Series
        Valores projetados (saída de projecao_naive_sazonal).
    desvio : float
        Desvio padrão histórico, usado para desenhar a faixa de confiança.

    Retorna
    -------
    fig : plotly.graph_objects.Figure
        Gráfico de linha com histórico, projeção tracejada e faixa ±1 desvio.
    """
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=serie_trimestral_full.index, y=serie_trimestral_full.values,
        name="Histórico", mode="lines+markers",
    ))
    fig.add_trace(go.Scatter(
        x=projecao.index, y=projecao.values,
        name="Projeção", mode="lines+markers", line=dict(dash="dash"),
    ))
    fig.add_trace(go.Scatter(
        x=list(projecao.index) + list(projecao.index[::-1]),
        y=list(projecao.values + desvio) + list(projecao.values[::-1] - desvio),
        fill="toself", fillcolor="rgba(255,165,0,0.15)", line=dict(width=0),
        name="Faixa de confiança (±1 desvio padrão)", hoverinfo="skip",
    ))
    fig.update_layout(yaxis_title="Valor total (R$)", xaxis_title="Trimestre")
    return fig


def tabela_cenarios_projecao(projecao, desvio):
    """
    Monta a tabela de cenários (pior/base/melhor) por trimestre projetado.

    Responde às perguntas:
    "Qual o intervalo de valores esperados em cada trimestre projetado?"

    Parâmetros
    ----------
    projecao : pd.Series
        Valores projetados (saída de projecao_naive_sazonal).
    desvio : float
        Desvio padrão histórico usado como faixa de confiança.

    Retorna
    -------
    pd.DataFrame
        Uma linha por trimestre, com colunas Trimestre / Pior cenário /
        Cenário base / Melhor cenário, valores já formatados em R$.
    """
    rotulo_trimestre = {1: "Jan-Mar", 4: "Abr-Jun", 7: "Jul-Set", 10: "Out-Dez"}
    return pd.DataFrame({
        "Trimestre": [f"{rotulo_trimestre[d.month]}/{d.year}" for d in projecao.index],
        "Pior cenário": [f"R$ {v:,.0f}" for v in projecao.values - desvio],
        "Cenário base": [f"R$ {v:,.0f}" for v in projecao.values],
        "Melhor cenário": [f"R$ {v:,.0f}" for v in projecao.values + desvio],
    })


@st.cache_data
def calcular_elasticidade_por_classe(df, classes_top):
    """
    Calcula o slope log-log entre quantidade e preço unitário (elasticidade
    preço-quantidade), uma regressão por classe de material — mesma
    regressão da hipótese H1, segmentada por classe.

    Responde às perguntas:
    "A economia de escala (desconto por volume) é uniforme entre classes de
    material, ou existem classes onde ela é mais forte?"
    "Quais classes têm maior potencial de ganho com consolidação de pedidos?"

    Parâmetros
    ----------
    df : pd.DataFrame
        Base completa (carregar_dados()), sem filtro de UI.
    classes_top : list[str]
        Classes de material a considerar (tipicamente as top N por valor).

    Retorna
    -------
    pd.DataFrame
        Uma linha por classe, com a elasticidade (slope) ordenada de forma
        crescente — mais negativo = desconto por volume mais forte.
    """
    freq_item = df.groupby("codigo_item_catalogo")["id_compra_item"].transform("count")
    sub = df[(freq_item >= 10) & (df["nome_classe"].isin(classes_top))].dropna(
        subset=["quantidade", "preco_unitario", "nome_classe"]
    )

    linhas = []
    for classe, grupo in sub.groupby("nome_classe"):
        x = np.log1p(grupo["quantidade"])
        y = np.log1p(grupo["preco_unitario"])
        slope, *_ = linregress(x, y)
        linhas.append({"nome_classe": classe, "elasticidade": slope})

    return pd.DataFrame(linhas).sort_values("elasticidade").reset_index(drop=True)


def grafico_elasticidade_h1(elasticidade_classe):
    """
    Gera um gráfico de barras horizontais com a elasticidade preço-quantidade
    por classe de material (hipótese H1).

    Responde às perguntas:
    "Em quais classes de material a economia de escala é mais forte?"
    "Existe alguma classe sem desconto por volume (elasticidade não negativa)?"

    Parâmetros
    ----------
    elasticidade_classe : pd.DataFrame
        Saída de calcular_elasticidade_por_classe().

    Retorna
    -------
    fig : plotly.graph_objects.Figure
        Gráfico de barras horizontais com linha de referência em zero.
    """
    fig = px.bar(
        elasticidade_classe, x="elasticidade", y="nome_classe", orientation="h",
        labels={"elasticidade": "Elasticidade média preço-quantidade (slope log-log)", "nome_classe": ""},
        title="Elasticidade preço-quantidade por classe (top 6 por valor) — negativo = desconto por volume",
    )
    fig.add_vline(x=0, line_dash="dash", line_color="red")
    return fig


@st.cache_data
def calcular_cv_h2(df):
    """
    Calcula o coeficiente de variação (CV) do preço unitário por fornecedor
    e por UASG, dentro do mesmo item — mesma lógica da hipótese H2.

    Responde às perguntas:
    "O preço de um mesmo item varia mais entre fornecedores ou entre UASGs?"
    "Onde vale mais a pena concentrar esforço de negociação: no
    relacionamento com fornecedores ou na centralização regional de compras?"

    Parâmetros
    ----------
    df : pd.DataFrame
        Base completa (carregar_dados()), sem filtro de UI.

    Retorna
    -------
    cv_fornecedor : pd.Series
        CV do preço unitário por (item, fornecedor).
    cv_uasg : pd.Series
        CV do preço unitário por (item, UASG).
    """
    cv_fornecedor = df.groupby(["codigo_item_catalogo", "ni_fornecedor"])["preco_unitario"].apply(
        lambda x: x.std() / x.mean() if x.mean() > 0 and len(x) > 1 else np.nan
    ).dropna()
    cv_uasg = df.groupby(["codigo_item_catalogo", "codigo_uasg"])["preco_unitario"].apply(
        lambda x: x.std() / x.mean() if x.mean() > 0 and len(x) > 1 else np.nan
    ).dropna()
    return cv_fornecedor, cv_uasg


def grafico_cv_h2(cv_fornecedor, cv_uasg):
    """
    Gera um gráfico de barras comparando o CV mediano do preço unitário
    entre fornecedores e entre UASGs (hipótese H2).

    Responde às perguntas:
    "Qual das duas dimensões (fornecedor ou UASG) explica mais variabilidade
    de preço para o mesmo item?"

    Parâmetros
    ----------
    cv_fornecedor : pd.Series
        Saída de calcular_cv_h2() — CV por (item, fornecedor).
    cv_uasg : pd.Series
        Saída de calcular_cv_h2() — CV por (item, UASG).

    Retorna
    -------
    fig : plotly.graph_objects.Figure
        Gráfico de barras com o CV mediano de cada grupo.
    """
    cv_medianas = pd.DataFrame({
        "Grupo": ["Por Fornecedor", "Por UASG"],
        "CV mediano do preço": [cv_fornecedor.median(), cv_uasg.median()],
    })
    fig = px.bar(
        cv_medianas, x="Grupo", y="CV mediano do preço", text_auto=".3f",
        title="Coeficiente de variação mediano do preço — Fornecedor vs. UASG",
    )
    return fig


@st.cache_data
def calcular_sazonalidade_h3(df):
    """
    Calcula a quantidade mediana comprada por mês, agregada em todas as
    classes de material — mesma lógica da hipótese H3.

    Responde às perguntas:
    "Existe concentração de demanda em algum período do ano civil?"
    "Em que mês a área de Suprimentos deveria antecipar o planejamento de
    licitações para evitar desabastecimento?"

    Parâmetros
    ----------
    df : pd.DataFrame
        Base completa (carregar_dados()), sem filtro de UI.

    Retorna
    -------
    pd.DataFrame
        Uma linha por mês (1-12), com a quantidade mediana comprada.
    """
    sub = df.dropna(subset=["data_compra"]).copy()
    sub["mes_compra"] = sub["data_compra"].dt.month
    return sub.groupby("mes_compra")["quantidade"].median().reset_index()


def grafico_sazonalidade_h3(sazonalidade_h3):
    """
    Gera um gráfico de barras com a quantidade mediana comprada por mês
    (hipótese H3).

    Responde às perguntas:
    "Em quais meses a demanda por materiais elétricos é historicamente maior?"

    Parâmetros
    ----------
    sazonalidade_h3 : pd.DataFrame
        Saída de calcular_sazonalidade_h3().

    Retorna
    -------
    fig : plotly.graph_objects.Figure
        Gráfico de barras com a quantidade mediana por mês (nomes em pt-br).
    """
    nomes_mes = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
                 7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}
    sazonalidade_h3 = sazonalidade_h3.copy()
    sazonalidade_h3["mes"] = sazonalidade_h3["mes_compra"].map(nomes_mes)
    fig = px.bar(
        sazonalidade_h3, x="mes", y="quantidade",
        labels={"mes": "Mês", "quantidade": "Quantidade mediana"},
        title="Quantidade mediana comprada por mês (todas as classes)",
    )
    return fig


@st.cache_data
def calcular_hhi_por_quartil_h4(df):
    """
    Calcula o HHI médio (concentração de fornecedor) por quartil de
    regularidade de consumo — mesma lógica da hipótese H4, resumida em 4
    quartis em vez do scatter item a item.

    Responde às perguntas:
    "Itens de consumo mais regular têm menos fornecedores concentrados, ou
    o índice de regularidade é independente da concentração de mercado?"
    "Quais itens são bons candidatos a Ata de Registro de Preços com base na
    previsibilidade do consumo?"

    Parâmetros
    ----------
    df : pd.DataFrame
        Base completa (carregar_dados()), sem filtro de UI.

    Retorna
    -------
    pd.DataFrame
        Uma linha por quartil de regularidade de consumo, com o HHI médio.
    """
    valor_mensal_item = df.dropna(subset=["data_compra"]).groupby(
        ["codigo_item_catalogo", pd.Grouper(key="data_compra", freq="ME")]
    )["valor_total"].sum()

    regularidade = valor_mensal_item.groupby("codigo_item_catalogo").apply(
        lambda x: x.mean() / x.std() if x.std() > 0 else np.nan
    )
    n_meses = valor_mensal_item.groupby("codigo_item_catalogo").count()
    regularidade = regularidade[n_meses >= 6].dropna()

    participacao_sq = (
        df.dropna(subset=["codigo_item_catalogo", "ni_fornecedor", "valor_total"])
        .groupby(["codigo_item_catalogo", "ni_fornecedor"])["valor_total"].sum()
        .groupby(level=0, group_keys=False).apply(lambda x: (x / x.sum()) ** 2)
    )
    hhi_item = participacao_sq.groupby("codigo_item_catalogo").sum().rename("hhi")

    df_q = pd.DataFrame({"regularidade_consumo": regularidade}).join(hhi_item).dropna()
    df_q["quartil"] = pd.qcut(
        df_q["regularidade_consumo"], 4,
        labels=["Q1 (menos regular)", "Q2", "Q3", "Q4 (mais regular)"],
    )
    return df_q.groupby("quartil", observed=True)["hhi"].mean().reset_index()


def grafico_hhi_h4(hhi_quartis_h4):
    """
    Gera um gráfico de barras com a concentração de fornecedor (HHI) por
    quartil de regularidade de consumo (hipótese H4).

    Responde às perguntas:
    "A concentração de fornecedor aumenta conforme o consumo de um item é
    menos regular?"

    Parâmetros
    ----------
    hhi_quartis_h4 : pd.DataFrame
        Saída de calcular_hhi_por_quartil_h4().

    Retorna
    -------
    fig : plotly.graph_objects.Figure
        Gráfico de barras com o HHI médio por quartil de regularidade.
    """
    fig = px.bar(
        hhi_quartis_h4, x="quartil", y="hhi",
        labels={"quartil": "Quartil de regularidade de consumo", "hhi": "HHI médio (concentração de fornecedor)"},
        title="Concentração de fornecedor (HHI) por quartil de regularidade de consumo",
    )
    return fig


#===============================================
# Select Directory - Load Files and Clean Dataset
#===============================================

df = carregar_dados()
data_min, data_max = df["data_compra"].min(), df["data_compra"].max()

#======================================
# Create a Sidebar
#======================================

df_filtrado = aplicar_filtros_sidebar(df)

if df_filtrado.empty:
    st.warning("Nenhum registro para os filtros selecionados.")
    st.stop()

#======================================
# Create a Body Page
#======================================

#Create a Header
st.title("Materiais Elétricos — Compras Públicas")
st.caption(
    "Fonte: API do Portal de Dados Abertos (dadosabertos.compras.gov.br) — "
    "grupos CATMAT 59 (Componentes Elétricos) e 61 (Condutores e Equip. de Energia)"
)

#Create Tabs In Page
aba_visao_geral, aba_projecao, aba_recomendacoes = st.tabs(
    ["Visão Geral", "Projeção de consumo", "Recomendações ao Departamento de Suprimentos"]
)

with aba_visao_geral:
    # ── KPIs ─────────────────────────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Valor total", f"R$ {df_filtrado['valor_total'].sum():,.0f}")
    col2.metric("Compras", f"{len(df_filtrado):,}")
    col3.metric("Fornecedores únicos", f"{df_filtrado['ni_fornecedor'].nunique():,}")
    col4.metric("UASGs únicas", f"{df_filtrado['codigo_uasg'].nunique():,}")
    col5.metric("Ticket médio", f"R$ {df_filtrado['valor_total'].mean():,.2f}")

    st.divider()

    # ── Série temporal ───────────────────────────────────────────────────
    with st.container():
        st.subheader("Consumo ao longo do tempo")
        granularidade = st.radio("Granularidade", ["Trimestral", "Mensal"], horizontal=True)
        freq = "QS" if granularidade == "Trimestral" else "MS"

        fig_serie = grafico_serie_temporal(df_filtrado, freq)                             # <- Função 1 - Série temporal
        st.plotly_chart(fig_serie, width="stretch")

    st.divider()

    # ── Rankings ──────────────────────────────────────────────────────────
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Top 10 fornecedores por valor")
        fig_top_fornecedores = grafico_top_fornecedores(df_filtrado)                       # <- Função 2 - Top fornecedores
        st.plotly_chart(fig_top_fornecedores, width="stretch")

    with col_b:
        st.subheader("Top 10 classes de material por valor")
        fig_top_classes = grafico_top_classes(df_filtrado)                                 # <- Função 3 - Top classes
        st.plotly_chart(fig_top_classes, width="stretch")

    st.divider()

    # ── Tabela detalhada ────────────────────────────────────────────────
    st.subheader("Dados filtrados")
    st.dataframe(
        df_filtrado[[
            "data_compra", "descricao_item", "nome_fornecedor", "nome_uasg", "estado",
            "quantidade", "preco_unitario", "valor_total",
        ]].sort_values("data_compra", ascending=False),
        width="stretch",
        height=300,
    )

with aba_projecao:
    serie_trimestral_full, ano_seguinte, n_trimestres_projecao = preparar_serie_trimestral_projecao(df, data_max)

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

    fig_projecao = grafico_projecao(serie_trimestral_full, projecao, desvio)               # <- Função 4 - Gráfico de projeção
    st.plotly_chart(fig_projecao, width="stretch")

    st.divider()

    # ── Tabela de cenários por trimestre ──────────────────────────────────
    st.subheader("Valores projetados por trimestre")
    tabela_projecao = tabela_cenarios_projecao(projecao, desvio)                           # <- Função 5 - Tabela de cenários
    st.dataframe(tabela_projecao, width="stretch", hide_index=True)

with aba_recomendacoes:
    st.subheader("Recomendações ao Departamento de Suprimentos")
    st.caption(
        "Gráficos baseados nas hipóteses de negócio testadas em "
        "notebooks/03_limpeza_eda.ipynb (seções 3.2 e 5.0). Calculado sobre a base completa "
        "(não respeita os filtros da barra lateral), para manter consistência com a validação "
        "estatística feita no notebook — os testes de significância (p-valores, correlações) "
        "não são recalculados aqui, só citados."
    )

    top_classes_valor = (
        df.groupby("nome_classe")["valor_total"].sum().sort_values(ascending=False).head(6).index.tolist()
    )

    # ── Resumo executivo ─────────────────────────────────────────────────
    st.markdown("#### Resumo executivo")
    st.markdown(
        "- **Escala de compra (H1):** consolidar pedidos reduz preço unitário (~0,49% por 1% de "
        "quantidade a mais), mas explica só ~27% da variação de preço — é uma alavanca real, não "
        "a única.\n"
        "- **Fornecedor > região (H2):** negociar com fornecedores reduz mais a variabilidade de "
        "preço do que centralizar compras por UASG/região, embora o efeito seja pequeno (~7%).\n"
        "- **Sazonalidade (H3):** demanda se concentra no início do ano civil — antecipar "
        "licitações reduz risco de desabastecimento; não há padrão de preço sazonal confiável "
        "para tentar comprar mais barato num mês específico.\n"
        "- **Regularidade de consumo (H4):** itens de consumo regular são bons candidatos a Ata "
        "de Registro de Preços (mais fáceis de planejar/negociar), independente de quantos "
        "fornecedores os atendem hoje.\n"
        "- **Orçamento 2027:** projeção naive sazonal aponta ~R$ 413 milhões para o ano civil "
        "seguinte (aba *Projeção de consumo*), faixa de confiança ±R$ 64,3 milhões/trimestre.\n\n"
        "Todas as recomendações estão ancoradas em testes estatísticos formais (regressão OLS, "
        "Mann-Whitney, Kruskal-Wallis, correlação de Spearman) documentados em "
        "`notebooks/03_limpeza_eda.ipynb`, seção 5.0 — nenhuma extrapola além do que os números "
        "sustentam."
    )

    tabela_resumo = pd.DataFrame({
        "Hipótese": ["H1 — Economia de escala", "H2 — Fornecedor vs. UASG", "H3 — Sazonalidade", "H4 — Regularidade de consumo"],
        "Achado": [
            "Preço unitário cai ~0,49% a cada 1% de aumento na quantidade (r²=0,27, p<0,001)",
            "CV de preço maior entre fornecedores do que entre UASGs (0,261 vs. 0,243; p=0,0096)",
            "Quantidade concentrada no início do ano civil (H=706,3, p<0,001)",
            "Menor regularidade de consumo → maior concentração de fornecedor (rho=-0,45, p<0,001)",
        ],
        "Recomendação": [
            "Consolidar pedidos entre UASGs para itens de alta recorrência",
            "Priorizar negociação com fornecedores sobre centralização regional",
            "Antecipar licitações antes da concentração de início de ano",
            "Usar regularidade para identificar candidatos a Ata de Registro de Preços",
        ],
    })
    st.dataframe(tabela_resumo, width="stretch", hide_index=True)

    st.divider()

    # ── H1 — Economia na quantidade comprada ────────────────────────────
    st.markdown("### H1 — Economia na quantidade comprada")
    st.markdown(
        "**Achado:** o preço unitário cai ~0,49% a cada 1% de aumento na quantidade comprada "
        "do mesmo item (slope=-0,489, r²=0,274, p<0,001, n=153.645 transações).\n\n"
        "**Recomendação:** para itens de alta recorrência, priorizar a consolidação de pedidos "
        "entre UASGs (compras conjuntas / atas de registro de preço compartilhadas) em vez de "
        "compras fracionadas por unidade. O ganho de escala é estatisticamente robusto, ainda "
        "que o R² de 0,27 indique que quantidade explica só parte da variação de preço — a "
        "decisão de compra não deve se basear apenas em volume."
    )
    elasticidade_classe = calcular_elasticidade_por_classe(df, top_classes_valor)
    fig_h1 = grafico_elasticidade_h1(elasticidade_classe)                                  # <- Função 6 - H1: elasticidade preço-quantidade
    st.plotly_chart(fig_h1, width="stretch")
    st.caption(
        "Verificação de robustez a outliers (IQR k=3 por item, seção 2.3.3 do notebook): "
        "removendo os pontos extremos de preço/quantidade já identificados, o slope muda pouco "
        "em qualquer recorte — ex. Transformadores para Estação de Força e Distribuição: "
        "slope -0,672→-0,667, r²=0,504→0,515 (n=678→579). No agregado (todas as classes), "
        "slope -0,489→-0,480, r²=0,274→0,234 (n=153.645→133.411). A elasticidade é calculada em "
        "escala log(quantidade) x log(preço), o que já comprime a cauda extrema — por isso a "
        "conclusão de H1 não depende de poucas compras de volume muito alto."
    )

    st.divider()

    # ── H2 — Variabilidade de preço: fornecedor vs. UASG ────────────────
    st.markdown("### H2 — Variabilidade de preço: fornecedor vs. UASG")
    st.markdown(
        "**Achado:** a variabilidade de preço dentro do mesmo item é maior entre fornecedores "
        "do que entre UASGs (mediana CV fornecedor=0,261 vs. mediana CV UASG=0,243; "
        "Mann-Whitney p=0,0096). Efeito estatisticamente significativo, mas de magnitude "
        "pequena (~7% de diferença relativa entre as medianas).\n\n"
        "**Recomendação:** direcionar esforço de negociação para o relacionamento com "
        "fornecedores (condições contratuais, prazos, descontos por fidelidade) em vez de "
        "estratégias de centralização de compras por região/UASG — sem tratar isso como "
        "alavanca prioritária, dado o tamanho de efeito modesto."
    )
    cv_fornecedor, cv_uasg = calcular_cv_h2(df)
    fig_h2 = grafico_cv_h2(cv_fornecedor, cv_uasg)                                         # <- Função 7 - H2: CV fornecedor vs. UASG
    st.plotly_chart(fig_h2, width="stretch")

    st.divider()

    # ── H3 — Sazonalidade ────────────────────────────────────────────────
    st.markdown("### H3 — Sazonalidade de preço e quantidade")
    st.markdown(
        "**Achado:** a quantidade comprada varia significativamente por mês, com concentração "
        "no início do ano civil (Kruskal-Wallis H=706,32, p=2,38e-144). O preço unitário também "
        "varia entre meses (H=98,48, p=3,58e-16), mas sem padrão sazonal visualmente "
        "consistente.\n\n"
        "**Recomendação:** antecipar o planejamento de demanda e os processos licitatórios para "
        "itens elétricos antes da concentração observada no início do ano, reduzindo o risco de "
        "desabastecimento ou compras emergenciais mais caras. Não recomendamos tentar cronometrar "
        "compras visando preço mais baixo em determinado mês — o achado de sazonalidade de preço "
        "não é confiável o suficiente para orientar essa decisão."
    )
    sazonalidade_h3 = calcular_sazonalidade_h3(df)
    fig_h3 = grafico_sazonalidade_h3(sazonalidade_h3)                                      # <- Função 8 - H3: sazonalidade
    st.plotly_chart(fig_h3, width="stretch")

    st.divider()

    # ── H4 — Regularidade de consumo ─────────────────────────────────────
    st.markdown("### H4 — Regularidade de consumo")
    st.markdown(
        "**Achado:** quanto menor a regularidade de consumo de um item, maior a concentração de "
        "fornecedores (HHI) que o atendem (rho=-0,451, p=8,31e-198, n=3.970 itens).\n\n"
        "**Recomendação:** o Índice de Regularidade de Consumo não é um proxy de risco de "
        "fornecimento (isso já é coberto por H2, via variabilidade de preço entre fornecedores). "
        "Ele é, na verdade, um sinal separado e útil por si só — indica candidatos a contrato de "
        "fornecimento recorrente/previsível (ex: Ata de Registro de Preços), porque um item com "
        "consumo regular é mais fácil de planejar e negociar com antecedência do que um item de "
        "demanda errática, independente de quantos fornecedores existam para ele."
    )
    hhi_quartis_h4 = calcular_hhi_por_quartil_h4(df)
    fig_h4 = grafico_hhi_h4(hhi_quartis_h4)                                                # <- Função 9 - H4: HHI por regularidade
    st.plotly_chart(fig_h4, width="stretch")
    st.caption(
        "Atenção — este é o achado mais sensível a outliers dos quatro: `regularidade_consumo` é "
        "uma razão média/desvio padrão do valor mensal por item, e um único mês atípico (ex. uma "
        "licitação isolada de grande volume) infla o desvio padrão e derruba artificialmente o "
        "índice, fazendo um item de consumo estável parecer 'irregular'. Diferente de H2/H3, que "
        "usam mediana e testes de rank (robustos por construção), aqui vale checar manualmente o "
        "histórico mensal antes de descartar um item como candidato a Ata de Registro de Preços."
    )
