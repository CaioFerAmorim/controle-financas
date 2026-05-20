/**
 * TabelaManager v6 — filtros estilo chips (inspirado no design Shopify/Lemon Squeezy)
 *
 * Fluxo de filtro:
 *   1. Usuário clica em "+ Filtro"
 *   2. Painel dropdown abre: lista de campos à esquerda
 *   3. Ao selecionar campo: operadores + input de valor à direita
 *   4. "Aplicar" → filter vira um chip acima da tabela
 *   5. Clicar no chip reabre para editar; "×" remove
 *
 * Operadores por tipo:
 *   texto (livre)  → contém | não contém | é | não é | tem valor
 *   texto (select) → é | não é
 *   numero         → = | ≠ | > | < | entre
 *   data           → é | antes de | depois de | entre
 *
 * Sort: clicar no <th> alterna asc → desc → original
 *
 * API pública:
 *   tm.adicionar(tr, meta)
 *   tm.remover(tr)
 *   tm.atualizar(tr, novaMeta)
 *   tm.contar()
 *   onEditar(meta, tr) — callback opcional
 */
class TabelaManager {
    constructor({ tbody, thead, toolbar, selLinhas, ulPag, infoSpan, colunas, onEditar }) {
        this.tbody     = tbody;
        this.thead     = thead;
        this.toolbar   = toolbar;
        this.selLinhas = selLinhas;
        this.ulPag     = ulPag;
        this.infoSpan  = infoSpan;
        this.colunas   = colunas.filter(c => c.tipo !== 'acoes' || true); // mantém todas
        this.onEditar  = onEditar || null;

        this.itens       = [];
        this.pag         = 1;
        this.sortCol     = null;
        this.sortDir     = 'asc';
        this.filtrosAtivos = [];   // [{ id, chave, op, val, val2 }]
        this._nextFiltroId = 1;

        // Valores únicos por coluna (para selects)
        this._opcoesUnicas = {};
        this.colunas.forEach(c => { this._opcoesUnicas[c.chave] = new Set(); });

        // Elementos do painel
        this._painel      = null;
        this._chipBar     = null;
        this._editandoId  = null;  // id do filtro sendo editado

        this._injetarCSS();
        this._construirToolbar();
        this._construirCabecalho();

        this.selLinhas?.addEventListener('change', () => { this.pag = 1; this._render(); });

        // Fecha painel ao clicar fora
        document.addEventListener('click', (e) => {
            if (this._painel && !this._painel.contains(e.target) &&
                !e.target.closest('.tm-add-btn') && !e.target.closest('.tm-chip')) {
                this._fecharPainel();
            }
        });
    }

    // ════════════════════════════════════════════════════════
    // CSS global (injeta uma vez)
    // ════════════════════════════════════════════════════════

