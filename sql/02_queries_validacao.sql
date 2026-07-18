
-- 1. Contagem geral por tabela
SELECT 'dim_material' AS tabela, COUNT(*) AS total FROM dim_material
UNION ALL
SELECT 'dim_fornecedor', COUNT(*) FROM dim_fornecedor
UNION ALL
SELECT 'dim_uasg', COUNT(*) FROM dim_uasg
UNION ALL
SELECT 'fato_precos_praticados', COUNT(*) FROM fato_precos_praticados;

-- 2. Registros do fato sem correspondência em dim_material (órfãos)
SELECT COUNT(*) AS itens_orfaos
FROM fato_precos_praticados f
LEFT JOIN dim_material m ON f.codigo_item_catalogo = m.codigo_item
WHERE m.codigo_item IS NULL;

-- 3. Valores nulos ou zerados em campos críticos
SELECT
    SUM(CASE WHEN preco_unitario IS NULL OR preco_unitario <= 0 THEN 1 ELSE 0 END) AS preco_invalido,
    SUM(CASE WHEN quantidade IS NULL OR quantidade <= 0 THEN 1 ELSE 0 END) AS quantidade_invalida,
    SUM(CASE WHEN ni_fornecedor IS NULL THEN 1 ELSE 0 END) AS fornecedor_nulo
FROM fato_precos_praticados;

-- 4. Top 10 materiais por volume de registros
SELECT m.nome_classe, m.descricao_item, COUNT(*) AS qtd_registros
FROM fato_precos_praticados f
JOIN dim_material m ON f.codigo_item_catalogo = m.codigo_item
GROUP BY m.codigo_item
ORDER BY qtd_registros DESC
LIMIT 10;
