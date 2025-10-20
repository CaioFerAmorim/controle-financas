from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)

# --------------------------
# Inicialização do banco
# --------------------------
def init_db():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()

        # Tabela de transações (despesas e receitas) - COM TODAS AS CORREÇÕES
        c.execute('''CREATE TABLE IF NOT EXISTS transacoes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tipo TEXT CHECK(tipo IN ('despesa','receita')),
                        descricao TEXT,
                        valor REAL,
                        categoria TEXT,
                        id_cartao INTEGER,
                        id_conta INTEGER,
                        tipo_receita TEXT CHECK(tipo_receita IN ('avulsa', 'fixa')) DEFAULT 'avulsa',
                        tipo_cobranca TEXT CHECK(tipo_cobranca IN ('avulsa', 'fixa')) DEFAULT 'avulsa',
                        dia_vencimento INTEGER,
                        tipo_compra TEXT CHECK(tipo_compra IN ('credito', 'debito')) DEFAULT 'credito',
                        pagamento TEXT CHECK(pagamento IN ('avista', 'parcelado')) DEFAULT 'avista',
                        parcelas INTEGER DEFAULT NULL,
                        data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (id_cartao) REFERENCES cartoes(id),
                        FOREIGN KEY (id_conta) REFERENCES contas(id)
                    )''')

        # Tabela de categorias - COM TIPO
        c.execute('''CREATE TABLE IF NOT EXISTS categorias (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT UNIQUE NOT NULL,
                        tipo TEXT CHECK(tipo IN ('despesa', 'receita')) DEFAULT 'despesa'
                    )''')

        # Tabela de contas
        c.execute('''CREATE TABLE IF NOT EXISTS contas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT UNIQUE NOT NULL,
                        saldo REAL DEFAULT 0
                    )''')

        # Tabela de cartões - CORREÇÃO APLICADA: valores sem acento
        c.execute('''CREATE TABLE IF NOT EXISTS cartoes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT NOT NULL UNIQUE,
                        conta INTEGER NOT NULL,
                        tipo_pagamento TEXT CHECK(tipo_pagamento IN ('credito', 'debito', 'multiplo')),
                        data_vencimento INTEGER,
                        dias_fechamento INTEGER,
                        limite REAL DEFAULT 0,
                        FOREIGN KEY (conta) REFERENCES contas(id)
                    )''')

        # Inserir algumas categorias padrão
        categorias_padrao = [
            ('Alimentação', 'despesa'),
            ('Transporte', 'despesa'),
            ('Moradia', 'despesa'),
            ('Saúde', 'despesa'),
            ('Educação', 'despesa'),
            ('Lazer', 'despesa'),
            ('Salário', 'receita'),
            ('Investimentos', 'receita'),
            ('Freelance', 'receita'),
            ('Presente', 'receita')
        ]
        
        for nome, tipo in categorias_padrao:
            try:
                c.execute("INSERT OR IGNORE INTO categorias (nome, tipo) VALUES (?, ?)", (nome, tipo))
            except:
                pass

        conn.commit()


