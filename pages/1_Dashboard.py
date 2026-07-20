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
from scipy.stats import linregress, zscore

#==================================
# Configuration Page
#==================================

# st.set_page_config já foi chamado em Home.py — uma página filha chamando de
# novo dispara StreamlitAPIException, por isso não é repetido aqui.
CAMINHO_BANCO = Path(__file__).parents[1] / "assets" / "data" / "database.db"

#===================================
# Functions
#===================================

def outlier_iqr(g, k=3):
    """
    Identifica outliers em uma série numérica pelo método do IQR — mesma
    função usada no notebook 03 (seção 2.3.3, célula de Helper Functions),
    replicada aqui para que o recálculo de H1 no dashboard aplique o mesmo
    filtro de outlier da análise validada.

    Responde às perguntas:
    "Este ponto deve ser tratado como outlier ao recalcular a elasticidade
    preço-quantidade por classe?"

    Parâmetros
    ----------
    g : pd.Series
        Série numérica ou grupo de dados (uso típico via
        groupby().transform() para isolar anomalias por item).
    k : float, opcional (padrão=3)
        Multiplicador do IQR. k=3 identifica outliers extremos.

    Retorna
    -------
    pd.Series
        Booleana (True = outlier), mesmo tamanho e índice do input.
    """
    q1, q3 = g.quantile([0.25, 0.75])
    iqr = q3 - q1
    return (g < q1 - k * iqr) | (g > q3 + k * iqr)


