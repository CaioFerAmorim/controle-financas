# CONTEXTO DO PROJETO — Controle de Finanças
> Cole este arquivo no início de qualquer nova conversa para retomar sem perder contexto.
> Última atualização: maio/2026

---

## Stack
- **Backend:** Python + Flask + SQLite (`financas.db`)
- **Frontend:** HTML + Bootstrap 5.3 + Jinja2 + JavaScript vanilla
- **Dependências Python:** `flask`, `python-dateutil`, `werkzeug` (já vem com Flask)
- **JS compartilhado:**
  - `static/js/tabela-utils.js` — classe `TabelaManager` (v6): sort, filtros como chips estilo Shopify, paginação
  - `static/js/editar-utils.js` — classe `EditorPanel` (Offcanvas Bootstrap para edição inline)

---

## Estrutura de arquivos

```
app.py                          ← backend completo
financas.db                     ← banco SQLite (gerado automaticamente)
migrar_banco.sql                ← rode UMA VEZ se o banco já tinha dados antes do login
static/
  js/
    tabela-utils.js             ← gerenciador de tabelas
    editar-utils.js             ← painel de edição via Offcanvas
templates/
  login.html                   ← página de login
  cadastro.html                ← página de cadastro (com indicador de força de senha)
  admin.html                   ← painel admin (gerencia usuários)
  index.html                   ← dashboard com abas por cartão
  lancamentos.html             ← despesas avulsas
  lancamentosAssinaturas.html  ← despesas fixas/assinaturas
  lancamentosReceita.html      ← receitas avulsas + receitas fixas
  lancamentosCartao.html       ← cadastro de cartões
  lancamentosConta.html        ← cadastro de contas
  lancamentosCategorias.html   ← categorias de despesa e receita
  projecoes.html               ← projeção dos próximos 6 meses
  visaoGeral.html              ← gráficos históricos + faturas por cartão
```

---

## Banco de dados — Schema completo

```sql
usuarios (
  id         INTEGER PK AUTOINCREMENT,
  nome       TEXT    NOT NULL,
  email      TEXT    UNIQUE NOT NULL,
  senha_hash TEXT    NOT NULL,          -- werkzeug pbkdf2:sha256
  role       TEXT    DEFAULT 'user',    -- 'user' | 'admin'
  criado_em  DATE    DEFAULT (DATE('now')),
  ativo      INTEGER DEFAULT 1
)

transacoes (
  id               INTEGER PK,
  user_id          INTEGER NOT NULL → usuarios.id,
  tipo             TEXT    -- 'despesa' | 'receita'
  descricao        TEXT,
  valor            REAL,   -- valor TOTAL (parcela = valor/parcelas)
  categoria        TEXT,   -- '_rf_{id}' = gerada por receita fixa; '_df_{id}' = por despesa fixa
  id_cartao        INTEGER → cartoes.id,
  id_conta         INTEGER → contas.id,
  tipo_receita     TEXT    DEFAULT 'avulsa',    -- 'avulsa' | 'fixa'
  tipo_cobranca    TEXT    DEFAULT 'avulsa',    -- 'avulsa' | 'fixa'
  dia_vencimento   INTEGER,
  tipo_compra      TEXT    DEFAULT 'credito',   -- 'credito' | 'debito'
  pagamento        TEXT    DEFAULT 'avista',    -- 'avista' | 'parcelado'
  parcelas         INTEGER,
  data_lancamento  DATE
)

categorias (
  id      INTEGER PK,
  user_id INTEGER NOT NULL,
  nome    TEXT,
  tipo    TEXT    -- 'despesa' | 'receita'
  -- índice: UNIQUE(user_id, nome)
)

contas (
  id      INTEGER PK,
  user_id INTEGER NOT NULL,
  nome    TEXT,
  saldo   REAL DEFAULT 0
  -- índice: UNIQUE(user_id, nome)
)

cartoes (
  id               INTEGER PK,
  user_id          INTEGER NOT NULL,
  nome             TEXT,
  conta            INTEGER → contas.id,
  tipo_pagamento   TEXT    -- 'credito' | 'debito' | 'multiplo'
  data_vencimento  INTEGER,   -- dia do mês (1-31)
  dias_fechamento  INTEGER,   -- dias antes do vencimento que a fatura fecha
  limite           REAL DEFAULT 0
)

receitas_fixas (
  id        INTEGER PK,
  user_id   INTEGER NOT NULL,
  descricao TEXT,
  valor     REAL,
  categoria TEXT,
  id_conta  INTEGER → contas.id,
  dia_mes   INTEGER DEFAULT 1,
  modo_dia  TEXT    DEFAULT 'fixo',  -- 'fixo' | 'primeiro_util' | 'ultimo_util'
  ativa     INTEGER DEFAULT 1
)

despesas_fixas (
  id        INTEGER PK,
  user_id   INTEGER NOT NULL,
  descricao TEXT,
  valor     REAL,
  categoria TEXT,
  id_cartao INTEGER → cartoes.id,   -- se cobrado no cartão de crédito
  id_conta  INTEGER → contas.id,    -- se débito direto em conta
  dia_mes   INTEGER DEFAULT 1,
  modo_dia  TEXT    DEFAULT 'fixo',
  ativa     INTEGER DEFAULT 1
)
```

