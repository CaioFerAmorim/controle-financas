/**
 * TabelaManager — sort, filtro global, filtro por coluna e paginação.
 *
 * Uso:
 *   const tm = new TabelaManager({
 *     tbody:      document.getElementById('minhaTabela'),
 *     thead:      document.getElementById('minhaCabecalho'),
 *     toolbar:    document.getElementById('minhaToolbar'),
 *     selLinhas:  document.getElementById('ipp'),
 *     ulPag:      document.getElementById('pag'),
 *     infoSpan:   document.getElementById('info'),
 *     colunas: [
 *       { chave: 'descricao', tipo: 'texto',   label: 'Descrição',  filtro: true },
 *       { chave: 'valor',     tipo: 'numero',  label: 'Valor',      filtro: false },
 *       { chave: 'categoria', tipo: 'texto',   label: 'Categoria',  filtro: true, opcoes: true },
 *       { chave: 'data',      tipo: 'data',    label: 'Data',       filtro: false },
 *       { chave: 'acoes',     tipo: 'acoes',   label: 'Ações',      filtro: false },
 *     ]
 *   });
 *
 *   // Ao adicionar uma linha passe o <tr> e os metadados:
 *   tm.adicionar(tr, { descricao: 'Mercado', valor: 150.00, categoria: 'Alimentação', data: '2026-04-10' });
 *   tm.remover(tr);
 */
class TabelaManager {
    constructor({ tbody, thead, toolbar, selLinhas, ulPag, infoSpan, colunas }) {
        this.tbody     = tbody;
        this.thead     = thead;
        this.toolbar   = toolbar;
        this.selLinhas = selLinhas;
        this.ulPag     = ulPag;
        this.infoSpan  = infoSpan;
        this.colunas   = colunas;

        // Estado interno
        this.itens    = [];          // { tr, meta }
        this.pag      = 1;
        this.sortCol  = null;
        this.sortDir  = 'asc';
        this.filtroTexto  = '';
        this.filtrosCols  = {};      // chave → valor selecionado

        this._construirCabecalho();
        this._construirToolbar();

        this.selLinhas?.addEventListener('change', () => { this.pag = 1; this._render(); });
    }

    // ── API pública ──────────────────────────────────────────────

    adicionar(tr, meta) {
        this.itens.push({ tr, meta });
        this.tbody.appendChild(tr);
        this._atualizarOpcoesDropdowns(meta);
        this._render();
    }

    remover(tr) {
        this.itens = this.itens.filter(i => i.tr !== tr);
        tr.remove();
        this._render();
    }

    limpar() {
        this.itens.forEach(i => i.tr.remove());
        this.itens = [];
        this._render();
    }

    contar() { return this.itens.length; }

    // ── Construção do cabeçalho com sort ─────────────────────────

    _construirCabecalho() {
        if (!this.thead) return;
        const ths = this.thead.querySelectorAll('th');
        ths.forEach((th, i) => {
            const col = this.colunas[i];
            if (!col || col.tipo === 'acoes') return;

            th.style.cursor = 'pointer';
            th.style.userSelect = 'none';
            th.style.whiteSpace = 'nowrap';

            // Ícone de sort
            const ico = document.createElement('span');
            ico.className = 'sort-ico ms-1';
            ico.style.opacity = '0.5';
            ico.style.fontSize = '10px';
            ico.textContent = '⇅';
            th.appendChild(ico);
            th.dataset.sortCol = col.chave;

            th.addEventListener('click', () => this._toggleSort(col.chave));
        });
    }

    _toggleSort(chave) {
        if (this.sortCol === chave) {
            if (this.sortDir === 'asc') this.sortDir = 'desc';
            else { this.sortCol = null; this.sortDir = 'asc'; }
        } else {
            this.sortCol = chave;
            this.sortDir = 'asc';
        }
        this._atualizarIconesSort();
        this.pag = 1;
        this._render();
    }

