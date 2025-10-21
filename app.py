from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import os
from datetime import datetime, timedelta

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

        # Tabela de categorias
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

        # Tabela de cartões
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
# Função para calcular próximas faturas - CORRIGIDA
# --------------------------
def calcular_proximas_faturas():
    """Calcula a projeção das próximas faturas (3 meses)"""
    hoje = datetime.now()
    proximas_faturas = []
    
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        
        # Calcular para os próximos 3 meses
        for meses_a_frente in range(1, 4):
            mes_projecao = hoje.month + meses_a_frente
            ano_projecao = hoje.year
            
            # Ajustar ano se passar de dezembro
            if mes_projecao > 12:
                mes_projecao -= 12
                ano_projecao += 1
            
            # Nome do mês em português
            meses_pt = {
                1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
            }
            nome_mes = f"{meses_pt[mes_projecao]}/{ano_projecao}"
            
            # Calcular receitas fixas para este mês
            c.execute("""
                SELECT SUM(valor) FROM transacoes 
                WHERE tipo = 'receita'
                AND tipo_receita = 'fixa'
            """)
            receitas_fixas = c.fetchone()[0] or 0
            
            # Calcular despesas fixas para este mês
            c.execute("""
                SELECT SUM(valor) FROM transacoes 
                WHERE tipo = 'despesa'
                AND tipo_cobranca = 'fixa'
            """)
            despesas_fixas = c.fetchone()[0] or 0
            
            # Calcular despesas parceladas que estarão ativas neste mês - CORREÇÃO
            c.execute("""
                SELECT t.id, t.descricao, t.valor, t.parcelas, t.data_criacao, t.tipo_compra
                FROM transacoes t
                WHERE t.tipo = 'despesa'
                AND t.pagamento = 'parcelado'
                AND t.parcelas > 1
            """)
            despesas_parceladas = c.fetchall()
            
            despesas_parceladas_mes = 0
            print(f"\n=== CÁLCULO PARCELAS MÊS {mes_projecao}/{ano_projecao} ===")
            
            for transacao_id, descricao, valor_total, parcelas, data_criacao, tipo_compra in despesas_parceladas:
                if data_criacao:
                    try:
                        data_compra = datetime.strptime(data_criacao, '%Y-%m-%d %H:%M:%S')
                        valor_parcela = valor_total / parcelas
                        
                        print(f"Transação {transacao_id}: {descricao}")
                        print(f"  Valor total: R$ {valor_total:.2f}, Parcelas: {parcelas}")
                        print(f"  Valor parcela: R$ {valor_parcela:.2f}")
                        print(f"  Data compra: {data_compra.strftime('%d/%m/%Y')}")
                        
                        # Verificar se esta parcela ainda estará ativa no mês da projeção
                        for parcela_num in range(parcelas):
                            mes_parcela = data_compra.month + parcela_num
                            ano_parcela = data_compra.year
                            
                            # Ajustar mês/ano se passar de dezembro
                            while mes_parcela > 12:
                                mes_parcela -= 12
                                ano_parcela += 1
                            
                            if mes_parcela == mes_projecao and ano_parcela == ano_projecao:
                                despesas_parceladas_mes += valor_parcela
                                print(f"  ✓ Parcela {parcela_num + 1} cai em {mes_projecao}/{ano_projecao}: +R$ {valor_parcela:.2f}")
                            else:
                                print(f"  ✗ Parcela {parcela_num + 1} cai em {mes_parcela}/{ano_parcela}")
                                
                    except Exception as e:
                        print(f"Erro ao processar parcela: {e}")
                        continue
            
            print(f"Total despesas parceladas mês {mes_projecao}: R$ {despesas_parceladas_mes:.2f}")
            
            # Calcular saldo final do mês
            receitas_total = receitas_fixas
            despesas_total = despesas_fixas + despesas_parceladas_mes
            saldo_final = receitas_total - despesas_total
            
            print(f"Resumo {nome_mes}:")
            print(f"  Receitas fixas: R$ {receitas_fixas:.2f}")
            print(f"  Despesas fixas: R$ {despesas_fixas:.2f}")
            print(f"  Despesas parceladas: R$ {despesas_parceladas_mes:.2f}")
            print(f"  Saldo final: R$ {saldo_final:.2f}")
            print("=" * 50)
            
            proximas_faturas.append({
                'mes_ano': nome_mes,
                'receitas_total': receitas_total,
                'despesas_total': despesas_total,
                'saldo_final': saldo_final
            })
    
    return proximas_faturas
