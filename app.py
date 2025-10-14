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

if __name__ == '__main__':
    init_db()
    app.run(debug=True)