    _atualizarIconesSort() {
        if (!this.thead) return;
        this.thead.querySelectorAll('th[data-sort-col]').forEach(th => {
            const ico = th.querySelector('.sort-ico');
            if (!ico) return;
            if (th.dataset.sortCol === this.sortCol) {
                ico.textContent = this.sortDir === 'asc' ? '↑' : '↓';
                ico.style.opacity = '1';
            } else {
                ico.textContent = '⇅';
                ico.style.opacity = '0.5';
            }
        });
    }

    // ── Construção da toolbar (filtros) ──────────────────────────

    _construirToolbar() {
        if (!this.toolbar) return;
        this.toolbar.innerHTML = '';
        this.toolbar.className = 'table-toolbar d-flex flex-wrap gap-2 align-items-center mb-2';

        // Busca global
        const wrapBusca = document.createElement('div');
        wrapBusca.className = 'input-group input-group-sm';
        wrapBusca.style.width = '200px';
        wrapBusca.innerHTML =
            '<span class="input-group-text bg-light"><i>🔍</i></span>' +
            '<input type="text" class="form-control" placeholder="Buscar em tudo..." id="filtroGlobal_' + this.tbody.id + '">';
        this.toolbar.appendChild(wrapBusca);

        const inputGlobal = wrapBusca.querySelector('input');
        inputGlobal.addEventListener('input', () => {
            this.filtroTexto = inputGlobal.value.toLowerCase().trim();
            this.pag = 1;
            this._render();
        });

        // Dropdowns por coluna com opcoes=true
        this.colunas.forEach(col => {
            if (!col.opcoes) return;
            const wrap = document.createElement('div');
            wrap.className = 'input-group input-group-sm';
            wrap.style.width = '160px';

            const lbl = document.createElement('span');
            lbl.className = 'input-group-text bg-light small';
            lbl.textContent = col.label;

            const sel = document.createElement('select');
            sel.className = 'form-select form-select-sm';
            sel.dataset.chave = col.chave;
            sel.innerHTML = '<option value="">Todos</option>';
            this.filtrosCols[col.chave] = '';

            sel.addEventListener('change', () => {
                this.filtrosCols[col.chave] = sel.value;
                this.pag = 1;
                this._render();
            });

            wrap.appendChild(lbl);
            wrap.appendChild(sel);
            this.toolbar.appendChild(wrap);
        });

        // Botão limpar filtros
        const btnLimpar = document.createElement('button');
        btnLimpar.className = 'btn btn-sm btn-outline-secondary';
        btnLimpar.textContent = '✕ Limpar';
        btnLimpar.title = 'Limpar todos os filtros';
        btnLimpar.addEventListener('click', () => this._limparFiltros(inputGlobal));
        this.toolbar.appendChild(btnLimpar);
    }

    _limparFiltros(inputGlobal) {
        this.filtroTexto = '';
        if (inputGlobal) inputGlobal.value = '';
        Object.keys(this.filtrosCols).forEach(k => { this.filtrosCols[k] = ''; });
        if (this.toolbar) {
            this.toolbar.querySelectorAll('select').forEach(s => s.value = '');
        }
        this.pag = 1;
        this._render();
    }

    _atualizarOpcoesDropdowns(meta) {
        if (!this.toolbar) return;
        this.toolbar.querySelectorAll('select[data-chave]').forEach(sel => {
            const chave = sel.dataset.chave;
            const val   = String(meta[chave] || '');
            if (!val) return;
            const jaExiste = [...sel.options].some(o => o.value === val);
            if (!jaExiste) {
                const opt = document.createElement('option');
                opt.value = val; opt.textContent = val;
                // Insere ordenado
                const opcoes = [...sel.options].slice(1).map(o => o.value);
                opcoes.push(val);
                opcoes.sort((a, b) => a.localeCompare(b, 'pt'));
                sel.innerHTML = '<option value="">Todos</option>';
                opcoes.forEach(v => {
                    const o = document.createElement('option');
                    o.value = v; o.textContent = v;
                    sel.appendChild(o);
                });
            }
        });
    }

