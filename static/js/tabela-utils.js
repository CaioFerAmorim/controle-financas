/**
 * TabelaManager v4
 * Todos os filtros ficam inline no <th> — sem toolbar separada.
 *
 * Tipos de coluna e filtro gerado:
 *   tipo:'texto'  + opcoes:true  → <select> com valores únicos
 *   tipo:'texto'  + opcoes:false → <input text> de busca livre
 *   tipo:'numero'                → dois <input number> (de / até)
 *   tipo:'data'                  → dois <input date> (de / até)
 *   tipo:'acoes'                 → sem filtro
 *
 * toolbar: só o botão "Limpar filtros" + dica de edição
 * onEditar(meta, tr): callback opcional para clique-para-editar
 *
 * API pública:
 *   tm.adicionar(tr, meta)
 *   tm.remover(tr)
 *   tm.atualizar(tr, novaMeta)
 *   tm.contar()
 */
class TabelaManager {
    constructor({ tbody, thead, toolbar, selLinhas, ulPag, infoSpan, colunas, onEditar }) {
        this.tbody     = tbody;
        this.thead     = thead;
        this.toolbar   = toolbar;
        this.selLinhas = selLinhas;
        this.ulPag     = ulPag;
        this.infoSpan  = infoSpan;
        this.colunas   = colunas;
        this.onEditar  = onEditar || null;

        this.itens    = [];
        this.pag      = 1;
        this.sortCol  = null;
        this.sortDir  = 'asc';
        this.filtros  = {};   // chave → { tipo, val, min, max }

        this._btnLimpar = null;

        this._inicializarFiltros();
        this._construirToolbar();
        this._construirCabecalho();

        this.selLinhas?.addEventListener('change', () => { this.pag = 1; this._render(); });
    }

    // ════════════════════════════════════════════════════════
    // Inicialização dos filtros
    // ════════════════════════════════════════════════════════

    _inicializarFiltros() {
        this.colunas.forEach(col => {
            if (col.tipo === 'acoes') return;
            if (col.tipo === 'numero' || col.tipo === 'data') {
                this.filtros[col.chave] = { min: '', max: '' };
            } else {
                this.filtros[col.chave] = { val: '' };
            }
        });
    }

    // ════════════════════════════════════════════════════════
    // Toolbar: só botão limpar + dica
    // ════════════════════════════════════════════════════════

    _construirToolbar() {
        if (!this.toolbar) return;
        this.toolbar.innerHTML = '';
        this.toolbar.className = 'd-flex align-items-center gap-2 mb-2';

        this._btnLimpar = document.createElement('button');
        this._btnLimpar.className = 'btn btn-sm btn-outline-secondary';
        this._btnLimpar.style.display = 'none';
        this._btnLimpar.innerHTML = '&times; Limpar filtros';
        this._btnLimpar.addEventListener('click', () => this._limparTudo());
        this.toolbar.appendChild(this._btnLimpar);

        if (this.onEditar) {
            const dica = document.createElement('small');
            dica.className = 'text-muted';
            dica.style.fontSize = '11px';
            dica.innerHTML =
                '<svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor" class="me-1" style="opacity:.55">' +
                '<path d="M12.146.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1 0 .708l-10 10a.5.5 0 0 1-.168.11l-5 2a.5.5 0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293zm-9.761 5.175-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325z"/>' +
                '</svg>Clique na linha para editar';
            this.toolbar.appendChild(dica);
        }
    }

    _limparTudo() {
        this.sortCol = null;
        this.sortDir = 'asc';
        this._inicializarFiltros();

        if (this.thead) {
            this.thead.querySelectorAll('.tm-filter').forEach(el => { el.value = ''; });
            this._atualizarIconesSort();
        }
        this._atualizarBtnLimpar();
        this.pag = 1;
        this._render();
    }

    _atualizarBtnLimpar() {
        if (!this._btnLimpar) return;
        const ativo = this.sortCol !== null || Object.values(this.filtros).some(f =>
            ('val' in f && f.val) || ('min' in f && (f.min || f.max))
        );
        this._btnLimpar.style.display = ativo ? '' : 'none';
    }