# --------------------------
# Função para calcular despesas da fatura atual - VERSÃO CORRIGIDA
# --------------------------
def calcular_despesas_fatura_atual():
    """Calcula o total de despesas que estão na fatura atual (em aberto) - CORREÇÃO: dia do fechamento vai para próxima fatura"""
    hoje = datetime.now()
    despesas_fatura_atual = 0
    
    with sqlite3.connect('financas.db', check_same_thread=False) as conn:
        c = conn.cursor()
        
        c.execute("SELECT id, dias_fechamento, data_vencimento FROM cartoes WHERE tipo_pagamento IN ('credito', 'multiplo')")
        cartoes = c.fetchall()
        
        for cartao_id, dias_fechamento, data_vencimento in cartoes:
            if dias_fechamento and data_vencimento:
                try:
                    # CORREÇÃO: Lógica correta - dia do fechamento vai para PRÓXIMA fatura
                    
                    # FATURA ATUAL: que vence no data_vencimento do PRÓXIMO mês
                    if hoje.month == 12:
                        mes_vencimento_fatura_atual = 1
                        ano_vencimento_fatura_atual = hoje.year + 1
                    else:
                        mes_vencimento_fatura_atual = hoje.month + 1
                        ano_vencimento_fatura_atual = hoje.year
                    
                    data_vencimento_fatura_atual = datetime(ano_vencimento_fatura_atual, mes_vencimento_fatura_atual, data_vencimento)
                    data_fechamento_fatura_atual = data_vencimento_fatura_atual - timedelta(days=dias_fechamento)
                    
                    # FATURA ANTERIOR: para calcular o início do período
                    if hoje.month == 1:
                        mes_vencimento_fatura_anterior = 12
                        ano_vencimento_fatura_anterior = hoje.year - 1
                    else:
                        mes_vencimento_fatura_anterior = hoje.month
                        ano_vencimento_fatura_anterior = hoje.year
                    
                    data_vencimento_fatura_anterior = datetime(ano_vencimento_fatura_anterior, mes_vencimento_fatura_anterior, data_vencimento)
                    data_fechamento_fatura_anterior = data_vencimento_fatura_anterior - timedelta(days=dias_fechamento)
                    
                    # PERÍODO CORRETO: 
                    # INÍCIO: dia do fechamento da fatura anterior (INCLUSIVE) - vai para fatura atual
                    # FIM: dia ANTERIOR ao fechamento da fatura atual - vai para fatura atual
                    data_inicio_periodo = data_fechamento_fatura_anterior
                    data_fim_periodo = data_fechamento_fatura_atual - timedelta(days=1)
                    
                    # DEBUG: Mostrar período calculado
                    print(f"=== CÁLCULO PERÍODO FATURA ===")
                    print(f"Cartão {cartao_id}:")
                    print(f"  Hoje: {hoje.strftime('%d/%m/%Y')}")
                    print(f"  Vencimento: dia {data_vencimento}")
                    print(f"  Fechamento: {dias_fechamento} dias antes")
                    print(f"  Fatura atual: {mes_vencimento_fatura_atual}/{ano_vencimento_fatura_atual} (vence {data_vencimento_fatura_atual.strftime('%d/%m/%Y')})")
                    print(f"  Fechamento atual: {data_fechamento_fatura_atual.strftime('%d/%m/%Y')}")
                    print(f"  Fechamento anterior: {data_fechamento_fatura_anterior.strftime('%d/%m/%Y')}")
                    print(f"  Período fatura atual: {data_inicio_periodo.strftime('%d/%m/%Y')} a {data_fim_periodo.strftime('%d/%m/%Y')}")
                    
                    # Buscar despesas neste período
                    c.execute("""
                        SELECT SUM(valor) FROM transacoes 
                        WHERE tipo = 'despesa'
                        AND id_cartao = ?
                        AND DATE(data_criacao) BETWEEN DATE(?) AND DATE(?)
                    """, (cartao_id, data_inicio_periodo.strftime('%Y-%m-%d'), data_fim_periodo.strftime('%Y-%m-%d')))
                    
                    despesas_cartao = c.fetchone()[0] or 0
                    despesas_fatura_atual += despesas_cartao
                    
                    print(f"  Despesas no período: R$ {despesas_cartao}")
                    
                    # DEBUG: Verificar despesas específicas
                    c.execute("""
                        SELECT descricao, valor, DATE(data_criacao) 
                        FROM transacoes 
                        WHERE tipo = 'despesa'
                        AND id_cartao = ?
                        AND DATE(data_criacao) BETWEEN DATE(?) AND DATE(?)
                    """, (cartao_id, data_inicio_periodo.strftime('%Y-%m-%d'), data_fim_periodo.strftime('%Y-%m-%d')))
                    
                    despesas_detalhadas = c.fetchall()
                    for desc, valor, data in despesas_detalhadas:
                        print(f"    - {desc}: R$ {valor} em {data}")
                    print("=" * 50)
                    
                except ValueError as e:
                    print(f"Erro no cartão {cartao_id}: {e}")
                    continue
    
    return despesas_fatura_atual

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

        # PROJEÇÃO DE RECEITAS FIXAS FUTURAS (que ainda não aconteceram este mês)
        c.execute("""
            SELECT SUM(valor) FROM transacoes 
            WHERE tipo = 'receita'
            AND tipo_receita = 'fixa'
            AND (strftime('%Y-%m', data_criacao) != strftime('%Y-%m', 'now') OR data_criacao IS NULL)
        """)
        receitas_fixas_futuras = c.fetchone()[0] or 0

        # PROJEÇÃO DE DESPESAS FIXAS FUTURAS (considerando datas de fechamento/vencimento)
        hoje = datetime.now()
        
        c.execute("SELECT id, dias_fechamento, data_vencimento FROM cartoes WHERE tipo_pagamento IN ('credito', 'multiplo')")
        cartoes = c.fetchall()
        
        despesas_fixas_futuras = 0
        
        for cartao_id, dias_fechamento, data_vencimento in cartoes:
            if dias_fechamento and data_vencimento:
                try:
                    # MESMA LÓGICA AUTO-SUSTENTÁVEL
                    if hoje.month == 12:
                        mes_vencimento_fatura_atual = 1
                        ano_vencimento_fatura_atual = hoje.year + 1
                    else:
                        mes_vencimento_fatura_atual = hoje.month + 1
                        ano_vencimento_fatura_atual = hoje.year
                    
                    data_vencimento_fatura_atual = datetime(ano_vencimento_fatura_atual, mes_vencimento_fatura_atual, data_vencimento)
                    data_fechamento_fatura_atual = data_vencimento_fatura_atual - timedelta(days=dias_fechamento)
                    
                    if hoje.month == 1:
                        mes_vencimento_fatura_anterior = 12
                        ano_vencimento_fatura_anterior = hoje.year - 1
                    else:
                        mes_vencimento_fatura_anterior = hoje.month
                        ano_vencimento_fatura_anterior = hoje.year
                    
                    data_vencimento_fatura_anterior = datetime(ano_vencimento_fatura_anterior, mes_vencimento_fatura_anterior, data_vencimento)
                    data_fechamento_fatura_anterior = data_vencimento_fatura_anterior - timedelta(days=dias_fechamento)
                    
                    # Buscar despesas fixas que caem dentro do período da fatura atual
                    c.execute("""
                        SELECT SUM(valor) FROM transacoes 
                        WHERE tipo = 'despesa'
                        AND tipo_cobranca = 'fixa'
                        AND (strftime('%Y-%m', data_criacao) != strftime('%Y-%m', 'now') OR data_criacao IS NULL)
                        AND dia_vencimento > ? AND dia_vencimento <= ?
                    """, (data_fechamento_fatura_anterior.day, data_fechamento_fatura_atual.day))
                    
                    despesas_cartao = c.fetchone()[0] or 0
                    despesas_fixas_futuras += despesas_cartao
                    
                    print(f"Despesas fixas futuras - Cartão {cartao_id}: R$ {despesas_cartao}")
                    print(f"  Período: dia {data_fechamento_fatura_anterior.day + 1} a {data_fechamento_fatura_atual.day}")
                    
                except ValueError as e:
                    print(f"Erro no cartão {cartao_id} (fixas): {e}")
                    continue

        # DESPESAS DA FATURA ATUAL (CORREÇÃO PRINCIPAL)
        despesas_fatura_atual = calcular_despesas_fatura_atual()

        # CÁLCULO CORRETO DO DISPONÍVEL MÊS:
        disponivel_mes = saldo_total + receitas_fixas_futuras - despesas_fixas_futuras - despesas_fatura_atual

        print(f"DEBUG CÁLCULO:")
        print(f"  Saldo total: R$ {saldo_total}")
        print(f"  Receitas fixas futuras: R$ {receitas_fixas_futuras}")
        print(f"  Despesas fixas futuras: R$ {despesas_fixas_futuras}")
        print(f"  Despesas fatura atual: R$ {despesas_fatura_atual}")
        print(f"  Disponível mês: R$ {disponivel_mes}")

        # Gastos no crédito da fatura atual (para o card de informação)
        gasto_credito_fatura_atual = 0
        
        for cartao_id, dias_fechamento, data_vencimento in cartoes:
            if dias_fechamento and data_vencimento:
                try:
                    if hoje.month == 12:
                        mes_vencimento = 1
                        ano_vencimento = hoje.year + 1
                    else:
                        mes_vencimento = hoje.month + 1
                        ano_vencimento = hoje.year
                    
                    data_vencimento_fatura = datetime(ano_vencimento, mes_vencimento, data_vencimento)
                    data_fechamento_fatura = data_vencimento_fatura - timedelta(days=dias_fechamento)
                    
                    if hoje.month == 1:
                        mes_vencimento_anterior = 12
                        ano_vencimento_anterior = hoje.year - 1
                    else:
                        mes_vencimento_anterior = hoje.month
                        ano_vencimento_anterior = hoje.year
                    
                    data_vencimento_anterior = datetime(ano_vencimento_anterior, mes_vencimento_anterior, data_vencimento)
                    data_fechamento_anterior = data_vencimento_anterior - timedelta(days=dias_fechamento)
                    
                    c.execute("""
                        SELECT SUM(valor) FROM transacoes 
                        WHERE tipo = 'despesa' 
                        AND tipo_compra = 'credito'
                        AND id_cartao = ?
                        AND DATE(data_criacao) BETWEEN DATE(?) AND DATE(?)
                    """, (cartao_id, data_fechamento_anterior.strftime('%Y-%m-%d'), data_fechamento_fatura.strftime('%Y-%m-%d')))
                    
                    gasto_cartao = c.fetchone()[0] or 0
                    gasto_credito_fatura_atual += gasto_cartao
                except ValueError:
                    continue

        # TOTAL DE RECEITAS DO MÊS (para outro card)
        c.execute("""
            SELECT SUM(valor) FROM transacoes 
            WHERE tipo = 'receita'
            AND strftime('%Y-%m', data_criacao) = strftime('%Y-%m', 'now')
        """)
        receitas_mes = c.fetchone()[0] or 0

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

        # Metas
        meta_economia_atual = min(650, 1000)
        meta_economia_percentual = int((meta_economia_atual / 1000) * 100) if 1000 > 0 else 0
        
        meta_gastos_atual = min(1500, 2000)
        meta_gastos_percentual = int((meta_gastos_atual / 2000) * 100) if 2000 > 0 else 0
        
        meta_economia = {'meta': 1000, 'atual': meta_economia_atual, 'percentual': meta_economia_percentual}
        meta_gastos = {'meta': 2000, 'atual': meta_gastos_atual, 'percentual': meta_gastos_percentual}
        
        # PRÓXIMAS FATURAS (nova funcionalidade)
        proximas_faturas = calcular_proximas_faturas()

    return render_template('index.html', 
                         transacoes=transacoes,
                         saldo_total=saldo_total,
                         gasto_credito=gasto_credito_fatura_atual,
                         receitas_mes=receitas_mes,
                         disponivel_mes=disponivel_mes,
                         proximas_faturas=proximas_faturas,
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

        # PROJEÇÃO DE RECEITAS FIXAS FUTURAS
        c.execute("""
            SELECT SUM(valor) FROM transacoes 
            WHERE tipo = 'receita'
            AND tipo_receita = 'fixa'
            AND (strftime('%Y-%m', data_criacao) != strftime('%Y-%m', 'now') OR data_criacao IS NULL)
        """)
        receitas_fixas_futuras = c.fetchone()[0] or 0

        # PROJEÇÃO DE DESPESAS FIXAS FUTURAS
        hoje = datetime.now()
        dia_hoje = hoje.day
        mes_hoje = hoje.month
        ano_hoje = hoje.year

        c.execute("""
            SELECT id, dias_fechamento, data_vencimento 
            FROM cartoes 
            WHERE tipo_pagamento IN ('credito', 'multiplo')
        """)
        cartoes = c.fetchall()
        
        despesas_fixas_futuras = 0
        
        for cartao_id, dias_fechamento, data_vencimento in cartoes:
            if dias_fechamento and data_vencimento:
                try:
                    mes_vencimento = mes_hoje + 1 if mes_hoje < 12 else 1
                    ano_vencimento = ano_hoje if mes_hoje < 12 else ano_hoje + 1
                    
                    data_vencimento_fatura = datetime(ano_vencimento, mes_vencimento, data_vencimento)
                    data_fechamento_fatura = data_vencimento_fatura - timedelta(days=dias_fechamento)
                    
                    mes_vencimento_anterior = mes_hoje
                    ano_vencimento_anterior = ano_hoje
                    data_vencimento_anterior = datetime(ano_vencimento_anterior, mes_vencimento_anterior, data_vencimento)
                    data_fechamento_anterior = data_vencimento_anterior - timedelta(days=dias_fechamento)
                    
                    c.execute("""
                        SELECT SUM(valor) FROM transacoes 
                        WHERE tipo = 'despesa'
                        AND tipo_cobranca = 'fixa'
                        AND (strftime('%Y-%m', data_criacao) != strftime('%Y-%m', 'now') OR data_criacao IS NULL)
                        AND dia_vencimento > ? AND dia_vencimento <= ?
                    """, (data_fechamento_anterior.day, data_fechamento_fatura.day))
                    
                    despesas_cartao = c.fetchone()[0] or 0
                    despesas_fixas_futuras += despesas_cartao
                    
                except ValueError:
                    continue

        # DESPESAS DA FATURA ATUAL (CORREÇÃO PRINCIPAL)
        despesas_fatura_atual = calcular_despesas_fatura_atual()

        # CÁLCULO CORRETO DO DISPONÍVEL MÊS
        disponivel_mes = saldo_total + receitas_fixas_futuras - despesas_fixas_futuras - despesas_fatura_atual

        # Gastos no crédito da fatura atual
        gasto_credito_fatura_atual = 0
        
        for cartao_id, dias_fechamento, data_vencimento in cartoes:
            if dias_fechamento and data_vencimento:
                try:
                    mes_vencimento = mes_hoje + 1 if mes_hoje < 12 else 1
                    ano_vencimento = ano_hoje if mes_hoje < 12 else ano_hoje + 1
                    
                    data_vencimento_fatura = datetime(ano_vencimento, mes_vencimento, data_vencimento)
                    data_fechamento_fatura = data_vencimento_fatura - timedelta(days=dias_fechamento)
                    
                    mes_vencimento_anterior = mes_hoje
                    ano_vencimento_anterior = ano_hoje
                    data_vencimento_anterior = datetime(ano_vencimento_anterior, mes_vencimento_anterior, data_vencimento)
                    data_fechamento_anterior = data_vencimento_anterior - timedelta(days=dias_fechamento)
                    
                    c.execute("""
                        SELECT SUM(valor) FROM transacoes 
                        WHERE tipo = 'despesa' 
                        AND tipo_compra = 'credito'
                        AND id_cartao = ?
                        AND DATE(data_criacao) BETWEEN DATE(?) AND DATE(?)
                    """, (cartao_id, data_fechamento_anterior.strftime('%Y-%m-%d'), data_fechamento_fatura.strftime('%Y-%m-%d')))
                    
                    gasto_cartao = c.fetchone()[0] or 0
                    gasto_credito_fatura_atual += gasto_cartao
                except ValueError:
                    continue

        # Total de receitas do mês
        c.execute("""
            SELECT SUM(valor) FROM transacoes 
            WHERE tipo = 'receita'
            AND strftime('%Y-%m', data_criacao) = strftime('%Y-%m', 'now')
        """)
        receitas_mes = c.fetchone()[0] or 0

    return jsonify({
        'saldo_total': saldo_total,
        'gasto_credito': gasto_credito_fatura_atual,
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
    try:
        data = request.get_json()
        print(f"Dados recebidos: {data}")  # DEBUG
        
        if not data:
            return {"success": False, "error": "Nenhum dado recebido"}
            
        descricao = data.get("descricao")
        tipo = data.get("tipo")  # "despesa" ou "receita"
        valor_str = data.get("valor")
        categoria = data.get("categoria")
        id_cartao_str = data.get("id_cartao")  # Pode vir como string
        id_conta_str = data.get("id_conta")    # Pode vir como string
        tipo_receita = data.get("tipo_receita", "avulsa")
        tipo_cobranca = data.get("tipo_cobranca", "avulsa")
        dia_vencimento_str = data.get("dia_vencimento")
        tipo_compra = data.get("tipo_compra", "credito")
        pagamento = data.get("pagamento", "avista")
        parcelas_str = data.get("parcelas")
        
        # NOVO: Receber a data do formulário
        data_criacao = data.get("data")

        # Validações básicas
        if not descricao:
            return {"success": False, "error": "Descrição é obrigatória"}
        if not tipo:
            return {"success": False, "error": "Tipo é obrigatório"}
        if not valor_str:
            return {"success": False, "error": "Valor é obrigatório"}
            
        try:
            valor = float(valor_str)
        except (ValueError, TypeError):
            return {"success": False, "error": "Valor inválido"}

        # CONVERSÃO SEGURA DOS IDs
        id_cartao = None
        if id_cartao_str and id_cartao_str != "":
            try:
                id_cartao = int(id_cartao_str)
            except (ValueError, TypeError):
                return {"success": False, "error": "ID do cartão inválido"}

        id_conta = None
        if id_conta_str and id_conta_str != "":
            try:
                id_conta = int(id_conta_str)
            except (ValueError, TypeError):
                return {"success": False, "error": "ID da conta inválido"}

        # CONVERSÃO SEGURA DOS OUTROS CAMPOS NUMÉRICOS
        dia_vencimento = None
        if dia_vencimento_str and dia_vencimento_str != "":
            try:
                dia_vencimento = int(dia_vencimento_str)
            except (ValueError, TypeError):
                return {"success": False, "error": "Dia de vencimento inválido"}

        parcelas = None
        if parcelas_str and parcelas_str != "":
            try:
                parcelas = int(parcelas_str)
            except (ValueError, TypeError):
                return {"success": False, "error": "Número de parcelas inválido"}

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
            
            # Verificar se o cartão existe e seu tipo (apenas para despesas)
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
            
            # CORREÇÃO: Inserir a transação COM A DATA FORNECIDA
            if data_criacao:
                # Se foi fornecida uma data, usar ela
                c.execute("""
                    INSERT INTO transacoes (tipo, descricao, valor, categoria, id_cartao, id_conta, 
                                           tipo_receita, tipo_cobranca, dia_vencimento, tipo_compra, pagamento, parcelas, data_criacao)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (tipo, descricao, valor, categoria, id_cartao, id_conta, tipo_receita, 
                      tipo_cobranca, dia_vencimento, tipo_compra, pagamento, parcelas, data_criacao))
            else:
                # Se não foi fornecida data, usar o DEFAULT (data atual)
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
        
    except Exception as e:
        print(f"Erro ao adicionar lançamento: {e}")
        import traceback
        traceback.print_exc()  # Mostra o traceback completo para debug
        return {"success": False, "error": f"Erro interno: {str(e)}"}
    
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