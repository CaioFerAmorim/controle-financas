/**
 * TabelaManager v2
 * - Clicar no nome da coluna: ordena (asc → desc → original)
 * - Select inline no <th>: filtra por aquela coluna (só colunas com opcoes:true)
 * - Toolbar: só busca global + botão "Limpar filtros"
 * - Paginação e info de registros
 *
 * Uso:
 *   const tm = new TabelaManager({ tbody, thead, toolbar, selLinhas, ulPag, infoSpan, colunas });
 *   tm.adicionar(tr, { campo1: valor1, campo2: valor2, ... });
 *   tm.remover(tr);
 *
 * Colunas:
 *   { chave: 'nome', tipo: 'texto'|'numero'|'data'|'acoes', label: 'Label', opcoes: true|false }
 *   opcoes:true → cria select de filtro inline no <th> daquela coluna
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

        this.itens       = [];
        this.pag         = 1;
        this.sortCol     = null;
        this.sortDir     = 'asc';
        this.filtroTexto = '';
        this.filtrosCols = {};

        this._inputBusca = null;
        this._btnLimpar  = null;

        this._construirToolbar();
        this._construirCabecalho();

        this.selLinhas?.addEventListener('change', () => { this.pag = 1; this._render(); });
    }

    // ════════════════════════════════════════════════════════
    // API pública
    // ════════════════════════════════════════════════════════

    adicionar(tr, meta) {
        this.itens.push({ tr, meta });
        this.tbody.appendChild(tr);
        this._atualizarSelects(meta);
        this._render();
    }

    remover(tr) {
        this.itens = this.itens.filter(i => i.tr !== tr);
        tr.remove();
        this._render();
    }

    contar() { return this.itens.length; }

    // ════════════════════════════════════════════════════════
    // Toolbar: busca global + botão limpar
    // ════════════════════════════════════════════════════════

    _construirToolbar() {
        if (!this.toolbar) return;
        this.toolbar.innerHTML = '';
        this.toolbar.className = 'd-flex align-items-center gap-2 mb-2';

        // Campo de busca global
        const wBusca = document.createElement('div');
        wBusca.className = 'input-group input-group-sm';
        wBusca.style.width = '210px';
        wBusca.innerHTML =
            '<span class="input-group-text bg-white" style="border-right:none;padding:0 8px;">' +
              '<svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" style="opacity:.5">' +
                '<path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398l3.85 3.85a1 1 0 0 0 1.415-1.415l-3.85-3.85zm-5.242 1.107a5 5 0 1 1 0-10 5 5 0 0 1 0 10z"/>' +
              '</svg>' +
            '</span>' +
            '<input type="text" class="form-control form-control-sm" placeholder="Buscar em tudo..." ' +
              'style="border-left:none;" id="tmbusca_' + this.tbody.id + '">';
        this.toolbar.appendChild(wBusca);

        this._inputBusca = wBusca.querySelector('input');
        this._inputBusca.addEventListener('input', () => {
            this.filtroTexto = this._inputBusca.value.toLowerCase().trim();
            this.pag = 1;
            this._atualizarBtnLimpar();
            this._render();
        });

        // Botão limpar (fica oculto quando não há filtro)
        this._btnLimpar = document.createElement('button');
        this._btnLimpar.className = 'btn btn-sm btn-outline-secondary';
        this._btnLimpar.style.display = 'none';
        this._btnLimpar.innerHTML = '&times; Limpar filtros';
        this._btnLimpar.addEventListener('click', () => this._limparTudo());
        this.toolbar.appendChild(this._btnLimpar);
    }

    _limparTudo() {
        this.filtroTexto = '';
        this.sortCol     = null;
        this.sortDir     = 'asc';

        if (this._inputBusca) this._inputBusca.value = '';

        Object.keys(this.filtrosCols).forEach(k => { this.filtrosCols[k] = ''; });
        if (this.thead) {
            this.thead.querySelectorAll('select.tm-filter').forEach(s => { s.value = ''; });
        }

        this._atualizarIconesSort();
        this._atualizarBtnLimpar();
        this.pag = 1;
        this._render();
    }

    _atualizarBtnLimpar() {
        if (!this._btnLimpar) return;
        const ativo = this.filtroTexto ||
            this.sortCol !== null ||
            Object.values(this.filtrosCols).some(v => v);
        this._btnLimpar.style.display = ativo ? '' : 'none';
    }

    // ════════════════════════════════════════════════════════
    // Cabeçalho: sort label + select inline por coluna
    // ════════════════════════════════════════════════════════

    _construirCabecalho() {
        if (!this.thead) return;
        const ths = this.thead.querySelectorAll('th');

        ths.forEach((th, i) => {
            const col = this.colunas[i];
            if (!col || col.tipo === 'acoes') return;

            const labelOriginal = th.textContent.trim();
            th.innerHTML = '';
            th.style.verticalAlign = 'top';

            // Label clicável para sort
            const sortWrap = document.createElement('div');
            sortWrap.style.cssText = 'display:flex;align-items:center;gap:5px;cursor:pointer;user-select:none;padding-bottom:4px;white-space:nowrap;';
            sortWrap.innerHTML =
                '<span>' + labelOriginal + '</span>' +
                '<span class="tm-sort-ico" style="font-size:9px;opacity:.4;letter-spacing:-1px;transition:opacity .15s;">⇅</span>';
            sortWrap.addEventListener('click', () => this._toggleSort(col.chave));
            th.appendChild(sortWrap);

            // Select inline (só se opcoes=true)
            if (col.opcoes) {
                this.filtrosCols[col.chave] = '';

                const sel = document.createElement('select');
                sel.className = 'tm-filter';
                sel.dataset.chave = col.chave;
                // Estilo para o select dentro do thead escuro
                sel.style.cssText = [
                    'font-size:10px',
                    'padding:2px 20px 2px 5px',
                    'height:22px',
                    'line-height:1',
                    'background-color:rgba(255,255,255,.13)',
                    'color:#fff',
                    'border:1px solid rgba(255,255,255,.3)',
                    'border-radius:4px',
                    'min-width:70px',
                    'max-width:130px',
                    'width:100%',
                    'appearance:auto',
                    '-webkit-appearance:auto',
                    'cursor:pointer',
                ].join(';');
                sel.innerHTML = '<option value="" style="color:#000;background:#fff;">Todos</option>';

                sel.addEventListener('change', () => {
                    this.filtrosCols[col.chave] = sel.value;
                    this.pag = 1;
                    this._atualizarBtnLimpar();
                    this._render();
                });

                th.appendChild(sel);
            }
        });
    }

    // ════════════════════════════════════════════════════════
    // Sort
    // ════════════════════════════════════════════════════════

    _toggleSort(chave) {
        if (this.sortCol === chave) {
            if (this.sortDir === 'asc') {
                this.sortDir = 'desc';
            } else {
                this.sortCol = null;
                this.sortDir = 'asc';
            }
        } else {
            this.sortCol = chave;
            this.sortDir = 'asc';
        }
        this._atualizarIconesSort();
        this._atualizarBtnLimpar();
        this.pag = 1;
        this._render();
    }

    _atualizarIconesSort() {
        if (!this.thead) return;
        const icos = this.thead.querySelectorAll('.tm-sort-ico');
        icos.forEach((ico, i) => {
            const col = this.colunas[i];
            if (!col || col.tipo === 'acoes') return;
            if (col.chave === this.sortCol) {
                ico.textContent = this.sortDir === 'asc' ? ' ↑' : ' ↓';
                ico.style.opacity = '1';
            } else {
                ico.textContent = '⇅';
                ico.style.opacity = '.4';
            }
        });
    }

    // ════════════════════════════════════════════════════════
    // Atualiza opções dos selects ao adicionar nova linha
    // ════════════════════════════════════════════════════════

    _atualizarSelects(meta) {
        if (!this.thead) return;
        this.thead.querySelectorAll('select.tm-filter').forEach(sel => {
            const chave = sel.dataset.chave;
            const val   = String(meta[chave] ?? '').trim();
            if (!val) return;

            const jaExiste = [...sel.options].some(o => o.value === val);
            if (jaExiste) return;

            // Recolhe, adiciona e reordena as opções
            const valorAtual = sel.value;
            const opcoes = [...sel.options]
                .slice(1)
                .map(o => o.value)
                .concat(val)
                .sort((a, b) => a.localeCompare(b, 'pt', { sensitivity: 'base' }));

            sel.innerHTML = '<option value="" style="color:#000;background:#fff;">Todos</option>';
            opcoes.forEach(v => {
                const o = document.createElement('option');
                o.value = v;
                o.textContent = v;
                o.style.cssText = 'color:#000;background:#fff;';
                sel.appendChild(o);
            });
            sel.value = valorAtual;
        });
    }

    // ════════════════════════════════════════════════════════
    // Filtragem
    // ════════════════════════════════════════════════════════

    _filtrados() {
        return this.itens.filter(({ meta }) => {
            // Busca global
            if (this.filtroTexto) {
                const tudo = Object.values(meta).join(' ').toLowerCase();
                if (!tudo.includes(this.filtroTexto)) return false;
            }
            // Filtros por coluna
            for (const [chave, val] of Object.entries(this.filtrosCols)) {
                if (!val) continue;
                const mv = String(meta[chave] ?? '').toLowerCase();
                if (mv !== val.toLowerCase()) return false;
            }
            return true;
        });
    }

    // ════════════════════════════════════════════════════════
    // Ordenação
    // ════════════════════════════════════════════════════════

    _ordenados(lista) {
        if (!this.sortCol) return lista;
        const col  = this.colunas.find(c => c.chave === this.sortCol);
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
                va = String(va || '');
                vb = String(vb || '');
                return this.sortDir === 'asc'
                    ? va.localeCompare(vb)
                    : vb.localeCompare(va);
            }
            // texto (padrão)
            va = String(va ?? '').toLowerCase();
            vb = String(vb ?? '').toLowerCase();
            return this.sortDir === 'asc'
                ? va.localeCompare(vb, 'pt', { sensitivity: 'base' })
                : vb.localeCompare(va, 'pt', { sensitivity: 'base' });
        });
    }

    // ════════════════════════════════════════════════════════
    // Render + paginação
    // ════════════════════════════════════════════════════════

    _ipp() { return this.selLinhas ? parseInt(this.selLinhas.value) : 10; }

    _render() {
        const filtrados = this._filtrados();
        const ordenados = this._ordenados(filtrados);
        const total  = ordenados.length;
        const ipp    = this._ipp();
        const tp     = Math.max(1, Math.ceil(total / ipp));
        this.pag     = Math.min(this.pag, tp);
        const ini    = (this.pag - 1) * ipp;
        const fim    = Math.min(ini + ipp, total);

        // Oculta tudo e reordena no DOM só os visíveis
        this.itens.forEach(({ tr }) => { tr.style.display = 'none'; });
        ordenados.slice(ini, fim).forEach(({ tr }) => {
            tr.style.display = '';
            this.tbody.appendChild(tr);
        });

        // Info
        if (this.infoSpan) {
            if (total === 0) {
                this.infoSpan.textContent = this.itens.length === 0
                    ? 'Nenhum registro'
                    : 'Nenhum resultado para os filtros aplicados';
            } else {
                const sufixo = total < this.itens.length
                    ? ' (total: ' + this.itens.length + ')'
                    : '';
                this.infoSpan.textContent =
                    'Mostrando ' + (ini + 1) + '\u2013' + fim + ' de ' + total + sufixo;
            }
        }

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

        add('«', 1,           this.pag === 1);
        add('‹', this.pag - 1, this.pag === 1);
        for (let p = b; p <= e; p++) add(p, p, false, p === this.pag);
        add('›', this.pag + 1, this.pag === tp);
        add('»', tp,           this.pag === tp);
    }
}
