from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import sqlite3, os, calendar
from datetime import date, timedelta, datetime
from functools import wraps
from dateutil.relativedelta import relativedelta  # pip install python-dateutil
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')
app.permanent_session_lifetime = timedelta(hours=8)
DB = 'financas.db'

# ================================================================
# BANCO DE DADOS
# ================================================================

def get_db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        c = conn.cursor()

        # ── usuarios ────────────────────────────────────────────
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            nome       TEXT    NOT NULL,
            email      TEXT    UNIQUE NOT NULL,
            senha_hash TEXT    NOT NULL,
            role       TEXT    NOT NULL DEFAULT 'user',
            criado_em  DATE    NOT NULL DEFAULT (DATE('now')),
            ativo      INTEGER NOT NULL DEFAULT 1
        )''')

        # ── transacoes ──────────────────────────────────────────
        c.execute('''CREATE TABLE IF NOT EXISTS transacoes (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER NOT NULL REFERENCES usuarios(id),
            tipo             TEXT NOT NULL CHECK(tipo IN ('despesa','receita')),
            descricao        TEXT NOT NULL,
            valor            REAL NOT NULL,
            categoria        TEXT,
            id_cartao        INTEGER REFERENCES cartoes(id),
            id_conta         INTEGER REFERENCES contas(id),
            tipo_receita     TEXT CHECK(tipo_receita  IN ('avulsa','fixa'))      DEFAULT 'avulsa',
            tipo_cobranca    TEXT CHECK(tipo_cobranca IN ('avulsa','fixa'))      DEFAULT 'avulsa',
            dia_vencimento   INTEGER,
            tipo_compra      TEXT CHECK(tipo_compra   IN ('credito','debito'))   DEFAULT 'credito',
            pagamento        TEXT CHECK(pagamento     IN ('avista','parcelado')) DEFAULT 'avista',
            parcelas         INTEGER DEFAULT NULL,
            data_lancamento  DATE NOT NULL DEFAULT (DATE('now'))
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS categorias (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES usuarios(id),
            nome    TEXT    NOT NULL,
            tipo    TEXT    CHECK(tipo IN ('despesa','receita')) DEFAULT 'despesa',
            UNIQUE(user_id, nome)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS contas (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES usuarios(id),
            nome    TEXT    NOT NULL,
            saldo   REAL    DEFAULT 0,
            UNIQUE(user_id, nome)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS cartoes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES usuarios(id),
            nome            TEXT    NOT NULL,
            conta           INTEGER NOT NULL REFERENCES contas(id),
            tipo_pagamento  TEXT    CHECK(tipo_pagamento IN ('credito','debito','multiplo')),
            data_vencimento INTEGER,
            dias_fechamento INTEGER,
            limite          REAL    DEFAULT 0,
            UNIQUE(user_id, nome)
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS receitas_fixas (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL REFERENCES usuarios(id),
            descricao TEXT    NOT NULL,
            valor     REAL    NOT NULL,
            categoria TEXT,
            id_conta  INTEGER NOT NULL REFERENCES contas(id),
            dia_mes   INTEGER NOT NULL DEFAULT 1,
            modo_dia  TEXT    NOT NULL DEFAULT 'fixo',
            ativa     INTEGER DEFAULT 1
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS despesas_fixas (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL REFERENCES usuarios(id),
            descricao TEXT    NOT NULL,
            valor     REAL    NOT NULL,
            categoria TEXT,
            id_cartao INTEGER REFERENCES cartoes(id),
            id_conta  INTEGER REFERENCES contas(id),
            dia_mes   INTEGER NOT NULL DEFAULT 1,
            modo_dia  TEXT    NOT NULL DEFAULT 'fixo',
            ativa     INTEGER DEFAULT 1
        )''')

        # Migrações seguras (banco já existente sem user_id)
        migracoes = [
            "ALTER TABLE transacoes    ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE categorias    ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE contas        ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE cartoes       ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE receitas_fixas ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE despesas_fixas ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE receitas_fixas ADD COLUMN modo_dia TEXT NOT NULL DEFAULT 'fixo'",
            "ALTER TABLE despesas_fixas ADD COLUMN modo_dia TEXT NOT NULL DEFAULT 'fixo'",
        ]
        for sql in migracoes:
            try: c.execute(sql)
            except: pass

        conn.commit()


def criar_categorias_padrao(user_id: int):
    """Cria categorias padrão para um novo usuário."""
    padrao = [
        ('Alimentação','despesa'), ('Transporte','despesa'), ('Moradia','despesa'),
        ('Saúde','despesa'),       ('Educação','despesa'),   ('Lazer','despesa'),
        ('Assinaturas','despesa'), ('Salário','receita'),
        ('Investimentos','receita'), ('Freelance','receita'), ('Presente','receita'),
    ]
    with get_db() as conn:
        c = conn.cursor()
        for nome, tipo in padrao:
            c.execute("INSERT OR IGNORE INTO categorias (user_id, nome, tipo) VALUES (?,?,?)",
                      (user_id, nome, tipo))
        conn.commit()


# ================================================================
# AUTENTICAÇÃO — decorators e helpers
# ================================================================

def uid():
    """Retorna o user_id da sessão atual."""
    return session.get('user_id')

def login_required(f):
    """Redireciona para /login se não houver sessão ativa."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not uid():
            flash('Faça login para continuar.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """Exige role='admin'. Retorna 403 se não for admin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not uid():
            return redirect(url_for('login'))
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT role, ativo FROM usuarios WHERE id=?", (uid(),))
            row = c.fetchone()
        if not row or row[0] != 'admin' or not row[1]:
            return jsonify({'error': 'Acesso negado'}), 403
        return f(*args, **kwargs)
    return decorated


# ================================================================
# DIAS ÚTEIS BRASILEIROS
# ================================================================

FERIADOS_FIXOS_BR = {
    (1,1),(4,21),(5,1),(9,7),(10,12),(11,2),(11,15),(12,25)
}

def eh_dia_util(d: date) -> bool:
    return d.weekday() < 5 and (d.month, d.day) not in FERIADOS_FIXOS_BR

def primeiro_dia_util(ano: int, mes: int) -> date:
    d = date(ano, mes, 1)
    while not eh_dia_util(d): d += timedelta(days=1)
    return d

def ultimo_dia_util(ano: int, mes: int) -> date:
    d = date(ano, mes, calendar.monthrange(ano, mes)[1])
    while not eh_dia_util(d): d -= timedelta(days=1)
    return d

def data_ocorrencia(ano: int, mes: int, dia_mes: int, modo_dia: str) -> date:
    """Data efetiva de um lançamento fixo em determinado mês/ano."""
    if modo_dia == 'primeiro_util': return primeiro_dia_util(ano, mes)
    if modo_dia == 'ultimo_util':   return ultimo_dia_util(ano, mes)
    return date(ano, mes, min(dia_mes, calendar.monthrange(ano, mes)[1]))


# ================================================================
# GERAÇÃO AUTOMÁTICA DE OCORRÊNCIAS
# ================================================================

def gerar_ocorrencias_receitas_fixas(user_id=None):
    """
    Gera ocorrências de receitas fixas do mês atual.
    - Chamada na inicialização (sem request): user_id=None → processa TODOS os usuários.
    - Chamada dentro de request: user_id=uid() → processa só o usuário logado.
    """
    hoje = date.today()
    with get_db() as conn:
        c = conn.cursor()
        if user_id is not None:
            c.execute("SELECT id, descricao, valor, categoria, id_conta, dia_mes, modo_dia, user_id FROM receitas_fixas WHERE ativa=1 AND user_id=?", (user_id,))
        else:
            c.execute("SELECT id, descricao, valor, categoria, id_conta, dia_mes, modo_dia, user_id FROM receitas_fixas WHERE ativa=1")
        for rf_id, desc, valor, cat, id_conta, dia_mes, modo, uid_rf in c.fetchall():
            data_oc = data_ocorrencia(hoje.year, hoje.month, dia_mes, modo or 'fixo')
            if hoje < data_oc: continue
            chave = f'_rf_{rf_id}'
            c.execute("SELECT COUNT(*) FROM transacoes WHERE tipo='receita' AND id_conta=? AND categoria=? AND user_id=? AND strftime('%Y-%m',data_lancamento)=?",
                      (id_conta, chave, uid_rf, hoje.strftime('%Y-%m')))
            if c.fetchone()[0] > 0: continue
            c.execute("INSERT INTO transacoes (user_id,tipo,descricao,valor,categoria,id_conta,tipo_receita,data_lancamento) VALUES (?,'receita',?,?,?,?,'avulsa',?)",
                      (uid_rf, desc, valor, chave, id_conta, data_oc.isoformat()))
            c.execute("UPDATE contas SET saldo=saldo+? WHERE id=?", (valor, id_conta))
        conn.commit()


def gerar_ocorrencias_despesas_fixas(user_id=None):
    """
    Gera ocorrências de despesas fixas do mês atual.
    - Chamada na inicialização (sem request): user_id=None → processa TODOS os usuários.
    - Chamada dentro de request: user_id=uid() → processa só o usuário logado.
    """
    hoje = date.today()
    with get_db() as conn:
        c = conn.cursor()
        if user_id is not None:
            c.execute("SELECT id, descricao, valor, categoria, id_cartao, id_conta, dia_mes, modo_dia, user_id FROM despesas_fixas WHERE ativa=1 AND user_id=?", (user_id,))
        else:
            c.execute("SELECT id, descricao, valor, categoria, id_cartao, id_conta, dia_mes, modo_dia, user_id FROM despesas_fixas WHERE ativa=1")
        for df_id, desc, valor, cat, id_cartao, id_conta, dia_mes, modo, uid_df in c.fetchall():
            data_oc = data_ocorrencia(hoje.year, hoje.month, dia_mes, modo or 'fixo')
            if hoje < data_oc: continue
            chave = f'_df_{df_id}'
            c.execute("SELECT COUNT(*) FROM transacoes WHERE tipo='despesa' AND categoria=? AND user_id=? AND strftime('%Y-%m',data_lancamento)=?",
                      (chave, uid_df, hoje.strftime('%Y-%m')))
            if c.fetchone()[0] > 0: continue

            # Determina tipo_compra pelo cartão
            tipo_compra = 'credito'
            if id_cartao:
                c.execute("SELECT tipo_pagamento FROM cartoes WHERE id=?", (id_cartao,))
                row = c.fetchone()
                if row and row[0] == 'debito': tipo_compra = 'debito'
            else:
                tipo_compra = 'debito'  # sem cartão → débito direto na conta

            c.execute("""INSERT INTO transacoes
                (user_id,tipo,descricao,valor,categoria,id_cartao,id_conta,tipo_cobranca,tipo_compra,pagamento,data_lancamento)
                VALUES (?,'despesa',?,?,?,?,?,'fixa',?,'avista',?)""",
                (uid_df, desc, valor, chave, id_cartao, id_conta, tipo_compra, data_oc.isoformat()))

            # Débito direto → desconta da conta imediatamente
            if tipo_compra == 'debito' and id_conta:
                c.execute("UPDATE contas SET saldo=saldo-? WHERE id=?", (valor, id_conta))

        conn.commit()


# ================================================================
# HELPERS — FATURA E PARCELAS
# ================================================================

def periodo_fatura_atual(dia_vencimento: int, dias_fechamento: int, referencia: date = None):
    """
    Retorna (inicio, fim, vencimento) da fatura ABERTA do cartão.
    início = fechamento da fatura anterior (inclusive)
    fim    = dia antes do fechamento atual (inclusive)
    """
    hoje = referencia or date.today()
    try:
        venc_corrente = date(hoje.year, hoje.month, dia_vencimento)
    except ValueError:
        venc_corrente = date(hoje.year, hoje.month, calendar.monthrange(hoje.year, hoje.month)[1])

    fech_corrente = venc_corrente - timedelta(days=dias_fechamento)
    venc_atual    = venc_corrente if hoje < fech_corrente else venc_corrente + relativedelta(months=1)
    venc_anterior = venc_atual - relativedelta(months=1)
    fech_atual    = venc_atual    - timedelta(days=dias_fechamento)
    fech_anterior = venc_anterior - timedelta(days=dias_fechamento)
    return fech_anterior, fech_atual - timedelta(days=1), venc_atual


def valor_parcela_na_fatura(valor_total: float, parcelas: int,
                             data_compra: date, inicio_fatura: date, fim_fatura: date) -> float:
    """
    Retorna o valor de UMA parcela se alguma delas cair no período da fatura.

    Regra: parcela N cai no mês (data_compra + N meses).
    Comparação por mês/ano: o período da fatura cobre aquele mês inteiro?
    Isso é correto porque o cartão cobra a parcela no mês em que ela cai,
    independente do dia exato dentro do mês.
    """
    if not parcelas or parcelas < 1:
        return 0.0
    vp = round(valor_total / parcelas, 2)
    for p in range(parcelas):
        mes_parcela = data_compra + relativedelta(months=p)
        ultimo = calendar.monthrange(mes_parcela.year, mes_parcela.month)[1]
        ini_mes = mes_parcela.replace(day=1)
        fim_mes = mes_parcela.replace(day=ultimo)
        if inicio_fatura <= fim_mes and fim_fatura >= ini_mes:
            return vp
    return 0.0


def total_fatura_atual():
    """
    Soma o que está na fatura aberta de todos os cartões de crédito.
    Para compras parceladas: conta apenas o valor da parcela do mês,
    não o valor total da compra.
    """
    total = 0.0
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, data_vencimento, dias_fechamento FROM cartoes
            WHERE tipo_pagamento IN ('credito','multiplo')
              AND data_vencimento IS NOT NULL AND dias_fechamento IS NOT NULL
        """)
        for cartao_id, dia_venc, dias_fech in c.fetchall():
            inicio, fim, _ = periodo_fatura_atual(dia_venc, dias_fech)

            # Despesas à vista no período
            c.execute("""
                SELECT COALESCE(SUM(valor), 0) FROM transacoes
                WHERE tipo='despesa' AND tipo_compra='credito'
                  AND pagamento='avista'
                  AND id_cartao=? AND data_lancamento BETWEEN ? AND ?
            """, (cartao_id, inicio.isoformat(), fim.isoformat()))
            total += c.fetchone()[0]

            # Despesas parceladas: conta apenas a parcela do período
            c.execute("""
                SELECT valor, parcelas, data_lancamento FROM transacoes
                WHERE tipo='despesa' AND tipo_compra='credito'
                  AND pagamento='parcelado' AND parcelas >= 2
                  AND id_cartao=?
            """, (cartao_id,))
            for valor_total, parcelas, data_str in c.fetchall():
                try:
                    data_compra = date.fromisoformat(str(data_str)[:10])
                except Exception:
                    continue
                total += valor_parcela_na_fatura(valor_total, parcelas, data_compra, inicio, fim)

    return round(total, 2)


def despesas_fixas_pendentes_mes():
    """
    Despesas fixas (assinaturas) que ainda não foram geradas este mês
    mas vão cair. Usadas no cálculo do Disponível.
    Retorna apenas as que são crédito (as de débito já descontam do saldo
    quando geradas, então já estão refletidas no saldo_total).
    """
    hoje = date.today()
    total = 0.0
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, valor, dia_mes, modo_dia, id_cartao FROM despesas_fixas WHERE ativa=1")
        for df_id, valor, dia_mes, modo, id_cartao in c.fetchall():
            data_oc = data_ocorrencia(hoje.year, hoje.month, dia_mes, modo or 'fixo')
            if data_oc <= hoje: continue  # já gerada ou gerada hoje
            chave = f'_df_{df_id}'
            c.execute("SELECT COUNT(*) FROM transacoes WHERE tipo='despesa' AND categoria=? AND strftime('%Y-%m',data_lancamento)=?",
                      (chave, hoje.strftime('%Y-%m')))
            if c.fetchone()[0] > 0: continue
            # Só considera se for crédito (débito vai abater do saldo quando gerado)
            if id_cartao:
                total += valor
    return round(total, 2)


def receitas_fixas_pendentes_mes():
    """
    Receitas fixas que ainda não foram creditadas neste mês mas vão cair.
    """
    hoje = date.today()
    total = 0.0
    with get_db() as conn:
        c = conn.cursor()
        user_id = uid() or 0
        c.execute("SELECT id, valor, dia_mes, modo_dia, id_conta FROM receitas_fixas WHERE ativa=1 AND user_id=?", (user_id,))
        for rf_id, valor, dia_mes, modo, id_conta in c.fetchall():
            data_oc = data_ocorrencia(hoje.year, hoje.month, dia_mes, modo or 'fixo')
            if data_oc <= hoje: continue
            chave = f'_rf_{rf_id}'
            c.execute("SELECT COUNT(*) FROM transacoes WHERE tipo='receita' AND id_conta=? AND categoria=? AND strftime('%Y-%m',data_lancamento)=?",
                      (id_conta, chave, hoje.strftime('%Y-%m')))
            if c.fetchone()[0] > 0: continue
            total += valor
    return round(total, 2)


def despesas_reais_mes(ano: int, mes: int, conn) -> float:
    """
    Calcula o total REAL de despesas de um mês específico, tratando
    parceladas corretamente: conta apenas o valor da parcela que cai
    naquele mês, não o valor total da compra.

    Para despesas à vista: usa data_lancamento normalmente.
    Para despesas parceladas: parcela N cai em (data_lancamento + N meses).
    """
    c = conn.cursor()
    mes_str = f"{ano:04d}-{mes:02d}"

    # Despesas à vista do mês (data_lancamento no mês)
    c.execute("""
        SELECT COALESCE(SUM(valor), 0) FROM transacoes
        WHERE tipo = 'despesa'
          AND pagamento = 'avista'
          AND strftime('%Y-%m', data_lancamento) = ?
          AND user_id = ?
          AND (categoria IS NULL OR (categoria NOT LIKE '_rf_%' AND categoria NOT LIKE '_df_%'))
    """, (mes_str, uid() or 0))
    total = c.fetchone()[0]

    # Parcelas que caem neste mês (independente de quando a compra foi feita)
    c.execute("""
        SELECT valor, parcelas, data_lancamento FROM transacoes
        WHERE tipo = 'despesa'
          AND pagamento = 'parcelado'
          AND parcelas >= 2
          AND user_id = ?
          AND (categoria IS NULL OR (categoria NOT LIKE '_rf_%' AND categoria NOT LIKE '_df_%'))
    """, (uid() or 0,))
    for valor_total, parcelas, data_str in c.fetchall():
        try:
            data_compra = date.fromisoformat(str(data_str)[:10])
        except Exception:
            continue
        vp = round(valor_total / parcelas, 2)
        for p in range(parcelas):
            mp = data_compra + relativedelta(months=p)
            if mp.year == ano and mp.month == mes:
                total += vp
                break

    return round(total, 2)


def gastos_categoria_mes(ano: int, mes: int, conn, limit: int = 5) -> list:
    """
    Retorna os gastos por categoria de um mês, tratando parceladas corretamente.
    Para parceladas: conta apenas a parcela do mês em cada categoria.
    """
    c = conn.cursor()
    mes_str = f"{ano:04d}-{mes:02d}"
    acum = {}  # categoria -> total

    # À vista
    c.execute("""
        SELECT COALESCE(categoria, 'Sem categoria'), COALESCE(SUM(valor), 0)
        FROM transacoes
        WHERE tipo = 'despesa' AND pagamento = 'avista'
          AND strftime('%Y-%m', data_lancamento) = ?
          AND (categoria IS NULL OR (categoria NOT LIKE '_rf_%' AND categoria NOT LIKE '_df_%'))
        GROUP BY categoria
    """, (mes_str,))
    for cat, val in c.fetchall():
        acum[cat] = acum.get(cat, 0) + val

    # Parceladas — parcela do mês por categoria
    c.execute("""
        SELECT COALESCE(categoria, 'Sem categoria'), valor, parcelas, data_lancamento
        FROM transacoes
        WHERE tipo = 'despesa' AND pagamento = 'parcelado' AND parcelas >= 2
          AND (categoria IS NULL OR (categoria NOT LIKE '_rf_%' AND categoria NOT LIKE '_df_%'))
    """)
    for cat, valor_total, parcelas, data_str in c.fetchall():
        try:
            data_compra = date.fromisoformat(str(data_str)[:10])
        except Exception:
            continue
        vp = round(valor_total / parcelas, 2)
        for p in range(parcelas):
            mp = data_compra + relativedelta(months=p)
            if mp.year == ano and mp.month == mes:
                acum[cat] = acum.get(cat, 0) + vp
                break

    resultado = sorted(
        [{'nome': k, 'total': round(v, 2)} for k, v in acum.items()],
        key=lambda x: x['total'], reverse=True
    )
    return resultado[:limit]



def dashboard_por_cartao(cartao_id: int) -> dict:
    """
    Calcula todos os dados do dashboard filtrados por um cartão específico.
    Retorna o mesmo formato do dashboard geral para o JS poder reutilizar
    a mesma lógica de renderização.
    """
    hoje = date.today()
    mes_str = hoje.strftime('%Y-%m')

    with get_db() as conn:
        c = conn.cursor()

        # Info do cartão
        c.execute("""
            SELECT ca.nome, ca.data_vencimento, ca.dias_fechamento, ca.limite,
                   ca.tipo_pagamento
            FROM cartoes ca WHERE ca.id = ? AND ca.user_id = ?
        """, (cartao_id, uid()))
        row = c.fetchone()
        if not row:
            return None
        nome_cartao, dia_venc, dias_fech, limite, tipo_pag = row

        # Período da fatura atual deste cartão
        fatura_atual = 0.0
        inicio_f = fim_f = venc_f = None
        if dia_venc and dias_fech:
            inicio_f, fim_f, venc_f = periodo_fatura_atual(dia_venc, dias_fech)

            # À vista na fatura atual
            c.execute("""
                SELECT COALESCE(SUM(valor), 0) FROM transacoes
                WHERE tipo='despesa' AND tipo_compra='credito' AND pagamento='avista'
                  AND id_cartao=? AND data_lancamento BETWEEN ? AND ?
            """, (cartao_id, inicio_f.isoformat(), fim_f.isoformat()))
            fatura_atual += c.fetchone()[0]

            # Parceladas — só a parcela do período
            c.execute("""
                SELECT valor, parcelas, data_lancamento FROM transacoes
                WHERE tipo='despesa' AND tipo_compra='credito' AND pagamento='parcelado'
                  AND parcelas >= 2 AND id_cartao=?
            """, (cartao_id,))
            for vt, parc, ds in c.fetchall():
                try:
                    dc = date.fromisoformat(str(ds)[:10])
                except Exception:
                    continue
                fatura_atual += valor_parcela_na_fatura(vt, parc, dc, inicio_f, fim_f)

        fatura_atual = round(fatura_atual, 2)

        # Gastos por categoria deste cartão no mês atual (parcelas corretas)
        acum = {}
        c.execute("""
            SELECT COALESCE(categoria, 'Sem categoria'), valor, pagamento, parcelas, data_lancamento
            FROM transacoes
            WHERE tipo='despesa' AND id_cartao=?
              AND (categoria IS NULL OR (categoria NOT LIKE '_rf_%' AND categoria NOT LIKE '_df_%'))
        """, (cartao_id,))
        for cat, vt, pag, parc, ds in c.fetchall():
            try:
                dc = date.fromisoformat(str(ds)[:10])
            except Exception:
                continue
            if pag == 'avista':
                if dc.year == hoje.year and dc.month == hoje.month:
                    acum[cat] = acum.get(cat, 0) + vt
            else:
                n = parc or 1
                vp = round(vt / n, 2)
                for p in range(n):
                    mp = dc + relativedelta(months=p)
                    if mp.year == hoje.year and mp.month == hoje.month:
                        acum[cat] = acum.get(cat, 0) + vp
                        break

        gastos_categoria = sorted(
            [{'nome': k, 'total': round(v, 2)} for k, v in acum.items()],
            key=lambda x: x['total'], reverse=True
        )[:5]

        # Últimas 10 transações deste cartão
        c.execute("""
            SELECT t.id, t.descricao, t.tipo, t.valor, t.categoria,
                   ca.nome AS cartao_nome, t.data_lancamento, t.pagamento, t.parcelas
            FROM transacoes t
            LEFT JOIN cartoes ca ON t.id_cartao = ca.id
            WHERE t.id_cartao = ? AND t.tipo = 'despesa'
            ORDER BY t.data_lancamento DESC, t.id DESC LIMIT 10
        """, (cartao_id,))
        transacoes = []
        for r in c.fetchall():
            d = dict(r)
            # Mostra valor da parcela se parcelado
            if d['pagamento'] == 'parcelado' and d['parcelas']:
                d['valor_exibido'] = round(d['valor'] / d['parcelas'], 2)
                d['valor_total']   = d['valor']
            else:
                d['valor_exibido'] = d['valor']
                d['valor_total']   = d['valor']
            transacoes.append(d)

        # Histórico 6 meses deste cartão (gastos por mês, parcelas corretas)
        historico = []
        meses_pt = {1:'Jan',2:'Fev',3:'Mar',4:'Abr',5:'Mai',6:'Jun',
                    7:'Jul',8:'Ago',9:'Set',10:'Out',11:'Nov',12:'Dez'}
        for delta in range(5, -1, -1):
            ref = hoje - relativedelta(months=delta)
            # Busca todas as despesas do cartão para calcular o mês correto
            c.execute("""
                SELECT valor, pagamento, parcelas, data_lancamento FROM transacoes
                WHERE tipo='despesa' AND id_cartao=?
                  AND (categoria IS NULL OR (categoria NOT LIKE '_rf_%' AND categoria NOT LIKE '_df_%'))
            """, (cartao_id,))
            desp_mes = 0.0
            for vt, pag, parc, ds in c.fetchall():
                try:
                    dc = date.fromisoformat(str(ds)[:10])
                except Exception:
                    continue
                if pag == 'avista':
                    if dc.year == ref.year and dc.month == ref.month:
                        desp_mes += vt
                else:
                    n = parc or 1
                    vp = round(vt / n, 2)
                    for p in range(n):
                        mp = dc + relativedelta(months=p)
                        if mp.year == ref.year and mp.month == ref.month:
                            desp_mes += vp
                            break
            historico.append({
                'label':    f"{meses_pt[ref.month]}/{ref.year}",
                'despesas': round(desp_mes, 2),
            })

    return {
        'nome_cartao':      nome_cartao,
        'tipo_pagamento':   tipo_pag,
        'limite':           limite,
        'fatura_atual':     fatura_atual,
        'periodo_inicio':   inicio_f.strftime('%d/%m/%Y') if inicio_f else None,
        'periodo_fim':      fim_f.strftime('%d/%m/%Y')    if fim_f    else None,
        'vencimento':       venc_f.strftime('%d/%m/%Y')   if venc_f   else None,
        'gastos_categoria': gastos_categoria,
        'transacoes':       transacoes,
        'historico':        historico,
    }

def projecao_mensal(n_meses: int = 3):
    """
    Projeção dos próximos n_meses.
    Parcelas: conta apenas o valor da parcela do mês, não o total.
    """
    hoje = date.today()
    meses_pt = {1:'Jan',2:'Fev',3:'Mar',4:'Abr',5:'Mai',6:'Jun',
                7:'Jul',8:'Ago',9:'Set',10:'Out',11:'Nov',12:'Dez'}
    resultado = []
    with get_db() as conn:
        c = conn.cursor()
        for delta in range(1, n_meses + 1):
            alvo = hoje + relativedelta(months=delta)
            ano_alvo, mes_alvo = alvo.year, alvo.month

            # Receitas fixas
            c.execute("SELECT COALESCE(SUM(valor), 0) FROM receitas_fixas WHERE ativa=1")
            rec_fixas = c.fetchone()[0]

            # Despesas fixas (assinaturas)
            c.execute("SELECT COALESCE(SUM(valor), 0) FROM despesas_fixas WHERE ativa=1")
            desp_fixas = c.fetchone()[0]

            # Parcelas: apenas a parcela que cai no mês alvo
            c.execute("SELECT valor, parcelas, data_lancamento FROM transacoes WHERE tipo='despesa' AND pagamento='parcelado' AND parcelas>=2")
            desp_parc = 0.0
            for valor_total, parcelas, data_str in c.fetchall():
                try: dc = date.fromisoformat(str(data_str)[:10])
                except: continue
                vp = round(valor_total / parcelas, 2)
                for p in range(parcelas):
                    mp = dc + relativedelta(months=p)
                    if mp.year == ano_alvo and mp.month == mes_alvo:
                        desp_parc += vp
                        break

            resultado.append({
                'mes_ano':             f"{meses_pt[mes_alvo]}/{ano_alvo}",
                'receitas':            round(rec_fixas, 2),
                'despesas_fixas':      round(desp_fixas, 2),
                'despesas_parceladas': round(desp_parc, 2),
                'saldo':               round(rec_fixas - desp_fixas - desp_parc, 2),
            })
    return resultado


# ================================================================
# ROTA PRINCIPAL /
# ================================================================

@app.route('/')
@login_required
def index():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT t.id, t.descricao, t.tipo, t.valor, t.categoria,
                   co.nome AS conta_nome, ca.nome AS cartao_nome, t.data_lancamento,
                   t.parcelas
            FROM transacoes t
            LEFT JOIN contas  co ON t.id_conta  = co.id
            LEFT JOIN cartoes ca ON t.id_cartao = ca.id
            WHERE t.user_id = ?
            ORDER BY t.data_lancamento DESC, t.id DESC LIMIT 10
        """, (uid(),))
        transacoes = [dict(r) for r in c.fetchall()]

        c.execute("SELECT COALESCE(SUM(saldo), 0) FROM contas WHERE user_id=?", (uid(),))
        saldo_total = round(c.fetchone()[0], 2)

        hoje = date.today()
        c.execute("""
            SELECT COALESCE(SUM(valor), 0) FROM transacoes
            WHERE tipo='receita' AND strftime('%Y-%m', data_lancamento)=?
              AND (categoria IS NULL OR categoria NOT LIKE '_rf_%')
              AND user_id=?
        """, (hoje.strftime('%Y-%m'), uid()))
        receitas_mes = round(c.fetchone()[0], 2)

        gastos_por_categoria = gastos_categoria_mes(hoje.year, hoje.month, conn, limit=5)

    fatura_atual   = total_fatura_atual()
    rec_pendentes  = receitas_fixas_pendentes_mes()
    desp_pendentes = despesas_fixas_pendentes_mes()

    # Disponível no Mês:
    #   saldo real (já na conta)
    # + receitas fixas ainda não geradas este mês
    # - fatura de crédito aberta (à vista + parcela do mês)
    # - despesas fixas de crédito ainda não geradas este mês
    disponivel_mes = round(saldo_total + rec_pendentes - fatura_atual - desp_pendentes, 2)

    # Cartões de crédito para as abas
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, nome FROM cartoes
            WHERE tipo_pagamento IN ('credito','multiplo') AND user_id=?
            ORDER BY nome
        """, (uid(),))
        cartoes_credito = [{'id': r[0], 'nome': r[1]} for r in c.fetchall()]

    return render_template('index.html',
        transacoes=transacoes,
        saldo_total=saldo_total,
        receitas_mes=receitas_mes,
        gasto_credito=fatura_atual,
        disponivel_mes=disponivel_mes,
        proximas_faturas=projecao_mensal(3),
        gastos_por_categoria=gastos_por_categoria,
        cartoes_credito=cartoes_credito,
    )


@app.route('/api/dashboard_data')
@login_required
def dashboard_data():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COALESCE(SUM(saldo), 0) FROM contas WHERE user_id=?", (uid(),))
        saldo_total = round(c.fetchone()[0], 2)
        hoje = date.today()
        c.execute("""
            SELECT COALESCE(SUM(valor), 0) FROM transacoes
            WHERE tipo='receita' AND strftime('%Y-%m', data_lancamento)=?
              AND (categoria IS NULL OR categoria NOT LIKE '_rf_%')
              AND user_id=?
        """, (hoje.strftime('%Y-%m'), uid()))
        receitas_mes = round(c.fetchone()[0], 2)

    fatura_atual   = total_fatura_atual()
    rec_pendentes  = receitas_fixas_pendentes_mes()
    desp_pendentes = despesas_fixas_pendentes_mes()
    return jsonify({
        'saldo_total':    saldo_total,
        'receitas_mes':   receitas_mes,
        'gasto_credito':  fatura_atual,
        'disponivel_mes': round(saldo_total + rec_pendentes - fatura_atual - desp_pendentes, 2),
    })


@app.route('/api/dashboard_cartao/<int:cartao_id>')
@login_required
def api_dashboard_cartao(cartao_id):
    """Retorna todos os dados do dashboard filtrados por um cartão."""
    dados = dashboard_por_cartao(cartao_id)
    if dados is None:
        return jsonify({'success': False, 'error': 'Cartão não encontrado'}), 404
    return jsonify({'success': True, **dados})


# ================================================================
# ROTAS DE PÁGINAS
# ================================================================

@app.route('/lancamentos')
@login_required
def lancamentos():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT t.id, t.descricao, t.tipo, t.valor, t.categoria,
                   ca.nome AS cartao_nome, t.data_lancamento,
                   t.pagamento, t.parcelas, t.tipo_compra, t.tipo_cobranca
            FROM transacoes t LEFT JOIN cartoes ca ON t.id_cartao=ca.id
            WHERE t.tipo='despesa' AND t.user_id=?
              AND (t.categoria IS NULL OR t.categoria NOT LIKE '_df_%')
            ORDER BY t.data_lancamento DESC, t.id DESC
        """, (uid(),))
        lancamentos_db = [list(r) for r in c.fetchall()]
    return render_template('lancamentos.html', lancamentos=lancamentos_db)


@app.route('/lancamentosReceita')
@login_required
def lancamentosReceita():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT t.id, t.descricao, t.tipo, t.valor,
                   COALESCE(t.categoria,'') AS categoria,
                   COALESCE(co.nome,'N/A') AS conta_nome,
                   COALESCE(t.tipo_receita,'avulsa'),
                   t.dia_vencimento
            FROM transacoes t LEFT JOIN contas co ON t.id_conta=co.id
            WHERE t.tipo='receita' AND t.user_id=?
              AND (t.categoria IS NULL OR t.categoria NOT LIKE '_rf_%')
            ORDER BY t.data_lancamento DESC, t.id DESC
        """, (uid(),))
        receitas = [list(r) for r in c.fetchall()]
    return render_template('lancamentosReceita.html', receitas=receitas)


@app.route('/lancamentosAssinaturas')
@login_required
def lancamentosAssinaturas():
    return render_template('lancamentosAssinaturas.html')


@app.route('/lancamentosConta')
@login_required
def lancamentosConta():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, nome, saldo FROM contas WHERE user_id=? ORDER BY nome", (uid(),))
        contas = [list(r) for r in c.fetchall()]
    return render_template('lancamentosConta.html', contas=contas)


@app.route('/lancamentosCartao')
@login_required
def lancamentosCartao():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT ca.id, ca.nome, co.nome AS conta_nome,
                   ca.dias_fechamento, ca.data_vencimento, ca.tipo_pagamento, ca.limite
            FROM cartoes ca LEFT JOIN contas co ON ca.conta=co.id
            WHERE ca.user_id=? ORDER BY ca.nome
        """, (uid(),))
        cartoes = [list(r) for r in c.fetchall()]
        c.execute("SELECT id, nome FROM contas WHERE user_id=? ORDER BY nome", (uid(),))
        contas = [list(r) for r in c.fetchall()]
    return render_template('lancamentosCartao.html', cartoes=cartoes, contas=contas)


@app.route('/lancamentosCategorias')
@login_required
def lancamentosCategorias():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, nome, tipo FROM categorias WHERE user_id=? ORDER BY tipo, nome", (uid(),))
        categorias = [list(r) for r in c.fetchall()]
    return render_template('lancamentosCategorias.html', categorias=categorias)


@app.route('/projecoes')
@login_required
def projecoes():
    return render_template('projecoes.html', projecoes=projecao_mensal(6))


@app.route('/visaoGeral')
@login_required
def visaoGeral():
    with get_db() as conn:
        c = conn.cursor()
        hoje = date.today()
        meses_pt = {1:'Jan',2:'Fev',3:'Mar',4:'Abr',5:'Mai',6:'Jun',
                    7:'Jul',8:'Ago',9:'Set',10:'Out',11:'Nov',12:'Dez'}

        historico = []
        for delta in range(5, -1, -1):
            ref = hoje - relativedelta(months=delta)
            # Receitas: SUM simples (receitas avulsas e fixas geradas)
            ms = ref.strftime('%Y-%m')
            c.execute("""
                SELECT COALESCE(SUM(valor),0) FROM transacoes
                WHERE tipo='receita' AND strftime('%Y-%m',data_lancamento)=? AND user_id=?
            """, (ms, uid()))
            rec = round(c.fetchone()[0], 2)
            # Despesas: usa despesas_reais_mes para tratar parcelas corretamente
            desp = despesas_reais_mes(ref.year, ref.month, conn)
            historico.append({
                'label': f"{meses_pt[ref.month]}/{ref.year}",
                'receitas': rec, 'despesas': desp, 'saldo': round(rec - desp, 2)
            })

        por_categoria = gastos_categoria_mes(hoje.year, hoje.month, conn, limit=20)

        c.execute("SELECT nome, saldo FROM contas WHERE user_id=? ORDER BY nome", (uid(),))
        por_conta = [{'nome': r[0], 'saldo': round(r[1],2)} for r in c.fetchall()]

        c.execute("""
            SELECT ca.id, ca.nome, ca.data_vencimento, ca.dias_fechamento, ca.limite
            FROM cartoes ca WHERE ca.tipo_pagamento IN ('credito','multiplo')
              AND ca.data_vencimento IS NOT NULL AND ca.dias_fechamento IS NOT NULL
              AND ca.user_id=?
        """)
        faturas_cartoes = []
        for cartao_id, nome_cartao, dia_venc, dias_fech, limite in c.fetchall():
            inicio, fim, vencimento = periodo_fatura_atual(dia_venc, dias_fech)
            # À vista
            c.execute("""
                SELECT COALESCE(SUM(valor),0) FROM transacoes
                WHERE tipo='despesa' AND tipo_compra='credito' AND pagamento='avista'
                  AND id_cartao=? AND data_lancamento BETWEEN ? AND ?
            """, (cartao_id, inicio.isoformat(), fim.isoformat()))
            gasto = c.fetchone()[0]
            # Parcelado (apenas parcela do período)
            c.execute("""
                SELECT valor, parcelas, data_lancamento FROM transacoes
                WHERE tipo='despesa' AND tipo_compra='credito' AND pagamento='parcelado'
                  AND parcelas>=2 AND id_cartao=?
            """, (cartao_id,))
            for vt, parc, ds in c.fetchall():
                try: dc = date.fromisoformat(str(ds)[:10])
                except: continue
                gasto += valor_parcela_na_fatura(vt, parc, dc, inicio, fim)
            faturas_cartoes.append({
                'nome': nome_cartao, 'gasto': round(gasto,2), 'limite': limite,
                'vencimento': vencimento.strftime('%d/%m/%Y'),
                'inicio': inicio.strftime('%d/%m/%Y'), 'fim': fim.strftime('%d/%m/%Y'),
            })

    return render_template('visaoGeral.html',
        historico=historico, por_categoria=por_categoria,
        por_conta=por_conta, faturas_cartoes=faturas_cartoes)


# ================================================================
# APIs — CONTAS
# ================================================================

@app.route('/api/contas')
@login_required
def api_contas():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, nome, saldo FROM contas WHERE user_id=? ORDER BY nome", (uid(),))
        contas = [{'id': r[0], 'nome': r[1], 'saldo': r[2]} for r in c.fetchall()]
    return jsonify({'contas': contas})

@app.route('/api/adicionar_conta', methods=['POST'])
@login_required
def adicionar_conta():
    data = request.get_json()
    nome = (data.get('nome') or '').strip()
    if not nome: return jsonify({'success': False, 'error': 'Nome obrigatório'})
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO contas (user_id, nome, saldo) VALUES (?, ?, 0)", (uid(), nome))
            conn.commit()
            return jsonify({'success': True, 'id': c.lastrowid, 'nome': nome})
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'error': 'Conta já existe'})

@app.route('/api/remover_conta', methods=['POST'])
@login_required
def remover_conta():
    data = request.get_json()
    conta_id = data.get('id')
    if not conta_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM cartoes WHERE conta=? AND user_id=?", (conta_id, uid()))
        if c.fetchone()[0] > 0: return jsonify({'success': False, 'error': 'Conta possui cartões vinculados'})
        c.execute("DELETE FROM contas WHERE id=? AND user_id=?", (conta_id, uid()))
        conn.commit()
    return jsonify({'success': True})


# ================================================================
# APIs — CARTÕES
# ================================================================

@app.route('/api/cartoes_disponiveis')
@login_required
def api_cartoes_disponiveis():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT ca.id, ca.nome, ca.tipo_pagamento, co.nome FROM cartoes ca LEFT JOIN contas co ON ca.conta=co.id WHERE ca.user_id=? ORDER BY ca.nome", (uid(),))
        cartoes = [{'id': r[0], 'nome': r[1], 'tipo_pagamento': r[2], 'conta_nome': r[3]} for r in c.fetchall()]
    return jsonify({'cartoes': cartoes})

@app.route('/api/adicionar_cartao', methods=['POST'])
@login_required
def adicionar_cartao():
    data = request.get_json()
    nome = (data.get('nome') or '').strip()
    conta = data.get('conta')
    tipo_pagamento  = data.get('tipo_pagamento')
    data_vencimento = data.get('data_vencimento')
    dias_fechamento = data.get('dias_fechamento')
    limite = float(data.get('limite') or 0)
    if not nome or not conta or not tipo_pagamento:
        return jsonify({'success': False, 'error': 'Nome, conta e tipo são obrigatórios'})
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO cartoes (user_id, nome, conta, tipo_pagamento, data_vencimento, dias_fechamento, limite) VALUES (?,?,?,?,?,?,?)",
                      (uid(), nome, conta, tipo_pagamento, data_vencimento, dias_fechamento, limite))
            conn.commit()
            return jsonify({'success': True, 'id': c.lastrowid, 'nome': nome})
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'error': 'Cartão já existe'})

@app.route('/api/remover_cartao', methods=['POST'])
@login_required
def remover_cartao():
    data = request.get_json()
    cartao_id = data.get('id')
    if not cartao_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM cartoes WHERE id=? AND user_id=?", (cartao_id, uid()))
        conn.commit()
    return jsonify({'success': True})


# ================================================================
# APIs — CATEGORIAS
# ================================================================

@app.route('/api/categorias')
@login_required
def api_categorias():
    tipo = request.args.get('tipo')
    with get_db() as conn:
        c = conn.cursor()
        if tipo in ('despesa', 'receita'):
            c.execute("SELECT id, nome, tipo FROM categorias WHERE tipo=? AND user_id=? ORDER BY nome", (tipo, uid()))
        else:
            c.execute("SELECT id, nome, tipo FROM categorias WHERE user_id=? ORDER BY nome", (uid(),))
        categorias = [{'id': r[0], 'nome': r[1], 'tipo': r[2]} for r in c.fetchall()]
    return jsonify({'categorias': categorias})

@app.route('/api/adicionar_categoria', methods=['POST'])
@login_required
def adicionar_categoria():
    data = request.get_json()
    nome = (data.get('nome') or '').strip()
    tipo = data.get('tipo', 'despesa')
    if not nome: return jsonify({'success': False, 'error': 'Nome obrigatório'})
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO categorias (user_id, nome, tipo) VALUES (?,?,?)", (uid(), nome, tipo))
            conn.commit()
            return jsonify({'success': True, 'id': c.lastrowid})
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'error': 'Categoria já existe'})

@app.route('/api/remover_categoria', methods=['POST'])
@login_required
def remover_categoria():
    data = request.get_json()
    cat_id = data.get('id')
    if not cat_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM categorias WHERE id=? AND user_id=?", (cat_id, uid()))
        conn.commit()
    return jsonify({'success': True})


# ================================================================
# APIs — LANÇAMENTOS (avulsos)
# ================================================================

@app.route('/api/adicionar_lancamento', methods=['POST'])
@login_required
def adicionar_lancamento():
    data = request.get_json()
    if not data: return jsonify({'success': False, 'error': 'Nenhum dado recebido'})

    descricao     = (data.get('descricao') or '').strip()
    tipo          = data.get('tipo')
    valor_str     = data.get('valor')
    categoria     = data.get('categoria')
    id_cartao_str = data.get('id_cartao')
    id_conta_str  = data.get('id_conta')
    tipo_receita  = data.get('tipo_receita',  'avulsa')
    tipo_cobranca = data.get('tipo_cobranca', 'avulsa')
    dia_venc_str  = data.get('dia_vencimento')
    tipo_compra   = data.get('tipo_compra', 'credito')
    pagamento     = data.get('pagamento',   'avista')
    parcelas_str  = data.get('parcelas')
    data_str      = data.get('data')

    if not descricao: return jsonify({'success': False, 'error': 'Descrição obrigatória'})
    if tipo not in ('despesa', 'receita'): return jsonify({'success': False, 'error': 'Tipo inválido'})
    try:
        valor = float(valor_str)
        if valor <= 0: raise ValueError
    except: return jsonify({'success': False, 'error': 'Valor inválido'})

    def to_int(v):
        try: return int(v) if v else None
        except: return None

    id_cartao = to_int(id_cartao_str)
    id_conta  = to_int(id_conta_str)
    dia_venc  = to_int(dia_venc_str)
    parcelas  = to_int(parcelas_str)

    try: data_lanc = date.fromisoformat(data_str) if data_str else date.today()
    except: data_lanc = date.today()

    if tipo == 'despesa' and not id_cartao:
        return jsonify({'success': False, 'error': 'Selecione um cartão para a despesa'})
    if tipo == 'receita' and not id_conta:
        return jsonify({'success': False, 'error': 'Selecione uma conta para a receita'})
    if pagamento == 'parcelado' and (not parcelas or parcelas < 2):
        return jsonify({'success': False, 'error': 'Parcelado exige mínimo 2 parcelas'})

    with get_db() as conn:
        c = conn.cursor()
        if tipo == 'despesa' and id_cartao:
            c.execute("SELECT tipo_pagamento FROM cartoes WHERE id=? AND user_id=?", (id_cartao, uid()))
            row = c.fetchone()
            if not row: return jsonify({'success': False, 'error': 'Cartão não encontrado'})
            tp = row[0]
            if tp != 'multiplo' and tipo_compra != tp:
                return jsonify({'success': False, 'error': f'Cartão só aceita {tp}'})
            if tp == 'debito' and pagamento == 'parcelado':
                return jsonify({'success': False, 'error': 'Débito não permite parcelamento'})

        c.execute("""
            INSERT INTO transacoes (user_id,tipo,descricao,valor,categoria,id_cartao,id_conta,
                tipo_receita,tipo_cobranca,dia_vencimento,tipo_compra,pagamento,parcelas,data_lancamento)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (uid(), tipo, descricao, valor, categoria, id_cartao, id_conta,
              tipo_receita, tipo_cobranca, dia_venc, tipo_compra,
              pagamento, parcelas, data_lanc.isoformat()))

        # Receita avulsa → credita agora
        # Despesa débito → debita agora
        # Despesa crédito parcelada ou à vista → NÃO mexe no saldo (cai na fatura)
        if tipo == 'receita' and tipo_receita == 'avulsa' and id_conta:
            c.execute("UPDATE contas SET saldo=saldo+? WHERE id=?", (valor, id_conta))
        elif tipo == 'despesa' and tipo_compra == 'debito' and id_cartao:
            c.execute("UPDATE contas SET saldo=saldo-? WHERE id=(SELECT conta FROM cartoes WHERE id=?)", (valor, id_cartao))

        conn.commit()
        return jsonify({'success': True, 'id': c.lastrowid})


@app.route('/api/remover_lancamento', methods=['POST'])
@login_required
def remover_lancamento():
    data = request.get_json()
    lid = data.get('id')
    if not lid: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT tipo, valor, id_conta, id_cartao, tipo_compra, tipo_receita FROM transacoes WHERE id=? AND user_id=?", (lid, uid()))
        row = c.fetchone()
        if row:
            tipo, valor, id_conta, id_cartao, tipo_compra, tipo_receita = row
            if tipo == 'receita' and tipo_receita != 'fixa' and id_conta:
                c.execute("UPDATE contas SET saldo=saldo-? WHERE id=?", (valor, id_conta))
            elif tipo == 'despesa' and tipo_compra == 'debito' and id_cartao:
                c.execute("UPDATE contas SET saldo=saldo+? WHERE id=(SELECT conta FROM cartoes WHERE id=?)", (valor, id_cartao))
        c.execute("DELETE FROM transacoes WHERE id=? AND user_id=?", (lid, uid()))
        conn.commit()
    return jsonify({'success': True})


# ================================================================
# APIs — RECEITAS FIXAS
# ================================================================

@app.route('/api/receitas_fixas')
@login_required
def api_listar_receitas_fixas():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT rf.id, rf.descricao, rf.valor, rf.categoria,
                   rf.id_conta, co.nome, rf.dia_mes, rf.ativa, COALESCE(rf.modo_dia,'fixo')
            FROM receitas_fixas rf LEFT JOIN contas co ON rf.id_conta=co.id
            ORDER BY rf.dia_mes, rf.descricao
        """)
        fixas = [{'id':r[0],'descricao':r[1],'valor':r[2],'categoria':r[3],
                  'id_conta':r[4],'conta_nome':r[5],'dia_mes':r[6],'ativa':r[7],'modo_dia':r[8]}
                 for r in c.fetchall()]
    return jsonify({'receitas_fixas': fixas})

@app.route('/api/adicionar_receita_fixa', methods=['POST'])
@login_required
def api_adicionar_receita_fixa():
    data = request.get_json()
    descricao = (data.get('descricao') or '').strip()
    valor_str = data.get('valor')
    categoria = data.get('categoria')
    id_conta  = data.get('id_conta')
    dia_mes   = int(data.get('dia_mes') or 1)
    modo_dia  = data.get('modo_dia', 'fixo')
    if not descricao or not valor_str or not id_conta:
        return jsonify({'success': False, 'error': 'Preencha todos os campos'})
    if modo_dia not in ('fixo','primeiro_util','ultimo_util'):
        return jsonify({'success': False, 'error': 'modo_dia inválido'})
    try: valor = float(valor_str)
    except: return jsonify({'success': False, 'error': 'Valor inválido'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO receitas_fixas (descricao,valor,categoria,id_conta,dia_mes,modo_dia) VALUES (?,?,?,?,?,?)",
                  (descricao, valor, categoria, id_conta, dia_mes, modo_dia))
        conn.commit()
        novo_id = c.lastrowid
    gerar_ocorrencias_receitas_fixas(user_id=uid())
    return jsonify({'success': True, 'id': novo_id})

@app.route('/api/remover_receita_fixa', methods=['POST'])
@login_required
def api_remover_receita_fixa():
    data = request.get_json()
    rf_id = data.get('id')
    if not rf_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM receitas_fixas WHERE id=? AND user_id=?", (rf_id, uid()))
        conn.commit()
    return jsonify({'success': True})

@app.route('/api/pausar_receita_fixa', methods=['POST'])
@login_required
def api_pausar_receita_fixa():
    data = request.get_json()
    rf_id = data.get('id')
    ativa = data.get('ativa', 1)
    if not rf_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE receitas_fixas SET ativa=? WHERE id=? AND user_id=?", (ativa, rf_id, uid()))
        conn.commit()
    return jsonify({'success': True})


# ================================================================
# APIs — DESPESAS FIXAS (assinaturas)
# ================================================================

@app.route('/api/despesas_fixas')
@login_required
def api_listar_despesas_fixas():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT df.id, df.descricao, df.valor, df.categoria,
                   df.id_cartao, ca.nome AS cartao_nome,
                   df.id_conta,  co.nome AS conta_nome,
                   df.dia_mes, df.ativa, COALESCE(df.modo_dia,'fixo')
            FROM despesas_fixas df
            LEFT JOIN cartoes ca ON df.id_cartao=ca.id
            LEFT JOIN contas  co ON df.id_conta=co.id
            ORDER BY df.dia_mes, df.descricao
        """, (uid(),))
        fixas = [{'id':r[0],'descricao':r[1],'valor':r[2],'categoria':r[3],
                  'id_cartao':r[4],'cartao_nome':r[5],'id_conta':r[6],'conta_nome':r[7],
                  'dia_mes':r[8],'ativa':r[9],'modo_dia':r[10]}
                 for r in c.fetchall()]
    return jsonify({'despesas_fixas': fixas})

@app.route('/api/adicionar_despesa_fixa', methods=['POST'])
@login_required
def api_adicionar_despesa_fixa():
    data = request.get_json()
    descricao  = (data.get('descricao') or '').strip()
    valor_str  = data.get('valor')
    categoria  = data.get('categoria')
    id_cartao  = data.get('id_cartao') or None
    id_conta   = data.get('id_conta')  or None
    dia_mes    = int(data.get('dia_mes') or 1)
    modo_dia   = data.get('modo_dia', 'fixo')
    if not descricao or not valor_str:
        return jsonify({'success': False, 'error': 'Preencha todos os campos'})
    if not id_cartao and not id_conta:
        return jsonify({'success': False, 'error': 'Selecione cartão ou conta'})
    if modo_dia not in ('fixo','primeiro_util','ultimo_util'):
        return jsonify({'success': False, 'error': 'modo_dia inválido'})
    try: valor = float(valor_str)
    except: return jsonify({'success': False, 'error': 'Valor inválido'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO despesas_fixas (descricao,valor,categoria,id_cartao,id_conta,dia_mes,modo_dia) VALUES (?,?,?,?,?,?,?)",
                  (descricao, valor, categoria, id_cartao, id_conta, dia_mes, modo_dia))
        conn.commit()
        novo_id = c.lastrowid
    gerar_ocorrencias_despesas_fixas(user_id=uid())
    return jsonify({'success': True, 'id': novo_id})

@app.route('/api/remover_despesa_fixa', methods=['POST'])
@login_required
def api_remover_despesa_fixa():
    data = request.get_json()
    df_id = data.get('id')
    if not df_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM despesas_fixas WHERE id=? AND user_id=?", (df_id, uid()))
        conn.commit()
    return jsonify({'success': True})

@app.route('/api/pausar_despesa_fixa', methods=['POST'])
@login_required
def api_pausar_despesa_fixa():
    data = request.get_json()
    df_id = data.get('id')
    ativa = data.get('ativa', 1)
    if not df_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE despesas_fixas SET ativa=? WHERE id=? AND user_id=?", (ativa, df_id, uid()))
        conn.commit()
    return jsonify({'success': True})


# ================================================================
# API — FATURA DETALHADA
# ================================================================

@app.route('/api/fatura/<int:cartao_id>')
@login_required
def fatura_cartao(cartao_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT data_vencimento, dias_fechamento FROM cartoes WHERE id=?", (cartao_id,))
        row = c.fetchone()
        if not row: return jsonify({'success': False, 'error': 'Cartão não encontrado'})
        inicio, fim, venc = periodo_fatura_atual(row[0], row[1])
        c.execute("""
            SELECT id, descricao, valor, data_lancamento, categoria, pagamento, parcelas
            FROM transacoes
            WHERE tipo='despesa' AND id_cartao=? AND data_lancamento BETWEEN ? AND ?
            ORDER BY data_lancamento
        """, (cartao_id, inicio.isoformat(), fim.isoformat()))
        itens = []
        total = 0.0
        for r in c.fetchall():
            tid, desc, vt, ds, cat, pag, parc = r
            if pag == 'parcelado' and parc and parc >= 2:
                try: dc = date.fromisoformat(str(ds)[:10])
                except: dc = date.today()
                v_item = valor_parcela_na_fatura(vt, parc, dc, inicio, fim)
                label = f"{desc} ({parc}x)"
            else:
                v_item = vt
                label  = desc
            itens.append({'id': tid, 'descricao': label, 'valor': round(v_item, 2),
                          'data': ds, 'categoria': cat})
            total += v_item
    return jsonify({
        'periodo_inicio': inicio.strftime('%d/%m/%Y'),
        'periodo_fim':    fim.strftime('%d/%m/%Y'),
        'vencimento':     venc.strftime('%d/%m/%Y'),
        'itens':          itens,
        'total':          round(total, 2),
    })


# ================================================================
# INICIALIZAÇÃO
# ================================================================


# ==============================================================
# APIs — UPDATE (edição in-place)
# ==============================================================

@app.route('/api/atualizar_lancamento', methods=['POST'])
@login_required
def atualizar_lancamento():
    """
    Atualiza campos editáveis de um lançamento.
    Campos: descricao, categoria, data, valor, parcelas.
    Cartão e tipo_compra não são alterados para não quebrar saldo.
    Para débito: ajusta saldo pela diferença de valor.
    """
    data = request.get_json()
    lid       = data.get('id')
    descricao = (data.get('descricao') or '').strip()
    categoria = data.get('categoria')
    data_str  = data.get('data')
    valor_str = data.get('valor')
    parcelas  = data.get('parcelas')

    if not lid or not descricao:
        return jsonify({'success': False, 'error': 'ID e descrição são obrigatórios'})

    try:
        novo_valor = float(valor_str)
        if novo_valor <= 0: raise ValueError
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Valor inválido'})

    try:
        nova_data = date.fromisoformat(data_str) if data_str else None
    except ValueError:
        return jsonify({'success': False, 'error': 'Data inválida'})

    try:
        novas_parcelas = int(parcelas) if parcelas else None
    except (TypeError, ValueError):
        novas_parcelas = None

    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT tipo, valor, parcelas, id_cartao, tipo_compra FROM transacoes WHERE id=?
        """, (lid,))
        row = c.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Lançamento não encontrado'})

        tipo, valor_antigo, parcelas_antigas, id_cartao, tipo_compra = row

        # Ajusta saldo para débito à vista
        if tipo == 'despesa' and tipo_compra == 'debito' and id_cartao:
            delta = novo_valor - valor_antigo
            if delta != 0:
                c.execute("""
                    UPDATE contas SET saldo = saldo - ?
                    WHERE id = (SELECT conta FROM cartoes WHERE id=?)
                """, (delta, id_cartao))

        # Ajusta saldo para receita avulsa
        if tipo == 'receita':
            delta = novo_valor - valor_antigo
            if delta != 0:
                c.execute("""
                    SELECT id_conta FROM transacoes WHERE id=?
                """, (lid,))
                id_conta = c.fetchone()
                if id_conta and id_conta[0]:
                    c.execute("UPDATE contas SET saldo = saldo + ? WHERE id=?", (delta, id_conta[0]))

        c.execute("""
            UPDATE transacoes
            SET descricao=?, categoria=?, data_lancamento=?, valor=?, parcelas=?
            WHERE id=? AND user_id=?
        """, (descricao, categoria,
              nova_data.isoformat() if nova_data else None,
              novo_valor,
              novas_parcelas,
              lid))
        conn.commit()

    return jsonify({'success': True})


@app.route('/api/atualizar_cartao', methods=['POST'])
@login_required
def atualizar_cartao():
    data = request.get_json()
    cid             = data.get('id')
    nome            = (data.get('nome') or '').strip()
    limite          = data.get('limite')
    data_vencimento = data.get('data_vencimento')
    dias_fechamento = data.get('dias_fechamento')

    if not cid or not nome:
        return jsonify({'success': False, 'error': 'ID e nome são obrigatórios'})

    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute("""
                UPDATE cartoes SET nome=?, limite=?, data_vencimento=?, dias_fechamento=?
                WHERE id=?
            """, (nome, float(limite or 0), data_vencimento, dias_fechamento, cid))
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'error': 'Já existe um cartão com esse nome'})

    return jsonify({'success': True})


@app.route('/api/atualizar_conta', methods=['POST'])
@login_required
def atualizar_conta():
    data = request.get_json()
    cid  = data.get('id')
    nome = (data.get('nome') or '').strip()

    if not cid or not nome:
        return jsonify({'success': False, 'error': 'ID e nome são obrigatórios'})

    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute("UPDATE contas SET nome=? WHERE id=? AND user_id=?", (nome, cid, uid()))
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'error': 'Já existe uma conta com esse nome'})

    return jsonify({'success': True})


@app.route('/api/atualizar_categoria', methods=['POST'])
@login_required
def atualizar_categoria():
    data = request.get_json()
    cid  = data.get('id')
    nome = (data.get('nome') or '').strip()

    if not cid or not nome:
        return jsonify({'success': False, 'error': 'ID e nome são obrigatórios'})

    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute("UPDATE categorias SET nome=? WHERE id=? AND user_id=?", (nome, cid, uid()))
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'error': 'Categoria já existe com esse nome'})

    return jsonify({'success': True})


@app.route('/api/atualizar_receita_fixa', methods=['POST'])
@login_required
def atualizar_receita_fixa():
    data     = request.get_json()
    rid      = data.get('id')
    descricao = (data.get('descricao') or '').strip()
    categoria = data.get('categoria')
    valor_str = data.get('valor')
    dia_mes   = data.get('dia_mes', 1)
    modo_dia  = data.get('modo_dia', 'fixo')

    if not rid or not descricao:
        return jsonify({'success': False, 'error': 'ID e descrição são obrigatórios'})
    if modo_dia not in ('fixo', 'primeiro_util', 'ultimo_util'):
        return jsonify({'success': False, 'error': 'modo_dia inválido'})
    try:
        valor = float(valor_str)
        if valor <= 0: raise ValueError
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Valor inválido'})

    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE receitas_fixas
            SET descricao=?, categoria=?, valor=?, dia_mes=?, modo_dia=?
            WHERE id=? AND user_id=?
        """, (descricao, categoria, valor, int(dia_mes), modo_dia, rid, uid()))
        conn.commit()

    return jsonify({'success': True})


@app.route('/api/atualizar_despesa_fixa', methods=['POST'])
@login_required
def atualizar_despesa_fixa():
    data      = request.get_json()
    did       = data.get('id')
    descricao = (data.get('descricao') or '').strip()
    categoria = data.get('categoria')
    valor_str = data.get('valor')
    dia_mes   = data.get('dia_mes', 1)
    modo_dia  = data.get('modo_dia', 'fixo')

    if not did or not descricao:
        return jsonify({'success': False, 'error': 'ID e descrição são obrigatórios'})
    if modo_dia not in ('fixo', 'primeiro_util', 'ultimo_util'):
        return jsonify({'success': False, 'error': 'modo_dia inválido'})
    try:
        valor = float(valor_str)
        if valor <= 0: raise ValueError
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Valor inválido'})

    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE despesas_fixas
            SET descricao=?, categoria=?, valor=?, dia_mes=?, modo_dia=?
            WHERE id=? AND user_id=?
        """, (descricao, categoria, valor, int(dia_mes), modo_dia, did, uid()))
        conn.commit()

    return jsonify({'success': True})


# ================================================================
# AUTENTICAÇÃO — login / cadastro / logout
# ================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if uid():
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        senha = request.form.get('senha') or ''

        if not email or not senha:
            flash('Preencha email e senha.', 'danger')
            return render_template('login.html')

        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT id, nome, senha_hash, role, ativo FROM usuarios WHERE email=?", (email,))
            user = c.fetchone()

        if not user or not check_password_hash(user[2], senha):
            flash('Email ou senha incorretos.', 'danger')
            return render_template('login.html')

        if not user[4]:
            flash('Conta desativada. Entre em contato com o administrador.', 'warning')
            return render_template('login.html')

        session.permanent = True
        session['user_id']   = user[0]
        session['user_nome'] = user[1]
        session['user_role'] = user[3]
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if uid():
        return redirect(url_for('index'))

    if request.method == 'POST':
        nome  = (request.form.get('nome')  or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        senha = request.form.get('senha')  or ''
        conf  = request.form.get('confirmar_senha') or ''

        erros = []
        if not nome:             erros.append('Nome obrigatório.')
        if not email:            erros.append('Email obrigatório.')
        if len(senha) < 8:       erros.append('Senha deve ter pelo menos 8 caracteres.')
        if senha != conf:        erros.append('Senhas não coincidem.')

        if erros:
            for e in erros: flash(e, 'danger')
            return render_template('cadastro.html', nome=nome, email=email)

        senha_hash = generate_password_hash(senha)

        with get_db() as conn:
            c = conn.cursor()
            try:
                c.execute(
                    "INSERT INTO usuarios (nome, email, senha_hash) VALUES (?,?,?)",
                    (nome, email, senha_hash)
                )
                conn.commit()
                novo_id = c.lastrowid
            except Exception:
                flash('Este email já está cadastrado.', 'danger')
                return render_template('cadastro.html', nome=nome, email=email)

        criar_categorias_padrao(novo_id)

        flash('Conta criada com sucesso! Faça login.', 'success')
        return redirect(url_for('login'))

    return render_template('cadastro.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('login'))


# ================================================================
# ADMIN — painel de usuários
# ================================================================

@app.route('/admin')
@admin_required
def admin():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT u.id, u.nome, u.email, u.role, u.ativo, u.criado_em,
                   COUNT(DISTINCT t.id)  AS total_transacoes,
                   COUNT(DISTINCT co.id) AS total_contas,
                   COUNT(DISTINCT ca.id) AS total_cartoes
            FROM usuarios u
            LEFT JOIN transacoes  t  ON t.user_id  = u.id
            LEFT JOIN contas      co ON co.user_id = u.id
            LEFT JOIN cartoes     ca ON ca.user_id = u.id
            GROUP BY u.id ORDER BY u.criado_em DESC
        """)
        usuarios = [dict(r) for r in c.fetchall()]
    return render_template('admin.html', usuarios=usuarios)


@app.route('/api/admin/usuarios')
@admin_required
def api_admin_usuarios():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, nome, email, role, ativo, criado_em FROM usuarios ORDER BY criado_em DESC
        """)
        usuarios = [dict(r) for r in c.fetchall()]
    return jsonify({'usuarios': usuarios})


@app.route('/api/admin/usuario/<int:user_id>', methods=['POST'])
@admin_required
def api_admin_usuario(user_id):
    """Ativa/desativa ou promove/rebaixa um usuário."""
    data = request.get_json()
    acao = data.get('acao')  # 'ativar' | 'desativar' | 'promover' | 'rebaixar' | 'resetar_senha'

    # Admin não pode agir sobre si mesmo para desativar/rebaixar
    if user_id == uid() and acao in ('desativar', 'rebaixar'):
        return jsonify({'success': False, 'error': 'Você não pode fazer isso na sua própria conta.'})

    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, role FROM usuarios WHERE id=?", (user_id,))
        user = c.fetchone()
        if not user:
            return jsonify({'success': False, 'error': 'Usuário não encontrado.'})

        if acao == 'ativar':
            c.execute("UPDATE usuarios SET ativo=1 WHERE id=?", (user_id,))
        elif acao == 'desativar':
            c.execute("UPDATE usuarios SET ativo=0 WHERE id=?", (user_id,))
        elif acao == 'promover':
            c.execute("UPDATE usuarios SET role='admin' WHERE id=?", (user_id,))
        elif acao == 'rebaixar':
            c.execute("UPDATE usuarios SET role='user' WHERE id=?", (user_id,))
        elif acao == 'resetar_senha':
            nova = data.get('nova_senha', '')
            if len(nova) < 8:
                return jsonify({'success': False, 'error': 'Senha deve ter mínimo 8 caracteres.'})
            c.execute("UPDATE usuarios SET senha_hash=? WHERE id=?",
                      (generate_password_hash(nova), user_id))
        else:
            return jsonify({'success': False, 'error': 'Ação inválida.'})

        conn.commit()

    return jsonify({'success': True})


@app.route('/api/minha_conta', methods=['POST'])
@login_required
def minha_conta():
    """Permite ao usuário alterar nome e/ou senha."""
    data = request.get_json()
    nome      = (data.get('nome') or '').strip()
    senha_atual = data.get('senha_atual') or ''
    nova_senha  = data.get('nova_senha')  or ''

    if not nome:
        return jsonify({'success': False, 'error': 'Nome obrigatório.'})

    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT senha_hash FROM usuarios WHERE id=?", (uid(),))
        row = c.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Usuário não encontrado.'})

        updates = ['nome=?']
        params  = [nome]

        if nova_senha:
            if not check_password_hash(row[0], senha_atual):
                return jsonify({'success': False, 'error': 'Senha atual incorreta.'})
            if len(nova_senha) < 8:
                return jsonify({'success': False, 'error': 'Nova senha deve ter mínimo 8 caracteres.'})
            updates.append('senha_hash=?')
            params.append(generate_password_hash(nova_senha))

        params.append(uid())
        c.execute(f"UPDATE usuarios SET {', '.join(updates)} WHERE id=?", params)
        conn.commit()

    session['user_nome'] = nome
    return jsonify({'success': True})

if __name__ == '__main__':
    init_db()
    gerar_ocorrencias_receitas_fixas()
    gerar_ocorrencias_despesas_fixas()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
