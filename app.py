from flask import Flask, render_template, request, jsonify
import sqlite3
import os
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta  # pip install python-dateutil

app = Flask(__name__)
DB = 'financas.db'

# ==============================================================
# BANCO DE DADOS
# ==============================================================

def get_db():
    """Retorna uma conexão com row_factory para acesso por nome."""
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS transacoes (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo             TEXT    NOT NULL CHECK(tipo IN ('despesa','receita')),
            descricao        TEXT    NOT NULL,
            valor            REAL    NOT NULL,
            categoria        TEXT,
            id_cartao        INTEGER REFERENCES cartoes(id),
            id_conta         INTEGER REFERENCES contas(id),
            tipo_receita     TEXT    CHECK(tipo_receita   IN ('avulsa','fixa'))    DEFAULT 'avulsa',
            tipo_cobranca    TEXT    CHECK(tipo_cobranca  IN ('avulsa','fixa'))    DEFAULT 'avulsa',
            dia_vencimento   INTEGER,
            tipo_compra      TEXT    CHECK(tipo_compra    IN ('credito','debito')) DEFAULT 'credito',
            pagamento        TEXT    CHECK(pagamento      IN ('avista','parcelado')) DEFAULT 'avista',
            parcelas         INTEGER DEFAULT NULL,
            data_lancamento  DATE    NOT NULL DEFAULT (DATE('now'))
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS categorias (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT    UNIQUE NOT NULL,
            tipo TEXT    CHECK(tipo IN ('despesa','receita')) DEFAULT 'despesa'
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS contas (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            nome  TEXT  UNIQUE NOT NULL,
            saldo REAL  DEFAULT 0
        )''')

        # dias_fechamento = quantos dias ANTES do vencimento a fatura fecha
        # data_vencimento = dia do mês em que a fatura vence
        c.execute('''CREATE TABLE IF NOT EXISTS cartoes (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            nome             TEXT  UNIQUE NOT NULL,
            conta            INTEGER NOT NULL REFERENCES contas(id),
            tipo_pagamento   TEXT  CHECK(tipo_pagamento IN ('credito','debito','multiplo')),
            data_vencimento  INTEGER,   -- dia do mês (1-31)
            dias_fechamento  INTEGER,   -- dias antes do vencimento que a fatura fecha
            limite           REAL  DEFAULT 0
        )''')

        # Categorias padrão
        categorias_padrao = [
            ('Alimentação','despesa'), ('Transporte','despesa'), ('Moradia','despesa'),
            ('Saúde','despesa'),       ('Educação','despesa'),   ('Lazer','despesa'),
            ('Salário','receita'),     ('Investimentos','receita'),
            ('Freelance','receita'),   ('Presente','receita'),
        ]
        for nome, tipo in categorias_padrao:
            c.execute("INSERT OR IGNORE INTO categorias (nome, tipo) VALUES (?,?)", (nome, tipo))

        conn.commit()


# ==============================================================
# HELPERS DE DATA  ← PONTO CENTRAL DE TODA LÓGICA DE FATURA
# ==============================================================

def periodo_fatura_atual(dia_vencimento: int, dias_fechamento: int, referencia: date = None):
    """
    Retorna (inicio, fim) do período que compõe a fatura ATUAL do cartão.

    Regra:
      - A fatura fecha `dias_fechamento` dias antes do vencimento.
      - Compras feitas NO DIA do fechamento ou depois entram na PRÓXIMA fatura.
      - Portanto o período da fatura atual é:
          início = fechamento da fatura anterior   (inclusive)
          fim    = fechamento da fatura atual - 1  (inclusive)

    Exemplo: vencimento dia 10, fecha 5 dias antes (dia 5)
      Fatura atual: 06/mar a 05/abr  →  vence 10/abr
    """
    if referencia is None:
        referencia = date.today()

    # Calcula a data de fechamento no mês atual e no próximo
    def fechamento_de(ano, mes):
        venc = date(ano, mes, dia_vencimento)
        return venc - timedelta(days=dias_fechamento)

    hoje = referencia

    # Vencimento "corrente" — mesmo mês de hoje
    try:
        venc_corrente = date(hoje.year, hoje.month, dia_vencimento)
    except ValueError:
        # dia_vencimento > dias no mês → usa último dia
        import calendar
        ultimo = calendar.monthrange(hoje.year, hoje.month)[1]
        venc_corrente = date(hoje.year, hoje.month, ultimo)

    fech_corrente = venc_corrente - timedelta(days=dias_fechamento)

    if hoje < fech_corrente:
        # Ainda não fechou → fatura atual vence neste mês
        venc_atual = venc_corrente
    else:
        # Já fechou → fatura atual vence no próximo mês
        venc_atual = venc_corrente + relativedelta(months=1)

    venc_anterior = venc_atual - relativedelta(months=1)

    fech_atual    = venc_atual    - timedelta(days=dias_fechamento)
    fech_anterior = venc_anterior - timedelta(days=dias_fechamento)

    inicio = fech_anterior      # inclusive
    fim    = fech_atual - timedelta(days=1)  # inclusive (dia do fechamento vai p/ próxima)

    return inicio, fim, venc_atual


def projecao_mensal(n_meses: int = 3):
    """
    Retorna lista com projeção dos próximos n_meses.
    Cada item: { mes_ano, receitas, despesas_fixas, despesas_parceladas, saldo }
    """
    hoje = date.today()
    resultado = []

    with get_db() as conn:
        c = conn.cursor()

        for delta in range(1, n_meses + 1):
            alvo = hoje + relativedelta(months=delta)
            ano_alvo, mes_alvo = alvo.year, alvo.month

            # ── Receitas fixas ──────────────────────────────────────
            c.execute("""
                SELECT COALESCE(SUM(valor), 0) FROM transacoes
                WHERE tipo = 'receita' AND tipo_receita = 'fixa'
            """)
            rec_fixas = c.fetchone()[0]

            # ── Despesas fixas ──────────────────────────────────────
            c.execute("""
                SELECT COALESCE(SUM(valor), 0) FROM transacoes
                WHERE tipo = 'despesa' AND tipo_cobranca = 'fixa'
            """)
            desp_fixas = c.fetchone()[0]

            # ── Despesas parceladas que caem neste mês ──────────────
            c.execute("""
                SELECT id, valor, parcelas, data_lancamento
                FROM transacoes
                WHERE tipo = 'despesa' AND pagamento = 'parcelado' AND parcelas >= 2
            """)
            desp_parc = 0
            for row in c.fetchall():
                tid, valor_total, parcelas, data_str = row
                try:
                    data_compra = date.fromisoformat(str(data_str)[:10])
                except Exception:
                    continue
                valor_parcela = valor_total / parcelas
                for p in range(parcelas):
                    mes_parcela = data_compra + relativedelta(months=p)
                    if mes_parcela.year == ano_alvo and mes_parcela.month == mes_alvo:
                        desp_parc += valor_parcela
                        break

            meses_pt = {1:'Jan',2:'Fev',3:'Mar',4:'Abr',5:'Mai',6:'Jun',
                        7:'Jul',8:'Ago',9:'Set',10:'Out',11:'Nov',12:'Dez'}
            resultado.append({
                'mes_ano':            f"{meses_pt[mes_alvo]}/{ano_alvo}",
                'receitas':           round(rec_fixas, 2),
                'despesas_fixas':     round(desp_fixas, 2),
                'despesas_parceladas':round(desp_parc, 2),
                'saldo':              round(rec_fixas - desp_fixas - desp_parc, 2),
            })

    return resultado


def total_fatura_atual():
    """Soma de TODAS as despesas de crédito que estão na fatura atual de cada cartão."""
    total = 0.0
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, data_vencimento, dias_fechamento
            FROM cartoes WHERE tipo_pagamento IN ('credito','multiplo')
            AND data_vencimento IS NOT NULL AND dias_fechamento IS NOT NULL
        """)
        for cartao_id, dia_venc, dias_fech in c.fetchall():
            inicio, fim, _ = periodo_fatura_atual(dia_venc, dias_fech)
            c.execute("""
                SELECT COALESCE(SUM(valor), 0) FROM transacoes
                WHERE tipo = 'despesa' AND tipo_compra = 'credito'
                AND id_cartao = ?
                AND data_lancamento BETWEEN ? AND ?
            """, (cartao_id, inicio.isoformat(), fim.isoformat()))
            total += c.fetchone()[0]
    return round(total, 2)


# ==============================================================
# ROTA PRINCIPAL  /
# ==============================================================

@app.route('/')
def index():
    with get_db() as conn:
        c = conn.cursor()

        # Últimas 10 transações
        c.execute("""
            SELECT t.id, t.descricao, t.tipo, t.valor, t.categoria,
                   co.nome  AS conta_nome,
                   ca.nome  AS cartao_nome,
                   t.data_lancamento
            FROM transacoes t
            LEFT JOIN contas  co ON t.id_conta  = co.id
            LEFT JOIN cartoes ca ON t.id_cartao = ca.id
            ORDER BY t.data_lancamento DESC, t.id DESC
            LIMIT 10
        """)
        transacoes = [dict(r) for r in c.fetchall()]

        # Saldo total
        c.execute("SELECT COALESCE(SUM(saldo), 0) FROM contas")
        saldo_total = round(c.fetchone()[0], 2)

        # Receitas do mês atual
        hoje = date.today()
        c.execute("""
            SELECT COALESCE(SUM(valor), 0) FROM transacoes
            WHERE tipo = 'receita'
            AND strftime('%Y-%m', data_lancamento) = ?
        """, (hoje.strftime('%Y-%m'),))
        receitas_mes = round(c.fetchone()[0], 2)

        # Top 5 categorias (mês atual)
        c.execute("""
            SELECT COALESCE(categoria,'Sem categoria') AS cat, SUM(valor) AS total
            FROM transacoes
            WHERE tipo = 'despesa'
            AND strftime('%Y-%m', data_lancamento) = ?
            GROUP BY cat ORDER BY total DESC LIMIT 5
        """, (hoje.strftime('%Y-%m'),))
        gastos_por_categoria = [{'nome': r[0], 'total': round(r[1], 2)} for r in c.fetchall()]

    gasto_credito  = total_fatura_atual()
    proximas_faturas = projecao_mensal(3)

    return render_template('index.html',
        transacoes=transacoes,
        saldo_total=saldo_total,
        receitas_mes=receitas_mes,
        gasto_credito=gasto_credito,
        disponivel_mes=round(saldo_total + receitas_mes - gasto_credito, 2),
        proximas_faturas=proximas_faturas,
        gastos_por_categoria=gastos_por_categoria,
    )


# ==============================================================
# API — DASHBOARD (atualização via JS)
# ==============================================================

@app.route('/api/dashboard_data')
def dashboard_data():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COALESCE(SUM(saldo), 0) FROM contas")
        saldo_total = round(c.fetchone()[0], 2)

        hoje = date.today()
        c.execute("""
            SELECT COALESCE(SUM(valor), 0) FROM transacoes
            WHERE tipo='receita' AND strftime('%Y-%m', data_lancamento) = ?
        """, (hoje.strftime('%Y-%m'),))
        receitas_mes = round(c.fetchone()[0], 2)

    gasto_credito = total_fatura_atual()
    return jsonify({
        'saldo_total':   saldo_total,
        'receitas_mes':  receitas_mes,
        'gasto_credito': gasto_credito,
        'disponivel_mes': round(saldo_total + receitas_mes - gasto_credito, 2),
    })


# ==============================================================
# LANÇAMENTOS — DESPESAS
# ==============================================================

@app.route('/lancamentos')
def lancamentos():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT t.id, t.descricao, t.tipo, t.valor, t.categoria,
                   ca.nome AS cartao_nome, t.data_lancamento,
                   t.pagamento, t.parcelas, t.tipo_compra, t.tipo_cobranca
            FROM transacoes t
            LEFT JOIN cartoes ca ON t.id_cartao = ca.id
            WHERE t.tipo = 'despesa'
            ORDER BY t.data_lancamento DESC, t.id DESC
        """)
        lancamentos_db = [list(r) for r in c.fetchall()]
    return render_template('lancamentos.html', lancamentos=lancamentos_db)


# ==============================================================
# LANÇAMENTOS — RECEITAS
# ==============================================================

@app.route('/lancamentosReceita')
def lancamentosReceita():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT t.id, t.descricao, t.tipo, t.valor, t.categoria,
                   COALESCE(co.nome,'N/A') AS conta_nome,
                   COALESCE(t.tipo_receita,'avulsa'),
                   t.dia_vencimento
            FROM transacoes t
            LEFT JOIN contas co ON t.id_conta = co.id
            WHERE t.tipo = 'receita'
            ORDER BY t.data_lancamento DESC, t.id DESC
        """)
        receitas = [list(r) for r in c.fetchall()]
    return render_template('lancamentosReceita.html', receitas=receitas)


# ==============================================================
# LANÇAMENTOS — CONTAS
# ==============================================================

@app.route('/lancamentosConta')
def lancamentosConta():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, nome, saldo FROM contas ORDER BY nome")
        contas = [list(r) for r in c.fetchall()]
    return render_template('lancamentosConta.html', contas=contas)


# ==============================================================
# LANÇAMENTOS — CARTÕES
# ==============================================================

@app.route('/lancamentosCartao')
def lancamentosCartao():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT ca.id, ca.nome, co.nome AS conta_nome,
                   ca.dias_fechamento, ca.data_vencimento, ca.tipo_pagamento, ca.limite
            FROM cartoes ca
            LEFT JOIN contas co ON ca.conta = co.id
            ORDER BY ca.nome
        """)
        cartoes = [list(r) for r in c.fetchall()]
        c.execute("SELECT id, nome FROM contas ORDER BY nome")
        contas = [list(r) for r in c.fetchall()]
    return render_template('lancamentosCartao.html', cartoes=cartoes, contas=contas)


# ==============================================================
# LANÇAMENTOS — CATEGORIAS
# ==============================================================

@app.route('/lancamentosCategorias')
def lancamentosCategorias():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, nome, tipo FROM categorias ORDER BY tipo, nome")
        categorias = [list(r) for r in c.fetchall()]
    return render_template('lancamentosCategorias.html', categorias=categorias)


# ==============================================================
# PROJEÇÕES
# ==============================================================

@app.route('/projecoes')
def projecoes():
    faturas = projecao_mensal(6)  # 6 meses à frente
    return render_template('projecoes.html', projecoes=faturas)


# ==============================================================
# VISÃO GERAL
# ==============================================================

@app.route('/visaoGeral')
def visaoGeral():
    with get_db() as conn:
        c = conn.cursor()

        hoje = date.today()
        mes_atual = hoje.strftime('%Y-%m')

        # Receitas e despesas dos últimos 6 meses
        historico = []
        for delta in range(5, -1, -1):
            ref = hoje - relativedelta(months=delta)
            mes_str = ref.strftime('%Y-%m')
            meses_pt = {1:'Jan',2:'Fev',3:'Mar',4:'Abr',5:'Mai',6:'Jun',
                        7:'Jul',8:'Ago',9:'Set',10:'Out',11:'Nov',12:'Dez'}
            label = f"{meses_pt[ref.month]}/{ref.year}"

            c.execute("""
                SELECT COALESCE(SUM(valor),0) FROM transacoes
                WHERE tipo='receita' AND strftime('%Y-%m', data_lancamento)=?
            """, (mes_str,))
            rec = round(c.fetchone()[0], 2)

            c.execute("""
                SELECT COALESCE(SUM(valor),0) FROM transacoes
                WHERE tipo='despesa' AND strftime('%Y-%m', data_lancamento)=?
            """, (mes_str,))
            desp = round(c.fetchone()[0], 2)

            historico.append({'label': label, 'receitas': rec, 'despesas': desp, 'saldo': round(rec-desp,2)})

        # Gastos por categoria (mês atual)
        c.execute("""
            SELECT COALESCE(categoria,'Sem categoria'), COALESCE(SUM(valor),0)
            FROM transacoes
            WHERE tipo='despesa' AND strftime('%Y-%m', data_lancamento)=?
            GROUP BY categoria ORDER BY 2 DESC
        """, (mes_atual,))
        por_categoria = [{'nome': r[0], 'total': round(r[1],2)} for r in c.fetchall()]

        # Saldo por conta
        c.execute("SELECT nome, saldo FROM contas ORDER BY nome")
        por_conta = [{'nome': r[0], 'saldo': round(r[1],2)} for r in c.fetchall()]

        # Fatura atual por cartão
        c.execute("""
            SELECT ca.id, ca.nome, ca.data_vencimento, ca.dias_fechamento, ca.limite
            FROM cartoes ca
            WHERE ca.tipo_pagamento IN ('credito','multiplo')
            AND ca.data_vencimento IS NOT NULL AND ca.dias_fechamento IS NOT NULL
        """)
        faturas_cartoes = []
        for cartao_id, nome_cartao, dia_venc, dias_fech, limite in c.fetchall():
            inicio, fim, vencimento = periodo_fatura_atual(dia_venc, dias_fech)
            c.execute("""
                SELECT COALESCE(SUM(valor),0) FROM transacoes
                WHERE tipo='despesa' AND tipo_compra='credito'
                AND id_cartao=? AND data_lancamento BETWEEN ? AND ?
            """, (cartao_id, inicio.isoformat(), fim.isoformat()))
            gasto = round(c.fetchone()[0], 2)
            faturas_cartoes.append({
                'nome': nome_cartao,
                'gasto': gasto,
                'limite': limite,
                'vencimento': vencimento.strftime('%d/%m/%Y'),
                'inicio': inicio.strftime('%d/%m/%Y'),
                'fim': fim.strftime('%d/%m/%Y'),
            })

    return render_template('visaoGeral.html',
        historico=historico,
        por_categoria=por_categoria,
        por_conta=por_conta,
        faturas_cartoes=faturas_cartoes,
    )


# ==============================================================
# APIs — CONTAS
# ==============================================================

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
    if not nome:
        return jsonify({'success': False, 'error': 'Nome obrigatório'})
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
    if not conta_id:
        return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM cartoes WHERE conta = ?", (conta_id,))
        if c.fetchone()[0] > 0:
            return jsonify({'success': False, 'error': 'Conta possui cartões vinculados'})
        c.execute("DELETE FROM contas WHERE id = ?", (conta_id,))
        conn.commit()
    return jsonify({'success': True})


# ==============================================================
# APIs — CARTÕES
# ==============================================================

@app.route('/api/cartoes_disponiveis')
def api_cartoes_disponiveis():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT ca.id, ca.nome, ca.tipo_pagamento, co.nome AS conta_nome
            FROM cartoes ca LEFT JOIN contas co ON ca.conta = co.id
            ORDER BY ca.nome
        """)
        cartoes = [{'id': r[0], 'nome': r[1], 'tipo_pagamento': r[2], 'conta_nome': r[3]}
                   for r in c.fetchall()]
    return jsonify({'cartoes': cartoes})

@app.route('/api/adicionar_cartao', methods=['POST'])
def adicionar_cartao():
    data = request.get_json()
    nome           = (data.get('nome') or '').strip()
    conta          = data.get('conta')
    tipo_pagamento = data.get('tipo_pagamento')
    data_vencimento = data.get('data_vencimento')   # dia do mês
    dias_fechamento = data.get('dias_fechamento')    # dias antes do vencimento
    limite         = float(data.get('limite') or 0)

    if not nome or not conta or not tipo_pagamento:
        return jsonify({'success': False, 'error': 'Nome, conta e tipo são obrigatórios'})

    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO cartoes (nome, conta, tipo_pagamento, data_vencimento, dias_fechamento, limite)
                VALUES (?,?,?,?,?,?)
            """, (nome, conta, tipo_pagamento, data_vencimento, dias_fechamento, limite))
            conn.commit()
            return jsonify({'success': True, 'id': c.lastrowid, 'nome': nome})
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'error': 'Cartão já existe'})

@app.route('/api/remover_cartao', methods=['POST'])
def remover_cartao():
    data = request.get_json()
    cartao_id = data.get('id')
    if not cartao_id:
        return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM cartoes WHERE id = ?", (cartao_id,))
        conn.commit()
    return jsonify({'success': True})


# ==============================================================
# APIs — CATEGORIAS
# ==============================================================

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
    if not nome:
        return jsonify({'success': False, 'error': 'Nome obrigatório'})
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
    if not cat_id:
        return jsonify({'success': False, 'error': 'ID não informado'})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM categorias WHERE id = ?", (cat_id,))
        conn.commit()
    return jsonify({'success': True})


# ==============================================================
# APIs — LANÇAMENTOS (adicionar / remover)
# ==============================================================

@app.route('/api/adicionar_lancamento', methods=['POST'])
def adicionar_lancamento():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Nenhum dado recebido'})

    descricao      = (data.get('descricao') or '').strip()
    tipo           = data.get('tipo')
    valor_str      = data.get('valor')
    categoria      = data.get('categoria')
    id_cartao_str  = data.get('id_cartao')
    id_conta_str   = data.get('id_conta')
    tipo_receita   = data.get('tipo_receita',  'avulsa')
    tipo_cobranca  = data.get('tipo_cobranca', 'avulsa')
    dia_venc_str   = data.get('dia_vencimento')
    tipo_compra    = data.get('tipo_compra', 'credito')
    pagamento      = data.get('pagamento',   'avista')
    parcelas_str   = data.get('parcelas')
    data_str       = data.get('data')  # YYYY-MM-DD vindo do input[type=date]

    # Validações básicas
    if not descricao:
        return jsonify({'success': False, 'error': 'Descrição obrigatória'})
    if tipo not in ('despesa', 'receita'):
        return jsonify({'success': False, 'error': 'Tipo inválido'})

    try:
        valor = float(valor_str)
        if valor <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Valor inválido'})

    # Conversões seguras
    def to_int(v):
        try: return int(v) if v else None
        except: return None

    id_cartao = to_int(id_cartao_str)
    id_conta  = to_int(id_conta_str)
    dia_venc  = to_int(dia_venc_str)
    parcelas  = to_int(parcelas_str)

    # Data do lançamento — usa a data do formulário ou hoje
    if data_str:
        try:
            data_lancamento = date.fromisoformat(data_str)
        except ValueError:
            data_lancamento = date.today()
    else:
        data_lancamento = date.today()

    # Regras de negócio
    if tipo == 'despesa' and not id_cartao:
        return jsonify({'success': False, 'error': 'Selecione um cartão para a despesa'})
    if tipo == 'receita' and not id_conta:
        return jsonify({'success': False, 'error': 'Selecione uma conta para a receita'})
    if tipo_receita == 'fixa' and not dia_venc:
        return jsonify({'success': False, 'error': 'Informe o dia do mês para receita fixa'})
    if pagamento == 'parcelado' and (not parcelas or parcelas < 2):
        return jsonify({'success': False, 'error': 'Parcelado exige mínimo 2 parcelas'})

    with get_db() as conn:
        c = conn.cursor()

        # Valida cartão
        if tipo == 'despesa' and id_cartao:
            c.execute("SELECT tipo_pagamento FROM cartoes WHERE id=?", (id_cartao,))
            row = c.fetchone()
            if not row:
                return jsonify({'success': False, 'error': 'Cartão não encontrado'})
            tipo_cartao = row[0]
            if tipo_cartao != 'multiplo' and tipo_compra != tipo_cartao:
                return jsonify({'success': False, 'error': f'Cartão só aceita {tipo_cartao}'})
            if tipo_cartao == 'debito' and pagamento == 'parcelado':
                return jsonify({'success': False, 'error': 'Débito não permite parcelamento'})

        c.execute("""
            INSERT INTO transacoes
                (tipo, descricao, valor, categoria, id_cartao, id_conta,
                 tipo_receita, tipo_cobranca, dia_vencimento, tipo_compra,
                 pagamento, parcelas, data_lancamento)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (tipo, descricao, valor, categoria, id_cartao, id_conta,
              tipo_receita, tipo_cobranca, dia_venc, tipo_compra,
              pagamento, parcelas, data_lancamento.isoformat()))

        # Atualiza saldo
        if tipo == 'receita' and id_conta:
            c.execute("UPDATE contas SET saldo = saldo + ? WHERE id = ?", (valor, id_conta))
        elif tipo == 'despesa' and tipo_compra == 'debito' and id_cartao:
            c.execute("""
                UPDATE contas SET saldo = saldo - ?
                WHERE id = (SELECT conta FROM cartoes WHERE id = ?)
            """, (valor, id_cartao))

        conn.commit()
        return jsonify({'success': True, 'id': c.lastrowid})


@app.route('/api/remover_lancamento', methods=['POST'])
def remover_lancamento():
    data = request.get_json()
    lid = data.get('id')
    if not lid:
        return jsonify({'success': False, 'error': 'ID não informado'})

    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT tipo, valor, id_conta, id_cartao, tipo_compra FROM transacoes WHERE id=?", (lid,))
        row = c.fetchone()
        if row:
            tipo, valor, id_conta, id_cartao, tipo_compra = row
            if tipo == 'receita' and id_conta:
                c.execute("UPDATE contas SET saldo = saldo - ? WHERE id = ?", (valor, id_conta))
            elif tipo == 'despesa' and tipo_compra == 'debito' and id_cartao:
                c.execute("""
                    UPDATE contas SET saldo = saldo + ?
                    WHERE id = (SELECT conta FROM cartoes WHERE id = ?)
                """, (valor, id_cartao))
        c.execute("DELETE FROM transacoes WHERE id = ?", (lid,))
        conn.commit()
    return jsonify({'success': True})


# ==============================================================
# API — FATURA DETALHADA DE UM CARTÃO (útil para debug / futuro)
# ==============================================================

@app.route('/api/fatura/<int:cartao_id>')
def fatura_cartao(cartao_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT data_vencimento, dias_fechamento FROM cartoes WHERE id=?", (cartao_id,))
        row = c.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Cartão não encontrado'})
        inicio, fim, venc = periodo_fatura_atual(row[0], row[1])
        c.execute("""
            SELECT id, descricao, valor, data_lancamento, categoria
            FROM transacoes
            WHERE tipo='despesa' AND id_cartao=?
            AND data_lancamento BETWEEN ? AND ?
            ORDER BY data_lancamento
        """, (cartao_id, inicio.isoformat(), fim.isoformat()))
        itens = [{'id': r[0], 'descricao': r[1], 'valor': r[2],
                  'data': r[3], 'categoria': r[4]} for r in c.fetchall()]
    return jsonify({
        'periodo_inicio': inicio.strftime('%d/%m/%Y'),
        'periodo_fim':    fim.strftime('%d/%m/%Y'),
        'vencimento':     venc.strftime('%d/%m/%Y'),
        'itens':          itens,
        'total':          round(sum(i['valor'] for i in itens), 2),
    })


# ==============================================================
# INICIALIZAÇÃO
# ==============================================================

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
