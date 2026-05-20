/**
 * user-menu.js — Popover de usuário (sidebar + topbar)
 * Uso: incluir o script e chamar SMUserMenu.init() após o DOM carregar.
 * O HTML dos triggers e do menu é gerado automaticamente.
 */

const SMUserMenu = (() => {

    let menu = null;
    let isAdmin = false;

    function _criarMenu() {
        if (document.getElementById('sm-user-menu')) return;

        const el = document.createElement('div');
        el.id = 'sm-user-menu';
        el.className = 'sm-user-menu';
        document.body.appendChild(el);
        menu = el;

        // Fechar ao clicar fora
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.sm-user-trigger') && !e.target.closest('#sm-user-menu')) {
                _fechar();
            }
        });

        // Fechar com Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') _fechar();
        });
    }

    function _renderMenu(nome, role) {
        const adminItem = isAdmin ? `
            <a href="/admin" class="sm-user-menu-item">
                <i class="ti ti-shield"></i> Admin
            </a>` : '';

        menu.innerHTML = `
            <div class="sm-user-menu-header">
                <div class="sm-user-menu-name">${nome}</div>
                <div class="sm-user-menu-role">${role}</div>
            </div>
            <div class="sm-user-menu-body">
                <a href="#" class="sm-user-menu-item" id="sm-menu-config">
                    <i class="ti ti-settings"></i> Configurações
                </a>
                ${adminItem}
                <div class="sm-user-menu-divider"></div>
                <a href="/logout" class="sm-user-menu-item danger">
                    <i class="ti ti-logout"></i> Sair
                </a>
            </div>`;

        // Configurações (placeholder por enquanto)
        menu.querySelector('#sm-menu-config')?.addEventListener('click', (e) => {
            e.preventDefault();
            _fechar();
            // Futuro: abrir modal de configurações
            WM.info('Configurações em breve!');
        });
    }

    function _abrir(trigger, nome, role) {
        if (!menu) return;
        _renderMenu(nome, role);

        // Posicionar acima ou abaixo do trigger
        const rect = trigger.getBoundingClientRect();
        const menuH = 180; // altura estimada
        const spaceAbove = rect.top;
        const spaceBelow = window.innerHeight - rect.bottom;

        let top, left;
        left = rect.left;

        // Se o trigger está na sidebar (esquerda), abrir à direita
        if (rect.left < 250) {
            left = rect.right + 8;
            top = rect.top - menuH / 2;
        } else {
            // Topbar — abrir abaixo
            left = rect.right - 220;
            top = rect.bottom + 8;
        }

        // Garantir que não sai da tela
        top = Math.max(8, Math.min(top, window.innerHeight - menuH - 8));
        left = Math.max(8, Math.min(left, window.innerWidth - 228));

        menu.style.top  = top + 'px';
        menu.style.left = left + 'px';

        menu.classList.add('open');
        trigger.classList.add('active');
    }

    function _fechar() {
        menu?.classList.remove('open');
        document.querySelectorAll('.sm-user-trigger.active')
            .forEach(t => t.classList.remove('active'));
    }

    function _toggleTrigger(trigger, nome, role) {
        if (menu?.classList.contains('open')) {
            _fechar();
        } else {
            _abrir(trigger, nome, role);
        }
    }

    /**
     * Inicializa o menu nos triggers da página.
     * @param {string} nome - Nome do usuário
     * @param {string} role - Perfil (user | admin)
     */
    function init(nome, role) {
        isAdmin = role === 'admin';
        _criarMenu();

        // Conectar todos os triggers com classe sm-user-trigger
        document.querySelectorAll('.sm-user-trigger').forEach(trigger => {
            trigger.addEventListener('click', (e) => {
                e.stopPropagation();
                _toggleTrigger(trigger, nome, role);
            });
        });
    }

    return { init };
})();
