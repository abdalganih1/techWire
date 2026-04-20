/* ══════════════════════════════════════
   مُراسِل — Frontend Logic
   ══════════════════════════════════════ */

// ─── State ───
const state = {
    currentTab: 'new',
    page: 1,
    limit: 20,
    searchQuery: '',
    currentCategory: '',
    currentSource: '',
    sortOrder: 'smart',
    aiSearch: false,
    theme: localStorage.getItem('murrasil-theme') || 'midnight',
    tts: { speaking: false, currentId: null },
    _cachedNews: null,  // client-side cache for instant filtering
    _cacheTab: null,
};

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ─── DOM Elements ───
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const els = {
    // Topbar
    btnFetchNow: $('#btnFetchNow'),
    lastFetchTimestamp: $('#lastFetchTimestamp'),
    inpSearch: $('#inpSearch'),
    btnClearSearch: $('#btnClearSearch'),
    btnAiSearch: $('#btnAiSearch'),
    btnNotifications: $('#btnNotifications'),
    notifBadge: $('#notifBadge'),
    btnTheme: $('#btnTheme'),
    btnOpenSettings: $('#btnOpenSettings'),

    // Theme
    themePicker: $('#themePicker'),

    // Stats
    statTotal: $('#statTotal'),
    statSources: $('#statSources'),
    statClusters: $('#statClusters'),

    // Tabs
    tabs: $$('.tab'),
    badgeNew: $('#badge-new'),
    badgeApproved: $('#badge-approved'),
    badgeRejected: $('#badge-rejected'),

    // Filters
    selSort: $('#selSort'),
    categoriesBar: $('#categoriesBar'),
    sourcesBar: $('#sourcesBar'),

    // Content
    contentArea: $('#contentArea'),
    btnPrevPage: $('#btnPrevPage'),
    btnNextPage: $('#btnNextPage'),
    pageIndicator: $('#pageIndicator'),

    // TTS
    ttsBar: $('#ttsBar'),
    ttsTitle: $('#ttsTitle'),
    ttsPlayPause: $('#ttsPlayPause'),
    ttsSpeed: $('#ttsSpeed'),
    ttsStop: $('#ttsStop'),

    // Notifications Panel
    notifOverlay: $('#notifOverlay'),
    notifPanel: $('#notifPanel'),
    notifList: $('#notifList'),
    btnCloseNotif: $('#btnCloseNotif'),
    btnMarkAllRead: $('#btnMarkAllRead'),

    // Settings Panel
    settingsOverlay: $('#settingsOverlay'),
    settingsPanel: $('#settingsPanel'),
    btnCloseSettings: $('#btnCloseSettings'),
    btnSaveSettings: $('#btnSaveSettings'),
    selInterval: $('#selInterval'),
    selMaxAge: $('#selMaxAge'),
    sourcesList: $('#sourcesList'),
    prefsList: $('#prefsList'),
    btnAddSource: $('#btnAddSource'),
    inpSourceName: $('#inpSourceName'),
    inpSourceUrl: $('#inpSourceUrl'),
    inpSourceLang: $('#inpSourceLang'),

    // Modals
    articleModal: $('#articleModal'),
    modalTitle: $('#modalTitle'),
    modalBody: $('#modalBody'),
    btnCloseModal: $('#btnCloseModal'),
    btnCopyArticle: $('#btnCopyArticle'),
    btnListenArticle: $('#btnListenArticle'),
    clusterModal: $('#clusterModal'),
    clusterBody: $('#clusterBody'),
    btnCloseCluster: $('#btnCloseCluster'),

    // Offline
    offlineBanner: $('#offlineBanner'),

    // Toast
    toast: $('#toast'),
    toastMsg: $('#toastMsg'),

    // Delete buttons
    btnClearOld: $('#btnClearOld'),
    btnClearAll: $('#btnClearAll'),
    btnToggleLog: $('#btnToggleLog'),

    // Progress
    fetchProgress: $('#fetchProgress'),
    progressLog: $('#progressLog'),
    progressTitle: $('#progressTitle'),
    btnCloseProgress: $('#btnCloseProgress'),
};


// ══════════════════════════════════════
// INIT
// ══════════════════════════════════════
async function init() {
    applyTheme(state.theme);
    setupEventListeners();
    await Promise.all([
        updateCounts(),
        loadNews(),
        loadStats(),
        loadSettings(),
        loadSources(),
        loadPreferences(),
        updateNotifBadge()
    ]);
    setupOfflineDetection();
    registerServiceWorker();
}