    _injetarCSS() {
        if (document.getElementById('tm-v6-style')) return;
        const s = document.createElement('style');
        s.id = 'tm-v6-style';
        s.textContent = `
/* Chip bar */
.tm-chip-bar {
    display: flex; flex-wrap: wrap; gap: 6px;
    align-items: center; margin-bottom: 10px; min-height: 28px;
}
.tm-chip {
    display: inline-flex; align-items: center; gap: 5px;
    background: var(--blue-50, #f0f4fb); border: 1px solid var(--blue-100, #e8eef8);
    border-radius: 99px; padding: 3px 10px 3px 12px;
    font-size: 12px; cursor: pointer; user-select: none;
    color: var(--blue-800, #0f2d5e); transition: background .15s;
    white-space: nowrap;
}
.tm-chip:hover { background: var(--blue-100, #e8eef8); }
.tm-chip .tm-chip-x {
    background: none; border: none; padding: 0; margin: 0;
    font-size: 14px; line-height: 1; color: var(--blue-800, #0f2d5e);
    cursor: pointer; opacity: .6; font-weight: 700;
    display: flex; align-items: center;
}
.tm-chip .tm-chip-x:hover { opacity: 1; }
.tm-add-btn {
    display: inline-flex; align-items: center; gap: 4px;
    background: #fff; border: 1px dashed #adb5bd;
    border-radius: 99px; padding: 3px 12px;
    font-size: 12px; color: #6c757d; cursor: pointer;
    transition: all .15s;
}
.tm-add-btn:hover { border-color: var(--blue-600, #2451a3); color: var(--blue-800, #0f2d5e); background: var(--blue-50, #f0f4fb); }

/* Painel dropdown */
.tm-painel {
    position: absolute; z-index: 1050;
    background: #fff; border: 1px solid #dee2e6;
    border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,.12);
    min-width: 420px; max-width: 520px;
    display: flex; flex-direction: column;
    overflow: hidden;
}
.tm-painel-inner { display: flex; min-height: 200px; }
.tm-painel-campos {
    width: 150px; flex-shrink: 0;
    border-right: 1px solid #f0f0f0;
    background: #f8f9fa; overflow-y: auto;
    padding: 6px 0;
}
.tm-painel-campo {
    padding: 8px 14px; font-size: 13px; cursor: pointer;
    color: #343a40; transition: background .1s; border: none;
    background: none; width: 100%; text-align: left;
}
.tm-painel-campo:hover  { background: #e9ecef; }
.tm-painel-campo.active { background: var(--blue-50, #f0f4fb); color: var(--blue-800, #0f2d5e); font-weight: 600; }
.tm-painel-direita {
    flex: 1; padding: 14px 16px; display: flex;
    flex-direction: column; gap: 10px;
}
.tm-op-list { display: flex; flex-direction: column; gap: 4px; }
.tm-op-label {
    display: flex; align-items: center; gap: 8px;
    font-size: 13px; cursor: pointer; padding: 3px 0;
}
.tm-op-label input[type=radio] { accent-color: #1A4D2E; }
.tm-val-input {
    width: 100%; padding: 7px 10px; font-size: 13px;
    border: 1px solid #ced4da; border-radius: 6px;
    outline: none; box-sizing: border-box;
    transition: border-color .15s;
}
.tm-val-input:focus { border-color: #1A4D2E; box-shadow: 0 0 0 2px rgba(26,77,46,.12); }
.tm-val-select {
    width: 100%; padding: 7px 10px; font-size: 13px;
    border: 1px solid #ced4da; border-radius: 6px;
    background: #fff; box-sizing: border-box; cursor: pointer;
}
.tm-range-wrap { display: flex; align-items: center; gap: 8px; }
.tm-range-wrap .tm-val-input { flex: 1; }
.tm-range-sep { color: #6c757d; font-size: 12px; flex-shrink: 0; }
.tm-painel-footer {
    padding: 10px 16px; border-top: 1px solid #f0f0f0;
    display: flex; justify-content: flex-end; gap: 8px;
    background: #fff;
}
.tm-btn-cancel {
    padding: 6px 16px; font-size: 13px; border-radius: 6px;
    border: 1px solid #dee2e6; background: #fff; cursor: pointer;
    color: #495057;
}
.tm-btn-apply {
    padding: 6px 16px; font-size: 13px; border-radius: 6px;
    border: none; background: #1A4D2E; color: #fff; cursor: pointer;
    font-weight: 500;
}
.tm-btn-apply:hover { background: #143d25; }
.tm-btn-cancel:hover { background: #f8f9fa; }

/* Sort no thead */
.tm-sort-row th {
    cursor: pointer; user-select: none; white-space: nowrap;
    vertical-align: middle;
    background: var(--blue-800, #0f2d5e) !important;
    color: #fff !important;
    font-size: 0.65rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: .6px;
    padding: 10px 14px; border: none !important;
}
.tm-sort-row th.no-sort { cursor: default; }
.tm-sort-ico { font-size: 9px; opacity: .5; margin-left: 4px; transition: opacity .15s; }
.tm-sort-row th:hover .tm-sort-ico { opacity: .9; }
        `;
        document.head.appendChild(s);
    }

    // ════════════════════════════════════════════════════════
    // Toolbar: chip bar + botão + (editar hint)
    // ════════════════════════════════════════════════════════

