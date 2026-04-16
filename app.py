from flask import Flask, render_template, request, jsonify
import sqlite3, os, calendar
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta  # pip install python-dateutil

app = Flask(__name__)
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

        # ── transacoes ──────────────────────────────────────────
        # valor = valor TOTAL da compra (não da parcela).
        # Para calcular a parcela: valor / parcelas.
        # tipo_cobranca='fixa' agora é APENAS legado/avulsa — despesas fixas recorrentes
        # ficam em despesas_fixas (igual a receitas_fixas).
        c.execute('''CREATE TABLE IF NOT EXISTS transacoes (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo             TEXT NOT NULL CHECK(tipo IN ('despesa','receita')),
            descricao        TEXT NOT NULL,
            valor            REAL NOT NULL,   -- valor TOTAL; parcela = valor/parcelas
            categoria        TEXT,
            id_cartao        INTEGER REFERENCES cartoes(id),
            id_conta         INTEGER REFERENCES contas(id),
            tipo_receita     TEXT CHECK(tipo_receita  IN ('avulsa','fixa'))     DEFAULT 'avulsa',
            tipo_cobranca    TEXT CHECK(tipo_cobranca IN ('avulsa','fixa'))     DEFAULT 'avulsa',
            dia_vencimento   INTEGER,
            tipo_compra      TEXT CHECK(tipo_compra   IN ('credito','debito'))  DEFAULT 'credito',
            pagamento        TEXT CHECK(pagamento     IN ('avista','parcelado')) DEFAULT 'avista',
            parcelas         INTEGER DEFAULT NULL,
            data_lancamento  DATE NOT NULL DEFAULT (DATE('now'))
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS categorias (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            tipo TEXT CHECK(tipo IN ('despesa','receita')) DEFAULT 'despesa'
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS contas (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            nome  TEXT UNIQUE NOT NULL,
            saldo REAL DEFAULT 0
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS cartoes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nome            TEXT UNIQUE NOT NULL,
            conta           INTEGER NOT NULL REFERENCES contas(id),
            tipo_pagamento  TEXT CHECK(tipo_pagamento IN ('credito','debito','multiplo')),
            data_vencimento INTEGER,   -- dia do mês (1-31)
            dias_fechamento INTEGER,   -- dias antes do vencimento que a fatura fecha
            limite          REAL DEFAULT 0
        )''')

        # ── receitas_fixas ──────────────────────────────────────
        # Receitas recorrentes (salário, aluguel recebido, etc.).
        # modo_dia: 'fixo' | 'primeiro_util' | 'ultimo_util'
        c.execute('''CREATE TABLE IF NOT EXISTS receitas_fixas (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            valor     REAL NOT NULL,
            categoria TEXT,
            id_conta  INTEGER NOT NULL REFERENCES contas(id),
            dia_mes   INTEGER NOT NULL DEFAULT 1,
            modo_dia  TEXT NOT NULL DEFAULT 'fixo',
            ativa     INTEGER DEFAULT 1
        )''')

        # ── despesas_fixas ──────────────────────────────────────
        # Assinaturas e gastos recorrentes (Netflix, academia, aluguel, etc.).
        # Funciona exatamente como receitas_fixas mas debita a conta ou fica
        # na fatura do cartão.
        # Se id_cartao preenchido → vai para crédito (não debita conta direto).
        # Se id_conta preenchido e sem cartão → debita a conta no dia.
        c.execute('''CREATE TABLE IF NOT EXISTS despesas_fixas (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            valor     REAL NOT NULL,
            categoria TEXT,
            id_cartao INTEGER REFERENCES cartoes(id),
            id_conta  INTEGER REFERENCES contas(id),
            dia_mes   INTEGER NOT NULL DEFAULT 1,
            modo_dia  TEXT NOT NULL DEFAULT 'fixo',
            ativa     INTEGER DEFAULT 1
        )''')

        # Migrações seguras
        for sql in [
            "ALTER TABLE receitas_fixas ADD COLUMN modo_dia TEXT NOT NULL DEFAULT 'fixo'",
            "ALTER TABLE despesas_fixas ADD COLUMN modo_dia TEXT NOT NULL DEFAULT 'fixo'",
        ]:
            try: c.execute(sql)
            except: pass

        # Categorias padrão
        for nome, tipo in [
            ('Alimentação','despesa'), ('Transporte','despesa'), ('Moradia','despesa'),
            ('Saúde','despesa'),       ('Educação','despesa'),   ('Lazer','despesa'),
            ('Assinaturas','despesa'), ('Salário','receita'),
            ('Investimentos','receita'), ('Freelance','receita'), ('Presente','receita'),
        ]:
            c.execute("INSERT OR IGNORE INTO categorias (nome, tipo) VALUES (?,?)", (nome, tipo))

        conn.commit()


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