// ══════════════════════════════════════
// API HELPER
// ══════════════════════════════════════
async function api(url, method = 'GET', body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    try {
        const res = await fetch(url, opts);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (e) {
        console.error("API Error:", e);
        return null;
    }
}


// ══════════════════════════════════════
// TOAST
// ══════════════════════════════════════
let toastTimeout;
function showToast(msg, isError = false) {
    const toast = els.toast;
    els.toastMsg.textContent = msg;
    const icon = toast.querySelector('i');
    icon.className = isError
        ? "fa-solid fa-circle-xmark"
        : "fa-solid fa-circle-check";
    toast.className = `toast ${isError ? 'error' : 'success'}`;
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
        toast.classList.add('hidden');
    }, 3500);
}


// ══════════════════════════════════════
// THEME SYSTEM (5 themes)
// ══════════════════════════════════════
function applyTheme(theme) {
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem('murrasil-theme', theme);
    state.theme = theme;
    // Update active button
    $$('.theme-option').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === theme);
    });
}


// ══════════════════════════════════════
// EVENT LISTENERS
// ══════════════════════════════════════
function setupEventListeners() {
    // ─── Tabs ───
    els.tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            if (tab.dataset.tab === state.currentTab) return;
            els.tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            state.currentTab = tab.dataset.tab;
            state.page = 1;
            loadNews();
        });
    });

    // ─── Pagination ───
    els.btnPrevPage.addEventListener('click', () => { if (state.page > 1) { state.page--; loadNews(true); } });
    els.btnNextPage.addEventListener('click', () => { state.page++; loadNews(true); });

    // ─── Search ───
    let searchTimeout;
    els.inpSearch.addEventListener('input', (e) => {
        const val = e.target.value;
        els.btnClearSearch.classList.toggle('hidden', val.length === 0);
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            state.searchQuery = val;
            state.aiSearch = false;
            state.page = 1;
            loadNews();
        }, 500);
    });

    els.btnClearSearch.addEventListener('click', () => {
        els.inpSearch.value = '';
        els.btnClearSearch.classList.add('hidden');
        state.searchQuery = '';
        state.aiSearch = false;
        state.page = 1;
        loadNews();
    });

    els.btnAiSearch.addEventListener('click', () => {
        const val = els.inpSearch.value.trim();
        if (!val) return showToast("يرجى إدخال نص للبحث", true);
        state.searchQuery = val;
        state.aiSearch = true;
        state.page = 1;

        const ogHtml = els.btnAiSearch.innerHTML;
        els.btnAiSearch.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
        els.btnAiSearch.disabled = true;

        loadNews().then(() => {
            els.btnAiSearch.innerHTML = ogHtml;
            els.btnAiSearch.disabled = false;
        });
    });

    // ─── Sort ───
    els.selSort.addEventListener('change', () => {
        state.sortOrder = els.selSort.value;
        state.page = 1;
        loadNews();
    });

    // ─── Fetch Now ───
    els.btnFetchNow.addEventListener('click', manualFetch);

    // ─── Delete buttons ───
    els.btnClearOld.addEventListener('click', async () => {
        if (!confirm('هل تريد حذف الأخبار الأقدم من 24 ساعة؟')) return;
        els.btnClearOld.disabled = true;
        const res = await api('/api/news/clear-old', 'POST');
        els.btnClearOld.disabled = false;
        if (res?.status === 'success') {
            showToast(`تم حذف ${res.deleted} خبر قديم`);
            updateCounts(); loadStats(); loadNews();
        }
    });
    els.btnClearAll.addEventListener('click', async () => {
        if (!confirm('هل تريد حذف جميع الأخبار؟ لا يمكن التراجع!')) return;
        els.btnClearAll.disabled = true;
        const res = await api('/api/news/clear-all', 'POST');
        els.btnClearAll.disabled = false;
        if (res?.status === 'success') {
            showToast(`تم حذف ${res.deleted} خبر`);
            updateCounts(); loadStats(); loadNews();
        }
    });

    // ─── Progress close & toggle ───
    els.btnCloseProgress.addEventListener('click', () => {
        els.fetchProgress.classList.add('hidden');
    });
    els.btnToggleLog.addEventListener('click', async () => {
        const isHidden = els.fetchProgress.classList.contains('hidden');
        if (isHidden) {
            // Fetch current state from API before showing
            try {
                const prog = await api('/api/news/fetch-progress');
                if (prog) {
                    const spinner = els.fetchProgress.querySelector('.progress-spinner');
                    if (prog.active && !prog.done) {
                        spinner.classList.remove('done');
                        els.progressTitle.textContent = 'جاري الجلب...';
                    } else if (prog.done && prog.messages?.length > 0) {
                        spinner.classList.add('done');
                        els.progressTitle.textContent = `اكتمل الجلب — ${prog.total_fetched} خبر`;
                    } else {
                        spinner.classList.add('done');
                        els.progressTitle.textContent = 'لا يوجد جلب نشط';
                    }
                    // Render messages if any
                    if (prog.messages?.length > 0 && els.progressLog.children.length === 0) {
                        els.progressLog.innerHTML = '';
                        for (const msg of prog.messages) {
                            const cssClass = msg.text.startsWith('❌') ? 'error' :
                                            (msg.text.startsWith('✅') || msg.text.startsWith('🎉')) ? 'success' : '';
                            const div = document.createElement('div');
                            div.className = `progress-msg ${cssClass}`;
                            div.innerHTML = `<span class="progress-time">${msg.time}</span><span class="progress-text">${msg.text}</span>`;
                            els.progressLog.appendChild(div);
                        }
                        els.progressLog.scrollTop = els.progressLog.scrollHeight;
                    }
                }
            } catch(e) {}
        }
        els.fetchProgress.classList.toggle('hidden');
    });

    // ─── Theme ───
    els.btnTheme.addEventListener('click', (e) => {
        e.stopPropagation();
        els.themePicker.classList.toggle('hidden');
    });
    $$('.theme-option').forEach(btn => {
        btn.addEventListener('click', () => {
            applyTheme(btn.dataset.theme);
            els.themePicker.classList.add('hidden');
        });
    });
    document.addEventListener('click', (e) => {
        if (!els.themePicker.contains(e.target) && e.target !== els.btnTheme) {
            els.themePicker.classList.add('hidden');
        }
    });

    // ─── Notifications Panel ───
    els.btnNotifications.addEventListener('click', () => togglePanel('notif', true));
    els.btnCloseNotif.addEventListener('click', () => togglePanel('notif', false));
    els.notifOverlay.addEventListener('click', () => togglePanel('notif', false));
    els.btnMarkAllRead.addEventListener('click', async () => {
        await api('/api/notifications/read', 'POST');
        showToast('تم تعليم الكل كمقروء');
        updateNotifBadge();
        loadNotifications();
    });

    // ─── Settings Panel ───
    els.btnOpenSettings.addEventListener('click', () => togglePanel('settings', true));
    els.btnCloseSettings.addEventListener('click', () => togglePanel('settings', false));
    els.settingsOverlay.addEventListener('click', () => togglePanel('settings', false));
    els.btnSaveSettings.addEventListener('click', saveSettings);
    els.btnAddSource.addEventListener('click', addSource);

    // ─── Article Modal ───
    els.btnCloseModal.addEventListener('click', () => closeModal('articleModal'));
    els.articleModal.addEventListener('click', (e) => {
        if (e.target === els.articleModal) closeModal('articleModal');
    });
    els.btnCopyArticle.addEventListener('click', copyArticle);
    els.btnListenArticle.addEventListener('click', () => {
        const text = els.modalTitle.textContent + '. ' + els.modalBody.textContent;
        startTTS(text, els.modalTitle.textContent);
    });

    // ─── Cluster Modal ───
    els.btnCloseCluster.addEventListener('click', () => closeModal('clusterModal'));
    els.clusterModal.addEventListener('click', (e) => {
        if (e.target === els.clusterModal) closeModal('clusterModal');
    });

    // ─── TTS Controls ───
    els.ttsPlayPause.addEventListener('click', toggleTTS);
    els.ttsStop.addEventListener('click', stopTTS);
    els.ttsSpeed.addEventListener('change', () => {
        if (speechSynthesis.speaking) {
            // Must restart to change rate
            const text = state.tts.currentText;
            const title = state.tts.currentTitleText;
            stopTTS();
            setTimeout(() => startTTS(text, title), 100);
        }
    });

    // ─── Keyboard ───
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeModal('articleModal');
            closeModal('clusterModal');
            togglePanel('settings', false);
            togglePanel('notif', false);
            els.themePicker.classList.add('hidden');
        }
    });
}


