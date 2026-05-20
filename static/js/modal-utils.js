/**
 * modal-utils.js — Sistema de notificações do projeto
 *
 * Substitui alert() e confirm() por toasts estilo do projeto (#1A4D2E).
 *
 * API:
 *   // Confirmação de remoção: ação imediata + botão Desfazer por 5s
 *   WM.confirmar(mensagem, onConfirmar, onDesfazer?)
 *
 *   // Toast informativo (some sozinho)
 *   WM.erro(mensagem)       — vermelho
 *   WM.aviso(mensagem)      — amarelo
 *   WM.sucesso(mensagem)    — verde
 *   WM.info(mensagem)       — cinza
 */

const WM = (() => {

    // ── Container ────────────────────────────────────────────────
    function _container() {
        let c = document.getElementById('_wm_container');
        if (!c) {
            c = document.createElement('div');
            c.id = '_wm_container';
            c.style.cssText = `
                position: fixed;
                bottom: 24px;
                right: 24px;
                z-index: 9999;
                display: flex;
                flex-direction: column-reverse;
                gap: 10px;
                pointer-events: none;
            `;
            document.body.appendChild(c);
        }
        return c;
    }

    // ── Toast base ───────────────────────────────────────────────
    function _toast({ icon, mensagem, cor, duracao, acoes }) {
        const container = _container();

        const el = document.createElement('div');
        el.style.cssText = `
            display: flex;
            align-items: center;
            gap: 12px;
            background: #1e1e1e;
            color: #f5f5f5;
            border-left: 4px solid ${cor};
            border-radius: 8px;
            padding: 12px 16px;
            min-width: 280px;
            max-width: 380px;
            box-shadow: 0 4px 20px rgba(0,0,0,.35);
            pointer-events: all;
            opacity: 0;
            transform: translateX(20px);
            transition: opacity .22s ease, transform .22s ease;
            font-family: inherit;
            font-size: 13px;
            line-height: 1.4;
        `;

        // Ícone
        const iconEl = document.createElement('span');
        iconEl.textContent = icon;
        iconEl.style.cssText = `font-size:16px; flex-shrink:0;`;
        el.appendChild(iconEl);

        // Mensagem
        const msgEl = document.createElement('span');
        msgEl.textContent = mensagem;
        msgEl.style.cssText = `flex:1;`;
        el.appendChild(msgEl);

        // Botões de ação (ex: Desfazer)
        if (acoes) {
            acoes.forEach(({ label, onClick, destaque }) => {
                const btn = document.createElement('button');
                btn.textContent = label;
                btn.style.cssText = `
                    background: ${destaque ? cor : 'transparent'};
                    color: ${destaque ? '#fff' : cor};
                    border: 1px solid ${cor};
                    border-radius: 5px;
                    padding: 3px 10px;
                    font-size: 12px;
                    font-weight: 600;
                    cursor: pointer;
                    flex-shrink: 0;
                    transition: background .15s, color .15s;
                    font-family: inherit;
                `;
                btn.addEventListener('mouseenter', () => {
                    btn.style.background = cor;
                    btn.style.color = '#fff';
                });
                btn.addEventListener('mouseleave', () => {
                    btn.style.background = destaque ? cor : 'transparent';
                    btn.style.color = destaque ? '#fff' : cor;
                });
                btn.addEventListener('click', () => {
                    onClick();
                    _fechar(el);
                });
                el.appendChild(btn);
            });
        }

        // Barra de progresso
        const barra = document.createElement('div');
        barra.style.cssText = `
            position: absolute;
            bottom: 0; left: 0;
            height: 3px;
            background: ${cor};
            opacity: .5;
            border-radius: 0 0 8px 8px;
            width: 100%;
            transition: width ${duracao}ms linear;
        `;
        el.style.position = 'relative';
        el.style.overflow = 'hidden';
        el.appendChild(barra);

        container.appendChild(el);

        // Entrada
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                el.style.opacity = '1';
                el.style.transform = 'translateX(0)';
                barra.style.width = '0%';
            });
        });

        // Auto-fechar
        let timer = setTimeout(() => _fechar(el), duracao);

        // Pausar ao hover
        el.addEventListener('mouseenter', () => {
            clearTimeout(timer);
            barra.style.transition = 'none';
        });
        el.addEventListener('mouseleave', () => {
            barra.style.transition = `width 1500ms linear`;
            barra.style.width = '0%';
            timer = setTimeout(() => _fechar(el), 1500);
        });

        return el;
    }

    function _fechar(el) {
        el.style.opacity = '0';
        el.style.transform = 'translateX(20px)';
        setTimeout(() => el.remove(), 250);
    }

    // ── API pública ──────────────────────────────────────────────

    /**
     * Confirmação de remoção com Desfazer.
     * Executa onConfirmar() imediatamente, mostra toast com botão Desfazer por 5s.
     * Se o usuário clicar Desfazer, chama onDesfazer() (ex: re-adicionar à tabela).
     */
    function confirmar(mensagem, onConfirmar, onDesfazer) {
        // Executa a ação imediatamente
        onConfirmar();

        // Mostra toast com desfazer
        _toast({
            icon: '🗑️',
            mensagem,
            cor: '#e05c5c',
            duracao: 5000,
            acoes: onDesfazer ? [{
                label: 'Desfazer',
                onClick: onDesfazer,
                destaque: false,
            }] : undefined,
        });
    }

    function erro(mensagem) {
        _toast({ icon: '✕', mensagem, cor: '#e05c5c', duracao: 5000, acoes: null });
    }

    function aviso(mensagem) {
        _toast({ icon: '⚠', mensagem, cor: '#f0a500', duracao: 4000, acoes: null });
    }

    function sucesso(mensagem) {
        _toast({ icon: '✓', mensagem, cor: '#2e9e5b', duracao: 3500, acoes: null });
    }

    function info(mensagem) {
        _toast({ icon: 'ℹ', mensagem, cor: '#6c9cb0', duracao: 3500, acoes: null });
    }

    return { confirmar, erro, aviso, sucesso, info };
})();