def formatar_valor_compacto(valor):
    """
    Formata um valor em reais de forma compacta (mil/mi/bi), evitando que
    números grandes estourem a largura dos cards de métrica em layouts com
    várias colunas lado a lado.

    Parâmetros
    ----------
    valor : float
        Valor em reais a ser formatado.

    Retorna
    -------
    str
        Valor formatado, ex. "R$ 2,11 mi", "R$ 413,00 mi", "R$ 8.200".
    """
    if abs(valor) >= 1_000_000_000:
        return f"R$ {valor / 1_000_000_000:,.2f} bi"
    if abs(valor) >= 1_000_000:
        return f"R$ {valor / 1_000_000:,.2f} mi"
    if abs(valor) >= 1_000:
        return f"R$ {valor / 1_000:,.2f} mil"
    return f"R$ {valor:,.0f}"


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

    # Erro de dado pontual: 4 lançamentos de "ISOLADOR EPOXI" (código 77127) em
    # 03/12/2021, fornecedor Sartorius (fabricante de equipamento de
    # laboratório) para o Instituto de Tecnologia em Imunobiológicos, a
    # R$30-31 milhões/unidade — as outras 69 compras do mesmo item no resto
    # da base custam entre R$4,49 e R$2.720,00. Fornecedor e comprador não
    # combinam com o item (isolador elétrico), indicando erro de
    # classificação/preço no catálogo, não uma compra real. Sozinhas, essas 4
    # linhas somam ~R$123 milhões e distorcem a série temporal e a projeção.
    df = df[~((df["codigo_item_catalogo"] == 77127) & (df["preco_unitario"] > 1_000_000))]

    # Erro sistemático (mesma lógica documentada no notebook 03, seção 1.9):
    # itens comuns (cabo, fio, eletroduto, chave elétrica) vendidos a preço de
    # equipamento pesado. Três filtros combinados, nenhum sozinho é
    # suficiente: (1) preço > R$500 mil (mesmo piso da seção 1.8, evita marcar
    # itens baratíssimos cuja razão explode sem magnitude real); (2) preço >=
    # 1.000x a mediana do próprio item (isola o item incompatível com o que
    # ele normalmente custa); (3) comprador não é uma grande concessionária/
    # geradora (CHESF, FURNAS, Eletronorte, EPE compram equipamento de
    # subestação legitimamente nessa faixa, mesmo sob código genérico
    # compartilhado com itens baratos). Preserva a variação real de preço na
    # série temporal dos dois lados, em vez de só cortar tudo acima de um teto.
    grandes_concessionarias = ["CHESF", "FURNAS", "ELETRONORTE", "CENTRAIS ELETRICAS DO NORTE", "EPE-CIA"]
    eh_grande_concessionaria = df["nome_uasg"].str.contains("|".join(grandes_concessionarias), case=False, na=False)
    mediana_por_item = df.groupby("codigo_item_catalogo")["preco_unitario"].transform("median")
    razao_mediana_item = df["preco_unitario"] / mediana_por_item
    outlier_preco_incompativel = (
        (df["preco_unitario"] > 500_000) & (razao_mediana_item >= 1000) & (~eh_grande_concessionaria)
    )
    df = df[~outlier_preco_incompativel]

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
        .reset_index()
    )
    fig = px.bar(
        top_fornecedores, x="valor_total", y="nome_fornecedor", orientation="h",
        labels={"valor_total": "Valor total (R$)", "nome_fornecedor": ""},
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
        .reset_index()
    )
    fig = px.bar(
        top_classes, x="valor_total", y="nome_classe", orientation="h",
        labels={"valor_total": "Valor total (R$)", "nome_classe": ""},
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
    17,6% vs. 20,0% do XGBoost.

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
    Calcula, por classe de material, quanto o preço unitário cai (%) quando a
    quantidade comprada de um item dobra. Deriva dessa mesma regressão
    log-log da hipótese H1 (elasticidade preço-quantidade), mas convertida
    para uma grandeza interpretável por um time não técnico.

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
        Uma linha por classe, com "desconto_dobro_pct" (queda percentual no
        preço unitário ao dobrar a quantidade comprada) ordenada de forma
        decrescente — maior valor = desconto por volume mais forte. Já
        exclui outliers de preço/quantidade (IQR k=3 por item, mesmo filtro
        do notebook seção 2.3.3), via outlier_iqr().
    """
    freq_item = df.groupby("codigo_item_catalogo")["id_compra_item"].transform("count")
    sub = df[(freq_item >= 10) & (df["nome_classe"].isin(classes_top))].dropna(
        subset=["quantidade", "preco_unitario", "nome_classe"]
    ).copy()

    # mesmo filtro de outlier do notebook (seção 2.3.3): IQR k=3, por item
    outlier_preco = sub.groupby("codigo_item_catalogo")["preco_unitario"].transform(outlier_iqr)
    outlier_quantidade = sub.groupby("codigo_item_catalogo")["quantidade"].transform(outlier_iqr)
    sub = sub[~(outlier_preco | outlier_quantidade)]

    linhas = []
    for classe, grupo in sub.groupby("nome_classe"):
        x = np.log1p(grupo["quantidade"])
        y = np.log1p(grupo["preco_unitario"])
        slope, *_ = linregress(x, y)
        desconto_dobro_pct = (1 - 2 ** slope) * 100
        linhas.append({"nome_classe": classe, "desconto_dobro_pct": desconto_dobro_pct})

    return pd.DataFrame(linhas).sort_values("desconto_dobro_pct", ascending=False).reset_index(drop=True)


def grafico_elasticidade_h1(elasticidade_classe):
    """
    Gera um gráfico de barras horizontais com a queda percentual no preço
    unitário ao dobrar a quantidade comprada, por classe de material
    (hipótese H1).

    Responde às perguntas:
    "Em quais classes de material a economia de escala é mais forte?"
    "Existe alguma classe sem desconto por volume?"

    Parâmetros
    ----------
    elasticidade_classe : pd.DataFrame
        Saída de calcular_elasticidade_por_classe().

    Retorna
    -------
    fig : plotly.graph_objects.Figure
        Gráfico de barras horizontais com linha de referência em zero e o
        valor percentual escrito ao lado de cada barra.
    """
    fig = px.bar(
        elasticidade_classe, x="desconto_dobro_pct", y="nome_classe", orientation="h",
        labels={
            "desconto_dobro_pct": "Queda no preço unitário ao dobrar a quantidade comprada (%)",
            "nome_classe": "",
        },
        title="Quanto o preço unitário cai ao dobrar o pedido, por classe (top 6 por valor)",
        text="desconto_dobro_pct",
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
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
    Gera um boxplot comparando a distribuição do CV do preço unitário entre
    fornecedores e entre UASGs (hipótese H2) — mesmo gráfico do notebook
    (seção 3.2), que mostra a dispersão completa das duas distribuições em
    vez de só a mediana, deixando mais claro visualmente qual grupo tem mais
    variabilidade de preço.

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
        Boxplot com uma caixa por grupo, sem outliers — mesmo critério do
        notebook (`showfliers=False`, cerca de 1,5×IQR acima do 3º
        quartil). Diferente do matplotlib, o boxplot do Plotly com
        `points=False` não limita sozinho o whisker a essa cerca — ele
        estica até o mínimo/máximo real dos dados, então os pontos além da
        cerca são removidos aqui antes de plotar, replicando o
        comportamento do notebook.
    """
    def sem_outliers(serie):
        q1, q3 = serie.quantile(0.25), serie.quantile(0.75)
        limite = q3 + 1.5 * (q3 - q1)
        return serie[serie <= limite]

    dados = pd.concat([
        pd.DataFrame({"Grupo": "Por Fornecedor", "CV do preço": sem_outliers(cv_fornecedor).values}),
        pd.DataFrame({"Grupo": "Por UASG", "CV do preço": sem_outliers(cv_uasg).values}),
    ], ignore_index=True)
    fig = px.box(
        dados, x="Grupo", y="CV do preço", points=False,
        labels={"CV do preço": "Coeficiente de variação do preço unitário", "Grupo": ""},
        title="Variabilidade de preço do mesmo item — Fornecedor vs. UASG",
    )
    return fig


@st.cache_data
def calcular_sazonalidade_h3(df):
    """
    Calcula a quantidade mediana comprada por mês, por classe de material —
    mesma lógica da hipótese H3, mas segmentada por classe em vez de
    agregada no portfólio inteiro (necessário para o heatmap mês x classe).

    Responde às perguntas:
    "Existe concentração de demanda em algum período do ano civil?"
    "Esse padrão sazonal é igual para todas as classes de material, ou muda
    dependendo do tipo de material comprado?"

    Parâmetros
    ----------
    df : pd.DataFrame
        Base completa (carregar_dados()), sem filtro de UI.

    Retorna
    -------
    pd.DataFrame
        Uma linha por combinação (classe, mês 1-12), com a quantidade
        mediana comprada.
    """
    sub = df.dropna(subset=["data_compra", "nome_classe"]).copy()
    sub["mes_compra"] = sub["data_compra"].dt.month
    return (
        sub.groupby(["nome_classe", "mes_compra"])["quantidade"]
        .median()
        .reset_index()
    )


def grafico_sazonalidade_h3(sazonalidade_h3):
    """
    Gera um heatmap de quantidade mediana comprada por mês x classe de
    material (hipótese H3), com a escala de cor normalizada por linha (por
    classe), não global.

    A normalização por linha existe porque, numa escala de cor global,
    classes de menor volume ficam visualmente "escondidas" (quase uma única
    cor), dominadas pelas classes de maior volume — normalizando cada linha
    pelo próprio pico, o padrão sazonal de cada classe fica visível
    independente do volume absoluto que ela movimenta. O valor real
    (quantidade mediana, não normalizado) aparece no hover.

    Responde às perguntas:
    "Em quais meses a demanda por materiais elétricos é historicamente
    maior, e esse padrão muda dependendo da classe de material?"

    Parâmetros
    ----------
    sazonalidade_h3 : pd.DataFrame
        Saída de calcular_sazonalidade_h3() (colunas: nome_classe,
        mes_compra, quantidade).

    Retorna
    -------
    fig : plotly.graph_objects.Figure
        Heatmap classe (eixo Y) x mês (eixo X, nomes em pt-br); cor =
        intensidade relativa ao pico da própria classe (0 a 1).
    """
    nomes_mes = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
                 7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}

    #1. Pivota para classe (linha) x mês (coluna) com a quantidade mediana
    pivot = sazonalidade_h3.pivot(index="nome_classe", columns="mes_compra", values="quantidade")
    pivot = pivot.reindex(columns=range(1, 13))
    pivot.columns = [nomes_mes[m] for m in pivot.columns]

    #2. Normalização por linha (por classe) — cada classe escalada pelo seu
    # próprio pico, para classes de menor volume não ficarem escondidas
    pivot_normalizado = pivot.div(pivot.max(axis=1), axis=0)

    fig = go.Figure(data=go.Heatmap(
        z=pivot_normalizado.values,
        x=pivot_normalizado.columns,
        y=pivot_normalizado.index,
        customdata=pivot.values,
        hovertemplate="Classe: %{y}<br>Mês: %{x}<br>Quantidade mediana: %{customdata:,.1f}<extra></extra>",
        colorscale="YlOrRd",
        colorbar=dict(title="Intensidade<br>relativa"),
    ))
    fig.update_layout(
        title="Sazonalidade de demanda por classe (escala normalizada por classe)",
        xaxis_title="Mês",
        yaxis_title="Classe de material",
    )
    return fig