// ══════════════════════════════════════
// NEWS LOADING & RENDERING
// ══════════════════════════════════════
const CATEGORY_ICONS = {
    'تكنولوجيا': '📱', 'رياضة': '⚽', 'صحة': '💊',
    'اقتصاد': '💰', 'سياسة': '🏛️', 'فن وترفيه': '🎬',
    'موضة وجمال': '💄', 'علوم': '🔬', 'منوعات': '📰', 'عاجل': '🔴'
};

function parseDate(isoStr) {
    if (!isoStr) return "غير محدد";
    const date = new Date(isoStr);
    if (isNaN(date)) return "غير محدد";
    const diff = Math.floor((Date.now() - date) / 60000);
    if (diff < 1) return 'الآن';
    if (diff < 60) return `منذ ${diff} د`;
    if (diff < 1440) return `منذ ${Math.floor(diff / 60)} س`;
    return `منذ ${Math.floor(diff / 1440)} يوم`;
}

async function loadNews(useCache = false) {
    // Try to render from cache for instant filtering
    if (useCache && state._cachedNews && state._cacheTab === state.currentTab && !state.searchQuery) {
        renderFromCache();
        return;
    }

    els.contentArea.innerHTML = '<div class="loading-state"><div class="loader"></div><p>جاري تحميل الأخبار...</p></div>';

    // Fetch ALL for this tab (cache-friendly)
    let url = `/api/news?status=${state.currentTab}&page=1&limit=500&sort=${state.sortOrder}`;
    if (state.searchQuery) url += `&q=${encodeURIComponent(state.searchQuery)}&ai_search=${state.aiSearch}`;

    const data = await api(url);

    if (!data) {
        els.contentArea.innerHTML = '<div class="empty-state"><i class="fa-solid fa-triangle-exclamation"></i><p>خطأ في تحميل الأخبار</p></div>';
        return;
    }

    // Cache the full result
    state._cachedNews = data.data;
    state._cacheTab = state.currentTab;

    renderFromCache();

    // Save to IndexedDB for offline
    if (data.data.length > 0) {
        saveToOfflineCache(data.data);
    }
}

