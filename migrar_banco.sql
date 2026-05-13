-- ================================================================
-- SCRIPT DE MIGRAÇÃO DO BANCO — rode UMA VEZ se já tinha dados
-- antes de implementar o sistema de login.
--
-- Como usar (com o servidor parado):
--   sqlite3 financas.db < migrar_banco.sql
-- ================================================================

-- 1. Garante que todos os registros sem user_id recebam id=1
--    (pressupõe que o primeiro usuário cadastrado tem id=1)
UPDATE transacoes     SET user_id = 1 WHERE user_id IS NULL OR user_id = 0;
UPDATE contas         SET user_id = 1 WHERE user_id IS NULL OR user_id = 0;
UPDATE cartoes        SET user_id = 1 WHERE user_id IS NULL OR user_id = 0;
UPDATE categorias     SET user_id = 1 WHERE user_id IS NULL OR user_id = 0;
UPDATE receitas_fixas SET user_id = 1 WHERE user_id IS NULL OR user_id = 0;
UPDATE despesas_fixas SET user_id = 1 WHERE user_id IS NULL OR user_id = 0;

-- 2. Cria índices únicos (se ainda não existirem)
CREATE UNIQUE INDEX IF NOT EXISTS idx_cat_user_nome    ON categorias(user_id, nome);
CREATE UNIQUE INDEX IF NOT EXISTS idx_conta_user_nome  ON contas(user_id, nome);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cartao_user_nome ON cartoes(user_id, nome);

-- 3. Remove duplicatas de categorias que podem existir do sistema antigo
--    (mantém apenas a de menor id por nome+user_id)
DELETE FROM categorias WHERE id NOT IN (
    SELECT MIN(id) FROM categorias GROUP BY user_id, nome
);

-- 4. Verifica resultado
SELECT 'usuarios' as tabela, COUNT(*) as total FROM usuarios
UNION ALL SELECT 'contas',         COUNT(*) FROM contas
UNION ALL SELECT 'cartoes',        COUNT(*) FROM cartoes
UNION ALL SELECT 'categorias',     COUNT(*) FROM categorias
UNION ALL SELECT 'transacoes',     COUNT(*) FROM transacoes
UNION ALL SELECT 'receitas_fixas', COUNT(*) FROM receitas_fixas
UNION ALL SELECT 'despesas_fixas', COUNT(*) FROM despesas_fixas;