    // ════════════════════════════════════════════════════════
    // Cabeçalho: sort + filtros inline
    // ════════════════════════════════════════════════════════

    // Estilos compartilhados para os elementos de filtro no thead
    _estiloInput() {
        return [
            'font-size:10px', 'height:22px', 'padding:2px 5px', 'line-height:1',
            'background-color:rgba(255,255,255,.13)', 'color:#fff',
            'border:1px solid rgba(255,255,255,.3)', 'border-radius:4px',
            'width:100%', 'min-width:60px', 'box-sizing:border-box',
        ].join(';');
    }

    _estiloSelect() {
        return this._estiloInput() + ';cursor:pointer;';
    }

    _construirCabecalho() {
        if (!this.thead) return;
        const ths = this.thead.querySelectorAll('th');

        ths.forEach((th, i) => {
            const col = this.colunas[i];
            if (!col || col.tipo === 'acoes') return;

            const labelOriginal = th.textContent.trim();
            th.innerHTML = '';
            th.style.verticalAlign = 'top';
            th.style.paddingBottom = '6px';

            // Label com ícone de sort
            const sortWrap = document.createElement('div');
            sortWrap.style.cssText = 'display:flex;align-items:center;gap:4px;cursor:pointer;user-select:none;white-space:nowrap;margin-bottom:5px;';
            sortWrap.innerHTML =
                '<span style="font-size:11px;font-weight:600;">' + labelOriginal + '</span>' +
                '<span class="tm-sort-ico" style="font-size:9px;opacity:.4;transition:opacity .15s;">⇅</span>';
            sortWrap.addEventListener('click', () => this._toggleSort(col.chave));
            th.appendChild(sortWrap);

            // ── Filtro por tipo ──────────────────────────────
            const tipo   = col.tipo   || 'texto';
            const opcoes = col.opcoes || false;

            if (tipo === 'numero') {
                // Dois inputs: de / até
                const wrap = document.createElement('div');
                wrap.style.cssText = 'display:flex;gap:3px;align-items:center;';

                const inputMin = document.createElement('input');
                inputMin.type = 'number'; inputMin.placeholder = 'De';
                inputMin.className = 'tm-filter'; inputMin.dataset.chave = col.chave; inputMin.dataset.lado = 'min';
                inputMin.style.cssText = this._estiloInput() + ';width:50%;';

                const inputMax = document.createElement('input');
                inputMax.type = 'number'; inputMax.placeholder = 'Até';
                inputMax.className = 'tm-filter'; inputMax.dataset.chave = col.chave; inputMax.dataset.lado = 'max';
                inputMax.style.cssText = this._estiloInput() + ';width:50%;';

                [inputMin, inputMax].forEach(inp => {
                    inp.addEventListener('input', () => {
                        this.filtros[col.chave].min = inputMin.value;
                        this.filtros[col.chave].max = inputMax.value;
                        this.pag = 1;
                        this._atualizarBtnLimpar();
                        this._render();
                    });
                });

                wrap.appendChild(inputMin);
                wrap.appendChild(document.createTextNode('–'));
                wrap.appendChild(inputMax);
                th.appendChild(wrap);

            } else if (tipo === 'data') {
                // Dois date pickers: de / até
                const wrap = document.createElement('div');
                wrap.style.cssText = 'display:flex;gap:3px;flex-direction:column;';

                const inputMin = document.createElement('input');
                inputMin.type = 'date'; inputMin.title = 'De';
                inputMin.className = 'tm-filter'; inputMin.dataset.chave = col.chave; inputMin.dataset.lado = 'min';
                inputMin.style.cssText = this._estiloInput() + ';min-width:105px;';

                const inputMax = document.createElement('input');
                inputMax.type = 'date'; inputMax.title = 'Até';
                inputMax.className = 'tm-filter'; inputMax.dataset.chave = col.chave; inputMax.dataset.lado = 'max';
                inputMax.style.cssText = this._estiloInput() + ';min-width:105px;';

                // Hack: força o ícone do date picker para branco
                const style = document.createElement('style');
                style.textContent = 'input.tm-filter[type=date]::-webkit-calendar-picker-indicator{filter:invert(1);opacity:.6;cursor:pointer;}';
                document.head.appendChild(style);

                [inputMin, inputMax].forEach(inp => {
                    inp.addEventListener('change', () => {
                        this.filtros[col.chave].min = inputMin.value;
                        this.filtros[col.chave].max = inputMax.value;
                        this.pag = 1;
                        this._atualizarBtnLimpar();
                        this._render();
                    });
                });

                wrap.appendChild(inputMin);
                wrap.appendChild(inputMax);
                th.appendChild(wrap);

            } else if (opcoes) {
                // Select com valores únicos
                const sel = document.createElement('select');
                sel.className = 'tm-filter';
                sel.dataset.chave = col.chave;
                sel.style.cssText = this._estiloSelect();
                sel.innerHTML = '<option value="" style="color:#000;background:#fff;">Todos</option>';
                sel.addEventListener('change', () => {
                    this.filtros[col.chave].val = sel.value;
                    this.pag = 1;
                    this._atualizarBtnLimpar();
                    this._render();
                });
                th.appendChild(sel);

            } else {
                // Input texto livre (busca parcial)
                const inp = document.createElement('input');
                inp.type = 'text'; inp.placeholder = 'Buscar…';
                inp.className = 'tm-filter';
                inp.dataset.chave = col.chave;
                inp.style.cssText = this._estiloInput();
                inp.addEventListener('input', () => {
                    this.filtros[col.chave].val = inp.value.toLowerCase().trim();
                    this.pag = 1;
                    this._atualizarBtnLimpar();
                    this._render();
                });
                th.appendChild(inp);
            }
        });
    }

