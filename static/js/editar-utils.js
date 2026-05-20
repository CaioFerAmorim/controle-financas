/**
 * EditorPanel — painel de edição via Offcanvas Bootstrap.
 *
 * Uso:
 *   const editor = new EditorPanel('meuEditor');
 *   editor.abrir({
 *     titulo: 'Editar Despesa',
 *     campos: [
 *       { chave: 'descricao', label: 'Descrição',  tipo: 'text',   valor: meta.descricao, required: true },
 *       { chave: 'categoria', label: 'Categoria',  tipo: 'select', valor: meta.categoria, opcoes: ['Alimentação','Lazer'] },
 *       { chave: 'valor',     label: 'Valor (R$)', tipo: 'number', valor: meta.valor,     min: 0.01, step: 0.01 },
 *       { chave: 'data',      label: 'Data',       tipo: 'date',   valor: meta.data },
 *       { chave: 'status',    label: 'Status',     tipo: 'select', valor: meta.status,
 *                             opcoes: [{label:'Ativo',value:'Ativa'},{label:'Pausado',value:'Pausada'}] },
 *     ],
 *     onSalvar: (dados) => { /* chama a API e atualiza a linha *\/ }
 *   });
 */
class EditorPanel {
    constructor(id = 'editorPanel') {
        this.id = id;
        this._el = null;
        this._offcanvas = null;
        this._onSalvar = null;
        this._construir();
    }

    // ── Constrói o offcanvas no DOM (uma vez) ────────────────────
    _construir() {
        if (document.getElementById(this.id)) return;

        const el = document.createElement('div');
        el.id = this.id;
        el.className = 'offcanvas offcanvas-end';
        el.tabIndex = -1;
        el.setAttribute('aria-labelledby', this.id + 'Label');
        el.style.width = '380px';

        el.innerHTML = `
            <div class="offcanvas-header" style="background:var(--blue-800,#0f2d5e);color:#fff;padding:14px 20px;border-bottom:1px solid rgba(255,255,255,.1);">
                <div style="display:flex;flex-direction:column;gap:2px;">
                    <h6 class="offcanvas-title mb-0" id="${this.id}Label" style="font-weight:700;font-size:.9rem;letter-spacing:-.2px;font-family:'DM Sans',sans-serif;"></h6>
                </div>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="offcanvas" style="opacity:.7"></button>
            </div>
            <div class="offcanvas-body" id="${this.id}Body" style="padding:20px;background:#f4f6fb;font-family:'DM Sans',sans-serif;"></div>
            <div class="offcanvas-footer" style="border-top:1px solid #e2e8f2;padding:14px 20px;display:flex;gap:8px;justify-content:flex-end;background:#fff;">
                <button type="button" class="btn btn-sm btn-outline-secondary" data-bs-dismiss="offcanvas"
                        style="font-family:'DM Sans',sans-serif;font-size:.82rem;border-radius:8px;padding:6px 14px;">Cancelar</button>
                <button type="button" class="btn btn-sm text-white" id="${this.id}BtnSalvar"
                        style="background:var(--blue-800,#0f2d5e);border:none;min-width:90px;border-radius:8px;font-family:'DM Sans',sans-serif;font-size:.82rem;font-weight:600;padding:6px 16px;">Salvar</button>
            </div>`;

        document.body.appendChild(el);
        this._el = el;
        this._offcanvas = null; // inicializado lazy no primeiro abrir()

        el.querySelector(`#${this.id}BtnSalvar`).addEventListener('click', () => this._salvar());

        // Acessibilidade: foca no primeiro campo ao abrir
        el.addEventListener('shown.bs.offcanvas', () => {
            const primeiro = el.querySelector('input:not([type=hidden]),select,textarea');
            if (primeiro) primeiro.focus();
        });
    }

