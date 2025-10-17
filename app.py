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
                        categoria TEXT
                    )''')

        # Tabela de categorias
        c.execute('''CREATE TABLE IF NOT EXISTS categorias (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT UNIQUE NOT NULL
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
            SELECT id, descricao, tipo, valor, categoria 
            FROM transacoes
            WHERE tipo='despesa'
        """)
        lancamentos = c.fetchall()
    return render_template('lancamentos.html', lancamentos=lancamentos)


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
# API - Lançamentos (Adicionar / Remover)
# --------------------------
@app.route('/api/adicionar_lancamento', methods=['POST'])
def api_adicionar_lancamento():
    data = request.get_json()
    descricao = data.get("descricao")
    tipo = data.get("tipo")  # "despesa" ou "receita"
    valor = float(data.get("valor"))
    categoria = data.get("categoria")

    if not descricao or not tipo or valor is None:
        return {"success": False, "error": "Campos obrigatórios ausentes"}

    with sqlite3.connect("financas.db", check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO transacoes (tipo, descricao, valor, categoria)
            VALUES (?, ?, ?, ?)
        """, (tipo, descricao, valor, categoria))
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