# --------------------------
# Rotas principais
# --------------------------
@app.route('/')
def index():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        
        # Últimas transações
        c.execute("""
            SELECT t.id, t.descricao, t.tipo, t.valor, t.categoria, 
                   c.nome as conta_nome, ct.nome as cartao_nome, DATE(t.data_criacao) as data
            FROM transacoes t
            LEFT JOIN contas c ON t.id_conta = c.id
            LEFT JOIN cartoes ct ON t.id_cartao = ct.id
            ORDER BY t.data_criacao DESC
            LIMIT 10
        """)
        transacoes = c.fetchall()

        # Saldo total nas contas
        c.execute("SELECT SUM(saldo) FROM contas")
        saldo_total = c.fetchone()[0] or 0

        # Total gasto no crédito (este mês)
        c.execute("""
            SELECT SUM(valor) FROM transacoes 
            WHERE tipo = 'despesa' 
            AND tipo_compra = 'credito'
            AND strftime('%Y-%m', data_criacao) = strftime('%Y-%m', 'now')
        """)
        gasto_credito = c.fetchone()[0] or 0

        # Total de receitas do mês
        c.execute("""
            SELECT SUM(valor) FROM transacoes 
            WHERE tipo = 'receita'
            AND strftime('%Y-%m', data_criacao) = strftime('%Y-%m', 'now')
        """)
        receitas_mes = c.fetchone()[0] or 0

        # Total disponível no mês (receitas + saldo - gastos crédito)
        disponivel_mes = receitas_mes + saldo_total - gasto_credito

        # Próximos vencimentos (próximos 7 dias)
        c.execute("""
            SELECT descricao, valor, data_criacao 
            FROM transacoes 
            WHERE tipo = 'despesa'
            AND tipo_cobranca = 'fixa'
            AND DATE(data_criacao) BETWEEN DATE('now') AND DATE('now', '+7 days')
            ORDER BY data_criacao ASC
            LIMIT 5
        """)
        vencimentos_raw = c.fetchall()
        proximos_vencimentos = []
        for row in vencimentos_raw:
            if row[2]:  # Verifica se a data não é None
                try:
                    data_formatada = datetime.strptime(row[2], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y')
                except:
                    data_formatada = row[2]
            else:
                data_formatada = '-'
            proximos_vencimentos.append({'descricao': row[0], 'valor': row[1], 'data': data_formatada})

        # Gastos por categoria (este mês)
        c.execute("""
            SELECT categoria, SUM(valor) as total 
            FROM transacoes 
            WHERE tipo = 'despesa'
            AND strftime('%Y-%m', data_criacao) = strftime('%Y-%m', 'now')
            GROUP BY categoria 
            ORDER BY total DESC 
            LIMIT 5
        """)
        gastos_cat_raw = c.fetchall()
        gastos_por_categoria = []
        for row in gastos_cat_raw:
            gastos_por_categoria.append({'nome': row[0] or 'Sem categoria', 'total': row[1] or 0})

        # Metas (exemplo - você pode personalizar)
        meta_economia_atual = min(650, 1000)
        meta_economia_percentual = int((meta_economia_atual / 1000) * 100) if 1000 > 0 else 0
        
        meta_gastos_atual = min(1500, 2000)
        meta_gastos_percentual = int((meta_gastos_atual / 2000) * 100) if 2000 > 0 else 0
        
        meta_economia = {'meta': 1000, 'atual': meta_economia_atual, 'percentual': meta_economia_percentual}
        meta_gastos = {'meta': 2000, 'atual': meta_gastos_atual, 'percentual': meta_gastos_percentual}

    return render_template('index.html', 
                         transacoes=transacoes,
                         saldo_total=saldo_total,
                         gasto_credito=gasto_credito,
                         receitas_mes=receitas_mes,
                         disponivel_mes=disponivel_mes,
                         proximos_vencimentos=proximos_vencimentos,
                         gastos_por_categoria=gastos_por_categoria,
                         meta_economia=meta_economia,
                         meta_gastos=meta_gastos)


# --------------------------
# API para dados do dashboard (atualização em tempo real)
# --------------------------
@app.route('/api/dashboard_data')
def dashboard_data():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        
        # Saldo total nas contas
        c.execute("SELECT SUM(saldo) FROM contas")
        saldo_total = c.fetchone()[0] or 0

        # Total gasto no crédito (este mês)
        c.execute("""
            SELECT SUM(valor) FROM transacoes 
            WHERE tipo = 'despesa' 
            AND tipo_compra = 'credito'
            AND strftime('%Y-%m', data_criacao) = strftime('%Y-%m', 'now')
        """)
        gasto_credito = c.fetchone()[0] or 0

        # Total de receitas do mês
        c.execute("""
            SELECT SUM(valor) FROM transacoes 
            WHERE tipo = 'receita'
            AND strftime('%Y-%m', data_criacao) = strftime('%Y-%m', 'now')
        """)
        receitas_mes = c.fetchone()[0] or 0

        # Total disponível no mês (receitas + saldo - gastos crédito)
        disponivel_mes = receitas_mes + saldo_total - gasto_credito

    return jsonify({
        'saldo_total': saldo_total,
        'gasto_credito': gasto_credito,
        'receitas_mes': receitas_mes,
        'disponivel_mes': disponivel_mes
    })


# --------------------------
# Lançamentos - DESPESAS - CORRIGIDA
# --------------------------
@app.route('/lancamentos')
def lancamentos():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT t.id, t.descricao, t.tipo, t.valor, t.categoria, 
                   ct.nome as cartao_nome, DATE(t.data_criacao) as data,
                   t.pagamento, t.parcelas, t.tipo_compra, t.tipo_cobranca
            FROM transacoes t
            LEFT JOIN cartoes ct ON t.id_cartao = ct.id
            WHERE t.tipo='despesa'
            ORDER BY t.data_criacao DESC
        """)
        lancamentos = c.fetchall()

        # Formatar os dados para o template
        lancamentos_formatados = []
        for lancamento in lancamentos:
            lancamentos_formatados.append(list(lancamento))

    return render_template('lancamentos.html', lancamentos=lancamentos_formatados)


# --------------------------
# Lançamentos - RECEITAS - COM TODOS OS CAMPOS
# --------------------------
@app.route('/lancamentosReceita')
def lancamentosReceita():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT t.id, t.descricao, t.tipo, t.valor, t.categoria, 
                   COALESCE(c.nome, 'N/A') as conta_nome,
                   COALESCE(t.tipo_receita, 'avulsa') as tipo_receita,
                   t.dia_vencimento
            FROM transacoes t
            LEFT JOIN contas c ON t.id_conta = c.id
            WHERE t.tipo='receita'
            ORDER BY t.data_criacao DESC
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
# API - CONTAS
# --------------------------
@app.route('/api/contas')
def listar_contas():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nome FROM contas ORDER BY nome")
        contas = c.fetchall()
    return {"contas": [{"id": id, "nome": nome} for id, nome in contas]}

@app.route("/api/adicionar_conta", methods=["POST"])
def adicionar_conta():
    data = request.get_json()
    nome = data.get("nome", "").strip()
    
    if not nome:
        return {"success": False, "error": "Nome da conta é obrigatório"}
    
    with sqlite3.connect("financas.db", check_same_thread=False) as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO contas (nome, saldo) VALUES (?, 0)", (nome,))
            conn.commit()
            conta_id = c.lastrowid
            return {"success": True, "id": conta_id, "nome": nome}
        except sqlite3.IntegrityError:
            return {"success": False, "error": "Conta já existente"}

@app.route("/api/remover_conta", methods=["POST"])
def remover_conta():
    data = request.get_json()
    conta_id = data.get("id")
    if not conta_id:
        return {"success": False, "error": "ID não fornecido"}

    with sqlite3.connect("financas.db", check_same_thread=False) as conn:
        c = conn.cursor()
        
        # Verificar se existem cartões vinculados a esta conta
        c.execute("SELECT COUNT(*) FROM cartoes WHERE conta = ?", (conta_id,))
        cartoes_vinculados = c.fetchone()[0]
        
        if cartoes_vinculados > 0:
            return {"success": False, "error": "Não é possível remover conta com cartões vinculados"}
        
        c.execute("DELETE FROM contas WHERE id = ?", (conta_id,))
        conn.commit()
        
    return {"success": True}


# --------------------------
# Lançamentos - CARTÕES
# --------------------------
@app.route('/lancamentosCartao')
def lancamentosCartao():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT c.id, c.nome, ct.nome as conta_nome, c.dias_fechamento, 
                   c.data_vencimento, c.tipo_pagamento, c.limite
            FROM cartoes c
            LEFT JOIN contas ct ON c.conta = ct.id
            ORDER BY c.nome
        """)
        cartoes = c.fetchall()

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