def gerar_ocorrencias_receitas_fixas():
    """
    Para cada receita fixa ativa: se a data de ocorrência do mês atual
    já chegou/passou e ainda não foi gerada → cria a transação e credita saldo.
    """
    hoje = date.today()
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, descricao, valor, categoria, id_conta, dia_mes, modo_dia FROM receitas_fixas WHERE ativa=1")
        for rf_id, desc, valor, cat, id_conta, dia_mes, modo in c.fetchall():
            data_oc = data_ocorrencia(hoje.year, hoje.month, dia_mes, modo or 'fixo')
            if hoje < data_oc: continue
            chave = f'_rf_{rf_id}'
            c.execute("SELECT COUNT(*) FROM transacoes WHERE tipo='receita' AND id_conta=? AND categoria=? AND strftime('%Y-%m',data_lancamento)=?",
                      (id_conta, chave, hoje.strftime('%Y-%m')))
            if c.fetchone()[0] > 0: continue
            c.execute("INSERT INTO transacoes (tipo,descricao,valor,categoria,id_conta,tipo_receita,data_lancamento) VALUES ('receita',?,?,?,?,'avulsa',?)",
                      (desc, valor, chave, id_conta, data_oc.isoformat()))
            c.execute("UPDATE contas SET saldo=saldo+? WHERE id=?", (valor, id_conta))
        conn.commit()


def gerar_ocorrencias_despesas_fixas():
    """
    Para cada despesa fixa ativa: se a data de ocorrência do mês atual
    já chegou/passou e ainda não foi gerada → cria a transação.
    - Com cartão de crédito: não debita conta (entra na fatura).
    - Com débito/conta direta: debita a conta imediatamente.
    """
    hoje = date.today()
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, descricao, valor, categoria, id_cartao, id_conta, dia_mes, modo_dia FROM despesas_fixas WHERE ativa=1")
        for df_id, desc, valor, cat, id_cartao, id_conta, dia_mes, modo in c.fetchall():
            data_oc = data_ocorrencia(hoje.year, hoje.month, dia_mes, modo or 'fixo')
            if hoje < data_oc: continue
            chave = f'_df_{df_id}'
            c.execute("SELECT COUNT(*) FROM transacoes WHERE tipo='despesa' AND categoria=? AND strftime('%Y-%m',data_lancamento)=?",
                      (chave, hoje.strftime('%Y-%m')))
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
                (tipo,descricao,valor,categoria,id_cartao,id_conta,tipo_cobranca,tipo_compra,pagamento,data_lancamento)
                VALUES ('despesa',?,?,?,?,?,'fixa',?,'avista',?)""",
                (desc, valor, chave, id_cartao, id_conta, tipo_compra, data_oc.isoformat()))

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
        c.execute("SELECT id, valor, dia_mes, modo_dia, id_conta FROM receitas_fixas WHERE ativa=1")
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
          AND (categoria IS NULL OR (categoria NOT LIKE '_rf_%' AND categoria NOT LIKE '_df_%'))
    """, (mes_str,))
    total = c.fetchone()[0]

    # Parcelas que caem neste mês (independente de quando a compra foi feita)
    c.execute("""
        SELECT valor, parcelas, data_lancamento FROM transacoes
        WHERE tipo = 'despesa'
          AND pagamento = 'parcelado'
          AND parcelas >= 2
          AND (categoria IS NULL OR (categoria NOT LIKE '_rf_%' AND categoria NOT LIKE '_df_%'))
    """)
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
            ORDER BY t.data_lancamento DESC, t.id DESC LIMIT 10
        """)
        transacoes = [dict(r) for r in c.fetchall()]

        c.execute("SELECT COALESCE(SUM(saldo), 0) FROM contas")
        saldo_total = round(c.fetchone()[0], 2)

        hoje = date.today()
        c.execute("""
            SELECT COALESCE(SUM(valor), 0) FROM transacoes
            WHERE tipo='receita' AND strftime('%Y-%m', data_lancamento)=?
              AND (categoria IS NULL OR categoria NOT LIKE '_rf_%')
        """, (hoje.strftime('%Y-%m'),))
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

    return render_template('index.html',
        transacoes=transacoes,
        saldo_total=saldo_total,
        receitas_mes=receitas_mes,
        gasto_credito=fatura_atual,
        disponivel_mes=disponivel_mes,
        proximas_faturas=projecao_mensal(3),
        gastos_por_categoria=gastos_por_categoria,
    )


@app.route('/api/dashboard_data')
def dashboard_data():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COALESCE(SUM(saldo), 0) FROM contas")
        saldo_total = round(c.fetchone()[0], 2)
        hoje = date.today()
        c.execute("""
            SELECT COALESCE(SUM(valor), 0) FROM transacoes
            WHERE tipo='receita' AND strftime('%Y-%m', data_lancamento)=?
              AND (categoria IS NULL OR categoria NOT LIKE '_rf_%')
        """, (hoje.strftime('%Y-%m'),))
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


# ================================================================
# ROTAS DE PÁGINAS
# ================================================================

@app.route('/lancamentos')
def lancamentos():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT t.id, t.descricao, t.tipo, t.valor, t.categoria,
                   ca.nome AS cartao_nome, t.data_lancamento,
                   t.pagamento, t.parcelas, t.tipo_compra, t.tipo_cobranca
            FROM transacoes t LEFT JOIN cartoes ca ON t.id_cartao=ca.id
            WHERE t.tipo='despesa'
              AND (t.categoria IS NULL OR t.categoria NOT LIKE '_df_%')
            ORDER BY t.data_lancamento DESC, t.id DESC
        """)
        lancamentos_db = [list(r) for r in c.fetchall()]
    return render_template('lancamentos.html', lancamentos=lancamentos_db)