---

## Regras de negócio críticas

### Autenticação
- Sessão via `flask.session` com `SECRET_KEY`, expira em 8h
- Todas as rotas protegidas por `@login_required`; admin por `@admin_required`
- `uid()` retorna `session.get('user_id')` — usar `uid() or 0` dentro de funções fora de request
- `criar_categorias_padrao(user_id)` chamada no cadastro E no login (cria só se usuário não tiver nenhuma)

### Isolamento de dados
- Toda query tem `WHERE user_id = ?` ou `AND user_id = ?`
- Funções `gerar_ocorrencias_*` aceitam `user_id=None` (processa todos) ou `user_id=uid()` (só o logado)

### Saldo das contas
- **Receita avulsa** → credita imediatamente
- **Receita fixa** → NÃO credita ao cadastrar; `gerar_ocorrencias_receitas_fixas()` cria a transação e credita no dia agendado
- **Despesa débito** → debita imediatamente
- **Despesa crédito** → não mexe no saldo (vai para fatura)
- Chave de idempotência: `categoria = '_rf_{id}'` ou `'_df_{id}'` + mês evita duplicatas

### Cálculo de parcelas — CRÍTICO
- `valor` em `transacoes` = valor TOTAL da compra, nunca da parcela
- Parcela N cai no mês `data_lancamento + N meses` (via `relativedelta`)
- `valor_parcela_na_fatura(valor_total, parcelas, data_compra, inicio, fim)` — comparação por mês/ano, não data exata
- Para somar despesas de um mês: usar `despesas_reais_mes(ano, mes, conn)` — nunca `SUM(valor)` diretamente

### Cálculo de fatura
```python
periodo_fatura_atual(dia_vencimento, dias_fechamento)
# → (inicio, fim, data_vencimento) da fatura ABERTA
# Fatura fecha `dias_fechamento` dias antes do vencimento
# Compra no dia do fechamento → entra na PRÓXIMA fatura
```

### Disponível no Mês
```
Disponível = Saldo atual + Receitas fixas pendentes - Fatura crédito atual
```
- Receitas fixas pendentes = fixas cuja data de ocorrência ainda não chegou neste mês

### Dias úteis (modo_dia)
```python
FERIADOS_FIXOS_BR = {(1,1),(4,21),(5,1),(9,7),(10,12),(11,2),(11,15),(12,25)}
# 'fixo' → dia_mes exato; 'primeiro_util' → 1º seg-sex sem feriado; 'ultimo_util' → idem
```

---

## APIs disponíveis (todas POST com JSON exceto GETs)

### Auth
| Rota | Método | Descrição |
|------|--------|-----------|
| `/login` | GET/POST | Login; cria sessão |
| `/cadastro` | GET/POST | Cadastro; cria categorias padrão |
| `/logout` | GET | Destrói sessão |
| `/admin` | GET | Painel admin (role=admin) |
| `/api/admin/usuario/<id>` | POST | `{acao: ativar\|desativar\|promover\|rebaixar\|resetar_senha}` |
| `/api/minha_conta` | POST | `{nome, senha_atual, nova_senha}` |

### Contas
| Rota | Descrição |
|------|-----------|
| GET `/api/contas` | Lista com saldo |
| POST `/api/adicionar_conta` | `{nome}` |
| POST `/api/remover_conta` | `{id}` |
| POST `/api/atualizar_conta` | `{id, nome}` |

### Cartões
| Rota | Descrição |
|------|-----------|
| GET `/api/cartoes_disponiveis` | Lista com tipo |
| POST `/api/adicionar_cartao` | `{nome, conta, tipo_pagamento, data_vencimento, dias_fechamento, limite}` |
| POST `/api/remover_cartao` | `{id}` |
| POST `/api/atualizar_cartao` | `{id, nome, limite, data_vencimento, dias_fechamento}` |
| GET `/api/fatura/<cartao_id>` | Detalhe da fatura atual |

### Categorias
| Rota | Descrição |
|------|-----------|
| GET `/api/categorias?tipo=despesa\|receita` | Lista |
| POST `/api/adicionar_categoria` | `{nome, tipo}` |
| POST `/api/remover_categoria` | `{id}` |
| POST `/api/atualizar_categoria` | `{id, nome}` |

### Lançamentos
| Rota | Descrição |
|------|-----------|
| POST `/api/adicionar_lancamento` | `{descricao, tipo, valor, categoria, data, pagamento, parcelas, id_cartao, tipo_compra, tipo_cobranca}` |
| POST `/api/remover_lancamento` | `{id}` — reverte saldo |
| POST `/api/atualizar_lancamento` | `{id, descricao, categoria, data, valor, parcelas}` |

### Receitas Fixas
| Rota | Descrição |
|------|-----------|
| GET `/api/receitas_fixas` | Lista |
| POST `/api/adicionar_receita_fixa` | `{descricao, valor, categoria, id_conta, dia_mes, modo_dia}` |
| POST `/api/remover_receita_fixa` | `{id}` |
| POST `/api/pausar_receita_fixa` | `{id, ativa: 0\|1}` |
| POST `/api/atualizar_receita_fixa` | `{id, descricao, categoria, valor, dia_mes, modo_dia}` |