@st.cache_data
def calcular_hhi_por_quartil_h4(df):
    """
    Calcula o HHI médio (concentração de fornecedor) por quartil do índice
    de dependência (`indice_dependencia_v2`) — mesma fórmula da hipótese H4
    no notebook (seção 2.3.4): regularidade de consumo e gasto total do
    item, cada um em z-score, somados. Resumido em 4 quartis em vez do
    scatter item a item da seção 5.4.

    Responde às perguntas:
    "Itens de consumo mais regular (e de maior gasto) têm menos fornecedores
    concentrados, ou o índice é independente da concentração de mercado?"
    "Quais itens são bons candidatos a Ata de Registro de Preços com base na
    previsibilidade do consumo?"

    Parâmetros
    ----------
    df : pd.DataFrame
        Base completa (carregar_dados()), sem filtro de UI.

    Retorna
    -------
    pd.DataFrame
        Uma linha por quartil de indice_dependencia_v2, com o HHI médio.
    """
    valor_mensal_item = df.dropna(subset=["data_compra"]).groupby(
        ["codigo_item_catalogo", pd.Grouper(key="data_compra", freq="ME")]
    )["valor_total"].sum()

    regularidade_consumo = valor_mensal_item.groupby("codigo_item_catalogo").apply(
        lambda x: x.mean() / x.std() if x.std() > 0 else np.nan
    )
    gasto_total_item = valor_mensal_item.groupby("codigo_item_catalogo").sum()
    n_meses = valor_mensal_item.groupby("codigo_item_catalogo").count()

    df_regularidade = pd.DataFrame({
        "regularidade_consumo": regularidade_consumo,
        "gasto_total": gasto_total_item,
        "n_meses": n_meses,
    }).query("n_meses >= 6").dropna(subset=["regularidade_consumo"])

    # mesma combinação do notebook (seção 2.3.4): regularidade e gasto total
    # em z-score, para que nenhuma das duas dimensões domine pela escala.
    df_regularidade["indice_dependencia_v2"] = (
        zscore(df_regularidade["regularidade_consumo"])
        + zscore(np.log1p(df_regularidade["gasto_total"]))
    )

    participacao_sq = (
        df.dropna(subset=["codigo_item_catalogo", "ni_fornecedor", "valor_total"])
        .groupby(["codigo_item_catalogo", "ni_fornecedor"])["valor_total"].sum()
        .groupby(level=0, group_keys=False).apply(lambda x: (x / x.sum()) ** 2)
    )
    hhi_item = participacao_sq.groupby("codigo_item_catalogo").sum().rename("hhi")

    df_q = df_regularidade[["indice_dependencia_v2"]].join(hhi_item).dropna()
    df_q["quartil"] = pd.qcut(
        df_q["indice_dependencia_v2"], 4,
        labels=["Q1 (menos regular)", "Q2", "Q3", "Q4 (mais regular)"],
    )
    resultado = df_q.groupby("quartil", observed=True)["hhi"].mean().reset_index()
    # HHI (0-1) não é intuitivo fora de quem já conhece a métrica; convertido
    # para "número efetivo de fornecedores" (1/HHI) — ex. HHI=0,5 equivale a
    # 2 fornecedores dividindo o mercado igualmente — grandeza que qualquer
    # pessoa do time de Suprimentos lê diretamente como "quantos fornecedores
    # de fato disputam esse item".
    resultado["fornecedores_efetivos"] = 1 / resultado["hhi"]
    return resultado