function renderFromCache() {
    let filtered = state._cachedNews || [];

    // Apply local filters
    if (state.currentCategory) {
        filtered = filtered.filter(n => n.category === state.currentCategory);
    }
    if (state.currentSource) {
        filtered = filtered.filter(n => n.source_name === state.currentSource);
    }

    // Pagination
    const total = filtered.length;
    const start = (state.page - 1) * state.limit;
    const paged = filtered.slice(start, start + state.limit);

    if (paged.length === 0) {
        els.contentArea.innerHTML = '<div class="empty-state"><i class="fa-regular fa-folder-open"></i><p>لا توجد أخبار تطابق بحثك</p></div>';
    } else {
        const cards = paged.map((item, i) => renderCard(item, i)).join('');
        els.contentArea.innerHTML = `<div class="news-grid">${cards}</div>`;
        attachCardListeners();
    }

    const hasMore = (state.page * state.limit) < total;
    els.btnPrevPage.disabled = state.page === 1;
    els.btnNextPage.disabled = !hasMore;
    els.pageIndicator.textContent = `صفحة ${state.page}`;
}

function renderCard(item, index) {
    const timeAgo = parseDate(item.published_at);
    const catIcon = CATEGORY_ICONS[item.category] || '📰';
    const catClass = item.category || 'منوعات';
    const clusterSize = item.cluster_size || 1;
    const delay = Math.min(index * 0.05, 0.5);

    let imageHtml = '';
    if (item.image_url) {
        imageHtml = `<img class="card-image" src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.title_ar)}" loading="lazy" onerror="this.outerHTML='<div class=card-image-placeholder></div>'">`;
    } else {
        imageHtml = '<div class="card-image-placeholder"></div>';
    }

    let actionsHtml = '';
    if (state.currentTab === 'new') {
        actionsHtml = `
            <div class="card-actions">
                <button class="card-btn listen" data-id="${item.id}" title="استماع">
                    <i class="fa-solid fa-headphones"></i>
                </button>
                <button class="card-btn approve" data-id="${item.id}">
                    <i class="fa-solid fa-wand-magic-sparkles"></i> كتابة الخبر
                </button>
                <button class="card-btn reject" data-id="${item.id}" title="رفض">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>`;
    } else if (state.currentTab === 'approved') {
        actionsHtml = `
            <div class="card-actions">
                <button class="card-btn listen" data-id="${item.id}" title="استماع">
                    <i class="fa-solid fa-headphones"></i>
                </button>
                <button class="card-btn view" data-id="${item.id}">
                    <i class="fa-regular fa-eye"></i> عرض المقال
                </button>
            </div>`;
    } else if (state.currentTab === 'rejected') {
        actionsHtml = `
            <div class="card-actions">
                <button class="card-btn restore" data-id="${item.id}">
                    <i class="fa-solid fa-rotate-left"></i> استعادة
                </button>
            </div>`;
    }

    let clusterBadge = '';
    if (clusterSize > 1 && item.cluster_id) {
        clusterBadge = `<span class="cluster-badge" data-cluster="${item.cluster_id}">
            <i class="fa-solid fa-layer-group"></i> من ${clusterSize} مصادر
        </span>`;
    }

    return `
        <article class="news-card" id="card-${escapeHtml(item.id)}" style="animation-delay: ${delay}s">
            ${imageHtml}
            <div class="card-body">
                <div class="card-meta">
                    <div class="card-meta-right">
                        <span class="cat-badge ${escapeHtml(catClass)}">${catIcon} ${escapeHtml(item.category) || 'منوعات'}</span>
                        ${clusterBadge}
                    </div>
                    <span class="time-tag">${timeAgo}</span>
                </div>
                <h3 class="card-title">
                    <a href="${escapeHtml(item.original_url || '#')}" target="_blank" rel="noopener">${escapeHtml(item.title_ar) || ''}</a>
                </h3>
                <p class="card-summary">${escapeHtml(item.summary_ar || item.article_ar) || ''}</p>
                <div class="card-meta" style="margin-top:auto; padding-top:8px;">
                    <span class="source-tag"><i class="fa-solid fa-globe"></i> ${escapeHtml(item.source_name) || ''}</span>
                </div>
                ${actionsHtml}
            </div>
        </article>`;
}