# NOVA API - CARTÕES DISPONÍVEIS
@app.route('/api/cartoes_disponiveis')
def listar_cartoes_completos():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT c.id, c.nome, c.tipo_pagamento, ct.nome as conta_nome
            FROM cartoes c
            LEFT JOIN contas ct ON c.conta = ct.id
            ORDER BY c.nome
        """)
        cartoes = c.fetchall()
    return {"cartoes": [{"id": id, "nome": nome, "tipo_pagamento": tipo, "conta_nome": conta_nome} 
                       for id, nome, tipo, conta_nome in cartoes]}


# --------------------------
# API - Lançamentos (Adicionar / Remover) - COMPLETA E CORRIGIDA
# --------------------------
@app.route('/api/adicionar_lancamento', methods=['POST'])
def api_adicionar_lancamento():
    data = request.get_json()
    descricao = data.get("descricao")
    tipo = data.get("tipo")  # "despesa" ou "receita"
    valor = float(data.get("valor"))
    categoria = data.get("categoria")
    id_cartao = data.get("id_cartao")
    id_conta = data.get("id_conta")
    tipo_receita = data.get("tipo_receita", "avulsa")  # "avulsa" ou "fixa"
    tipo_cobranca = data.get("tipo_cobranca", "avulsa")  # "avulsa" ou "fixa"
    dia_vencimento = data.get("dia_vencimento")  # 1-31
    tipo_compra = data.get("tipo_compra", "credito")  # "credito" ou "debito"
    pagamento = data.get("pagamento", "avista")  # "avista" ou "parcelado"
    parcelas = data.get("parcelas")  # número de parcelas (pode ser None)

    if not descricao or not tipo or valor is None:
        return {"success": False, "error": "Campos obrigatórios ausentes"}

    # Validações específicas
    if tipo == "despesa" and not id_cartao:
        return {"success": False, "error": "Para despesas, selecione um cartão"}
    if tipo == "receita" and not id_conta:
        return {"success": False, "error": "Para receitas, selecione uma conta"}
    if tipo == "receita" and tipo_receita == "fixa" and not dia_vencimento:
        return {"success": False, "error": "Para receita fixa, informe o dia do mês"}

    # Validação para tipo_compra em despesas
    if tipo == "despesa" and tipo_compra not in ['credito', 'debito']:
        return {"success": False, "error": "Tipo de compra inválido"}

    # Validação para pagamento parcelado
    if pagamento == "parcelado" and (not parcelas or parcelas < 2):
        return {"success": False, "error": "Para pagamento parcelado, informe o número de parcelas (mínimo 2)"}

    with sqlite3.connect("financas.db", check_same_thread=False) as conn:
        c = conn.cursor()
        
        # Verificar se o cartão existe e seu tipo
        if tipo == "despesa" and id_cartao:
            c.execute("SELECT tipo_pagamento FROM cartoes WHERE id = ?", (id_cartao,))
            cartao = c.fetchone()
            if not cartao:
                return {"success": False, "error": "Cartão não encontrado"}
            
            # Validar compatibilidade entre tipo do cartão e tipo da compra
            tipo_cartao = cartao[0]
            if tipo_cartao != 'multiplo' and tipo_compra != tipo_cartao:
                return {"success": False, "error": f"Este cartão só aceita pagamentos no {tipo_cartao}"}
            
            # Validar se cartão débito não está tentando parcelar
            if tipo_cartao == 'debito' and pagamento == 'parcelado':
                return {"success": False, "error": "Cartão de débito não permite parcelamento"}
        
        # Inserir a transação COM OS NOVOS CAMPOS
        c.execute("""
            INSERT INTO transacoes (tipo, descricao, valor, categoria, id_cartao, id_conta, 
                                   tipo_receita, tipo_cobranca, dia_vencimento, tipo_compra, pagamento, parcelas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tipo, descricao, valor, categoria, id_cartao, id_conta, tipo_receita, 
              tipo_cobranca, dia_vencimento, tipo_compra, pagamento, parcelas))
        
        # ATUALIZAR SALDO DA CONTA se for RECEITA ou DESPESA NO DÉBITO
        if tipo == "receita" and id_conta:
            c.execute("UPDATE contas SET saldo = saldo + ? WHERE id = ?", (valor, id_conta))
        elif tipo == "despesa" and tipo_compra == "debito" and id_cartao:
            # Para débito, desconta direto da conta vinculada ao cartão
            c.execute("""
                UPDATE contas 
                SET saldo = saldo - ? 
                WHERE id = (SELECT conta FROM cartoes WHERE id = ?)
            """, (valor, id_cartao))
        
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
        
        # Buscar a transação completa para reversão
        c.execute("""
            SELECT tipo, valor, id_conta, id_cartao, tipo_compra 
            FROM transacoes WHERE id = ?
        """, (lancamento_id,))
        transacao = c.fetchone()
        
        if transacao:
            tipo, valor, id_conta, id_cartao, tipo_compra = transacao
            
            # Reverter saldo se for receita
            if tipo == "receita" and id_conta:
                c.execute("UPDATE contas SET saldo = saldo - ? WHERE id = ?", (valor, id_conta))
            # Reverter saldo se for despesa no débito
            elif tipo == "despesa" and tipo_compra == "debito" and id_cartao:
                c.execute("""
                    UPDATE contas 
                    SET saldo = saldo + ? 
                    WHERE id = (SELECT conta FROM cartoes WHERE id = ?)
                """, (valor, id_cartao))
        
        c.execute("DELETE FROM transacoes WHERE id = ?", (lancamento_id,))
        conn.commit()
        
    return {"success": True}