def grafico_hhi_h4(hhi_quartis_h4):
    """
    Gera um gráfico de barras com o número efetivo de fornecedores (1/HHI)
    por quartil de regularidade de consumo (hipótese H4) — quanto mais
    regular o consumo do item, mais fornecedores efetivamente concorrem por
    ele, sustentando visualmente o insight de H4.

    Responde às perguntas:
    "Itens de consumo mais regular têm mais fornecedores concorrendo, ou o
    número de fornecedores é parecido independente da regularidade?"

    Parâmetros
    ----------
    hhi_quartis_h4 : pd.DataFrame
        Saída de calcular_hhi_por_quartil_h4().

    Retorna
    -------
    fig : plotly.graph_objects.Figure
        Gráfico de barras com o número efetivo de fornecedores por quartil
        de regularidade, do menos ao mais regular.
    """
    fig = px.bar(
        hhi_quartis_h4, x="quartil", y="fornecedores_efetivos", text_auto=".1f",
        labels={
            "quartil": "Regularidade de consumo do item",
            "fornecedores_efetivos": "Número efetivo de fornecedores concorrendo",
        },
        title="Quanto mais regular o consumo, mais fornecedores concorrem pelo item",
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
    ["Visão Geral", "Projeção de Consumo", "Recomendações ao Departamento de Suprimentos"]
)

