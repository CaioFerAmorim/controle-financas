from flask import Flask, render_template, request, redirect
import sqlite3
import os

app = Flask(__name__)

# --------------------------
# Inicialização do banco
# --------------------------
def init_db():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()

        # Tabela de transações (despesas e receitas)
        c.execute('''CREATE TABLE IF NOT EXISTS transacoes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tipo TEXT CHECK(tipo IN ('despesa','receita')),
                        descricao TEXT,
                        valor REAL,
                        categoria TEXT,
                        id_cartao INTEGER,
                        FOREIGN KEY (id_cartao) REFERENCES cartoes(id)
                    )''')

        # Tabela de categorias
        c.execute('''CREATE TABLE IF NOT EXISTS categorias (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT UNIQUE NOT NULL
                    )''')

        # Tabela de contas
        c.execute('''CREATE TABLE IF NOT EXISTS contas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT UNIQUE NOT NULL,
                        saldo REAL DEFAULT 0
                    )''')

        # Tabela de cartões
        c.execute('''CREATE TABLE IF NOT EXISTS cartoes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT NOT NULL UNIQUE,
                        conta INTEGER NOT NULL,
                        tipo_pagamento TEXT CHECK(tipo_pagamento IN ('débito', 'crédito', 'múltiplo')),
                        data_vencimento INTEGER,
                        dias_fechamento INTEGER,
                        limite REAL DEFAULT 0,
                        FOREIGN KEY (conta) REFERENCES contas(id)
                    )''')

        conn.commit()


# --------------------------
# Rotas principais
# --------------------------
@app.route('/')
def index():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM transacoes")
        transacoes = c.fetchall()

        # Calcula saldo total (receitas - despesas)
        c.execute("""
            SELECT SUM(CASE WHEN tipo='receita' THEN valor ELSE -valor END)
            FROM transacoes
        """)
        saldo = c.fetchone()[0] or 0

    return render_template('index.html', transacoes=transacoes, saldo=saldo)


# --------------------------
# Lançamentos - DESPESAS
# --------------------------
@app.route('/lancamentos')
def lancamentos():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, descricao, tipo, valor, categoria, id_cartao
            FROM transacoes
            WHERE tipo='despesa'
        """)
        lancamentos = c.fetchall()

        # Carrega cartões para o select
        c.execute("SELECT id, nome FROM cartoes ORDER BY nome")
        cartoes = c.fetchall()

    return render_template('lancamentos.html', lancamentos=lancamentos, cartoes=cartoes)


# --------------------------
# Lançamentos - RECEITAS
# --------------------------
@app.route('/lancamentosReceita')
def lancamentosReceita():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, descricao, tipo, valor, categoria 
            FROM transacoes
            WHERE tipo='receita'
        """)
        receitas = c.fetchall()
    return render_template('lancamentosReceita.html', receitas=receitas)


# --------------------------
# Lançamentos - CONTAS
# --------------------------
@app.route('/lancamentosConta')
def lancamentosConta():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nome, saldo FROM contas ORDER BY nome")
        contas = c.fetchall()
    return render_template('lancamentosConta.html', contas=contas)


# --------------------------
# Lançamentos - CARTÕES
# --------------------------
@app.route('/lancamentosCartao')
def lancamentosCartao():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        # Seleciona todos os cartões com o nome da conta
        c.execute("""
            SELECT c.id, c.nome, ct.nome as conta_nome, c.data_vencimento, c.dias_fechamento, c.limite, c.tipo_pagamento
            FROM cartoes c
            LEFT JOIN contas ct ON c.conta = ct.id
        """)
        cartoes = c.fetchall()

        # Carrega contas para o select
        c.execute("SELECT id, nome FROM contas ORDER BY nome")
        contas = c.fetchall()

    return render_template('lancamentosCartao.html', cartoes=cartoes, contas=contas)