    _construirToolbar() {
        if (!this.toolbar) return;
        this.toolbar.innerHTML = '';
        this.toolbar.style.position = 'relative';

        // Chip bar
        this._chipBar = document.createElement('div');
        this._chipBar.className = 'tm-chip-bar';
        this.toolbar.appendChild(this._chipBar);

        // Botão + Filtro
        const btn = document.createElement('button');
        btn.className = 'tm-add-btn';
        btn.innerHTML = '<span style="font-size:15px;line-height:1;">+</span> Filtro';
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (this._painel) { this._fecharPainel(); return; }
            this._abrirPainel(null, btn);
        });
        this._chipBar.appendChild(btn);
        this._btnAdd = btn;

        // Dica de edição
        if (this.onEditar) {
            const dica = document.createElement('small');
            dica.className = 'text-muted ms-2';
            dica.style.fontSize = '11px';
            dica.innerHTML =
                '<svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor" class="me-1" style="opacity:.5">' +
                '<path d="M12.146.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1 0 .708l-10 10a.5.5 0 0 1-.168.11l-5 2a.5.5 0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293zm-9.761 5.175-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325z"/>' +
                '</svg>Clique na linha para editar';
            this._chipBar.appendChild(dica);
        }
    }

    // ════════════════════════════════════════════════════════
    // Painel de filtro
    // ════════════════════════════════════════════════════════

    _operadoresPorTipo(col) {
        if (col.opcoes) return [
            { val: 'eq',  label: 'é' },
            { val: 'neq', label: 'não é' },
        ];
        if (col.tipo === 'numero') return [
            { val: 'eq',      label: 'é igual a' },
            { val: 'neq',     label: 'é diferente de' },
            { val: 'gt',      label: 'é maior que' },
            { val: 'lt',      label: 'é menor que' },
            { val: 'between', label: 'está entre' },
        ];
        if (col.tipo === 'data') return [
            { val: 'eq',      label: 'é' },
            { val: 'gt',      label: 'é depois de' },
            { val: 'lt',      label: 'é antes de' },
            { val: 'between', label: 'está entre' },
        ];
        // texto livre
        return [
            { val: 'contains',    label: 'contém' },
            { val: 'notcontains', label: 'não contém' },
            { val: 'eq',          label: 'é exatamente' },
            { val: 'neq',         label: 'não é' },
            { val: 'hasvalue',    label: 'tem algum valor' },
        ];
    }

    _abrirPainel(filtroExistente, ancora) {
        this._fecharPainel();
        this._editandoId = filtroExistente?.id || null;

        const painel = document.createElement('div');
        painel.className = 'tm-painel';
        this._painel = painel;

        // Posiciona abaixo do botão/chip
        const rect = ancora.getBoundingClientRect();
        const toolbarRect = this.toolbar.getBoundingClientRect();
        painel.style.top  = (rect.bottom - toolbarRect.top + 4) + 'px';
        painel.style.left = Math.max(0, rect.left - toolbarRect.left) + 'px';

        // Estado interno do painel
        const colsFiltravelis = this.colunas.filter(c => c.tipo !== 'acoes');
        let colSel = filtroExistente
            ? this.colunas.find(c => c.chave === filtroExistente.chave)
            : colsFiltravelis[0];
        let opSel  = filtroExistente?.op  || this._operadoresPorTipo(colSel)[0].val;
        let valSel = filtroExistente?.val  || '';
        let val2Sel= filtroExistente?.val2 || '';

        // ── Layout ──────────────────────────────────────────
        const inner = document.createElement('div');
        inner.className = 'tm-painel-inner';

        // Coluna da esquerda: campos
        const esq = document.createElement('div');
        esq.className = 'tm-painel-campos';
        colsFiltravelis.forEach(col => {
            const btn = document.createElement('button');
            btn.className = 'tm-painel-campo' + (col.chave === colSel.chave ? ' active' : '');
            btn.textContent = col.label;
            btn.addEventListener('click', () => {
                colSel = col;
                opSel  = this._operadoresPorTipo(col)[0].val;
                valSel = ''; val2Sel = '';
                esq.querySelectorAll('.tm-painel-campo').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                renderDir();
            });
            esq.appendChild(btn);
        });

        // Coluna da direita: operadores + valor
        const dir = document.createElement('div');
        dir.className = 'tm-painel-direita';

        const renderDir = () => {
            dir.innerHTML = '';
            const ops = this._operadoresPorTipo(colSel);

            // Título
            const titulo = document.createElement('div');
            titulo.style.cssText = 'font-size:12px;font-weight:600;color:#6c757d;text-transform:uppercase;letter-spacing:.05em;';
            titulo.textContent = colSel.label;
            dir.appendChild(titulo);

            // Operadores
            const opList = document.createElement('div');
            opList.className = 'tm-op-list';
            ops.forEach(op => {
                const lbl = document.createElement('label');
                lbl.className = 'tm-op-label';
                const radio = document.createElement('input');
                radio.type = 'radio'; radio.name = 'tm-op-' + this.tbody.id;
                radio.value = op.val;
                if (op.val === opSel) radio.checked = true;
                radio.addEventListener('change', () => {
                    opSel = op.val;
                    renderInputValor();
                });
                lbl.appendChild(radio);
                lbl.appendChild(document.createTextNode(op.label));
                opList.appendChild(lbl);
            });
            dir.appendChild(opList);

            // Input de valor
            const inputWrap = document.createElement('div');
            inputWrap.id = 'tm-input-wrap-' + this.tbody.id;
            dir.appendChild(inputWrap);

            const renderInputValor = () => {
                inputWrap.innerHTML = '';
                // Sem valor: hasvalue
                if (opSel === 'hasvalue') return;

                if (colSel.opcoes) {
                    // Select com valores únicos
                    const sel = document.createElement('select');
                    sel.className = 'tm-val-select';
                    sel.innerHTML = '<option value="">Selecione…</option>';
                    [...(this._opcoesUnicas[colSel.chave] || [])].sort((a,b) => a.localeCompare(b,'pt')).forEach(v => {
                        const o = document.createElement('option');
                        o.value = v; o.textContent = v;
                        if (v === valSel) o.selected = true;
                        sel.appendChild(o);
                    });
                    sel.addEventListener('change', () => { valSel = sel.value; });
                    inputWrap.appendChild(sel);

                } else if (opSel === 'between') {
                    const wrap = document.createElement('div');
                    wrap.className = 'tm-range-wrap';
                    const i1 = document.createElement('input');
                    i1.className = 'tm-val-input';
                    i1.type  = colSel.tipo === 'data' ? 'date' : 'number';
                    i1.value = valSel;
                    i1.placeholder = 'De';
                    i1.addEventListener('input', () => { valSel = i1.value; });
                    const sep = document.createElement('span');
                    sep.className = 'tm-range-sep'; sep.textContent = 'e';
                    const i2 = document.createElement('input');
                    i2.className = 'tm-val-input';
                    i2.type  = colSel.tipo === 'data' ? 'date' : 'number';
                    i2.value = val2Sel;
                    i2.placeholder = 'Até';
                    i2.addEventListener('input', () => { val2Sel = i2.value; });
                    wrap.append(i1, sep, i2);
                    inputWrap.appendChild(wrap);

                } else {
                    const inp = document.createElement('input');
                    inp.className = 'tm-val-input';
                    inp.type = colSel.tipo === 'numero' ? 'number'
                             : colSel.tipo === 'data'   ? 'date'
                             : 'text';
                    inp.value = valSel;
                    inp.placeholder = 'Valor…';
                    inp.addEventListener('input',  () => { valSel = inp.value; });
                    inp.addEventListener('change', () => { valSel = inp.value; });
                    // Foca no campo automaticamente
                    setTimeout(() => inp.focus(), 50);
                    inputWrap.appendChild(inp);
                }
            };

            renderInputValor();

            // Re-renderiza input ao mudar operador
            opList.querySelectorAll('input[type=radio]').forEach(r => {
                r.addEventListener('change', renderInputValor);
            });
        };

        renderDir();
        inner.append(esq, dir);

        // Footer
        const footer = document.createElement('div');
        footer.className = 'tm-painel-footer';

        const btnCancel = document.createElement('button');
        btnCancel.className = 'tm-btn-cancel'; btnCancel.textContent = 'Cancelar';
        btnCancel.addEventListener('click', () => this._fecharPainel());

        const btnApply = document.createElement('button');
        btnApply.className = 'tm-btn-apply'; btnApply.textContent = 'Aplicar filtro';
        btnApply.addEventListener('click', () => {
            if (opSel !== 'hasvalue' && !valSel) return;
            this._aplicarFiltro(colSel, opSel, valSel, val2Sel);
            this._fecharPainel();
        });

        footer.append(btnCancel, btnApply);
        painel.append(inner, footer);
        this.toolbar.appendChild(painel);
    }

    _fecharPainel() {
        if (this._painel) { this._painel.remove(); this._painel = null; }
        this._editandoId = null;
    }

    // ════════════════════════════════════════════════════════
    // Gerenciar filtros ativos
    // ════════════════════════════════════════════════════════

    _aplicarFiltro(col, op, val, val2) {
        if (this._editandoId !== null) {
            // Edita existente
            const f = this.filtrosAtivos.find(f => f.id === this._editandoId);
            if (f) { f.chave = col.chave; f.op = op; f.val = val; f.val2 = val2; }
        } else {
            this.filtrosAtivos.push({
                id: this._nextFiltroId++,
                chave: col.chave, op, val, val2
            });
        }
        this._renderChips();
        this.pag = 1;
        this._render();
    }

    _removerFiltro(id) {
        this.filtrosAtivos = this.filtrosAtivos.filter(f => f.id !== id);
        this._renderChips();
        this.pag = 1;
        this._render();
    }

    _labelFiltro(f) {
        const col = this.colunas.find(c => c.chave === f.chave);
        if (!col) return '';
        const ops = this._operadoresPorTipo(col);
        const opLabel = (ops.find(o => o.val === f.op) || {}).label || f.op;
        if (f.op === 'hasvalue') return col.label + ' tem valor';
        if (f.op === 'between')  return col.label + ' entre ' + f.val + ' e ' + f.val2;
        return col.label + ' ' + opLabel + ' ' + f.val;
    }

    _renderChips() {
        if (!this._chipBar) return;
        // Limpa chips antigos (mantém botão + e dica)
        [...this._chipBar.children].forEach(el => {
            if (!el.classList.contains('tm-add-btn') && !el.classList.contains('text-muted')) {
                el.remove();
            }
        });

        this.filtrosAtivos.forEach(f => {
            const chip = document.createElement('span');
            chip.className = 'tm-chip';
            chip.dataset.fid = f.id;

            const label = document.createElement('span');
            label.textContent = this._labelFiltro(f);

            const btnX = document.createElement('button');
            btnX.className = 'tm-chip-x';
            btnX.innerHTML = '&times;';
            btnX.title = 'Remover filtro';
            btnX.addEventListener('click', (e) => {
                e.stopPropagation();
                this._removerFiltro(f.id);
            });

            chip.append(label, btnX);
            chip.addEventListener('click', (e) => {
                e.stopPropagation();
                if (this._painel) { this._fecharPainel(); return; }
                this._abrirPainel(f, chip);
            });

            // Insere antes do botão +
            this._chipBar.insertBefore(chip, this._btnAdd);
        });
    }

    // ════════════════════════════════════════════════════════
    // Cabeçalho: apenas sort (sem linha de filtros)
    // ════════════════════════════════════════════════════════

    _construirCabecalho() {
        if (!this.thead) return;
        this.thead.innerHTML = '';

        const tr = document.createElement('tr');
        tr.className = 'tm-sort-row';

        this.colunas.forEach(col => {
            const th = document.createElement('th');

            if (col.tipo === 'acoes') {
                th.className = 'no-sort';
                th.style.textAlign = 'center';
                th.innerHTML = col.label || 'Ações';
            } else {
                th.innerHTML =
                    '<span>' + col.label + '</span>' +
                    '<span class="tm-sort-ico">⇅</span>';
                th.addEventListener('click', () => this._toggleSort(col.chave));
            }
            tr.appendChild(th);
        });

        this.thead.appendChild(tr);
    }

    _toggleSort(chave) {
        if (this.sortCol === chave) {
            if (this.sortDir === 'asc') this.sortDir = 'desc';
            else { this.sortCol = null; this.sortDir = 'asc'; }
        } else {
            this.sortCol = chave; this.sortDir = 'asc';
        }
        this._atualizarIconesSort();
        this.pag = 1;
        this._render();
    }

    _atualizarIconesSort() {
        if (!this.thead) return;
        const ths = this.thead.querySelectorAll('th');
        ths.forEach((th, i) => {
            const col = this.colunas[i];
            if (!col || col.tipo === 'acoes') return;
            const ico = th.querySelector('.tm-sort-ico');
            if (!ico) return;
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
    // API pública
    // ════════════════════════════════════════════════════════

    adicionar(tr, meta) {
        this.itens.push({ tr, meta });
        this.tbody.appendChild(tr);

        // Atualiza valores únicos por coluna
        this.colunas.forEach(col => {
            if (col.opcoes && meta[col.chave]) {
                this._opcoesUnicas[col.chave] = this._opcoesUnicas[col.chave] || new Set();
                this._opcoesUnicas[col.chave].add(String(meta[col.chave]));
            }
        });

        if (this.onEditar) {
            tr.style.cursor = 'pointer';
            tr.title = 'Clique para editar';
            tr.addEventListener('mouseenter', () => { if (!tr._editando) tr.style.background = '#f0f7f0'; });
            tr.addEventListener('mouseleave', () => { if (!tr._editando) tr.style.background = '';       });
            tr.addEventListener('click', (e) => {
                console.log('[TabelaManager] clique na linha, target:', e.target.tagName, e.target.closest('button, a, select, input'));
                if (e.target.closest('button, a, select, input')) return;
                console.log('[TabelaManager] chamando onEditar, meta:', meta);
                try { this.onEditar(meta, tr); } catch(err) { console.error('[TabelaManager] erro no onEditar:', err); }
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
            this.colunas.forEach(col => {
                if (col.opcoes && novaMeta[col.chave]) {
                    this._opcoesUnicas[col.chave].add(String(novaMeta[col.chave]));
                }
            });
        }
        this._render();
    }

    contar() { return this.itens.length; }

    // ════════════════════════════════════════════════════════
    // Filtragem
    // ════════════════════════════════════════════════════════

    _passaFiltros(meta) {
        return this.filtrosAtivos.every(f => {
            const col = this.colunas.find(c => c.chave === f.chave);
            if (!col) return true;
            const raw = meta[f.chave];
            const str = String(raw ?? '').toLowerCase();
            const fv  = String(f.val).toLowerCase();

            if (f.op === 'hasvalue')    return str !== '';
            if (f.op === 'eq')          return str === fv;
            if (f.op === 'neq')         return str !== fv;
            if (f.op === 'contains')    return str.includes(fv);
            if (f.op === 'notcontains') return !str.includes(fv);

            const n = parseFloat(raw) || 0;
            if (f.op === 'gt')      return n > parseFloat(f.val);
            if (f.op === 'lt')      return n < parseFloat(f.val);
            if (f.op === 'between') {
                if (col.tipo === 'data') return str >= f.val && str <= (f.val2 || '9999');
                return n >= parseFloat(f.val) && n <= parseFloat(f.val2);
            }
            return true;
        });
    }

    _filtrados() {
        return this.itens.filter(({ meta }) => this._passaFiltros(meta));
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
                va = parseFloat(va)||0; vb = parseFloat(vb)||0;
                return this.sortDir === 'asc' ? va-vb : vb-va;
            }
            if (tipo === 'data') {
                va = String(va||''); vb = String(vb||'');
                return this.sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
            }
            va = String(va??'').toLowerCase(); vb = String(vb??'').toLowerCase();
            return this.sortDir === 'asc'
                ? va.localeCompare(vb,'pt',{sensitivity:'base'})
                : vb.localeCompare(va,'pt',{sensitivity:'base'});
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
                this.infoSpan.textContent = 'Mostrando ' + (ini+1) + '–' + fim + ' de ' + total + suf;
            }
        }

        if (this.ulPag) this._renderPag(tp);
    }

    _renderPag(tp) {
        this.ulPag.innerHTML = '';
        if (tp <= 1) return;
        let b = Math.max(1, this.pag-2), e = Math.min(tp, b+4);
        if (e-b < 4) b = Math.max(1, e-4);
        const add = (lbl, p, dis, act) => {
            const li = document.createElement('li');
            li.className = 'page-item'+(dis?' disabled':'')+(act?' active':'');
            li.innerHTML = '<button class="page-link">'+lbl+'</button>';
            if (!dis && !act) li.querySelector('button').onclick = () => { this.pag = p; this._render(); };
            this.ulPag.appendChild(li);
        };
        add('«',1,this.pag===1); add('‹',this.pag-1,this.pag===1);
        for (let p=b;p<=e;p++) add(p,p,false,p===this.pag);
        add('›',this.pag+1,this.pag===tp); add('»',tp,this.pag===tp);
    }
}
