/* ═══════════════════════════════════════════════
   Profile — Load user data & orders
   ═══════════════════════════════════════════════ */
(function () {
    if (!window._isTelegram) {
        var loading = document.getElementById('profileLoading');
        var content = document.getElementById('profileContent');
        if (loading) loading.style.display = 'none';
        if (content) {
            content.style.display = 'block';
            showTelegramRequired('profileContent');
        }
        return;
    }

    // Wait for auth
    if (!window._authReady) {
        window.addEventListener('tgAuthReady', function () {
            doLoadProfile();
        });
        setTimeout(function () {
            if (!window._profileLoaded) doLoadProfile();
        }, 2000);
    } else {
        doLoadProfile();
    }

    function doLoadProfile() {
        window._profileLoaded = true;

        fetch('/api/profile', { headers: getAuthHeaders() })
            .then(function (r) {
                if (!r.ok) throw new Error('Auth');
                return r.json();
            })
            .then(function (data) {
                var loading = document.getElementById('profileLoading');
                var content = document.getElementById('profileContent');
                if (loading) loading.style.display = 'none';
                if (content) content.style.display = 'block';

                var u = data.user;

                var avatarEl = document.getElementById('profileAvatar');
                if (avatarEl) {
                    if (u.photo_url) {
                        avatarEl.innerHTML = '<img src="' + u.photo_url + '" alt="">';
                    } else {
                        avatarEl.textContent = (u.first_name || 'U').charAt(0).toUpperCase();
                    }
                }

                var nameEl = document.getElementById('profileName');
                if (nameEl) {
                    nameEl.textContent = [u.first_name, u.last_name].filter(Boolean).join(' ') || 'User';
                }

                var usernameEl = document.getElementById('profileUsername');
                if (usernameEl) {
                    usernameEl.textContent = u.username ? '@' + u.username : '';
                }

                var spentEl = document.getElementById('profileSpent');
                if (spentEl) spentEl.textContent = u.total_spent || 0;

                var ordersEl = document.getElementById('profileOrders');
                if (ordersEl) ordersEl.textContent = data.orders.length;

                var sinceEl = document.getElementById('profileSince');
                if (sinceEl && u.member_since) {
                    var since = new Date(u.member_since);
                    var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                    sinceEl.textContent = months[since.getMonth()] + ' ' + since.getFullYear();
                }

                // Admin button
                if (window._tgUser && window._tgUser.is_admin) {
                    var adminBtn = document.getElementById('adminButton');
                    if (adminBtn) adminBtn.style.display = 'block';
                }

                // Orders
                var list = document.getElementById('ordersList');
                var noOrders = document.getElementById('noOrders');
                
                if (data.orders.length === 0) {
                    if (noOrders) noOrders.style.display = 'block';
                    return;
                }

                if (list) {
                    data.orders.forEach(function (o) {
                        var div = document.createElement('div');
                        div.className = 'order-card';
                        var date = new Date(o.created_at);
                        var statusBadge = o.status === 'paid'
                            ? '<span class="badge badge-success">Paid</span>'
                            : o.status === 'refunded'
                            ? '<span class="badge badge-error">Refunded</span>'
                            : '<span class="badge badge-warning">Pending</span>';

                        div.innerHTML =
                            '<div class="order-card-left">' +
                            '<div class="order-card-id">Order #' + o.id + '</div>' +
                            '<div class="order-card-date">' + date.toLocaleDateString() + ' · ' + o.items_count + ' items</div>' +
                            '</div>' +
                            '<div class="order-card-right">' +
                            '<div class="order-card-amount">⭐ ' + o.total_stars + '</div>' +
                            statusBadge +
                            '</div>';
                        list.appendChild(div);
                    });
                }
            })
            .catch(function () {
                var loading = document.getElementById('profileLoading');
                var content = document.getElementById('profileContent');
                if (loading) loading.style.display = 'none';
                if (content) {
                    content.style.display = 'block';
                    content.innerHTML = '<div class="empty-state"><p>Could not load profile. Try again.</p></div>';
                }
            });
    }
})();