with aba_visao_geral:
    # ── KPIs ─────────────────────────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Valor total", formatar_valor_compacto(df_filtrado['valor_total'].sum()))
    col2.metric("Compras", f"{len(df_filtrado):,}")
    col3.metric("Fornecedores únicos", f"{df_filtrado['ni_fornecedor'].nunique():,}")
    col4.metric("UASGs únicas", f"{df_filtrado['codigo_uasg'].nunique():,}")
    col5.metric("Ticket médio", formatar_valor_compacto(df_filtrado['valor_total'].mean()))

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
        "Projeção calculada sobre a base completa (não respeita os filtros acima), "
        "utilizando o método: naive sazonal — com MAPE de 17,6%.\n"
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
        "- **H1 — Economia de escala**\n"
        "  - Achado: Preço unitário cai ~0,49% a cada 1% de aumento na quantidade (r²=0,27, p<0,001)\n"
        "  - Recomendação: Consolidar pedidos entre UASGs para itens de alta recorrência\n"
        "- **H2 — Fornecedor vs. UASG**\n"
        "  - Achado: CV de preço maior entre fornecedores do que entre UASGs (0,260 vs. 0,243; p=0,0107)\n"
        "  - Recomendação: Priorizar negociação com fornecedores sobre centralização regional\n"
        "- **H3 — Sazonalidade**\n"
        "  - Achado: Quantidade concentrada no início do ano civil (H=708,8, p<0,001)\n"
        "  - Recomendação: Antecipar licitações antes da concentração de início de ano\n"
        "- **H4 — Regularidade de consumo**\n"
        "  - Achado: Menor regularidade de consumo → maior concentração de fornecedor (rho=-0,45, p<0,001)\n"
        "  - Recomendação: Mapear os itens com menor índice de regularidade de consumo e priorizar a qualificação de fornecedores alternativos para esse grupo"
    )

    st.divider()

    # ── H1 — Economia na quantidade comprada ────────────────────────────
    st.markdown("### H1 — Economia na quantidade comprada")
    st.markdown(
        "- **Insight:** Preço unitário cai ~0,49% a cada 1% de aumento na quantidade (r²=0,27, p<0,001)\n"
        "- **Recomendação:** Consolidar pedidos entre UASGs para itens de alta recorrência"
    )
    elasticidade_classe = calcular_elasticidade_por_classe(df, top_classes_valor)
    fig_h1 = grafico_elasticidade_h1(elasticidade_classe)                                  # <- Função 6 - H1: elasticidade preço-quantidade
    st.plotly_chart(fig_h1, width="stretch")

    st.divider()

    # ── H2 — Variabilidade de preço: fornecedor vs. UASG ────────────────
    st.markdown("### H2 — Variabilidade de preço: fornecedor vs. UASG")
    st.markdown(
        "- **Insight:** CV de preço maior entre fornecedores do que entre UASGs (0,260 vs. 0,243; p=0,0107)\n"
        "- **Recomendação:** Priorizar negociação com fornecedores sobre centralização regional"
    )
    cv_fornecedor, cv_uasg = calcular_cv_h2(df)
    fig_h2 = grafico_cv_h2(cv_fornecedor, cv_uasg)                                         # <- Função 7 - H2: CV fornecedor vs. UASG
    st.plotly_chart(fig_h2, width="stretch")

    st.divider()

    # ── H3 — Sazonalidade ────────────────────────────────────────────────
    st.markdown("### H3 — Sazonalidade de preço e quantidade")
    st.markdown(
        "- **Insight:** Quantidade concentrada no início do ano civil (H=708,8, p<0,001)\n"
        "- **Recomendação:** Antecipar licitações antes da concentração de início de ano"
    )
    sazonalidade_h3 = calcular_sazonalidade_h3(df)
    fig_h3 = grafico_sazonalidade_h3(sazonalidade_h3)                                      # <- Função 8 - H3: sazonalidade
    st.plotly_chart(fig_h3, width="stretch")

    st.divider()

    # ── H4 — Regularidade de consumo ─────────────────────────────────────
    st.markdown("### H4 — Regularidade de consumo")
    st.markdown(
        "- **Insight:** Menor regularidade de consumo → maior concentração de fornecedor (rho=-0,45, p<0,001)\n"
        "- **Recomendação:** mapear os itens com menor índice de regularidade de consumo e priorizar a qualificação de fornecedores alternativos para esse grupo"
    )
    hhi_quartis_h4 = calcular_hhi_por_quartil_h4(df)
    fig_h4 = grafico_hhi_h4(hhi_quartis_h4)                                                # <- Função 9 - H4: HHI por regularidade
    st.plotly_chart(fig_h4, width="stretch")
    st.caption(
        "Este gráfico mostra o padrão agregado por quartil — não identifica quais itens estão em "
        "cada grupo. Para levantar a lista de itens específicos do quartil 'menos regular' "
        "(candidatos à prospecção de fornecedores alternativos), seria necessário calcular o índice "
        "de regularidade item a item e cruzar com a descrição do material."
    )