### Despesas Fixas (Assinaturas)
| Rota | Descrição |
|------|-----------|
| GET `/api/despesas_fixas` | Lista |
| POST `/api/adicionar_despesa_fixa` | `{descricao, valor, categoria, id_cartao, id_conta, dia_mes, modo_dia}` |
| POST `/api/remover_despesa_fixa` | `{id}` |
| POST `/api/pausar_despesa_fixa` | `{id, ativa: 0\|1}` |
| POST `/api/atualizar_despesa_fixa` | `{id, descricao, categoria, valor, dia_mes, modo_dia}` |

### Dashboard
| Rota | Descrição |
|------|-----------|
| GET `/api/dashboard_data` | Saldo, fatura, disponível, receitas do mês |
| GET `/api/dashboard_cartao/<id>` | Dashboard filtrado por cartão |

---

## Frontend — TabelaManager (tabela-utils.js v6)

Filtros como **chips** acima da tabela (estilo Shopify):
- Botão `+ Filtro` abre painel com campos à esquerda e operadores+valor à direita
- Operadores por tipo: texto livre (contém/não contém/é/não é/tem valor), select (é/não é), número (=/≠/>/</entre), data (é/antes/depois/entre)
- Cada filtro vira um chip clicável; `×` remove

```javascript
const tm = new TabelaManager({
    tbody, thead, toolbar, selLinhas, ulPag, infoSpan,
    colunas: [
        { chave: 'descricao', tipo: 'texto',  label: 'Descrição'            },  // busca livre
        { chave: 'categoria', tipo: 'texto',  label: 'Categoria', opcoes:true }, // select
        { chave: 'valor',     tipo: 'numero', label: 'Valor'                },  // De/Até
        { chave: 'data',      tipo: 'data',   label: 'Data'                 },  // date range
        { chave: 'acoes',     tipo: 'acoes',  label: 'Ações'                },  // sem filtro
    ],
    onEditar: (meta, tr) => { /* abre EditorPanel */ }  // opcional
});
tm.adicionar(tr, { descricao: '...', categoria: '...', valor: 150.0, data: '2026-04-10' });
tm.remover(tr);
tm.atualizar(tr, novaMeta);
```

## Frontend — EditorPanel (editar-utils.js)

**BUG CONHECIDO — NÃO CORRIGIDO:** `bootstrap is not defined` ao carregar o arquivo.
**Causa:** `editar-utils.js` é carregado antes do Bootstrap JS, então `new bootstrap.Offcanvas()` falha.
**Correção necessária:** mover a inicialização do Offcanvas para dentro do método `abrir()` em vez do construtor.

```javascript
// Padrão de uso (quando corrigido):
const editor = new EditorPanel('meuEditor');
editor.abrir({
    titulo: 'Editar Conta',
    campos: [
        { chave: 'nome', tipo: 'text', label: 'Nome', valor: meta.nome, required: true },
    ],
    onSalvar: (dados) => apiAtualizar('/api/atualizar_conta', { id: tr.dataset.id, nome: dados.nome })
        .then(ok => { if (ok) { pag.remover(tr); addConta(tr.dataset.id, dados.nome, meta.saldo); } return ok; })
});
```

---

## Estrutura visual (padrão em todos os HTMLs)

```html
<header style="background:#1A4D2E">  <!-- logo + nav + nome usuário + botão Sair -->
<div class="page-wrapper">           <!-- display:flex, min-height:calc(100vh - 98px) -->
    <nav class="sidebar-nav bg-dark"> <!-- 200px fixo; links: Despesas|Assinaturas|Receitas|Contas|Cartões|Categorias -->
    <div class="sidebar-content">     <!-- flex:1, padding:1.5rem -->
```

Cabeçalho de tabela: `<thead class="thead-fin" id="theadXxx">` — fundo `#1A4D2E`, branco, uppercase 11px.

---

## Pendente / Bugs conhecidos

- [ ] **`editar-utils.js` — `bootstrap is not defined`** — mover `new bootstrap.Offcanvas(el)` do `_construir()` para o `abrir()`. Enquanto isso, a funcionalidade de edição clicando na linha não funciona.
- [ ] **Exportação de tabelas** para CSV/Excel
- [ ] **Filtro por período no dashboard** — selecionar mês/ano nos cards
- [ ] **Feriados móveis** (Carnaval, Páscoa) no cálculo de dias úteis

---

## Como iniciar nova conversa

Cole este arquivo e diga:
> "Continuando o projeto de controle de finanças. [descreva o que quer fazer]."

Se for mexer em um arquivo específico, cole também o conteúdo atual desse arquivo.

## Divisão Claude / Gemini

**Claude:** lógica de negócio, bugs, novas funcionalidades, arquitetura
**Gemini:** tarefas mecânicas — "Leia o CONTEXTO.md. Adicione X em todos os HTMLs", substituições simples, formatação
