from flask import Flask, render_template, request, redirect
import sqlite3

app = Flask(__name__)

# Banco de dados inicial
def init_db():
    conn = sqlite3.connect('financas.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transacoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT,
                    descricao TEXT,
                    valor REAL
                )''')
    conn.commit()
    conn.close()

# --------------------------
# Rotas
# --------------------------

@app.route('/')
def index():
    conn = sqlite3.connect('financas.db')
    c = conn.cursor()
    c.execute("SELECT * FROM transacoes")
    transacoes = c.fetchall()
    c.execute("SELECT SUM(CASE WHEN tipo='receita' THEN valor ELSE -valor END) FROM transacoes")
    saldo = c.fetchone()[0] or 0
    conn.close()
    return render_template('index.html', transacoes=transacoes, saldo=saldo)

@app.route('/lancamentos')
def lancamentos():
    conn = sqlite3.connect('financas.db')
    c = conn.cursor()
    c.execute("SELECT id, descricao, tipo, valor FROM transacoes")
    lancamentos = c.fetchall()
    conn.close()
    return render_template('lancamentos.html', lancamentos=lancamentos)

@app.route('/api/adicionar_lancamento', methods=['POST'])
def api_adicionar_lancamento():
    data = request.get_json()
    descricao = data.get("descricao")
    tipo = data.get("tipo")
    valor = float(data.get("valor"))

    conn = sqlite3.connect("financas.db")
    c = conn.cursor()
    c.execute("INSERT INTO transacoes (tipo, descricao, valor) VALUES (?, ?, ?)",
              (tipo, descricao, valor))
    conn.commit()
    lancamento_id = c.lastrowid
    conn.close()

    return {"success": True, "id": lancamento_id}

@app.route("/api/remover_lancamento", methods=["POST"])
def remover_lancamento():
    data = request.get_json()
    lancamento_id = data.get("id")
    if not lancamento_id:
        return {"success": False, "error": "ID não fornecido"}

    conn = sqlite3.connect("financas.db")
    c = conn.cursor()
    c.execute("DELETE FROM transacoes WHERE id = ?", (lancamento_id,))
    conn.commit()
    conn.close()
    return {"success": True}

@app.route('/projecoes')
def projecoes():
    return render_template('projecoes.html')

@app.route('/visaoGeral')
def visaoGeral():
    return render_template('visaoGeral.html')

@app.route('/adicionar', methods=['GET', 'POST'])
def adicionar():
    if request.method == 'POST':
        tipo = request.form['tipo']
        descricao = request.form['descricao']
        valor = float(request.form['valor'])

        conn = sqlite3.connect('financas.db')
        c = conn.cursor()
        c.execute("INSERT INTO transacoes (tipo, descricao, valor) VALUES (?, ?, ?)", (tipo, descricao, valor))
        conn.commit()
        conn.close()
        return redirect('/')
    return render_template('adicionar.html')

@app.route('/lancamentosReceita')
def lancamentosReceita():
    conn = sqlite3.connect('financas.db')
    c = conn.cursor()
    c.execute("SELECT id, descricao, tipo, valor FROM transacoes")
    receitas = c.fetchall()
    conn.close()
    return render_template('lancamentosReceita.html', receitas=receitas)

# --------------------------
# Main
# --------------------------
if __name__ == '__main__':
    init_db()  # Cria o banco caso não exista
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)