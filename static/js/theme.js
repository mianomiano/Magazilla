/* ═══════════════════════════════════════════════
   Theme — Syncs with Telegram's actual theme params
   ═══════════════════════════════════════════════ */
(function () {
    var tg = window.Telegram && window.Telegram.WebApp;

    window._isTelegram = !!(tg && tg.initData && tg.initData.length > 0);
    window._authReady = false;

    if (tg) {
        tg.ready();
        tg.expand();

        // Apply ALL Telegram theme params to CSS variables
        applyTelegramTheme();

        // Listen for theme changes
        tg.onEvent('themeChanged', function () {
            applyTelegramTheme();
        });
    }

    function applyTelegramTheme() {
        if (!tg) return;
        var tp = tg.themeParams;
        if (!tp) return;

        var root = document.documentElement.style;

        // Map every Telegram theme param to our CSS variables
        if (tp.bg_color) root.setProperty('--bg-primary', tp.bg_color);
        if (tp.secondary_bg_color) root.setProperty('--bg-secondary', tp.secondary_bg_color);
        if (tp.section_bg_color) root.setProperty('--bg-card', tp.section_bg_color);
        if (tp.text_color) root.setProperty('--text-primary', tp.text_color);
        if (tp.subtitle_text_color) root.setProperty('--text-secondary', tp.subtitle_text_color);
        if (tp.hint_color) root.setProperty('--text-muted', tp.hint_color);
        if (tp.link_color) root.setProperty('--accent', tp.link_color);
        if (tp.button_color) root.setProperty('--accent', tp.button_color);
        if (tp.destructive_text_color) root.setProperty('--danger', tp.destructive_text_color);
        if (tp.accent_text_color) root.setProperty('--accent', tp.accent_text_color);
        if (tp.section_header_text_color) {
            // Use for section titles if desired
        }

        // Header and bottom bar colors
        if (tp.header_bg_color) {
            try { tg.setHeaderColor(tp.header_bg_color); } catch (e) {}
        }
        if (tp.bottom_bar_bg_color) {
            try { tg.setBottomBarColor(tp.bottom_bar_bg_color); } catch (e) {}
        }

        // Derive bg-input from bg_color (slightly darker/lighter)
        if (tp.bg_color) {
            root.setProperty('--bg-input', tp.secondary_bg_color || tp.bg_color);
        }

        // Set border color based on text color with low opacity
        if (tp.hint_color) {
            root.setProperty('--border', tp.hint_color + '22');
        }

        // Light/dark class for any CSS that needs it
        var cs = tg.colorScheme;
        if (cs === 'light') {
            document.body.classList.add('tg-theme-light');
            document.body.classList.remove('tg-theme-dark');
        } else {
            document.body.classList.add('tg-theme-dark');
            document.body.classList.remove('tg-theme-light');
        }
    }

    // Auth: send initData on page load
    if (window._isTelegram) {
        fetch('/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: tg.initData })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.ok) {
                window._tgUser = data.user;
                window._authReady = true;
                updateCartBadge();
                window.dispatchEvent(new Event('tgAuthReady'));
            }
        })
        .catch(function () {});
    }

    // Helper: get auth headers for API calls
    window.getAuthHeaders = function () {
        var headers = { 'Content-Type': 'application/json' };
        if (window._isTelegram) {
            headers['X-Telegram-Init-Data'] = tg.initData;
        }
        return headers;
    };

    // Cart badge updater
    window.updateCartBadge = function () {
        if (!window._isTelegram) return;
        fetch('/api/cart', { headers: getAuthHeaders() })
            .then(function (r) {
                if (!r.ok) return null;
                return r.json();
            })
            .then(function (data) {
                if (!data) return;
                var badge = document.getElementById('cartBadge');
                if (badge) {
                    if (data.count > 0) {
                        badge.textContent = data.count;
                        badge.style.display = 'flex';
                    } else {
                        badge.style.display = 'none';
                    }
                }
            })
            .catch(function () {});
    };

    // Toast notification
    window.showToast = function (message, type) {
        type = type || '';
        var existing = document.querySelector('.toast');
        if (existing) existing.remove();

        var toast = document.createElement('div');
        toast.className = 'toast' + (type ? ' toast-' + type : '');
        toast.textContent = message;
        document.body.appendChild(toast);

        requestAnimationFrame(function () {
            toast.classList.add('show');
        });

        setTimeout(function () {
            toast.classList.remove('show');
            setTimeout(function () { toast.remove(); }, 300);
        }, 2500);
    };

    // Haptic feedback
    window.haptic = function (type) {
        if (tg && tg.HapticFeedback) {
            if (type === 'light') tg.HapticFeedback.impactOccurred('light');
            else if (type === 'medium') tg.HapticFeedback.impactOccurred('medium');
            else if (type === 'heavy') tg.HapticFeedback.impactOccurred('heavy');
            else if (type === 'success') tg.HapticFeedback.notificationOccurred('success');
            else if (type === 'error') tg.HapticFeedback.notificationOccurred('error');
        }
    };

    // Show "open in Telegram" message
    window.showTelegramRequired = function (elementId) {
        var el = document.getElementById(elementId);
        if (el) {
            el.innerHTML = '<div style="text-align:center;padding:60px 20px;">' +
                '<p style="font-size:48px;margin-bottom:16px;">🤖</p>' +
                '<h2 style="margin-bottom:8px;">Open in Telegram</h2>' +
                '<p style="color:var(--text-secondary);margin-bottom:20px;">This page only works inside the Telegram app.</p>' +
                '<a href="/shop" class="btn btn-primary">Browse Shop</a>' +
                '</div>';
        }
    };
})();