    // ── Filtragem ────────────────────────────────────────────────

    _filtrados() {
        return this.itens.filter(({ meta }) => {
            // Filtro de texto global: busca em todos os campos de texto
            if (this.filtroTexto) {
                const tudo = Object.values(meta).join(' ').toLowerCase();
                if (!tudo.includes(this.filtroTexto)) return false;
            }
            // Filtros por coluna
            for (const [chave, val] of Object.entries(this.filtrosCols)) {
                if (!val) continue;
                const metaVal = String(meta[chave] || '').toLowerCase();
                if (metaVal !== val.toLowerCase()) return false;
            }
            return true;
        });
    }

    // ── Ordenação ────────────────────────────────────────────────

    _ordenados(lista) {
        if (!this.sortCol) return lista;
        const col = this.colunas.find(c => c.chave === this.sortCol);
        const tipo = col?.tipo || 'texto';
        return [...lista].sort((a, b) => {
            let va = a.meta[this.sortCol];
            let vb = b.meta[this.sortCol];
            if (tipo === 'numero') {
                va = parseFloat(va) || 0;
                vb = parseFloat(vb) || 0;
                return this.sortDir === 'asc' ? va - vb : vb - va;
            }
            if (tipo === 'data') {
                va = va || ''; vb = vb || '';
                return this.sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
            }
            va = String(va || '').toLowerCase();
            vb = String(vb || '').toLowerCase();
            return this.sortDir === 'asc' ? va.localeCompare(vb, 'pt') : vb.localeCompare(va, 'pt');
        });
    }

    // ── Paginação e render ───────────────────────────────────────

    _ipp() { return this.selLinhas ? parseInt(this.selLinhas.value) : 10; }

    _render() {
        const filtrados = this._filtrados();
        const ordenados = this._ordenados(filtrados);
        const total = ordenados.length;
        const ipp   = this._ipp();
        const tp    = Math.max(1, Math.ceil(total / ipp));
        this.pag    = Math.min(this.pag, tp);
        const ini   = (this.pag - 1) * ipp;
        const fim   = Math.min(ini + ipp, total);

        // Mostra/oculta linhas na ordem correta
        this.itens.forEach(i => { i.tr.style.display = 'none'; });
        ordenados.slice(ini, fim).forEach(({ tr }) => {
            tr.style.display = '';
            this.tbody.appendChild(tr); // reordena no DOM
        });

        // Info
        if (this.infoSpan) {
            this.infoSpan.textContent = total === 0
                ? 'Nenhum registro'
                : `Mostrando ${ini + 1}–${fim} de ${total}` +
                  (total < this.itens.length ? ` (${this.itens.length} no total)` : '');
        }

        // Paginação
        if (this.ulPag) this._renderPag(tp);
    }

    _renderPag(tp) {
        this.ulPag.innerHTML = '';
        if (tp <= 1) return;
        let b = Math.max(1, this.pag - 2);
        let e = Math.min(tp, b + 4);
        if (e - b < 4) b = Math.max(1, e - 4);

        const add = (lbl, p, dis, act) => {
            const li = document.createElement('li');
            li.className = 'page-item' + (dis ? ' disabled' : '') + (act ? ' active' : '');
            li.innerHTML = '<button class="page-link">' + lbl + '</button>';
            if (!dis && !act) li.querySelector('button').onclick = () => { this.pag = p; this._render(); };
            this.ulPag.appendChild(li);
        };
        add('«', 1, this.pag === 1);
        add('‹', this.pag - 1, this.pag === 1);
        for (let p = b; p <= e; p++) add(p, p, false, p === this.pag);
        add('›', this.pag + 1, this.pag === tp);
        add('»', tp, this.pag === tp);
    }
}