function attachCardListeners() {
    // Approve
    $$('.card-btn.approve').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.dataset.id;
            const card = $(`#card-${id}`);
            const ogHtml = btn.innerHTML;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> جاري الكتابة...';
            btn.disabled = true;

            const res = await api(`/api/news/${id}/approve`, 'POST');
            if (res?.status === 'success') {
                showToast('تم توليد المقال بنجاح!');
                card.style.opacity = '0';
                card.style.transform = 'scale(0.9)';
                setTimeout(() => card.style.display = 'none', 300);
                updateCounts();
                openArticleModal(card.querySelector('.card-title a')?.textContent || '', res.article_ar);
            } else {
                btn.innerHTML = ogHtml;
                btn.disabled = false;
                showToast('فشل في توليد المقال', true);
            }
        });
    });

    // Reject
    $$('.card-btn.reject').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.dataset.id;
            const card = $(`#card-${id}`);
            await api(`/api/news/${id}/reject`, 'POST');
            card.style.opacity = '0';
            card.style.transform = 'scale(0.9)';
            setTimeout(() => card.style.display = 'none', 300);
            updateCounts();
        });
    });

    // Restore
    $$('.card-btn.restore').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.dataset.id;
            const card = $(`#card-${id}`);
            await api(`/api/news/${id}/restore`, 'POST');
            card.style.display = 'none';
            updateCounts();
            showToast('تمت الاستعادة');
        });
    });

    // View Article
    $$('.card-btn.view').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.dataset.id;
            const res = await api(`/api/news/${id}`);
            if (res) openArticleModal(res.title_ar, res.article_ar || res.summary_ar);
        });
    });

    // Listen (TTS)
    $$('.card-btn.listen').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = btn.dataset.id;
            const card = $(`#card-${id}`);
            const title = card.querySelector('.card-title a')?.textContent || '';
            const summary = card.querySelector('.card-summary')?.textContent || '';
            const text = title + '. ' + summary;
            startTTS(text, title);
            // Track interaction
            api(`/api/news/${id}/listen`, 'POST');
        });
    });

    // Cluster badge
    $$('.cluster-badge').forEach(badge => {
        badge.addEventListener('click', async () => {
            const clusterId = badge.dataset.cluster;
            const res = await api(`/api/news/cluster/${clusterId}`);
            if (res) openClusterModal(res.articles);
        });
    });

    // Track reads on card click (title click)
    $$('.card-title a').forEach(link => {
        link.addEventListener('click', () => {
            const card = link.closest('.news-card');
            const id = card.id.replace('card-', '');
            api(`/api/news/${id}/read`, 'POST');
        });
    });
}


// ══════════════════════════════════════
// COUNTS & STATS
// ══════════════════════════════════════
async function updateCounts() {
    const counts = await api('/api/news/counts');
    if (counts) {
        els.badgeNew.textContent = counts.new || 0;
        els.badgeApproved.textContent = counts.approved || 0;
        els.badgeRejected.textContent = counts.rejected || 0;
    }

    // Update category chips
    if (state.currentTab === 'new') {
        const catCounts = await api('/api/categories/counts');
        if (catCounts) {
            let html = `<button data-cat="" class="chip ${state.currentCategory === '' ? 'active' : ''}">الكل</button>`;
            for (const [cat, count] of Object.entries(catCounts)) {
                if (!cat) continue;
                const icon = CATEGORY_ICONS[cat] || '📰';
                const isActive = state.currentCategory === cat;
                html += `<button data-cat="${escapeHtml(cat)}" class="chip ${isActive ? 'active' : ''}">${icon} ${escapeHtml(cat)} (${count})</button>`;
            }
            els.categoriesBar.innerHTML = html;
            $$('#categoriesBar .chip').forEach(btn => {
                btn.addEventListener('click', () => {
                    // Instantly update active state visually
                    $$('#categoriesBar .chip').forEach(c => c.classList.remove('active'));
                    btn.classList.add('active');
                    state.currentCategory = btn.dataset.cat;
                    state.page = 1;
                    loadNews(true);
                    // Update source chips counts (light refresh)
                    refreshSourceChips();
                });
            });
        }

        await refreshSourceChips();
    }
}

async function refreshSourceChips() {
    const srcCounts = await api('/api/sources/counts');
    if (srcCounts) {
        let html = `<button data-src="" class="chip ${state.currentSource === '' ? 'active' : ''}">كل المصادر</button>`;
        for (const [src, count] of Object.entries(srcCounts)) {
            if (!src) continue;
            const isActive = state.currentSource === src;
            html += `<button data-src="${escapeHtml(src)}" class="chip ${isActive ? 'active' : ''}">${escapeHtml(src)} (${count})</button>`;
        }
        els.sourcesBar.innerHTML = html;
        $$('#sourcesBar .chip').forEach(btn => {
            btn.addEventListener('click', () => {
                // Instantly update active state visually
                $$('#sourcesBar .chip').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                state.currentSource = btn.dataset.src;
                state.page = 1;
                loadNews(true);
            });
        });
    }
}