@app.route('/lancamentosReceita')
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
            WHERE t.tipo='receita'
              AND (t.categoria IS NULL OR t.categoria NOT LIKE '_rf_%')
            ORDER BY t.data_lancamento DESC, t.id DESC
        """)
        receitas = [list(r) for r in c.fetchall()]
    return render_template('lancamentosReceita.html', receitas=receitas)


@app.route('/lancamentosAssinaturas')
def lancamentosAssinaturas():
    return render_template('lancamentosAssinaturas.html')


@app.route('/lancamentosConta')
def lancamentosConta():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, nome, saldo FROM contas ORDER BY nome")
        contas = [list(r) for r in c.fetchall()]
    return render_template('lancamentosConta.html', contas=contas)


@app.route('/lancamentosCartao')
def lancamentosCartao():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT ca.id, ca.nome, co.nome AS conta_nome,
                   ca.dias_fechamento, ca.data_vencimento, ca.tipo_pagamento, ca.limite
            FROM cartoes ca LEFT JOIN contas co ON ca.conta=co.id ORDER BY ca.nome
        """)
        cartoes = [list(r) for r in c.fetchall()]
        c.execute("SELECT id, nome FROM contas ORDER BY nome")
        contas = [list(r) for r in c.fetchall()]
    return render_template('lancamentosCartao.html', cartoes=cartoes, contas=contas)


@app.route('/lancamentosCategorias')
def lancamentosCategorias():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, nome, tipo FROM categorias ORDER BY tipo, nome")
        categorias = [list(r) for r in c.fetchall()]
    return render_template('lancamentosCategorias.html', categorias=categorias)


@app.route('/projecoes')
def projecoes():
    return render_template('projecoes.html', projecoes=projecao_mensal(6))


@app.route('/visaoGeral')
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
                WHERE tipo='receita' AND strftime('%Y-%m',data_lancamento)=?
            """, (ms,))
            rec = round(c.fetchone()[0], 2)
            # Despesas: usa despesas_reais_mes para tratar parcelas corretamente
            desp = despesas_reais_mes(ref.year, ref.month, conn)
            historico.append({
                'label': f"{meses_pt[ref.month]}/{ref.year}",
                'receitas': rec, 'despesas': desp, 'saldo': round(rec - desp, 2)
            })

        por_categoria = gastos_categoria_mes(hoje.year, hoje.month, conn, limit=20)

        c.execute("SELECT nome, saldo FROM contas ORDER BY nome")
        por_conta = [{'nome': r[0], 'saldo': round(r[1],2)} for r in c.fetchall()]

        c.execute("""
            SELECT ca.id, ca.nome, ca.data_vencimento, ca.dias_fechamento, ca.limite
            FROM cartoes ca WHERE ca.tipo_pagamento IN ('credito','multiplo')
              AND ca.data_vencimento IS NOT NULL AND ca.dias_fechamento IS NOT NULL
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
def api_contas():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, nome, saldo FROM contas ORDER BY nome")
        contas = [{'id': r[0], 'nome': r[1], 'saldo': r[2]} for r in c.fetchall()]
    return jsonify({'contas': contas})