# --------------------------
# API - CARTÕES
# --------------------------
@app.route('/api/adicionar_cartao', methods=['POST'])
def adicionar_cartao():
    data = request.get_json()
    nome = data.get("nome", "").strip()
    conta = data.get("conta")  # id da conta
    tipo_pagamento = data.get("tipo_pagamento")
    data_vencimento = data.get("data_vencimento")
    dias_fechamento = data.get("dias_fechamento")
    limite = float(data.get("limite") or 0)

    if not nome or not tipo_pagamento or not conta:
        return {"success": False, "error": "Nome, tipo e conta são obrigatórios"}

    with sqlite3.connect("financas.db", check_same_thread=False) as conn:
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO cartoes (nome, conta, tipo_pagamento, data_vencimento, dias_fechamento, limite)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nome, conta, tipo_pagamento, data_vencimento, dias_fechamento, limite))
            conn.commit()
            cartao_id = c.lastrowid
            return {"success": True, "id": cartao_id, "nome": nome}
        except sqlite3.IntegrityError:
            return {"success": False, "error": "Esse cartão já existe"}


@app.route("/api/remover_cartao", methods=["POST"])
def remover_cartao():
    data = request.get_json()
    cartao_id = data.get("id")
    if not cartao_id:
        return {"success": False, "error": "ID não fornecido"}

    with sqlite3.connect("financas.db", check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM cartoes WHERE id = ?", (cartao_id,))
        conn.commit()
    return {"success": True}


# --------------------------
# API - Lançamentos (Adicionar / Remover)
# --------------------------
@app.route('/api/adicionar_lancamento', methods=['POST'])
def api_adicionar_lancamento():
    data = request.get_json()
    descricao = data.get("descricao")
    tipo = data.get("tipo")  # "despesa" ou "receita"
    valor = float(data.get("valor"))
    categoria = data.get("categoria")
    id_cartao = data.get("id_cartao")

    if not descricao or not tipo or valor is None:
        return {"success": False, "error": "Campos obrigatórios ausentes"}

    with sqlite3.connect("financas.db", check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO transacoes (tipo, descricao, valor, categoria, id_cartao)
            VALUES (?, ?, ?, ?, ?)
        """, (tipo, descricao, valor, categoria, id_cartao))
        conn.commit()
        lancamento_id = c.lastrowid

    return {"success": True, "id": lancamento_id}


@app.route("/api/remover_lancamento", methods=["POST"])
def remover_lancamento():
    data = request.get_json()
    lancamento_id = data.get("id")
    if not lancamento_id:
        return {"success": False, "error": "ID não fornecido"}

    with sqlite3.connect("financas.db", check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM transacoes WHERE id = ?", (lancamento_id,))
        conn.commit()
    return {"success": True}


# --------------------------
# Categorias
# --------------------------
@app.route('/lancamentosCategorias')
def lancamentosCategorias():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nome FROM categorias ORDER BY nome")
        categorias = c.fetchall()
    return render_template('lancamentosCategorias.html', categorias=categorias)


@app.route('/api/categorias')
def listar_categorias():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nome FROM categorias ORDER BY nome")
        categorias = c.fetchall()
    return {"categorias": [{"id": id, "nome": nome} for id, nome in categorias]}


@app.route("/api/adicionar_categoria", methods=["POST"])
def adicionar_categoria():
    data = request.get_json()
    nome = data.get("nome", "").strip()
    if not nome:
        return {"success": False, "error": "Nome da categoria obrigatório"}

    with sqlite3.connect("financas.db", check_same_thread=False) as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO categorias (nome) VALUES (?)", (nome,))
            conn.commit()
            categoria_id = c.lastrowid
            return {"success": True, "id": categoria_id, "nome": nome}
        except sqlite3.IntegrityError:
            return {"success": False, "error": "Categoria já existente"}


@app.route("/api/remover_categoria", methods=["POST"])
def remover_categoria():
    data = request.get_json()
    categoria_id = data.get("id")
    if not categoria_id:
        return {"success": False, "error": "ID não fornecido"}

    with sqlite3.connect("financas.db", check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))
        conn.commit()
    return {"success": True}


# --------------------------
# Outras páginas
# --------------------------
@app.route('/projecoes')
def projecoes():
    return render_template('projecoes.html')


@app.route('/visaoGeral')
def visaoGeral():
    return render_template('visaoGeral.html')


# --------------------------
# Inicialização
# --------------------------
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
