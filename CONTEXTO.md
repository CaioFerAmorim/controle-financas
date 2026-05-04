# CONTEXTO DO PROJETO — Controle de Finanças
> Cole este arquivo no início de qualquer conversa com Claude ou Gemini para retomar o projeto sem perder contexto.

---

## Stack
- **Backend:** Python + Flask + SQLite (`financas.db`)
- **Frontend:** HTML + Bootstrap 5.3 + Jinja2 templates + JavaScript vanilla
- **Dependências Python:** `flask`, `python-dateutil` (para `relativedelta`)
- **JS compartilhado:** `static/js/tabela-utils.js` (classe `TabelaManager`)

---

## Estrutura de arquivos

```
app.py                          ← backend completo (rotas + lógica de negócio)
financas.db                     ← banco SQLite (gerado automaticamente)
static/
  js/
    tabela-utils.js             ← gerenciador de tabelas (sort, filtro, paginação)
templates/
  index.html                    ← dashboard principal com abas por cartão
  lancamentos.html              ← despesas avulsas
  lancamentosAssinaturas.html   ← despesas fixas recorrentes
  lancamentosReceita.html       ← receitas avulsas + receitas fixas
  lancamentosCartao.html        ← cadastro de cartões
  lancamentosConta.html         ← cadastro de contas
  lancamentosCategorias.html    ← categorias de despesa e receita
  projecoes.html                ← projeção dos próximos 6 meses
  visaoGeral.html               ← gráficos históricos + faturas por cartão
```

---

## Banco de dados — Schema completo

```sql
-- Transações avulsas (despesas e receitas manuais)
transacoes (
  id               INTEGER PK AUTOINCREMENT,
  tipo             TEXT    NOT NULL  -- 'despesa' | 'receita'
  descricao        TEXT    NOT NULL,
  valor            REAL    NOT NULL, -- valor TOTAL (não da parcela)
  categoria        TEXT,             -- '_fixo_rf_{id}' = gerada por receita fixa
                                     -- '_fixo_df_{id}' = gerada por despesa fixa
  id_cartao        INTEGER → cartoes.id,
  id_conta         INTEGER → contas.id,
  tipo_receita     TEXT    DEFAULT 'avulsa'   -- 'avulsa' | 'fixa'
  tipo_cobranca    TEXT    DEFAULT 'avulsa'   -- 'avulsa' | 'fixa'
  dia_vencimento   INTEGER,
  tipo_compra      TEXT    DEFAULT 'credito'  -- 'credito' | 'debito'
  pagamento        TEXT    DEFAULT 'avista'   -- 'avista' | 'parcelado'
  parcelas         INTEGER DEFAULT NULL,      -- número total de parcelas
  data_lancamento  DATE    NOT NULL           -- data da compra (YYYY-MM-DD)
)

-- Categorias de despesa e receita
categorias (
  id   INTEGER PK AUTOINCREMENT,
  nome TEXT    UNIQUE NOT NULL,
  tipo TEXT    -- 'despesa' | 'receita'
)

-- Contas bancárias (saldo real = receitas avulsas + ocorrências geradas)
contas (
  id    INTEGER PK AUTOINCREMENT,
  nome  TEXT  UNIQUE NOT NULL,
  saldo REAL  DEFAULT 0
)

-- Cartões de crédito/débito
cartoes (
  id               INTEGER PK AUTOINCREMENT,
  nome             TEXT  UNIQUE NOT NULL,
  conta            INTEGER NOT NULL → contas.id,
  tipo_pagamento   TEXT    -- 'credito' | 'debito' | 'multiplo'
  data_vencimento  INTEGER,  -- dia do mês que a fatura vence (1-31)
  dias_fechamento  INTEGER,  -- dias ANTES do vencimento que a fatura fecha
  limite           REAL  DEFAULT 0
)

-- Receitas fixas recorrentes (modelo — não são transações diretas)
receitas_fixas (
  id        INTEGER PK AUTOINCREMENT,
  descricao TEXT    NOT NULL,
  valor     REAL    NOT NULL,
  categoria TEXT,
  id_conta  INTEGER NOT NULL → contas.id,
  dia_mes   INTEGER NOT NULL DEFAULT 1,
  modo_dia  TEXT    DEFAULT 'fixo'  -- 'fixo' | 'primeiro_util' | 'ultimo_util'
  ativa     INTEGER DEFAULT 1       -- 1=ativa | 0=pausada
)

-- Despesas fixas recorrentes / assinaturas (modelo — não são transações diretas)
despesas_fixas (
  id        INTEGER PK AUTOINCREMENT,
  descricao TEXT    NOT NULL,
  valor     REAL    NOT NULL,
  categoria TEXT,
  id_cartao INTEGER → cartoes.id,   -- se cobrado no cartão
  id_conta  INTEGER → contas.id,    -- se cobrado em conta (débito)
  dia_mes   INTEGER NOT NULL DEFAULT 1,
  modo_dia  TEXT    DEFAULT 'fixo'  -- 'fixo' | 'primeiro_util' | 'ultimo_util'
  ativa     INTEGER DEFAULT 1
)
```