@app.route('/api/adicionar_conta', methods=['POST'])
def adicionar_conta():
    data = request.get_json()
    nome = (data.get('nome') or '').strip()
    if not nome: return jsonify({'success': False, 'error': 'Nome obrigatório'})
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO contas (nome, saldo) VALUES (?, 0)", (nome,))
            conn.commit()
            return jsonify({'success': True, 'id': c.lastrowid, 'nome': nome})
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'error': 'Conta já existe'})

@app.route('/api/remover_conta', methods=['POST'])
def remover_conta():
    data = request.get_json()
    conta_id = data.get('id')
    if not conta_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM cartoes WHERE conta=?", (conta_id,))
        if c.fetchone()[0] > 0: return jsonify({'success': False, 'error': 'Conta possui cartões vinculados'})
        c.execute("DELETE FROM contas WHERE id=?", (conta_id,))
        conn.commit()
    return jsonify({'success': True})


# ================================================================
# APIs — CARTÕES
# ================================================================

@app.route('/api/cartoes_disponiveis')
def api_cartoes_disponiveis():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT ca.id, ca.nome, ca.tipo_pagamento, co.nome FROM cartoes ca LEFT JOIN contas co ON ca.conta=co.id ORDER BY ca.nome")
        cartoes = [{'id': r[0], 'nome': r[1], 'tipo_pagamento': r[2], 'conta_nome': r[3]} for r in c.fetchall()]
    return jsonify({'cartoes': cartoes})

@app.route('/api/adicionar_cartao', methods=['POST'])
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
            c.execute("INSERT INTO cartoes (nome, conta, tipo_pagamento, data_vencimento, dias_fechamento, limite) VALUES (?,?,?,?,?,?)",
                      (nome, conta, tipo_pagamento, data_vencimento, dias_fechamento, limite))
            conn.commit()
            return jsonify({'success': True, 'id': c.lastrowid, 'nome': nome})
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'error': 'Cartão já existe'})

@app.route('/api/remover_cartao', methods=['POST'])
def remover_cartao():
    data = request.get_json()
    cartao_id = data.get('id')
    if not cartao_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM cartoes WHERE id=?", (cartao_id,))
        conn.commit()
    return jsonify({'success': True})


# ================================================================
# APIs — CATEGORIAS
# ================================================================

@app.route('/api/categorias')
def api_categorias():
    tipo = request.args.get('tipo')
    with get_db() as conn:
        c = conn.cursor()
        if tipo in ('despesa', 'receita'):
            c.execute("SELECT id, nome, tipo FROM categorias WHERE tipo=? ORDER BY nome", (tipo,))
        else:
            c.execute("SELECT id, nome, tipo FROM categorias ORDER BY nome")
        categorias = [{'id': r[0], 'nome': r[1], 'tipo': r[2]} for r in c.fetchall()]
    return jsonify({'categorias': categorias})

@app.route('/api/adicionar_categoria', methods=['POST'])
def adicionar_categoria():
    data = request.get_json()
    nome = (data.get('nome') or '').strip()
    tipo = data.get('tipo', 'despesa')
    if not nome: return jsonify({'success': False, 'error': 'Nome obrigatório'})
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO categorias (nome, tipo) VALUES (?,?)", (nome, tipo))
            conn.commit()
            return jsonify({'success': True, 'id': c.lastrowid})
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'error': 'Categoria já existe'})

@app.route('/api/remover_categoria', methods=['POST'])
def remover_categoria():
    data = request.get_json()
    cat_id = data.get('id')
    if not cat_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM categorias WHERE id=?", (cat_id,))
        conn.commit()
    return jsonify({'success': True})


# ================================================================
# APIs — LANÇAMENTOS (avulsos)
# ================================================================