async function loadStats() {
    const stats = await api('/api/stats');
    if (stats) {
        els.statTotal.textContent = stats.total_articles || 0;
        els.statSources.textContent = stats.active_sources || 0;
        els.statClusters.textContent = stats.story_clusters || 0;
    }
}


// ══════════════════════════════════════
// MODALS
// ══════════════════════════════════════
function openArticleModal(title, body) {
    els.modalTitle.textContent = title;
    els.modalBody.innerHTML = body || 'لا يوجد محتوى';
    els.articleModal.classList.remove('hidden');
}

function openClusterModal(articles) {
    els.clusterBody.innerHTML = articles.map(a => `
        <div class="notif-item" style="flex-direction:column">
            <div style="display:flex;justify-content:space-between;width:100%">
                <span class="source-tag"><i class="fa-solid fa-globe"></i> ${escapeHtml(a.source_name)}</span>
                <span class="time-tag">${parseDate(a.published_at)}</span>
            </div>
            <h4 style="font-weight:700;margin:8px 0 4px">${escapeHtml(a.title_ar)}</h4>
            <p style="font-size:0.85rem;color:var(--text-secondary);line-height:1.7">${escapeHtml(a.summary_ar) || ''}</p>
        </div>
    `).join('');
    els.clusterModal.classList.remove('hidden');
}

function closeModal(id) {
    $(`#${id}`).classList.add('hidden');
}

function copyArticle() {
    navigator.clipboard.writeText(els.modalTitle.textContent + '\n\n' + els.modalBody.textContent)
        .then(() => showToast('تم النسخ!'));
}


// ══════════════════════════════════════
// TTS (Text-to-Speech)
// ══════════════════════════════════════
function startTTS(text, title) {
    stopTTS();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'ar-SA';
    utterance.rate = parseFloat(els.ttsSpeed.value);

    // Try to find Arabic voice
    const voices = speechSynthesis.getVoices();
    const arVoice = voices.find(v => v.lang.startsWith('ar'));
    if (arVoice) utterance.voice = arVoice;

    utterance.onend = () => {
        state.tts.speaking = false;
        els.ttsBar.classList.add('hidden');
    };

    speechSynthesis.speak(utterance);
    state.tts.speaking = true;
    state.tts.currentText = text;
    state.tts.currentTitleText = title;
    state.tts.currentId = null;

    els.ttsTitle.textContent = title;
    els.ttsBar.classList.remove('hidden');
    els.ttsPlayPause.innerHTML = '<i class="fa-solid fa-pause"></i>';
}

function toggleTTS() {
    if (speechSynthesis.paused) {
        speechSynthesis.resume();
        els.ttsPlayPause.innerHTML = '<i class="fa-solid fa-pause"></i>';
    } else if (speechSynthesis.speaking) {
        speechSynthesis.pause();
        els.ttsPlayPause.innerHTML = '<i class="fa-solid fa-play"></i>';
    }
}

function stopTTS() {
    speechSynthesis.cancel();
    state.tts.speaking = false;
    els.ttsBar.classList.add('hidden');
}

// Load voices
speechSynthesis.onvoiceschanged = () => speechSynthesis.getVoices();


// ══════════════════════════════════════
// NOTIFICATIONS
// ══════════════════════════════════════
async function updateNotifBadge() {
    const res = await api('/api/notifications?unread_only=true&limit=1');
    if (res) {
        const count = res.unread_count || 0;
        els.notifBadge.textContent = count;
        els.notifBadge.classList.toggle('hidden', count === 0);
    }
}

async function loadNotifications() {
    const res = await api('/api/notifications?limit=30');
    if (!res) return;

    if (res.notifications.length === 0) {
        els.notifList.innerHTML = '<div class="empty-state"><i class="fa-regular fa-bell-slash"></i><p>لا توجد إشعارات</p></div>';
        return;
    }

    els.notifList.innerHTML = res.notifications.map(n => `
        <div class="notif-item ${n.read ? '' : 'unread'}">
            <div class="notif-icon"><i class="fa-solid fa-newspaper"></i></div>
            <div class="notif-content">
                <div class="notif-title">${escapeHtml(n.title)}</div>
                <div class="notif-body">${escapeHtml(n.body)}</div>
                <div class="notif-time">${parseDate(n.created_at)}</div>
            </div>
        </div>
    `).join('');
}


