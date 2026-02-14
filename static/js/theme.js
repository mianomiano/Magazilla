/* ═══════════════════════════════════════════════
   Theme — Syncs with Telegram's color scheme
   ═══════════════════════════════════════════════ */
(function () {
    const tg = window.Telegram && window.Telegram.WebApp;

    if (tg) {
        // Tell Telegram the app is ready
        tg.ready();
        tg.expand();

        // Apply Telegram theme
        const cs = tg.colorScheme; // 'dark' or 'light'
        if (cs === 'light') {
            document.body.classList.add('tg-theme-light');
        }

        // Map Telegram theme params to CSS variables if available
        const tp = tg.themeParams;
        if (tp) {
            const root = document.documentElement.style;
            if (tp.bg_color) root.setProperty('--bg-primary', tp.bg_color);
            if (tp.secondary_bg_color) root.setProperty('--bg-secondary', tp.secondary_bg_color);
            if (tp.text_color) root.setProperty('--text-primary', tp.text_color);
            if (tp.hint_color) root.setProperty('--text-secondary', tp.hint_color);
            if (tp.link_color) root.setProperty('--accent', tp.link_color);
            if (tp.button_color) root.setProperty('--accent', tp.button_color);
            if (tp.button_text_color) {
                // Can use for button text if needed
            }
        }

        // Handle viewport changes
        tg.onEvent('viewportChanged', function () {
            // Adjust layout if needed
        });
    }

    // Auth: send initData on page load
    if (tg && tg.initData) {
        fetch('/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData })
        })
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                window._tgUser = data.user;
                // Update cart badge
                updateCartBadge();
            }
        })
        .catch(() => {});
    }

    // Helper: get initData header for API calls
    window.getAuthHeaders = function () {
        const headers = { 'Content-Type': 'application/json' };
        if (tg && tg.initData) {
            headers['X-Telegram-Init-Data'] = tg.initData;
        }
        return headers;
    };

    // Cart badge updater
    window.updateCartBadge = function () {
        fetch('/api/cart', { headers: getAuthHeaders() })
            .then(r => {
                if (!r.ok) return null;
                return r.json();
            })
            .then(data => {
                if (!data) return;
                const badge = document.getElementById('cartBadge');
                if (badge) {
                    if (data.count > 0) {
                        badge.textContent = data.count;
                        badge.style.display = 'flex';
                    } else {
                        badge.style.display = 'none';
                    }
                }
            })
            .catch(() => {});
    };

    // Toast notification
    window.showToast = function (message, type = '') {
        const existing = document.querySelector('.toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.className = `toast ${type ? 'toast-' + type : ''}`;
        toast.textContent = message;
        document.body.appendChild(toast);

        requestAnimationFrame(() => {
            toast.classList.add('show');
        });

        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 2500);
    };

    // Haptic feedback helper
    window.haptic = function (type) {
        if (tg && tg.HapticFeedback) {
            if (type === 'light') tg.HapticFeedback.impactOccurred('light');
            else if (type === 'medium') tg.HapticFeedback.impactOccurred('medium');
            else if (type === 'heavy') tg.HapticFeedback.impactOccurred('heavy');
            else if (type === 'success') tg.HapticFeedback.notificationOccurred('success');
            else if (type === 'error') tg.HapticFeedback.notificationOccurred('error');
        }
    };
})();
