/* ═══════════════════════════════════════════════
   Profile — Load user data & orders
   ═══════════════════════════════════════════════ */
(function () {
    fetch('/api/profile', { headers: getAuthHeaders() })
        .then(r => {
            if (!r.ok) throw new Error('Auth');
            return r.json();
        })
        .then(data => {
            document.getElementById('profileLoading').style.display = 'none';
            document.getElementById('profileContent').style.display = 'block';

            const u = data.user;

            // Avatar
            const avatarEl = document.getElementById('profileAvatar');
            if (u.photo_url) {
                avatarEl.innerHTML = `<img src="${u.photo_url}" alt="">`;
            } else {
                avatarEl.textContent = (u.first_name || 'U').charAt(0).toUpperCase();
            }

            // Name
            document.getElementById('profileName').textContent =
                [u.first_name, u.last_name].filter(Boolean).join(' ') || 'User';
            document.getElementById('profileUsername').textContent =
                u.username ? '@' + u.username : '';

            // Stats
            document.getElementById('profileSpent').textContent = u.total_spent || 0;
            document.getElementById('profileOrders').textContent = data.orders.length;

            const since = new Date(u.member_since);
            const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            document.getElementById('profileSince').textContent =
                months[since.getMonth()] + ' ' + since.getFullYear();

            // Orders
            const list = document.getElementById('ordersList');
            if (data.orders.length === 0) {
                document.getElementById('noOrders').style.display = 'block';
                return;
            }

            data.orders.forEach(o => {
                const div = document.createElement('div');
                div.className = 'order-card';
                const date = new Date(o.created_at);
                const statusBadge = o.status === 'paid'
                    ? '<span class="badge badge-success">Paid</span>'
                    : o.status === 'refunded'
                    ? '<span class="badge badge-error">Refunded</span>'
                    : '<span class="badge badge-warning">Pending</span>';

                div.innerHTML = `
                    <div class="order-card-left">
                        <div class="order-card-id">Order #${o.id}</div>
                        <div class="order-card-date">${date.toLocaleDateString()} · ${o.items_count} items</div>
                    </div>
                    <div class="order-card-right">
                        <div class="order-card-amount">⭐ ${o.total_stars}</div>
                        ${statusBadge}
                    </div>
                `;
                list.appendChild(div);
            });
        })
        .catch(() => {
            document.getElementById('profileLoading').innerHTML =
                '<p>Please open this app from Telegram</p>';
        });
})();