// ══════════════════════════════════════
// PANELS
// ══════════════════════════════════════
function togglePanel(type, show) {
    const panel = type === 'notif' ? els.notifPanel : els.settingsPanel;
    const overlay = type === 'notif' ? els.notifOverlay : els.settingsOverlay;

    if (show) {
        panel.classList.remove('hidden');
        overlay.classList.remove('hidden');
        if (type === 'notif') loadNotifications();
    } else {
        panel.classList.add('hidden');
        overlay.classList.add('hidden');
    }
}


// ══════════════════════════════════════
// SETTINGS
// ══════════════════════════════════════
async function loadSettings() {
    const sets = await api('/api/settings');
    if (sets) {
        if (sets.FETCH_INTERVAL_MINUTES) els.selInterval.value = sets.FETCH_INTERVAL_MINUTES;
        if (sets.MAX_NEWS_AGE_HOURS) els.selMaxAge.value = sets.MAX_NEWS_AGE_HOURS;
    }
}

async function saveSettings() {
    const updates = {
        FETCH_INTERVAL_MINUTES: els.selInterval.value,
        MAX_NEWS_AGE_HOURS: els.selMaxAge.value
    };

    const ogHtml = els.btnSaveSettings.innerHTML;
    els.btnSaveSettings.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> جاري الحفظ...';

    // Save settings
    await api('/api/settings', 'POST', updates);

    // Save preferences
    const prefInputs = $$('.pref-notify-toggle');
    const prefUpdates = [];
    prefInputs.forEach(inp => {
        prefUpdates.push({
            category: inp.dataset.category,
            weight: 1.0,
            notify: inp.checked ? 1 : 0
        });
    });
    if (prefUpdates.length > 0) {
        await api('/api/preferences', 'POST', prefUpdates);
    }

    els.btnSaveSettings.innerHTML = ogHtml;
    showToast('تم حفظ الإعدادات');
    togglePanel('settings', false);
}


// ══════════════════════════════════════
// SOURCES
// ══════════════════════════════════════
async function loadSources() {
    const sources = await api('/api/sources');
    if (!sources) return;

    els.sourcesList.innerHTML = sources.map(s => `
        <div class="source-item">
            <span class="source-item-name">${escapeHtml(s.name)}</span>
            <div class="source-item-controls">
                <input type="checkbox" class="source-toggle" ${s.enabled ? 'checked' : ''}
                       onchange="window._toggleSource(${s.id}, this.checked)">
                <button class="source-delete" onclick="window._deleteSource(${s.id})">
                    <i class="fa-solid fa-trash"></i>
                </button>
            </div>
        </div>
    `).join('');
}

window._toggleSource = async (id, enabled) => {
    await api(`/api/sources/${id}`, 'PUT', { enabled: enabled ? 1 : 0 });
};

window._deleteSource = async (id) => {
    if (!confirm('هل أنت متأكد من حذف المصدر؟')) return;
    await api(`/api/sources/${id}`, 'DELETE');
    loadSources();
};

async function addSource() {
    const name = els.inpSourceName.value.trim();
    const url = els.inpSourceUrl.value.trim();
    const lang = els.inpSourceLang.value;
    if (!name || !url) return showToast('يرجى ملء الاسم والرابط', true);

    const res = await api('/api/sources', 'POST', { name, url, lang, category_hint: '' });
    if (res?.status === 'success') {
        els.inpSourceName.value = '';
        els.inpSourceUrl.value = '';
        loadSources();
        showToast('تم إضافة المصدر');
    }
}


// ══════════════════════════════════════
// PREFERENCES
// ══════════════════════════════════════
async function loadPreferences() {
    const prefs = await api('/api/preferences');
    if (!prefs) return;

    els.prefsList.innerHTML = prefs.map(p => `
        <div class="pref-item">
            <span class="pref-item-name">${CATEGORY_ICONS[p.category] || '📰'} ${escapeHtml(p.category)}</span>
            <div class="pref-item-controls">
                <span style="font-size:0.7rem;color:var(--text-muted)">🔔</span>
                <input type="checkbox" class="pref-notify-toggle" data-category="${escapeHtml(p.category)}" ${p.notify ? 'checked' : ''}>
            </div>
        </div>
    `).join('');
}