---

## Regras de negócio críticas

### Saldo das contas
- **Receita avulsa** → credita o saldo imediatamente ao adicionar.
- **Receita fixa** → **não** credita ao cadastrar. A função `gerar_ocorrencias_receitas_fixas()` cria a transação e credita o saldo no dia agendado (roda ao iniciar o servidor e ao adicionar nova receita fixa).
- **Despesa débito** → debita o saldo imediatamente.
- **Despesa crédito** → **não** mexe no saldo (vai para a fatura do cartão).
- **Idempotência de ocorrências:** a chave `categoria = '_fixo_rf_{id}'` ou `'_fixo_df_{id}'` + mês evita duplicatas.

### Cálculo de parcelas (IMPORTANTE)
- O campo `valor` em `transacoes` guarda o **valor total** da compra.
- **Valor da parcela** = `valor / parcelas` — calculado dinamicamente, nunca armazenado.
- A parcela N cai no mês `data_lancamento + N meses` (usando `relativedelta`).
- A função `valor_parcela_na_fatura(valor_total, parcelas, data_compra, inicio_fatura, fim_fatura)` retorna o valor de UMA parcela se alguma delas cair no período da fatura, ou 0. A comparação é feita por **mês/ano** (não por data exata).
- Para somar despesas de um mês corretamente use `despesas_reais_mes(ano, mes, conn)` — nunca `SUM(valor) WHERE strftime('%Y-%m', data_lancamento) = mês` para despesas parceladas.

### Cálculo de fatura do cartão
```python
def periodo_fatura_atual(dia_vencimento, dias_fechamento, referencia=None):
    # Retorna (inicio, fim, data_vencimento) da fatura ABERTA do cartão
    # Regra: fatura fecha `dias_fechamento` dias antes do vencimento
    # Compra no dia do fechamento → entra na PRÓXIMA fatura
    # Período: [fechamento_anterior, fechamento_atual - 1 dia]
```
- Cada cartão tem seu próprio período de fatura, calculado independentemente.
- `total_fatura_atual()` soma as parcelas corretas de todos os cartões de crédito.

### Disponível no Mês
```
Disponível = Saldo atual + Receitas fixas pendentes - Fatura de crédito atual
```
- **Receitas fixas pendentes** = fixas ativas cuja data de ocorrência ainda não chegou neste mês (função `receitas_fixas_pendentes_mes()`).
- **NÃO** usa receitas avulsas do mês — essas já estão no saldo.

### Dias úteis (para receitas/despesas fixas)
```python
FERIADOS_FIXOS_BR = {(1,1),(4,21),(5,1),(9,7),(10,12),(11,2),(11,15),(12,25)}
# modo_dia: 'fixo' | 'primeiro_util' | 'ultimo_util'
# 'primeiro_util' e 'ultimo_util' respeitam seg-sex e feriados fixos nacionais
# Feriados móveis (Carnaval, Páscoa, Corpus Christi) não incluídos
```

---

## APIs disponíveis (todas via POST com JSON, exceto GETs)

### Contas
| Método | Rota | Descrição |
|--------|------|-----------|
| GET  | `/api/contas` | Lista contas com saldo |
| POST | `/api/adicionar_conta` | `{nome}` |
| POST | `/api/remover_conta` | `{id}` |
| POST | `/api/atualizar_conta` | `{id, nome}` |

### Cartões
| Método | Rota | Descrição |
|--------|------|-----------|
| GET  | `/api/cartoes_disponiveis` | Lista cartões com tipo |
| POST | `/api/adicionar_cartao` | `{nome, conta, tipo_pagamento, data_vencimento, dias_fechamento, limite}` |
| POST | `/api/remover_cartao` | `{id}` |
| POST | `/api/atualizar_cartao` | `{id, nome, limite, data_vencimento, dias_fechamento}` |
| GET  | `/api/fatura/<cartao_id>` | Detalhe da fatura atual do cartão |

### Categorias
| Método | Rota | Descrição |
|--------|------|-----------|
| GET  | `/api/categorias?tipo=despesa\|receita` | Lista categorias |
| POST | `/api/adicionar_categoria` | `{nome, tipo}` |
| POST | `/api/remover_categoria` | `{id}` |
| POST | `/api/atualizar_categoria` | `{id, nome}` |