# --------------------------
# Categorias - COMPLETA
# --------------------------
@app.route('/lancamentosCategorias')
def lancamentosCategorias():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("SELECT id, nome, tipo FROM categorias ORDER BY tipo, nome")
        categorias = c.fetchall()
    return render_template('lancamentosCategorias.html', categorias=categorias)

# API - CATEGORIAS: Com filtro por tipo
@app.route('/api/categorias')
def listar_categorias():
    tipo = request.args.get('tipo')  # 'despesa' ou 'receita'
    
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        
        if tipo and tipo in ['despesa', 'receita']:
            # Filtra por tipo específico
            c.execute("SELECT id, nome, tipo FROM categorias WHERE tipo = ? ORDER BY nome", (tipo,))
        else:
            # Retorna todas as categorias (compatibilidade)
            c.execute("SELECT id, nome, tipo FROM categorias ORDER BY nome")
            
        categorias = c.fetchall()
    return {"categorias": [{"id": id, "nome": nome, "tipo": tipo} for id, nome, tipo in categorias]}

@app.route("/api/adicionar_categoria", methods=["POST"])
def adicionar_categoria():
    data = request.get_json()
    nome = data.get("nome", "").strip()
    tipo = data.get("tipo", "despesa")  # Padrão: despesa
    
    if not nome:
        return {"success": False, "error": "Nome da categoria obrigatório"}

    with sqlite3.connect("financas.db", check_same_thread=False) as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO categorias (nome, tipo) VALUES (?, ?)", (nome, tipo))
            conn.commit()
            categoria_id = c.lastrowid
            return {"success": True, "id": categoria_id, "nome": nome, "tipo": tipo}
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
# NOVA API - Buscar despesas completas para a tela
# --------------------------
@app.route('/api/despesas_completas')
def despesas_completas():
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT t.id, t.descricao, t.tipo, t.valor, t.categoria, 
                   ct.nome as cartao_nome, DATE(t.data_criacao) as data,
                   t.pagamento, t.parcelas, t.tipo_compra, t.tipo_cobranca
            FROM transacoes t
            LEFT JOIN cartoes ct ON t.id_cartao = ct.id
            WHERE t.tipo='despesa'
            ORDER BY t.data_criacao DESC
        """)
        despesas = c.fetchall()
    
    # Formatar no formato esperado pelo frontend
    despesas_formatadas = []
    for despesa in despesas:
        despesas_formatadas.append(list(despesa))
    
    return jsonify({"despesas": despesas_formatadas})


# --------------------------
# FUNÇÃO PARA GERAR RECEITAS FIXAS (Para implementar depois)
# --------------------------
def gerar_receitas_fixas():
    """Função para gerar automaticamente receitas fixas no dia correto"""
    # Esta função pode ser chamada por um agendador (cron job)
    # ou executada quando o sistema inicia
    hoje = datetime.now().day
    
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        
        # Buscar receitas fixas que ainda não foram geradas este mês
        c.execute("""
            SELECT id, descricao, valor, categoria, id_conta, dia_vencimento
            FROM transacoes 
            WHERE tipo='receita' 
            AND tipo_receita='fixa' 
            AND dia_vencimento = ?
            AND strftime('%Y-%m', data_criacao) != strftime('%Y-%m', 'now')
        """, (hoje,))
        
        receitas_para_gerar = c.fetchall()
        
        for receita in receitas_para_gerar:
            id_original, descricao, valor, categoria, id_conta, dia_vencimento = receita
            
            # Gerar nova receita
            c.execute("""
                INSERT INTO transacoes (tipo, descricao, valor, categoria, id_conta, tipo_receita, dia_vencimento)
                VALUES (?, ?, ?, ?, ?, 'fixa', ?)
            """, ('receita', descricao, valor, categoria, id_conta, dia_vencimento))
            
            # Atualizar saldo da conta
            c.execute("UPDATE contas SET saldo = saldo + ? WHERE id = ?", (valor, id_conta))
        
        conn.commit()


# --------------------------
# FUNÇÃO PARA GERAR DESPESAS FIXAS
# --------------------------
def gerar_despesas_fixas():
    """Função para gerar automaticamente despesas fixas no dia correto"""
    hoje = datetime.now().day
    
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        
        # Buscar despesas fixas que ainda não foram geradas este mês
        c.execute("""
            SELECT id, descricao, valor, categoria, id_cartao, tipo_compra, dia_vencimento
            FROM transacoes 
            WHERE tipo='despesa' 
            AND tipo_cobranca='fixa' 
            AND dia_vencimento = ?
            AND strftime('%Y-%m', data_criacao) != strftime('%Y-%m', 'now')
        """, (hoje,))
        
        despesas_para_gerar = c.fetchall()
        
        for despesa in despesas_para_gerar:
            id_original, descricao, valor, categoria, id_cartao, tipo_compra, dia_vencimento = despesa
            
            # Gerar nova despesa
            c.execute("""
                INSERT INTO transacoes (tipo, descricao, valor, categoria, id_cartao, tipo_cobranca, tipo_compra, dia_vencimento)
                VALUES (?, ?, ?, ?, ?, 'fixa', ?, ?)
            """, ('despesa', descricao, valor, categoria, id_cartao, tipo_compra, dia_vencimento))
            
            # Se for débito, desconta da conta
            if tipo_compra == "debito" and id_cartao:
                c.execute("""
                    UPDATE contas 
                    SET saldo = saldo - ? 
                    WHERE id = (SELECT conta FROM cartoes WHERE id = ?)
                """, (valor, id_cartao))
        
        conn.commit()


# --------------------------
# ROTA PARA TESTE - Gerar dados de exemplo
# --------------------------
@app.route('/api/gerar_dados_exemplo')
def gerar_dados_exemplo():
    """Rota para gerar dados de exemplo para teste"""
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        
        # Inserir algumas contas de exemplo
        contas_exemplo = [
            ('Conta Corrente', 1000.00),
            ('Conta Poupança', 5000.00),
            ('Carteira', 200.00)
        ]
        
        for nome, saldo in contas_exemplo:
            try:
                c.execute("INSERT OR IGNORE INTO contas (nome, saldo) VALUES (?, ?)", (nome, saldo))
            except:
                pass
        
        # Inserir alguns cartões de exemplo
        c.execute("SELECT id FROM contas WHERE nome = 'Conta Corrente'")
        conta_id = c.fetchone()[0]
        
        cartoes_exemplo = [
            ('Cartão Crédito Nubank', conta_id, 'credito', 10, 5, 5000.00),
            ('Cartão Débito Itaú', conta_id, 'debito', None, None, 0),
            ('Cartão Multi Santander', conta_id, 'multiplo', 15, 10, 3000.00)
        ]
        
        for nome, conta, tipo_pagamento, data_venc, dias_fech, limite in cartoes_exemplo:
            try:
                c.execute("""
                    INSERT OR IGNORE INTO cartoes (nome, conta, tipo_pagamento, data_vencimento, dias_fechamento, limite)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (nome, conta, tipo_pagamento, data_venc, dias_fech, limite))
            except:
                pass
        
        conn.commit()
    
    return {"success": True, "message": "Dados de exemplo gerados com sucesso"}


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
    # Para garantir que o banco seja recriado com todas as correções
    if os.path.exists('financas.db'):
        os.remove('financas.db')
    
    init_db()
    
    # Gerar receitas e despesas fixas ao iniciar (opcional)
    try:
        gerar_receitas_fixas()
        gerar_despesas_fixas()
    except Exception as e:
        print(f"Erro ao gerar transações fixas: {e}")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)