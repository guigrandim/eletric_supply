# ⚡ Materiais Elétricos — Compras Públicas | Analytics de Suprimentos

Dashboard analítico e pipeline de dados sobre compras públicas de materiais elétricos, construído para apoiar decisões da área de Suprimentos de uma empresa do setor elétrico.

![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.59-FF4B4B?logo=streamlit&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly-6.9-3F4F75?logo=plotly&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-3.2-006ACC)
![License](https://img.shields.io/badge/license-MIT-green)

⚠️ O app pode levar ~30s para inicializar se estiver inativo.

Link para o projeto: https://eletricsupply.streamlit.app

<p align="center">
<img src="./assets/img/fluxo.png" alt="Fluxo do Projeto - Materiais Elétricos, Compras Públicas" width="800px">
</p>

### 🎯 Destaques
- Construí um pipeline completo — extração via API pública, banco relacional em esquema estrela e dashboard de 3 abas — sobre **164.680 registros** de compras públicas de materiais elétricos (2021–2026), dando à área de Suprimentos autoatendimento analítico em minutos.
- Validei **4 hipóteses de negócio** com testes não-paramétricos, incluindo um achado contra-intuitivo: itens de consumo irregular têm **maior**, não menor, concentração de fornecedor (ρ=-0,451, p≈8,3e-198) — um proxy real de risco de ruptura de suprimento.
- Comparei 6 métodos de projeção de consumo em backtest real contra dados de 2026: o método mais simples (naive sazonal) venceu o XGBoost por larga margem (**MAPE 15,5% vs. 51,4%**), decisão de modelo orientada por evidência, não por complexidade.

---

## 🚨 Problema de Negócio

A área de Suprimentos de uma empresa do setor elétrico compra materiais elétricos (transformadores, cabos, disjuntores, chaves, isoladores, ferragens) de forma recorrente através de licitações públicas registradas no Compras.gov.br.

Até então, decisões como consolidação de compras entre unidades, negociação com fornecedores, antecipação de demanda sazonal e planejamento orçamentário para o ano seguinte não tinham uma leitura consolidada do histórico de mercado — sem visibilidade clara sobre padrões de preço, variabilidade e risco de dependência de fornecedor.

**Pergunta central:** Que padrões, tendências e riscos existem nas compras públicas de materiais elétricos, e quanto a área deve esperar gastar no próximo ano?

**Minha tarefa:** construir sozinho o pipeline completo — da extração de dados via API até o dashboard final — formular e testar hipóteses de negócio, projetar consumo para o ano seguinte com metodologia e limitações explícitas, e traduzir tudo isso em recomendações acionáveis para Suprimentos.

---

## 🗺️ Planejamento da Solução

A solução foi estruturada seguindo a metodologia **CRISP-DS**, em 3 notebooks sequenciais seguidos de um dashboard interativo:

1. **Extração e carga** — validação isolada da API, depois coleta paralela com rate limiter (thread-safe) e retry com backoff exponencial, escrita num banco SQLite em esquema estrela, com lógica de retomada de coleta interrompida.

2. **Tratamento e padronização** — tipagem corrigida, deduplicação de fornecedor por CNPJ, tratamento de nulos sem imputação global (decisão deliberada, documentada por coluna).

3. **Análise exploratória e hipóteses de negócio** — univariada, bivariada e multivariada; testes não-paramétricos (curtose ≈ 20.816 nos dados de preço/quantidade inviabiliza métodos paramétricos); validação de 4 hipóteses (H1–H4), incluindo um índice de regularidade de consumo adaptado da Ciência do Esporte (monotonia = média/desvio padrão do gasto mensal por item).

4. **Projeção de consumo** — diagnóstico de volatilidade por granularidade (mensal descartada, trimestral adotada), backtest comparando 6 métodos de projeção contra dados reais de 2026.

5. **Construção do dashboard** — aplicação Streamlit multi-página com filtros por período, estado, classe CATMAT e fornecedor, KPIs, série temporal, rankings, projeção e recomendações consolidadas.

**Ferramentas:** Python (Pandas, NumPy, SciPy, statsmodels, scikit-learn, XGBoost), SQLite, Streamlit, Plotly. Código escrito com apoio do Claude Code; definição das hipóteses, testes estatísticos e interpretação dos resultados são autorais.

---

## 🛠️ Desenvolvimento

### Dataset

| Atributo | Detalhe |
|---|---|
| Fonte | API do Portal de Dados Abertos — `dadosabertos.compras.gov.br` |
| Escopo | Grupos CATMAT 59 e 61 — 7 classes de materiais elétricos |
| Granularidade | 1 linha = 1 item comprado (preço praticado) |
| Integridade | Verificação de nulos por coluna, deduplicação de fornecedor por CNPJ, validação cruzada contra o banco (contagem de linhas, chave única, amostragem) |

### Abas do Dashboard

1. **Visão Geral**
- Focada em consumo agregado, evolução temporal e os principais fornecedores e classes de material.
- Métricas Chave: Valor total, nº de compras, fornecedores únicos, UASGs únicas, ticket médio.
- Gráficos: Série temporal (mensal/trimestral), Top 10 fornecedores por valor, Top 10 classes, tabela detalhada filtrável por período/estado/classe/fornecedor.

2. **Projeção de Consumo**
- Focada no cenário de gasto esperado para o próximo ano civil, com a incerteza sempre visível.
- Métricas Chave: Total projetado (≈R$ 413 milhões para 2027), faixa de confiança de ±1 desvio padrão histórico por trimestre.
- Gráficos: Série histórica + projeção naive sazonal com banda de confiança, tabela de cenários (pior/base/melhor) por trimestre.

3. **Recomendações ao Departamento de Suprimentos**
- Síntese executiva que consolida as 4 hipóteses de negócio validadas em ação recomendada.
- Métricas Chave: tabela-resumo H1–H4 (achado estatístico + recomendação de ação).
- Gráficos: um gráfico de apoio por hipótese — elasticidade preço x quantidade (H1), variabilidade por fornecedor x UASG (H2), sazonalidade mensal (H3), regularidade x concentração de fornecedor/HHI (H4).

### Métodos de Projeção Avaliados

| Método | Complexidade | MAPE (backtest 2026) |
|---|---|---|
| **Naive Sazonal ✅** | 0 parâmetros | **15,5%** |
| Holt-Winters | 3 parâmetros | 14,6% |
| Média simples | 0 parâmetros | 22,6% |
| Naive + tendência | 1 parâmetro | 25,4% |
| Média móvel (4 trimestres) | 0 parâmetros | 46,3% |
| XGBoost | 50 árvores | 51,4% |

O **naive sazonal** (repete o valor do mesmo trimestre do ano anterior) foi escolhido em detrimento do XGBoost por vencer o backtest com folga — com apenas 13–17 trimestres de histórico, o XGBoost sofreu overfitting e teve o pior resultado entre todos os métodos testados. O Holt-Winters ficou estatisticamente próximo do naive (diferença de 0,9 p.p., não confiável com só 2 pontos de teste), mas exige 3 parâmetros ajustados — pela navalha de Occam, entre métodos com desempenho equivalente, o mais simples e interpretável venceu.

A granularidade também foi decidida por evidência: agregação **mensal** foi descartada (CV=1,12, piora para 1,29 sem outliers — ruído estrutural de licitações públicas, não outliers pontuais) em favor da agregação **trimestral** (CV=0,58), que estabiliza a série o suficiente para um backtest confiável.

### Estrutura do Projeto

```text
eletric_supply/
├── assets/             # Banco de dados SQLite (esquema estrela) e imagens usadas no dashboard/README
├── notebooks/          # 01 validação da API · 02 extração e carga no banco · 03 limpeza, EDA e projeção
├── sql/                # Script de criação do schema e queries de validação (contagem, órfãos, nulos)
├── pages/              # Página secundária do dashboard Streamlit (Dashboard)
├── utils/              # Reservado para módulo compartilhado (config, conexão com o banco)
├── .gitignore          # Arquivos e pastas ignorados pelo Git
├── Home.py             # Ponto de entrada do dashboard Streamlit (resumo do projeto e navegação)
├── LICENSE             # Licença MIT do projeto
├── README.md           # Documentação principal do projeto
└── requirements.txt    # Lista de bibliotecas Python necessárias
```

### Como Executar Localmente

```bash
git clone https://github.com/guigrandim/eletric_supply.git
cd eletric_supply
pip install -r requirements.txt
streamlit run Home.py
```

> O banco `assets/data/database.db` já está versionado no repositório — a aplicação roda direto, sem precisar re-executar os notebooks de extração. Para regenerar os dados do zero (ex. período mais recente), rode `notebooks/01` e `notebooks/02` nesta ordem.

---

## 💡 Top Insights

### 1. 📉 Comprar mais reduz o preço unitário — economia de escala confirmada

**H1 confirmada** — regressão log-log entre quantidade e preço unitário mostra relação negativa robusta (slope=-0,489, r²=0,274, p<0,001, n=153.645). Suprimentos pode usar isso de forma direta: consolidar compras de itens recorrentes entre UASGs via atas compartilhadas gera ganho de escala mensurável.

---

### 2. 🏭 A variabilidade de preço está mais ligada ao fornecedor do que à unidade compradora — mas o efeito é pequeno

**H2 confirmada, efeito pequeno** — o coeficiente de variação de preço é maior entre fornecedores (mediana 0,261) do que entre UASGs (mediana 0,243), diferença estatisticamente significativa (p=0,0096) mas de baixa magnitude. Direciona esforço de negociação para o fornecedor, mas não justifica uma reestruturação de compras baseada só nesse achado.

---

### 3. 📅 A quantidade comprada varia fortemente ao longo do ano — o preço, não

**H3 parcialmente confirmada** — a quantidade comprada por mês varia de forma fortemente significativa (Kruskal-Wallis H=706,3, p≈2,4e-144), concentrada no início do ano civil. Já a sazonalidade de preço, embora estatisticamente significativa, não tem um padrão prático interpretável — decisão consciente de não superinterpretar esse segundo resultado.

---

### 4. ⚠️ Itens comprados de forma irregular têm MAIS dependência de fornecedor, não menos

**H4 confirmada, contra-intuitivo** — usando um índice de regularidade de consumo (monotonia = média/desvio padrão do gasto mensal, conceito adaptado da Ciência do Esporte) cruzado com o Herfindahl-Hirschman Index (HHI) de concentração de fornecedor por item, encontrei correlação negativa forte (ρ=-0,451, p≈8,3e-198, n=3.970): quanto mais esporádica e imprevisível a compra de um item, maior a concentração em poucos fornecedores dispostos a atendê-la. Vira recomendação direta de qualificar fornecedores alternativos para esses itens.

---

## 📊 Resultados

### Resultado da Entrega

O dashboard substituiu a consulta manual e pontual ao histórico de compras por um painel de autoatendimento: a área de Suprimentos passa a filtrar por período, estado, classe CATMAT e fornecedor, ver KPIs e rankings em segundos, e consultar uma síntese executiva com as 4 hipóteses validadas — achado, recomendação e gráfico de apoio — sem depender de leitura do notebook técnico a cada decisão.

<p align="center">
<img src="./assets/img/schema_sem_tratamento.png" alt="Esquema do banco de dados (esquema estrela)" width="700px">
</p>

### Projeção de Consumo — Ano Civil de 2027

Método de produção: **naive sazonal**, com faixa de confiança heurística de ±1 desvio padrão histórico (≈ R$ 64,3 milhões por trimestre).

| Trimestre | Valor projetado |
|---|---|
| Jan–Mar/27 | R$ 75,3 milhões |
| Abr–Jun/27 | R$ 72,1 milhões |
| Jul–Set/27 | R$ 150,4 milhões |
| Out–Dez/27 | R$ 115,6 milhões |
| **Total 2027** | **≈ R$ 413 milhões** |

---

## ✅ Conclusões

A solução cobre o ciclo completo de um projeto de analytics aplicado a Suprimentos — extração via API, tratamento e estruturação em banco relacional, EDA com hipóteses testadas estatisticamente, projeção de consumo com metodologia e limitações explícitas, dashboard interativo e recomendações ancoradas em achados específicos, sem extrapolação além do que os dados suportam.

**Próximos passos:**
- Reavaliar a escolha do método de projeção (naive sazonal vs. Holt-Winters vs. XGBoost) a cada novo trimestre real disponível.
- Projetar por classe/grupo CATMAT, não só no agregado do portfólio.
- Extrair a lógica duplicada de cálculo (CV, HHI, elasticidade) entre notebook e dashboard para um módulo compartilhado em `utils/`.
- Migrar `database.db` para Git LFS ou storage externo (hoje versionado diretamente no repositório).

**Limitações:** o backtest da projeção usou apenas 2 trimestres reais de 2026 — MAPE tem alta variância com tão poucos pontos; a amostra de treino é pequena (13–17 trimestres), o que penaliza modelos de ML mais complexos frente a baselines simples; a faixa de confiança é heurística (±1 desvio padrão), não um intervalo de predição estatístico formal; a projeção não incorpora eventos futuros conhecidos (reajustes contratuais, novas licitações de grande porte, câmbio para itens importados).

---

*📊 Dados: Portal de Dados Abertos, Compras.gov.br (CATMAT 59 e 61) · 🗓️ 2021–2026 · 🧮 CRISP-DS · 📈 Streamlit + Plotly*

## 🧰 Skills Demonstradas

- **Engenharia de dados:** extração via API com rate limiting e retry, banco relacional em esquema estrela, pipeline resumível.
- **Estatística aplicada:** testes não-paramétricos (Mann-Whitney, Kruskal-Wallis, Spearman) justificados por diagnóstico de curtose/assimetria, em vez de aplicar testes paramétricos por padrão.
- **Séries temporais:** diagnóstico de granularidade por coeficiente de variação, backtest comparando 6 métodos de projeção, feature engineering sem vazamento temporal.
- **Visualização de dados:** dashboard Streamlit multi-página com filtros, KPIs e projeção interativa.
- **Comunicação executiva:** tradução de 4 hipóteses estatísticas em recomendações acionáveis para Suprimentos, com transparência sobre efeitos pequenos vs. grandes.

## 👩‍💻 Autor

Desenvolvido por Guilherme Grandim como um projeto de portfólio em Ciências/Análise de Dados.
Sinta-se à vontade para entrar em contato ou contribuir com o projeto!
Linkedin: [🔗](https://www.linkedin.com/in/guilherme-grandim/)
Gmail: [📧](mailto:gui.grandim@gmail.com)

## 📄 Licença

Este projeto está sob a licença MIT — veja [LICENSE](./LICENSE) para detalhes.