    // ── Abre o painel com a configuração passada ─────────────────
    abrir({ titulo, campos, onSalvar }) {
        // Inicializa o Offcanvas na primeira chamada (Bootstrap já está carregado aqui)
        if (!this._offcanvas) {
            this._offcanvas = new bootstrap.Offcanvas(this._el);
        }
        this._onSalvar = onSalvar;

        // Título
        this._el.querySelector(`#${this.id}Label`).textContent = titulo || 'Editar';

        // Corpo do formulário
        const body = this._el.querySelector(`#${this.id}Body`);
        body.innerHTML = '';

        const form = document.createElement('form');
        form.id = this.id + 'Form';
        form.noValidate = true;

        campos.forEach(campo => {
            const wrap = document.createElement('div');
            wrap.className = 'mb-3'; wrap.style.cssText = 'margin-bottom:16px;';

            const label = document.createElement('label');
            label.style.cssText = 'display:block;font-size:.68rem;font-weight:700;color:#8394ae;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px;font-family:DM Sans,sans-serif;';
            label.textContent = campo.label + (campo.required ? ' *' : '');
            wrap.appendChild(label);

            let input;

            if (campo.tipo === 'select') {
                input = document.createElement('select');
                input.className = 'form-select form-select-sm'; input.style.cssText = 'border-radius:8px;border:1.5px solid #e2e8f2;font-family:DM Sans,sans-serif;font-size:.86rem;height:36px;';
                (campo.opcoes || []).forEach(op => {
                    const o = document.createElement('option');
                    if (typeof op === 'object') {
                        o.value = op.value; o.textContent = op.label;
                        if (op.value === campo.valor) o.selected = true;
                    } else {
                        o.value = op; o.textContent = op;
                        if (op === campo.valor) o.selected = true;
                    }
                    input.appendChild(o);
                });

            } else if (campo.tipo === 'textarea') {
                input = document.createElement('textarea');
                input.className = 'form-control form-control-sm'; input.style.cssText = 'border-radius:8px;border:1.5px solid #e2e8f2;font-family:DM Sans,sans-serif;font-size:.86rem;height:36px;';
                input.rows = campo.rows || 3;
                input.value = campo.valor || '';

            } else if (campo.tipo === 'readonly') {
                input = document.createElement('input');
                input.className = 'form-control form-control-sm bg-light'; input.style.cssText = 'border-radius:8px;border:1.5px solid #e2e8f2;font-family:DM Sans,sans-serif;font-size:.86rem;height:36px;background:#f4f6fb;';
                input.type = 'text';
                input.value = campo.valor || '';
                input.readOnly = true;
                if (campo.help) {
                    const help = document.createElement('small');
                    help.className = 'text-muted';
                    help.textContent = campo.help;
                    wrap.appendChild(label);
                    wrap.appendChild(input);
                    wrap.appendChild(help);
                    body.appendChild(wrap);
                    return;
                }

            } else {
                input = document.createElement('input');
                input.className = 'form-control form-control-sm';
                input.type = campo.tipo || 'text';
                input.value = campo.valor !== undefined ? campo.valor : '';
                if (campo.min  !== undefined) input.min  = campo.min;
                if (campo.max  !== undefined) input.max  = campo.max;
                if (campo.step !== undefined) input.step = campo.step;
                if (campo.placeholder) input.placeholder = campo.placeholder;
            }

            input.dataset.chave = campo.chave;
            if (campo.required) {
                input.required = true;
                input.addEventListener('input', () => input.classList.remove('is-invalid'));
            }

            // Foco verde
            input.addEventListener('focus', () => {
                input.style.borderColor = '#2451a3';
                input.style.boxShadow   = '0 0 0 3px rgba(36,81,163,.12)';
            });
            input.addEventListener('blur', () => {
                input.style.borderColor = '#e2e8f2';
                input.style.boxShadow   = '';
            });

            wrap.appendChild(input);
            form.appendChild(wrap);
        });

        body.appendChild(form);
        this._offcanvas.show();
    }

    // ── Coleta dados e chama onSalvar ────────────────────────────
    _salvar() {
        const form = this._el.querySelector(`#${this.id}Form`);
        if (!form) return;

        // Valida campos obrigatórios
        let valido = true;
        form.querySelectorAll('[required]').forEach(el => {
            if (!el.value.trim()) {
                el.classList.add('is-invalid');
                valido = false;
            }
        });
        if (!valido) return;

        const dados = {};
        form.querySelectorAll('[data-chave]').forEach(el => {
            dados[el.dataset.chave] = el.value;
        });

        const btnSalvar = this._el.querySelector(`#${this.id}BtnSalvar`);
        btnSalvar.disabled = true;
        btnSalvar.textContent = 'Salvando…';

        Promise.resolve(this._onSalvar(dados))
            .then(ok => {
                if (ok !== false) this._offcanvas.hide();
            })
            .catch(() => {})
            .finally(() => {
                btnSalvar.disabled = false;
                btnSalvar.textContent = 'Salvar';
            });
    }

    fechar() {
        this._offcanvas?.hide();
    }
}

// ════════════════════════════════════════════════════════════════
// Helper global: chama API de update e retorna Promise<boolean>
// ════════════════════════════════════════════════════════════════
function apiAtualizar(url, dados) {
    return fetch(url, {
        method:  'POST',
        headers: {'Content-Type': 'application/json'},
        body:    JSON.stringify(dados),
    })
    .then(r => r.json())
    .then(d => {
        if (!d.success) { WM.erro('Erro ao salvar: ' + (d.error || 'desconhecido')); return false; }
        return true;
    })
    .catch(() => { WM.erro('Erro de conexão.'); return false; });
}
