/**
 * settings-modal.js — Modal de Configurações/Admin
 * Uso: SMSettings.init(nome, role) no DOMContentLoaded
 *      SMSettings.abrir(aba?) para abrir em uma aba específica
 */
const SMSettings = (() => {

    let modal = null;
    let overlay = null;
    let abaAtiva = 'perfil';
    let userRole = 'user';
    let userName = '';

    // ── CSS injetado ──────────────────────────────────────────────
    function _injetarCSS() {
        if (document.getElementById('sm-settings-css')) return;
        const s = document.createElement('style');
        s.id = 'sm-settings-css';
        s.textContent = `
        .sms-overlay {
            position: fixed; inset: 0;
            background: rgba(10,20,40,.45);
            backdrop-filter: blur(2px);
            z-index: 10000;
            display: flex; align-items: center; justify-content: center;
            opacity: 0; transition: opacity .22s ease;
            pointer-events: none;
        }
        .sms-overlay.open { opacity: 1; pointer-events: all; }

        .sms-modal {
            background: var(--surface, #fff);
            border-radius: 16px;
            box-shadow: 0 24px 80px rgba(10,20,40,.22);
            width: 860px; max-width: calc(100vw - 32px);
            height: 580px; max-height: calc(100vh - 64px);
            display: flex; flex-direction: column;
            overflow: hidden;
            transform: translateY(12px) scale(.98);
            transition: transform .22s ease;
            font-family: 'DM Sans', system-ui, sans-serif;
        }
        .sms-overlay.open .sms-modal { transform: translateY(0) scale(1); }

        /* Header */
        .sms-header {
            display: flex; align-items: center; justify-content: space-between;
            padding: 16px 20px;
            border-bottom: 1px solid var(--border, #e2e8f2);
            flex-shrink: 0;
        }
        .sms-title {
            font-size: .88rem; font-weight: 700;
            color: var(--text-primary, #0f1f3d);
            letter-spacing: -.2px;
        }
        .sms-close {
            width: 30px; height: 30px;
            border: none; background: none;
            border-radius: 8px; cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            color: var(--text-muted, #8394ae);
            font-size: 18px; transition: background .15s, color .15s;
        }
        .sms-close:hover { background: var(--red-bg, #fee2e2); color: var(--red, #dc2626); }

        /* Body */
        .sms-body { display: flex; flex: 1; overflow: hidden; }

        /* Sidebar interna */
        .sms-nav {
            width: 200px; flex-shrink: 0;
            border-right: 1px solid var(--border, #e2e8f2);
            padding: 12px 8px;
            overflow-y: auto;
            background: var(--bg, #f4f6fb);
        }
        .sms-nav-section {
            font-size: .6rem; font-weight: 700;
            color: var(--border-2, #d0d9ea);
            text-transform: uppercase; letter-spacing: 1.2px;
            padding: 8px 10px 4px;
        }
        .sms-nav-item {
            display: flex; align-items: center; gap: 8px;
            padding: 8px 10px; border-radius: 8px;
            font-size: .82rem; font-weight: 500;
            color: var(--text-secondary, #4a5878);
            cursor: pointer; transition: background .12s, color .12s;
            border: none; background: none; width: 100%; text-align: left;
            font-family: inherit;
        }
        .sms-nav-item:hover { background: var(--blue-50, #f0f4fb); color: var(--blue-800, #0f2d5e); }
        .sms-nav-item.active {
            background: var(--blue-100, #e8eef8);
            color: var(--blue-800, #0f2d5e);
            font-weight: 600;
        }
        .sms-nav-item i { font-size: 16px; flex-shrink: 0; }
        .sms-nav-divider { height: 1px; background: var(--border, #e2e8f2); margin: 6px 10px; }

        /* Conteúdo */
        .sms-content {
            flex: 1; overflow-y: auto;
            padding: 24px 28px;
        }

        .sms-pane { display: none; }
        .sms-pane.active { display: block; }

        .sms-pane-title {
            font-size: 1rem; font-weight: 700;
            color: var(--text-primary, #0f1f3d);
            margin-bottom: 4px; letter-spacing: -.2px;
        }
        .sms-pane-sub {
            font-size: .75rem; color: var(--text-muted, #8394ae);
            margin-bottom: 20px;
        }

        /* Form fields */
        .sms-field { margin-bottom: 16px; }
        .sms-label {
            display: block; font-size: .68rem; font-weight: 700;
            color: var(--text-muted, #8394ae);
            text-transform: uppercase; letter-spacing: .5px; margin-bottom: 5px;
        }
        .sms-input {
            width: 100%; height: 38px; padding: 0 12px;
            border: 1.5px solid var(--border-2, #d0d9ea);
            border-radius: 8px; font-family: inherit; font-size: .86rem;
            color: var(--text-primary, #0f1f3d);
            background: #fff; outline: none;
            transition: border-color .15s, box-shadow .15s;
        }
        .sms-input:focus {
            border-color: var(--blue-600, #2451a3);
            box-shadow: 0 0 0 3px rgba(36,81,163,.1);
        }
        .sms-input[readonly] {
            background: var(--bg, #f4f6fb);
            cursor: default; color: var(--text-muted, #8394ae);
        }
        .sms-strength { height: 3px; border-radius: 2px; background: var(--border, #e2e8f2); margin-top: 6px; }
        .sms-strength div { height: 100%; border-radius: 2px; transition: all .3s; width: 0%; }

        .sms-btn {
            display: inline-flex; align-items: center; gap: 6px;
            height: 36px; padding: 0 16px; border-radius: 8px;
            font-family: inherit; font-size: .84rem; font-weight: 600;
            cursor: pointer; border: none; transition: all .15s;
        }
        .sms-btn-primary { background: var(--blue-800, #0f2d5e); color: #fff; }
        .sms-btn-primary:hover { background: var(--blue-700, #1a3f7a); }
        .sms-btn-primary:disabled { opacity: .6; cursor: not-allowed; }

        /* Avatar */
        .sms-avatar {
            width: 56px; height: 56px; border-radius: 50%;
            background: var(--blue-800, #0f2d5e); color: #fff;
            display: flex; align-items: center; justify-content: center;
            font-size: 1.4rem; font-weight: 700; flex-shrink: 0;
        }

        /* Tabela de usuários */
        .sms-table { width: 100%; border-collapse: collapse; font-size: .8rem; }
        .sms-table thead th {
            background: var(--blue-800, #0f2d5e) !important;
            color: #fff !important;
            padding: 9px 12px; font-size: .62rem; font-weight: 700;
            text-transform: uppercase; letter-spacing: .6px; border: none;
        }
        .sms-table tbody td {
            padding: 10px 12px; border-bottom: 1px solid var(--border, #e2e8f2);
            vertical-align: middle;
        }
        .sms-table tbody tr:last-child td { border-bottom: none; }
        .sms-table tbody tr:hover td { background: var(--blue-50, #f0f4fb); }

        .sms-action-btn {
            width: 28px; height: 28px; border-radius: 6px;
            border: 1px solid var(--border, #e2e8f2);
            background: none; cursor: pointer;
            display: inline-flex; align-items: center; justify-content: center;
            font-size: 14px; color: var(--text-muted, #8394ae);
            transition: all .12s;
        }
        .sms-action-btn:hover { background: var(--blue-50, #f0f4fb); color: var(--blue-800, #0f2d5e); }
        .sms-action-btn.danger:hover { background: var(--red-bg, #fee2e2); color: var(--red, #dc2626); border-color: #fca5a5; }
        .sms-action-btn.success:hover { background: var(--green-bg, #dcfce7); color: var(--green, #16a34a); border-color: #86efac; }
        .sms-action-btn.warn:hover { background: #fef3c7; color: var(--amber, #d97706); border-color: #fcd34d; }

        /* Reset senha inline */
        .sms-reset-form {
            display: none; margin-top: 8px; padding: 10px;
            background: var(--bg, #f4f6fb); border-radius: 8px;
        }
        `;
        document.head.appendChild(s);
    }

    // ── Criar DOM do modal ────────────────────────────────────────
    function _criar() {
        if (document.getElementById('sms-overlay')) return;

        overlay = document.createElement('div');
        overlay.id = 'sms-overlay';
        overlay.className = 'sms-overlay';
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) fechar();
        });

        modal = document.createElement('div');
        modal.className = 'sms-modal';
        modal.innerHTML = `
            <div class="sms-header">
                <span class="sms-title" id="sms-title">Configurações</span>
                <button class="sms-close" onclick="SMSettings.fechar()" title="Fechar">
                    <i class="ti ti-x"></i>
                </button>
            </div>
            <div class="sms-body">
                <nav class="sms-nav" id="sms-nav"></nav>
                <div class="sms-content" id="sms-content"></div>
            </div>`;

        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && overlay.classList.contains('open')) fechar();
        });
    }

    // ── Renderizar nav ────────────────────────────────────────────
    function _renderNav() {
        const nav = document.getElementById('sms-nav');
        const isAdmin = userRole === 'admin';

        nav.innerHTML = `
            <div class="sms-nav-section">Configurações</div>
            <button class="sms-nav-item ${abaAtiva==='perfil'?'active':''}" onclick="SMSettings._mudarAba('perfil')">
                <i class="ti ti-user"></i> Perfil
            </button>
            <button class="sms-nav-item ${abaAtiva==='seguranca'?'active':''}" onclick="SMSettings._mudarAba('seguranca')">
                <i class="ti ti-lock"></i> Segurança
            </button>
            ${isAdmin ? `
            <div class="sms-nav-divider"></div>
            <div class="sms-nav-section">Admin</div>
            <button class="sms-nav-item ${abaAtiva==='usuarios'?'active':''}" onclick="SMSettings._mudarAba('usuarios')">
                <i class="ti ti-users"></i> Usuários
            </button>` : ''}
        `;
    }

    // ── Panes ─────────────────────────────────────────────────────
    function _renderPerfil() {
        return `
        <div class="sms-pane active" id="sms-pane-perfil">
            <div class="sms-pane-title">Perfil</div>
            <div class="sms-pane-sub">Suas informações pessoais</div>
            <div style="display:flex;align-items:center;gap:14px;margin-bottom:20px">
                <div class="sms-avatar" id="sms-avatar-letra">?</div>
                <div>
                    <div style="font-weight:700;font-size:.9rem" id="sms-perfil-nome-label">—</div>
                    <div style="font-size:.75rem;color:var(--text-muted)" id="sms-perfil-email-label">—</div>
                </div>
            </div>
            <form id="sms-form-perfil" onsubmit="SMSettings._salvarPerfil(event)">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
                    <div class="sms-field">
                        <label class="sms-label">Nome completo</label>
                        <input type="text" class="sms-input" id="sms-nome" required>
                    </div>
                    <div class="sms-field">
                        <label class="sms-label">Email <span style="font-weight:400;text-transform:none;letter-spacing:0;color:var(--text-muted)">(não editável)</span></label>
                        <input type="email" class="sms-input" id="sms-email" readonly>
                    </div>
                    <div class="sms-field">
                        <label class="sms-label">Telefone <span style="font-weight:400;text-transform:none;letter-spacing:0;color:var(--text-muted)">(opcional)</span></label>
                        <input type="tel" class="sms-input" id="sms-telefone" placeholder="(11) 99999-9999">
                    </div>
                    <div class="sms-field">
                        <label class="sms-label">Membro desde</label>
                        <input type="text" class="sms-input" id="sms-membro" readonly>
                    </div>
                </div>
                <div style="display:flex;justify-content:flex-end;margin-top:8px">
                    <button type="submit" class="sms-btn sms-btn-primary" id="sms-btn-perfil">
                        <i class="ti ti-check"></i> Salvar perfil
                    </button>
                </div>
            </form>
        </div>`;
    }

    function _renderSeguranca() {
        return `
        <div class="sms-pane" id="sms-pane-seguranca">
            <div class="sms-pane-title">Segurança</div>
            <div class="sms-pane-sub">Altere sua senha de acesso</div>
            <form id="sms-form-senha" onsubmit="SMSettings._salvarSenha(event)" style="max-width:440px">
                <div class="sms-field">
                    <label class="sms-label">Senha atual</label>
                    <input type="password" class="sms-input" id="sms-senha-atual" placeholder="••••••••" autocomplete="current-password">
                </div>
                <div class="sms-field">
                    <label class="sms-label">Nova senha</label>
                    <input type="password" class="sms-input" id="sms-nova-senha" placeholder="Mínimo 8 caracteres"
                           autocomplete="new-password" oninput="SMSettings._forca(this.value)">
                    <div class="sms-strength"><div id="sms-forca-bar"></div></div>
                    <small id="sms-forca-txt" style="font-size:.68rem;color:var(--text-muted)"></small>
                </div>
                <div class="sms-field">
                    <label class="sms-label">Confirmar nova senha</label>
                    <input type="password" class="sms-input" id="sms-confirmar" placeholder="Repita a senha"
                           autocomplete="new-password" oninput="SMSettings._match()">
                    <small id="sms-match-txt" style="font-size:.68rem"></small>
                </div>
                <div style="display:flex;justify-content:flex-end;margin-top:8px">
                    <button type="submit" class="sms-btn sms-btn-primary" id="sms-btn-senha">
                        <i class="ti ti-lock-check"></i> Alterar senha
                    </button>
                </div>
            </form>
        </div>`;
    }

    function _renderUsuarios() {
        return `
        <div class="sms-pane" id="sms-pane-usuarios">
            <div class="sms-pane-title">Usuários</div>
            <div class="sms-pane-sub">Gerencie acesso e permissões</div>
            <div id="sms-usuarios-loading" style="text-align:center;padding:32px;color:var(--text-muted);font-size:.82rem">
                Carregando...
            </div>
            <div class="sms-table-wrap" style="overflow-x:auto;display:none" id="sms-usuarios-wrap">
                <table class="sms-table">
                    <thead>
                        <tr>
                            <th>Nome</th><th>Email</th><th>Perfil</th>
                            <th>Status</th><th class="text-center">Desde</th>
                            <th class="text-center">Ações</th>
                        </tr>
                    </thead>
                    <tbody id="sms-usuarios-tbody"></tbody>
                </table>
            </div>
        </div>`;
    }

    // ── Mudar aba ─────────────────────────────────────────────────
    function _mudarAba(aba) {
        abaAtiva = aba;
        _renderNav();

        const titles = { perfil: 'Perfil', seguranca: 'Segurança', usuarios: 'Usuários' };
        document.getElementById('sms-title').textContent = titles[aba] || aba;

        const content = document.getElementById('sms-content');
        // Manter panes existentes, só trocar active
        content.querySelectorAll('.sms-pane').forEach(p => p.classList.remove('active'));
        const existing = document.getElementById('sms-pane-' + aba);
        if (existing) {
            existing.classList.add('active');
        } else {
            // Criar o pane
            let html = '';
            if (aba === 'perfil')     html = _renderPerfil();
            if (aba === 'seguranca')  html = _renderSeguranca();
            if (aba === 'usuarios')   html = _renderUsuarios();
            content.insertAdjacentHTML('beforeend', html);
            _bindEvents(aba);
        }

        if (aba === 'perfil')    _carregarPerfil();
        if (aba === 'usuarios')  _carregarUsuarios();
    }

    // ── Bind de eventos ───────────────────────────────────────────
    function _bindEvents(aba) {
        if (aba === 'perfil') {
            const tel = document.getElementById('sms-telefone');
            if (tel) tel.addEventListener('input', function() {
                let v = this.value.replace(/\D/g,'').substring(0,11);
                if (v.length > 2)  v = '(' + v.substring(0,2) + ') ' + v.substring(2);
                if (v.length > 10) v = v.substring(0,10) + '-' + v.substring(10);
                this.value = v;
            });
        }
    }

    // ── Perfil ────────────────────────────────────────────────────
    function _carregarPerfil() {
        fetch('/api/minha_conta')
            .then(r => r.json())
            .then(d => {
                if (!d.success) return;
                document.getElementById('sms-nome').value     = d.nome || '';
                document.getElementById('sms-email').value    = d.email || '';
                document.getElementById('sms-telefone').value = d.telefone || '';
                document.getElementById('sms-membro').value   = d.criado_em || '';
                document.getElementById('sms-avatar-letra').textContent   = (d.nome||'?')[0].toUpperCase();
                document.getElementById('sms-perfil-nome-label').textContent  = d.nome || '—';
                document.getElementById('sms-perfil-email-label').textContent = d.email || '—';
            });
    }

    function _salvarPerfil(e) {
        e.preventDefault();
        const nome     = document.getElementById('sms-nome').value.trim();
        const telefone = document.getElementById('sms-telefone').value.trim();
        if (!nome) { WM.aviso('Nome é obrigatório.'); return; }

        const btn = document.getElementById('sms-btn-perfil');
        btn.disabled = true; btn.innerHTML = '<i class="ti ti-loader"></i> Salvando…';

        fetch('/api/minha_conta', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ nome, telefone }),
        })
        .then(r => r.json())
        .then(d => {
            if (d.success) {
                WM.sucesso('Perfil atualizado!');
                document.getElementById('sms-avatar-letra').textContent = nome[0].toUpperCase();
                document.getElementById('sms-perfil-nome-label').textContent = nome;
                // Atualizar sidebar principal
                document.querySelectorAll('.sm-sb-username').forEach(el => el.textContent = nome);
                document.querySelectorAll('.sm-topbar-user').forEach(el => {
                    const av = el.querySelector('.sm-topbar-avatar');
                    if (av) av.textContent = nome[0].toUpperCase();
                    el.childNodes.forEach(n => { if (n.nodeType===3) n.textContent = ' ' + nome + ' '; });
                });
            } else WM.erro(d.error || 'Erro ao salvar.');
        })
        .catch(() => WM.erro('Erro de conexão.'))
        .finally(() => { btn.disabled=false; btn.innerHTML='<i class="ti ti-check"></i> Salvar perfil'; });
    }

    // ── Segurança ─────────────────────────────────────────────────
    function _forca(senha) {
        const bar = document.getElementById('sms-forca-bar');
        const txt = document.getElementById('sms-forca-txt');
        if (!bar) return;
        let p = 0;
        if (senha.length>=8) p++; if (senha.length>=12) p++;
        if (/[A-Z]/.test(senha)) p++; if (/[0-9]/.test(senha)) p++;
        if (/[^A-Za-z0-9]/.test(senha)) p++;
        const cfg = [
            {w:'0%',cor:'var(--border)',label:''},
            {w:'25%',cor:'var(--red)',label:'Muito fraca'},
            {w:'50%',cor:'var(--amber)',label:'Fraca'},
            {w:'75%',cor:'#ca8a04',label:'Boa'},
            {w:'90%',cor:'var(--green)',label:'Forte'},
            {w:'100%',cor:'var(--blue-800)',label:'Muito forte'},
        ][Math.min(p,5)];
        bar.style.width=cfg.w; bar.style.background=cfg.cor;
        txt.textContent=cfg.label; txt.style.color=cfg.cor;
    }

    function _match() {
        const s1 = document.getElementById('sms-nova-senha')?.value;
        const s2 = document.getElementById('sms-confirmar')?.value;
        const el = document.getElementById('sms-match-txt');
        if (!el || !s2) return;
        el.textContent = s1===s2 ? '✓ Senhas coincidem' : '✗ Senhas não coincidem';
        el.style.color  = s1===s2 ? 'var(--green)' : 'var(--red)';
    }

    function _salvarSenha(e) {
        e.preventDefault();
        const nome       = document.getElementById('sms-nome')?.value.trim() || userName;
        const senhaAtual = document.getElementById('sms-senha-atual').value;
        const novaSenha  = document.getElementById('sms-nova-senha').value;
        const confirmar  = document.getElementById('sms-confirmar').value;

        if (!senhaAtual)           { WM.aviso('Informe a senha atual.'); return; }
        if (!novaSenha)            { WM.aviso('Informe a nova senha.'); return; }
        if (novaSenha.length < 8)  { WM.aviso('Mínimo 8 caracteres.'); return; }
        if (novaSenha !== confirmar){ WM.aviso('As senhas não coincidem.'); return; }

        const btn = document.getElementById('sms-btn-senha');
        btn.disabled=true; btn.innerHTML='<i class="ti ti-loader"></i> Alterando…';

        fetch('/api/minha_conta', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ nome, senha_atual: senhaAtual, nova_senha: novaSenha }),
        })
        .then(r=>r.json())
        .then(d => {
            if (d.success) {
                WM.sucesso('Senha alterada!');
                document.getElementById('sms-form-senha').reset();
                const bar = document.getElementById('sms-forca-bar');
                if (bar) { bar.style.width='0%'; }
                const txt = document.getElementById('sms-forca-txt');
                if (txt) txt.textContent='';
                const mt = document.getElementById('sms-match-txt');
                if (mt) mt.textContent='';
            } else WM.erro(d.error || 'Erro.');
        })
        .catch(()=>WM.erro('Erro de conexão.'))
        .finally(()=>{ btn.disabled=false; btn.innerHTML='<i class="ti ti-lock-check"></i> Alterar senha'; });
    }

    // ── Admin: Usuários ───────────────────────────────────────────
    function _carregarUsuarios() {
        fetch('/api/admin/usuarios')
            .then(r=>r.json())
            .then(d => {
                const loading = document.getElementById('sms-usuarios-loading');
                const wrap    = document.getElementById('sms-usuarios-wrap');
                const tbody   = document.getElementById('sms-usuarios-tbody');
                if (!loading || !wrap || !tbody) return;

                loading.style.display = 'none';
                wrap.style.display = '';

                tbody.innerHTML = (d.usuarios || []).map(u => `
                    <tr id="sms-row-${u.id}">
                        <td><span style="font-weight:600">${u.nome}</span></td>
                        <td style="font-size:.75rem;color:var(--text-muted)">${u.email}</td>
                        <td>
                            <span style="font-size:.65rem;font-weight:700;padding:2px 8px;border-radius:10px;
                                background:${u.role==='admin'?'var(--blue-100)':'#f1f5f9'};
                                color:${u.role==='admin'?'var(--blue-800)':'#475569'}">
                                ${u.role}
                            </span>
                        </td>
                        <td>
                            <span style="font-size:.65rem;font-weight:700;padding:2px 8px;border-radius:10px;
                                background:${u.ativo?'var(--green-bg)':'var(--red-bg)'};
                                color:${u.ativo?'#166534':'#991b1b'}">
                                ${u.ativo?'Ativo':'Inativo'}
                            </span>
                        </td>
                        <td style="text-align:center;font-size:.75rem;color:var(--text-muted)">${u.criado_em||'—'}</td>
                        <td style="text-align:center">
                            <div style="display:flex;gap:4px;justify-content:center">
                                ${u.id !== (window._smsCurrentUserId||0) ? `
                                <button class="sms-action-btn ${u.ativo?'danger':'success'}"
                                    onclick="SMSettings._acoesAdmin(${u.id},'${u.ativo?'desativar':'ativar'}')"
                                    title="${u.ativo?'Desativar':'Ativar'}">
                                    <i class="ti ti-user-${u.ativo?'off':'check'}"></i>
                                </button>
                                <button class="sms-action-btn"
                                    onclick="SMSettings._acoesAdmin(${u.id},'${u.role==='user'?'promover':'rebaixar'}')"
                                    title="${u.role==='user'?'Promover a admin':'Remover admin'}">
                                    <i class="ti ti-arrow-${u.role==='user'?'up':'down'}-circle"></i>
                                </button>` : ''}
                                <button class="sms-action-btn warn"
                                    onclick="SMSettings._resetarSenha(${u.id},'${u.nome}')"
                                    title="Resetar senha">
                                    <i class="ti ti-key"></i>
                                </button>
                            </div>
                            <div class="sms-reset-form" id="sms-reset-${u.id}">
                                <input type="password" class="sms-input" id="sms-nova-pwd-${u.id}"
                                       placeholder="Nova senha (mín. 8 car.)"
                                       style="height:32px;font-size:.78rem;margin-bottom:6px">
                                <div style="display:flex;gap:6px;justify-content:flex-end">
                                    <button class="sms-btn sms-btn-primary" style="height:28px;padding:0 10px;font-size:.75rem"
                                            onclick="SMSettings._confirmarReset(${u.id})">Salvar</button>
                                    <button style="height:28px;padding:0 10px;font-size:.75rem;border:1px solid var(--border);border-radius:6px;background:none;cursor:pointer"
                                            onclick="document.getElementById('sms-reset-${u.id}').style.display='none'">Cancelar</button>
                                </div>
                            </div>
                        </td>
                    </tr>`).join('');
            })
            .catch(()=>WM.erro('Erro ao carregar usuários.'));
    }

    function _acoesAdmin(userId, tipo) {
        const msgs = {
            desativar:'Desativar este usuário?', ativar:'Ativar este usuário?',
            promover:'Promover a admin?', rebaixar:'Remover permissão de admin?',
        };
        if (!confirm(msgs[tipo]||'Confirmar?')) return;
        fetch('/api/admin/usuario/'+userId, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({acao:tipo})
        })
        .then(r=>r.json())
        .then(d=>{
            if (d.success) _carregarUsuarios();
            else WM.erro('Erro: '+(d.error||'desconhecido'));
        });
    }

    function _resetarSenha(userId, nome) {
        // Esconder outros forms abertos
        document.querySelectorAll('.sms-reset-form').forEach(f=>f.style.display='none');
        const form = document.getElementById('sms-reset-'+userId);
        if (form) form.style.display = 'block';
    }

    function _confirmarReset(userId) {
        const nova = document.getElementById('sms-nova-pwd-'+userId)?.value;
        if (!nova || nova.length < 8) { WM.aviso('Mínimo 8 caracteres.'); return; }
        fetch('/api/admin/usuario/'+userId, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({acao:'resetar_senha', nova_senha:nova})
        })
        .then(r=>r.json())
        .then(d=>{
            if (d.success) {
                WM.sucesso('Senha resetada!');
                const form = document.getElementById('sms-reset-'+userId);
                if (form) form.style.display='none';
            } else WM.erro('Erro: '+(d.error||'desconhecido'));
        });
    }

    // ── API pública ───────────────────────────────────────────────
    function abrir(aba) {
        overlay.classList.add('open');
        _mudarAba(aba || abaAtiva);
    }

    function fechar() {
        overlay.classList.remove('open');
    }

    function init(nome, role, currentUserId) {
        userName = nome;
        userRole = role;
        window._smsCurrentUserId = currentUserId || 0;
        _injetarCSS();
        _criar();

        // Renderizar conteúdo inicial
        const content = document.getElementById('sms-content');
        content.innerHTML = _renderPerfil() + _renderSeguranca() + _renderUsuarios();
        _bindEvents('perfil');
        _bindEvents('seguranca');

        // Conectar triggers do user menu
        document.addEventListener('click', (e) => {
            const item = e.target.closest('[data-sms-aba]');
            if (item) {
                e.preventDefault();
                // Fechar o user menu antes de abrir o modal
                const menu = document.getElementById('sm-user-menu');
                if (menu) menu.classList.remove('open');
                document.querySelectorAll('.sm-user-trigger.active')
                    .forEach(t => t.classList.remove('active'));
                abrir(item.dataset.smsAba);
            }
        });
    }

    return { init, abrir, fechar, _mudarAba, _forca, _match, _salvarPerfil, _salvarSenha,
             _carregarUsuarios, _acoesAdmin, _resetarSenha, _confirmarReset };
})();