// ══════════════════════════════════════
// FETCH
// ══════════════════════════════════════
async function manualFetch() {
    const ogHtml = els.btnFetchNow.innerHTML;
    els.btnFetchNow.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    els.btnFetchNow.disabled = true;

    // Show progress panel
    els.fetchProgress.classList.remove('hidden');
    els.progressLog.innerHTML = '';
    els.progressTitle.textContent = 'جاري الجلب...';
    const spinner = els.fetchProgress.querySelector('.progress-spinner');
    spinner.classList.remove('done');

    // Start fetch (async - returns when done)
    const fetchPromise = api('/api/news/fetch', 'POST');

    // Poll for progress updates
    let lastMsgCount = 0;
    const pollInterval = setInterval(async () => {
        try {
            const prog = await api('/api/news/fetch-progress');
            if (!prog) return;

            // Render new messages only
            if (prog.messages && prog.messages.length > lastMsgCount) {
                for (let i = lastMsgCount; i < prog.messages.length; i++) {
                    const msg = prog.messages[i];
                    const cssClass = msg.text.startsWith('❌') ? 'error' :
                                    (msg.text.startsWith('✅') || msg.text.startsWith('🎉')) ? 'success' : '';
                    const div = document.createElement('div');
                    div.className = `progress-msg ${cssClass}`;
                    div.innerHTML = `<span class="progress-time">${msg.time}</span><span class="progress-text">${msg.text}</span>`;
                    els.progressLog.appendChild(div);
                }
                lastMsgCount = prog.messages.length;
                // Auto-scroll to bottom
                els.progressLog.scrollTop = els.progressLog.scrollHeight;
            }

            if (prog.done) {
                clearInterval(pollInterval);
                spinner.classList.add('done');
                els.progressTitle.textContent = `اكتمل الجلب — ${prog.total_fetched} خبر`;
            }
        } catch (e) { /* ignore poll errors */ }
    }, 1000);

    // Wait for fetch to complete
    const res = await fetchPromise;
    clearInterval(pollInterval);

    els.btnFetchNow.innerHTML = ogHtml;
    els.btnFetchNow.disabled = false;

    // Final poll to get last messages
    try {
        const finalProg = await api('/api/news/fetch-progress');
        if (finalProg?.messages) {
            for (let i = lastMsgCount; i < finalProg.messages.length; i++) {
                const msg = finalProg.messages[i];
                const cssClass = msg.text.startsWith('❌') ? 'error' :
                                (msg.text.startsWith('✅') || msg.text.startsWith('🎉')) ? 'success' : '';
                const div = document.createElement('div');
                div.className = `progress-msg ${cssClass}`;
                div.innerHTML = `<span class="progress-time">${msg.time}</span><span class="progress-text">${msg.text}</span>`;
                els.progressLog.appendChild(div);
            }
            els.progressLog.scrollTop = els.progressLog.scrollHeight;
        }
    } catch(e) {}

    spinner.classList.add('done');
    els.progressTitle.textContent = `اكتمل الجلب — ${res?.fetched || 0} خبر`;

    if (res?.status === 'success') {
        showToast(`اكتمل الجلب — أُضيف ${res.fetched} خبر جديد`);
        els.lastFetchTimestamp.textContent = 'آخر تحديث: الآن';
        updateCounts();
        loadStats();
        if (state.currentTab === 'new') loadNews();
    } else {
        showToast('خطأ في جلب الأخبار', true);
    }
}


// ══════════════════════════════════════
// OFFLINE SUPPORT (IndexedDB)
// ══════════════════════════════════════
const DB_NAME = 'murrasil_offline';
const DB_VERSION = 1;
const STORE_NAME = 'news_cache';

function openDB() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, DB_VERSION);
        req.onupgradeneeded = () => {
            const db = req.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, { keyPath: 'id' });
            }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

async function saveToOfflineCache(articles) {
    try {
        const db = await openDB();
        const tx = db.transaction(STORE_NAME, 'readwrite');
        const store = tx.objectStore(STORE_NAME);
        articles.forEach(a => store.put(a));
    } catch (e) {
        console.warn('IndexedDB save error:', e);
    }
}

async function loadFromOfflineCache() {
    try {
        const db = await openDB();
        const tx = db.transaction(STORE_NAME, 'readonly');
        const store = tx.objectStore(STORE_NAME);
        const req = store.getAll();
        return new Promise(resolve => {
            req.onsuccess = () => resolve(req.result || []);
            req.onerror = () => resolve([]);
        });
    } catch (e) {
        return [];
    }
}

function setupOfflineDetection() {
    const updateStatus = () => {
        if (!navigator.onLine) {
            els.offlineBanner.classList.remove('hidden');
            // Load from cache
            loadFromOfflineCache().then(data => {
                if (data.length > 0) {
                    const cards = data.map((item, i) => renderCard(item, i)).join('');
                    els.contentArea.innerHTML = `<div class="news-grid">${cards}</div>`;
                    attachCardListeners();
                }
            });
        } else {
            els.offlineBanner.classList.add('hidden');
        }
    };

    window.addEventListener('online', updateStatus);
    window.addEventListener('offline', updateStatus);
    updateStatus();
}


// ══════════════════════════════════════
// SERVICE WORKER REGISTRATION
// ══════════════════════════════════════
async function registerServiceWorker() {
    if ('serviceWorker' in navigator) {
        try {
            const reg = await navigator.serviceWorker.register('/sw.js');
            console.log('SW registered:', reg.scope);
        } catch (e) {
            console.warn('SW registration failed:', e);
        }
    }
}


// ══════════════════════════════════════
// BOOTSTRAP
// ══════════════════════════════════════
init();
