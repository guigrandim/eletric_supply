"""
Materiais Elétricos — Compras Públicas | Home
==============================================
Ponto de entrada da aplicação Streamlit.
Define a navegação multi-página e renderiza o conteúdo da Home.

Autor: Guilherme Grandim
"""

#==================================
# Import Library
#==================================

import streamlit as st
from pathlib import Path

#==================================
# Configuration Page
#==================================

st.set_page_config(page_title="Home", page_icon="⚡", layout="wide")

# ==================================
# Caminhos dos Assets
# ==================================

base_dir = Path(__file__).parents[0]
img_dir = base_dir / "assets" / "img"

fluxo_img = img_dir / "fluxo.png"

# ==================================
# Páginas
# ==================================

def render_home() -> None:
    """
    Renderiza o conteúdo da página Home.
    Exibe resumo do projeto, escopo dos dados e o fluxo do projeto.
    """
    st.title("Materiais Elétricos — Compras Públicas")
    st.caption(
        "Projeto de portfólio em Data Analytics — apoio a decisões da área de Suprimentos"
    )

    st.divider()

    st.markdown("## Resumo do Projeto")
    st.markdown(
        """
        Solução que consome, trata, analisa e apresenta dados públicos de compras de
        materiais elétricos do Portal de Dados Abertos do Compras.gov.br, restrita aos
        grupos CATMAT **59** (Componentes Elétricos) e **61** (Condutores Elétricos e
        Equipamentos para Geração e Distribuição de Energia), para apoiar decisões da
        área de Suprimentos.

        - **Extração**: API `dadosabertos.compras.gov.br`, com carga num banco SQLite
          em esquema estrela.
        - **Tratamento e EDA**: limpeza, padronização, hipóteses de negócio (H1-H4) e
          testes estatísticos em `notebooks/03_limpeza_eda.ipynb`.
        - **Projeção**: consumo estimado para os próximos 4 trimestres (naive
          sazonal), com metodologia e limitações documentadas.
        - **Dashboard**: filtros por período, estado, classe de material e fornecedor,
          KPIs, série temporal, rankings e gráfico de projeção.

        Use o menu lateral para acessar o **Dashboard**.
        """
    )

    st.divider()
    
    st.markdown("## Navegação das Abas do Dashboard")
    st.markdown(
        """
        As abas que compõem o dashboard ao navegar são:

        1. **Visão Geral:** Focada em consumo agregado, evolução temporal e os principais fornecedores e classes de material.
            - **Métricas Chave:** Valor total, nº de compras, fornecedores únicos, UASGs únicas, ticket médio.
            - **Gráficos:** Série temporal (mensal/trimestral), Top 10 fornecedores por valor, Top 10 classes, tabela detalhada filtrável por período/estado/classe/fornecedor.
        
        ---
        
        2. **Projeção de Consumo:** Focada no cenário de gasto esperado para o próximo ano civil, com a incerteza sempre visível.
            - **Métricas Chave:** Total projetado com faixa de confiança de ±1 desvio padrão histórico por trimestre.
            - **Gráficos:** Série histórica + projeção naive sazonal com banda de confiança, tabela de cenários (pior/base/melhor) por trimestre.

        ---
        
        3. **Recomendações ao Departamento de Suprimentos:** Síntese executiva que consolida as 4 hipóteses de negócio validadas em ação recomendada.
            - **Métricas Chave:** Tabela-resumo H1-H4 (achado estatístico + recomendação de ação).
            - **Gráficos:** Um gráfico de apoio por hipótese — elasticidade preço x quantidade (H1), variabilidade por fornecedor x UASG (H2), sazonalidade mensal (H3), regularidade x concentração de fornecedor/HHI (H4).
        """
    )

    st.divider()
    
    st.markdown("## Fluxo do Projeto")
    if fluxo_img.exists():
        st.image(str(fluxo_img), width="stretch")
    else:
        st.warning("Imagem do fluxo do projeto não encontrada.")


def build_navigation() -> st.navigation:
    """
    Constrói e retorna o objeto de navegação com todas as páginas do dashboard.

    Retorna:
        st.navigation: Objeto de navegação configurado com as páginas do app.
    """
    home = st.Page(render_home, title="Home", icon="🏠")
    dashboard = st.Page("pages/1_Dashboard.py", title="Dashboard", icon="⚡")

    return st.navigation([home, dashboard])

# ==================================
# Entry Point
# ==================================

def main() -> None:
    """
    Função principal da aplicação.
    Inicializa a navegação e executa a página ativa.
    """
    pg = build_navigation()
    pg.run()


main()