@app.route('/api/adicionar_lancamento', methods=['POST'])
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
            c.execute("SELECT tipo_pagamento FROM cartoes WHERE id=?", (id_cartao,))
            row = c.fetchone()
            if not row: return jsonify({'success': False, 'error': 'Cartão não encontrado'})
            tp = row[0]
            if tp != 'multiplo' and tipo_compra != tp:
                return jsonify({'success': False, 'error': f'Cartão só aceita {tp}'})
            if tp == 'debito' and pagamento == 'parcelado':
                return jsonify({'success': False, 'error': 'Débito não permite parcelamento'})

        c.execute("""
            INSERT INTO transacoes (tipo,descricao,valor,categoria,id_cartao,id_conta,
                tipo_receita,tipo_cobranca,dia_vencimento,tipo_compra,pagamento,parcelas,data_lancamento)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (tipo, descricao, valor, categoria, id_cartao, id_conta,
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
def remover_lancamento():
    data = request.get_json()
    lid = data.get('id')
    if not lid: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT tipo, valor, id_conta, id_cartao, tipo_compra, tipo_receita FROM transacoes WHERE id=?", (lid,))
        row = c.fetchone()
        if row:
            tipo, valor, id_conta, id_cartao, tipo_compra, tipo_receita = row
            if tipo == 'receita' and tipo_receita != 'fixa' and id_conta:
                c.execute("UPDATE contas SET saldo=saldo-? WHERE id=?", (valor, id_conta))
            elif tipo == 'despesa' and tipo_compra == 'debito' and id_cartao:
                c.execute("UPDATE contas SET saldo=saldo+? WHERE id=(SELECT conta FROM cartoes WHERE id=?)", (valor, id_cartao))
        c.execute("DELETE FROM transacoes WHERE id=?", (lid,))
        conn.commit()
    return jsonify({'success': True})


# ================================================================
# APIs — RECEITAS FIXAS
# ================================================================

@app.route('/api/receitas_fixas')
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
    gerar_ocorrencias_receitas_fixas()
    return jsonify({'success': True, 'id': novo_id})

@app.route('/api/remover_receita_fixa', methods=['POST'])
def api_remover_receita_fixa():
    data = request.get_json()
    rf_id = data.get('id')
    if not rf_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM receitas_fixas WHERE id=?", (rf_id,))
        conn.commit()
    return jsonify({'success': True})

@app.route('/api/pausar_receita_fixa', methods=['POST'])
def api_pausar_receita_fixa():
    data = request.get_json()
    rf_id = data.get('id')
    ativa = data.get('ativa', 1)
    if not rf_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE receitas_fixas SET ativa=? WHERE id=?", (ativa, rf_id))
        conn.commit()
    return jsonify({'success': True})


# ================================================================
# APIs — DESPESAS FIXAS (assinaturas)
# ================================================================

@app.route('/api/despesas_fixas')
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
        """)
        fixas = [{'id':r[0],'descricao':r[1],'valor':r[2],'categoria':r[3],
                  'id_cartao':r[4],'cartao_nome':r[5],'id_conta':r[6],'conta_nome':r[7],
                  'dia_mes':r[8],'ativa':r[9],'modo_dia':r[10]}
                 for r in c.fetchall()]
    return jsonify({'despesas_fixas': fixas})

@app.route('/api/adicionar_despesa_fixa', methods=['POST'])
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
    gerar_ocorrencias_despesas_fixas()
    return jsonify({'success': True, 'id': novo_id})

@app.route('/api/remover_despesa_fixa', methods=['POST'])
def api_remover_despesa_fixa():
    data = request.get_json()
    df_id = data.get('id')
    if not df_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM despesas_fixas WHERE id=?", (df_id,))
        conn.commit()
    return jsonify({'success': True})

@app.route('/api/pausar_despesa_fixa', methods=['POST'])
def api_pausar_despesa_fixa():
    data = request.get_json()
    df_id = data.get('id')
    ativa = data.get('ativa', 1)
    if not df_id: return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("UPDATE despesas_fixas SET ativa=? WHERE id=?", (ativa, df_id))
        conn.commit()
    return jsonify({'success': True})


# ================================================================
# API — FATURA DETALHADA
# ================================================================

@app.route('/api/fatura/<int:cartao_id>')
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

if __name__ == '__main__':
    init_db()
    gerar_ocorrencias_receitas_fixas()
    gerar_ocorrencias_despesas_fixas()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