### Lançamentos (despesas/receitas avulsas)
| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/adicionar_lancamento` | `{descricao, tipo, valor, categoria, data, pagamento, parcelas, id_cartao, tipo_compra, tipo_cobranca}` |
| POST | `/api/remover_lancamento` | `{id}` — reverte saldo se necessário |
| POST | `/api/atualizar_lancamento` | `{id, descricao, categoria, data, valor, parcelas}` |

### Receitas Fixas
| Método | Rota | Descrição |
|--------|------|-----------|
| GET  | `/api/receitas_fixas` | Lista todas |
| POST | `/api/adicionar_receita_fixa` | `{descricao, valor, categoria, id_conta, dia_mes, modo_dia}` |
| POST | `/api/remover_receita_fixa` | `{id}` |
| POST | `/api/pausar_receita_fixa` | `{id, ativa: 0\|1}` |
| POST | `/api/atualizar_receita_fixa` | `{id, descricao, categoria, valor, dia_mes, modo_dia}` |

### Despesas Fixas (Assinaturas)
| Método | Rota | Descrição |
|--------|------|-----------|
| GET  | `/api/despesas_fixas` | Lista todas |
| POST | `/api/adicionar_despesa_fixa` | `{descricao, valor, categoria, id_cartao, id_conta, dia_mes, modo_dia}` |
| POST | `/api/remover_despesa_fixa` | `{id}` |
| POST | `/api/pausar_despesa_fixa` | `{id, ativa: 0\|1}` |
| POST | `/api/atualizar_despesa_fixa` | `{id, descricao, categoria, valor, dia_mes, modo_dia}` |

### Dashboard
| Método | Rota | Descrição |
|--------|------|-----------|
| GET  | `/api/dashboard_data` | Saldo, fatura, disponível, receitas do mês |
| GET  | `/api/dashboard_cartao/<id>` | Dashboard completo filtrado por cartão |

---

## Frontend — TabelaManager (tabela-utils.js v4)

**Uso:**
```javascript
const tm = new TabelaManager({
    tbody:     document.getElementById('minhaTabela'),
    thead:     document.getElementById('minhaCabecalho'),  // thead com id
    toolbar:   document.getElementById('minhaToolbar'),    // div para botão limpar
    selLinhas: document.getElementById('ipp'),
    ulPag:     document.getElementById('pag'),
    infoSpan:  document.getElementById('info'),
    colunas: [
        { chave: 'descricao', tipo: 'texto',  label: 'Descrição'           },  // input texto livre
        { chave: 'categoria', tipo: 'texto',  label: 'Categoria', opcoes: true },  // select valores únicos
        { chave: 'valor',     tipo: 'numero', label: 'Valor'               },  // inputs De/Até
        { chave: 'data',      tipo: 'data',   label: 'Data'                },  // date pickers De/Até
        { chave: 'acoes',     tipo: 'acoes',  label: 'Ações'               },  // sem filtro
    ],
    onEditar: (meta, tr) => { /* abre painel de edição */ }  // opcional
});

tm.adicionar(tr, { descricao: '...', categoria: '...', valor: 150.0, data: '2026-04-10' });
tm.remover(tr);
tm.atualizar(tr, novoMeta);  // após edição bem-sucedida
```

**Tipos de filtro por coluna:**
- `tipo:'texto'` sem `opcoes` → `<input text>` busca parcial
- `tipo:'texto'` com `opcoes:true` → `<select>` valores únicos (auto-populado)
- `tipo:'numero'` → dois `<input number>` De/Até
- `tipo:'data'` → dois `<input date>` De/Até
- `tipo:'acoes'` → sem filtro

**Toolbar:** só botão "× Limpar filtros" (aparece quando há filtro/sort ativo).

---

## Estrutura visual (todos os HTMLs)

```html
<header>  <!-- verde #1A4D2E, logo + nav principal -->
<div class="page-wrapper">  <!-- display:flex, min-height:calc(100vh - 98px) -->
    <nav class="sidebar-nav bg-dark">  <!-- largura 200px, fixa -->
        <!-- Links: Despesas | Assinaturas | Receitas | Contas | Cartões | Categorias -->
    </nav>
    <div class="sidebar-content">  <!-- flex:1, padding:1.5rem -->
        <!-- conteúdo da página -->
    </div>
</div>
```

**Cabeçalho de tabela padrão:** `<thead class="thead-fin">` — fundo `#1A4D2E`, texto branco, uppercase 11px.

---

## Pendente / Próximos passos

- [ ] **Edição in-place** — `onEditar` no TabelaManager está implementado no JS mas os painéis de edição (Offcanvas) ainda não foram criados nos HTMLs. Rotas `/api/atualizar_*` já existem no backend.
- [ ] **Exportação** — exportar tabelas para CSV/Excel
- [ ] **Filtro por período no dashboard** — selecionar mês/ano nos cards
- [ ] **Relatório mensal** — PDF com resumo do mês
- [ ] **Feriados móveis** — Carnaval, Páscoa, Corpus Christi no cálculo de dias úteis

---

## Como usar este arquivo com Gemini

**Para tarefas mecânicas** (aplicar sidebar em todos os HTMLs, substituir textos, formatar código):
> "Leia o CONTEXTO.md. Preciso que você [tarefa específica] no arquivo [nome do arquivo]."

**Para tarefas complexas** (lógica de negócio, bugs de data/parcela, nova funcionalidade):
> Traga para o Claude com este CONTEXTO.md + o arquivo específico em questão.

---

## Como iniciar uma nova conversa com Claude

Cole este arquivo e adicione:
> "Continuando o projeto de controle de finanças. [descreva o que quer fazer]."

Se for mexer em um arquivo específico, cole também o conteúdo atual desse arquivo.