    // ════════════════════════════════════════════════════════
    // Sort
    // ════════════════════════════════════════════════════════

    _toggleSort(chave) {
        if (this.sortCol === chave) {
            if (this.sortDir === 'asc') { this.sortDir = 'desc'; }
            else { this.sortCol = null; this.sortDir = 'asc'; }
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
        this.thead.querySelectorAll('.tm-sort-ico').forEach((ico, i) => {
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
    // Selects: atualiza opções dinamicamente
    // ════════════════════════════════════════════════════════

    _atualizarSelects(meta) {
        if (!this.thead) return;
        this.thead.querySelectorAll('select.tm-filter').forEach(sel => {
            const chave = sel.dataset.chave;
            const val   = String(meta[chave] ?? '').trim();
            if (!val || [...sel.options].some(o => o.value === val)) return;

            const atual  = sel.value;
            const opcoes = [...sel.options].slice(1).map(o => o.value)
                .concat(val)
                .sort((a, b) => a.localeCompare(b, 'pt', { sensitivity: 'base' }));

            sel.innerHTML = '<option value="" style="color:#000;background:#fff;">Todos</option>';
            opcoes.forEach(v => {
                const o = document.createElement('option');
                o.value = v; o.textContent = v;
                o.style.cssText = 'color:#000;background:#fff;';
                sel.appendChild(o);
            });
            sel.value = atual;
        });
    }

    // ════════════════════════════════════════════════════════
    // API pública
    // ════════════════════════════════════════════════════════

    adicionar(tr, meta) {
        this.itens.push({ tr, meta });
        this.tbody.appendChild(tr);
        this._atualizarSelects(meta);

        if (this.onEditar) {
            tr.style.cursor = 'pointer';
            tr.title = 'Clique para editar';
            tr.addEventListener('mouseenter', () => { if (!tr._editando) tr.style.background = '#f0f7f0'; });
            tr.addEventListener('mouseleave', () => { if (!tr._editando) tr.style.background = '';       });
            tr.addEventListener('click', (e) => {
                if (e.target.closest('button, a, select, input')) return;
                this.onEditar(meta, tr);
            });
        }

        this._render();
    }

    remover(tr) {
        this.itens = this.itens.filter(i => i.tr !== tr);
        tr.remove();
        this._render();
    }

    atualizar(tr, novaMeta) {
        const item = this.itens.find(i => i.tr === tr);
        if (item) {
            item.meta = novaMeta;
            this._atualizarSelects(novaMeta);
        }
        this._render();
    }

    contar() { return this.itens.length; }

    // ════════════════════════════════════════════════════════
    // Filtragem
    // ════════════════════════════════════════════════════════

    _filtrados() {
        return this.itens.filter(({ meta }) => {
            for (const col of this.colunas) {
                if (col.tipo === 'acoes') continue;
                const f   = this.filtros[col.chave];
                const val = meta[col.chave];

                if (col.tipo === 'numero') {
                    const n = parseFloat(val) || 0;
                    if (f.min !== '' && !isNaN(f.min) && n < parseFloat(f.min)) return false;
                    if (f.max !== '' && !isNaN(f.max) && n > parseFloat(f.max)) return false;
                } else if (col.tipo === 'data') {
                    const d = String(val || '');
                    if (f.min && d && d < f.min) return false;
                    if (f.max && d && d > f.max) return false;
                } else {
                    // texto ou select
                    if (!f.val) continue;
                    const mv = String(val ?? '').toLowerCase();
                    const fv = f.val.toLowerCase();
                    // select (opcoes:true) → match exato; input texto → match parcial
                    if (col.opcoes) {
                        if (mv !== fv) return false;
                    } else {
                        if (!mv.includes(fv)) return false;
                    }
                }
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
            let va = a.meta[this.sortCol], vb = b.meta[this.sortCol];
            if (tipo === 'numero') {
                va = parseFloat(va) || 0; vb = parseFloat(vb) || 0;
                return this.sortDir === 'asc' ? va - vb : vb - va;
            }
            if (tipo === 'data') {
                va = String(va || ''); vb = String(vb || '');
                return this.sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
            }
            va = String(va ?? '').toLowerCase(); vb = String(vb ?? '').toLowerCase();
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
        const total = ordenados.length;
        const ipp   = this._ipp();
        const tp    = Math.max(1, Math.ceil(total / ipp));
        this.pag    = Math.min(this.pag, tp);
        const ini   = (this.pag - 1) * ipp;
        const fim   = Math.min(ini + ipp, total);

        this.itens.forEach(({ tr }) => { tr.style.display = 'none'; });
        ordenados.slice(ini, fim).forEach(({ tr }) => {
            tr.style.display = '';
            this.tbody.appendChild(tr);
        });

        if (this.infoSpan) {
            if (total === 0) {
                this.infoSpan.textContent = this.itens.length === 0
                    ? 'Nenhum registro'
                    : 'Nenhum resultado para os filtros aplicados';
            } else {
                const suf = total < this.itens.length ? ' (total: ' + this.itens.length + ')' : '';
                this.infoSpan.textContent = 'Mostrando ' + (ini + 1) + '–' + fim + ' de ' + total + suf;
            }
        }

        if (this.ulPag) this._renderPag(tp);
    }

    _renderPag(tp) {
        this.ulPag.innerHTML = '';
        if (tp <= 1) return;
        let b = Math.max(1, this.pag - 2), e = Math.min(tp, b + 4);
        if (e - b < 4) b = Math.max(1, e - 4);
        const add = (lbl, p, dis, act) => {
            const li = document.createElement('li');
            li.className = 'page-item' + (dis ? ' disabled' : '') + (act ? ' active' : '');
            li.innerHTML = '<button class="page-link">' + lbl + '</button>';
            if (!dis && !act) li.querySelector('button').onclick = () => { this.pag = p; this._render(); };
            this.ulPag.appendChild(li);
        };
        add('«', 1, this.pag === 1); add('‹', this.pag - 1, this.pag === 1);
        for (let p = b; p <= e; p++) add(p, p, false, p === this.pag);
        add('›', this.pag + 1, this.pag === tp); add('»', tp, this.pag === tp);
    }
}
