const state = {
    currentTab: 'new',
    page: 1,
    limit: 20,
    totalPages: 1
};

// UI Elements
const els = {
    tabs: document.querySelectorAll('.tab-btn'),
    contentArea: document.getElementById('contentArea'),
    badgeNew: document.getElementById('badge-new'),
    badgeApproved: document.getElementById('badge-approved'),
    badgeRejected: document.getElementById('badge-rejected'),
    pageIndicator: document.getElementById('pageIndicator'),
    btnPrevPage: document.getElementById('btnPrevPage'),
    btnNextPage: document.getElementById('btnNextPage'),
    btnFetchNow: document.getElementById('btnFetchNow'),
    lastFetchTimestamp: document.getElementById('lastFetchTimestamp'),

    // Settings
    btnOpenSettings: document.getElementById('btnOpenSettings'),
    btnCloseSettings: document.getElementById('btnCloseSettings'),
    settingsSidebar: document.getElementById('settingsSidebar'),
    settingsOverlay: document.getElementById('settingsOverlay'),
    btnSaveSettings: document.getElementById('btnSaveSettings'),
    sourcesList: document.getElementById('sourcesList'),
    btnAddSource: document.getElementById('btnAddSource'),
    inpSourceName: document.getElementById('inpSourceName'),
    inpSourceUrl: document.getElementById('inpSourceUrl'),
    selInterval: document.getElementById('selInterval'),
    selMaxAge: document.getElementById('selMaxAge'),

    // Modal
    articleModal: document.getElementById('articleModal'),
    articleModalContent: document.getElementById('articleModalContent'),
    modalTitle: document.getElementById('modalTitle'),
    modalBody: document.getElementById('modalBody'),
    btnCloseModal: document.getElementById('btnCloseModal'),
    btnCopyArticle: document.getElementById('btnCopyArticle'),

    // Toast
    toast: document.getElementById('toast'),
    toastMsg: document.getElementById('toastMsg')
};

// ================= API CALLS =================
async function api(url, method = 'GET', body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    try {
        const res = await fetch(url, opts);
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        return await res.json();
    } catch (e) {
        console.error("API Error:", e);
        return null;
    }
}

// ================= TOAST =================
function showToast(msg, isError = false) {
    els.toastMsg.textContent = msg;
    const icon = els.toast.querySelector('i');
    icon.className = isError ? "fa-solid fa-circle-xmark text-red-400" : "fa-solid fa-circle-check text-green-400";
    els.toast.classList.remove('translate-y-20', 'opacity-0');
    setTimeout(() => {
        els.toast.classList.add('translate-y-20', 'opacity-0');
    }, 3000);
}

// ================= INITS & LOADS =================
async function init() {
    setupEventListeners();
    await updateCounts();
    await loadNews();
    await loadSettings();
    await loadSources();
}

function setupEventListeners() {
    // Tabs
    els.tabs.forEach(tab => {
        tab.addEventListener('click', (e) => {
            const tgt = e.currentTarget;
            if (tgt.dataset.tab === state.currentTab) return;

            // UI Update
            els.tabs.forEach(t => {
                t.classList.remove('border-primary', 'text-primary');
                t.classList.add('border-transparent', 'text-gray-500');
            });
            tgt.classList.remove('border-transparent', 'text-gray-500');
            tgt.classList.add('border-primary', 'text-primary');

            state.currentTab = tgt.dataset.tab;
            state.page = 1;
            loadNews();
        });
    });

    // Pagination
    els.btnPrevPage.addEventListener('click', () => { if (state.page > 1) { state.page--; loadNews(); } });
    els.btnNextPage.addEventListener('click', () => { state.page++; loadNews(); });

    // Settings toggles
    els.btnOpenSettings.addEventListener('click', () => toggleSettings(true));
    els.btnCloseSettings.addEventListener('click', () => toggleSettings(false));
    els.settingsOverlay.addEventListener('click', () => toggleSettings(false));
    els.btnSaveSettings.addEventListener('click', saveSettings);
    els.btnAddSource.addEventListener('click', addSource);

    // Modal
    els.btnCloseModal.addEventListener('click', closeModal);
    els.btnCopyArticle.addEventListener('click', copyArticle);

    // Close modal on click outside
    els.articleModal.addEventListener('click', (e) => {
        if (e.target === els.articleModal) closeModal();
    });

    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !els.articleModal.classList.contains('hidden')) {
            closeModal();
            toggleSettings(false); // Also close settings if open
        }
    });

    // Fetch Now
    els.btnFetchNow.addEventListener('click', manualFetch);
}

// ================= RENDER LOGIC =================

function parseDate(isoStr) {
    if (!isoStr) return "غير معروف";
    const date = new Date(isoStr);
    const now = new Date();
    const diff = Math.floor((now - date) / 60000); // in minutes
    if (diff < 60) return `منذ ${diff} دقيقة`;
    if (diff < 1440) return `منذ ${Math.floor(diff / 60)} ساعة`;
    return `منذ ${Math.floor(diff / 1440)} يوم`;
}

async function loadNews() {
    els.contentArea.innerHTML = '<div class="flex justify-center items-center h-full"><i class="fa-solid fa-spinner fa-spin text-3xl text-gray-300"></i></div>';
    const data = await api(`/api/news?status=${state.currentTab}&page=${state.page}&limit=${state.limit}`);

    if (!data) {
        els.contentArea.innerHTML = '<div class="text-center text-red-500 mt-10">حدث خطأ أثناء تحميل الأخبار</div>';
        return;
    }

    if (data.data.length === 0) {
        els.contentArea.innerHTML = `
            <div class="flex flex-col justify-center items-center h-full text-gray-400 gap-3">
                <i class="fa-regular fa-folder-open text-5xl opacity-50"></i>
                <p>لا يوجد أي أخبار لعرضها هنا</p>
            </div>
        `;
    } else {
        els.contentArea.innerHTML = `<div class="grid gap-4 w-full max-w-4xl mx-auto pb-8">${data.data.map(renderCard).join('')}</div>`;
        attachCardListeners();
    }

    // Pagination update
    const hasMore = (state.page * state.limit) < data.total;
    els.btnPrevPage.disabled = state.page === 1;
    els.btnNextPage.disabled = !hasMore;
    els.pageIndicator.textContent = `صفحة ${state.page}`;
}

function renderCard(item) {
    const timeAgo = parseDate(item.published_at);

    let actionButtons = '';
    let preview = `<p class="text-gray-600 text-sm mt-2 line-clamp-3">${item.summary_ar}</p>`;

    if (state.currentTab === 'new') {
        actionButtons = `
            <div class="flex gap-2 mt-4 pt-3 border-t border-gray-100">
                <button class="btn-approve flex-1 bg-green-50 text-green-700 hover:bg-green-100 px-3 py-2 rounded-md text-sm font-semibold transition" data-id="${item.id}">
                    <i class="fa-solid fa-wand-magic-sparkles mr-1"></i> كتابة الخبر
                </button>
                <button class="btn-reject bg-red-50 text-red-600 hover:bg-red-100 px-4 py-2 rounded-md text-sm transition" data-id="${item.id}">
                    <i class="fa-solid fa-xmark"></i> رفض
                </button>
            </div>
        `;
    } else if (state.currentTab === 'approved') {
        preview = `<p class="text-gray-600 text-sm mt-2 line-clamp-2">${item.article_ar || ''}</p>`;
        actionButtons = `
            <div class="flex gap-2 mt-4 pt-3 border-t border-gray-100">
                <button class="btn-view w-full bg-blue-50 text-blue-700 hover:bg-blue-100 px-3 py-2 rounded-md text-sm font-semibold transition" data-id="${item.id}">
                    <i class="fa-regular fa-eye mr-1"></i> عرض المقال الكامل
                </button>
            </div>
        `;
    } else if (state.currentTab === 'rejected') {
        actionButtons = `
            <div class="flex justify-end mt-2 pt-2 border-t border-gray-100">
                <button class="btn-restore text-gray-400 hover:text-green-600 px-3 py-1 text-sm font-semibold transition" data-id="${item.id}">
                    <i class="fa-solid fa-rotate-left mr-1"></i> استعادة
                </button>
            </div>
        `;
    }

    return `
        <div class="bg-white p-5 rounded-xl shadow-sm border border-gray-200 hover:shadow-md transition-shadow animate-fade-in" id="card-${item.id}">
            <div class="flex justify-between items-start mb-2">
                <div class="flex items-center gap-2">
                    <span class="bg-gray-100 text-gray-600 text-xs px-2 py-1 rounded-md font-semibold">${item.category}</span>
                    <span class="text-xs text-gray-400 ml-2"><i class="fa-solid fa-globe ml-1"></i> ${item.source_name}</span>
                </div>
                <span class="text-xs text-gray-400">${timeAgo}</span>
            </div>
            <a href="${item.original_url}" target="_blank" class="block">
                <h3 class="text-lg font-bold text-gray-800 leading-snug hover:text-primary transition-colors">${item.title_ar}</h3>
            </a>
            ${preview}
            ${actionButtons}
        </div>
    `;
}

function attachCardListeners() {
    document.querySelectorAll('.btn-approve').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.currentTarget.dataset.id;
            const card = document.getElementById(`card-${id}`);
            const ogContent = btn.innerHTML;

            // Loading state
            btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> جاري الكتابة...`;
            btn.disabled = true;

            const res = await api(`/api/news/${id}/approve`, 'POST');
            if (res && res.status === 'success') {
                showToast("تم توليد المقال بنجاح!");
                card.style.display = 'none'; // hide optimistically
                updateCounts();
                openModal(card.querySelector('h3').textContent, res.article_ar);
            } else {
                btn.innerHTML = ogContent;
                btn.disabled = false;
                showToast("فشل في توليد المقال", true);
            }
        });
    });

    document.querySelectorAll('.btn-reject').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.currentTarget.dataset.id;
            const card = document.getElementById(`card-${id}`);
            await api(`/api/news/${id}/reject`, 'POST');
            card.classList.add('opacity-50', 'scale-95');
            setTimeout(() => card.style.display = 'none', 300);
            updateCounts();
        });
    });

    document.querySelectorAll('.btn-restore').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.currentTarget.dataset.id;
            const card = document.getElementById(`card-${id}`);
            await api(`/api/news/${id}/restore`, 'POST');
            card.style.display = 'none';
            updateCounts();
        });
    });

    document.querySelectorAll('.btn-view').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = e.currentTarget.dataset.id;
            // Best way is to fetch the item or extract from DOM. For simplicity, we just fetch list and find it.
            // But since we already have DOM, we could just re-fetch that single item.
            // Since there's no single item GET, we read from DOM (limited) or just fetch the page again.
            // We have the article in DB. Let's make a quick API call... actually we don't have single GET.
            // Re-fetch all approved and find
            const data = await api(`/api/news?status=approved&limit=100`);
            const item = data.data.find(x => x.id === id);
            if (item) openModal(item.title_ar, item.article_ar);
        });
    });
}

// ================= MODAL =================
function openModal(title, body) {
    els.modalTitle.textContent = title;
    // Replace newlines with <br> for HTML rendering, or use CSS whitespace-pre-line
    els.modalBody.innerHTML = body || "لا يوجد محتوى";
    els.articleModal.classList.remove('hidden');
    // slight delay for animation
    setTimeout(() => {
        els.articleModalContent.classList.remove('scale-95');
        els.articleModalContent.classList.add('scale-100');
    }, 10);
}

function closeModal() {
    els.articleModalContent.classList.remove('scale-100');
    els.articleModalContent.classList.add('scale-95');
    setTimeout(() => {
        els.articleModal.classList.add('hidden');
    }, 200);
}

function copyArticle() {
    navigator.clipboard.writeText(els.modalTitle.textContent + "\n\n" + els.modalBody.textContent).then(() => {
        showToast("تم النسخ للحافظة!");
    });
}

// ================= ACTIONS =================
async function manualFetch() {
    const ogHtml = els.btnFetchNow.innerHTML;
    els.btnFetchNow.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> جاري الجلب...`;
    els.btnFetchNow.disabled = true;

    const res = await api('/api/news/fetch', 'POST');

    els.btnFetchNow.innerHTML = ogHtml;
    els.btnFetchNow.disabled = false;

    if (res && res.status === 'success') {
        showToast(`اكتمل الجلب. أضيف ${res.fetched} خبر جديد`);
        els.lastFetchTimestamp.textContent = "آخر تحديث: قبل لحظات";
        updateCounts();
        if (state.currentTab === 'new') loadNews();
        showToast("اكتمل الجلب، ولكن لم تضف كل الأخبار الجديدة. ربما حدث خطأ في اتصال Gemini API.", true);
    } else {
        showToast("⚠️ خطأ في الاتصال بـ Gemini API — تحقق من المفتاح في ملف .env", true);
    }
}

async function updateCounts() {
    const counts = await api('/api/news/counts');
    if (counts) {
        els.badgeNew.textContent = counts.new || 0;
        els.badgeApproved.textContent = counts.approved || 0;
        els.badgeRejected.textContent = counts.rejected || 0;
    }
}

// ================= SETTINGS & SOURCES =================
function toggleSettings(show) {
    if (show) {
        els.settingsOverlay.classList.remove('hidden');
        els.settingsSidebar.classList.remove('-translate-x-full');
    } else {
        els.settingsOverlay.classList.add('hidden');
        els.settingsSidebar.classList.add('-translate-x-full');
    }
}

async function loadSettings() {
    const sets = await api('/api/settings');
    if (sets) {
        if (sets.FETCH_INTERVAL_MINUTES) els.selInterval.value = sets.FETCH_INTERVAL_MINUTES;
        if (sets.MAX_NEWS_AGE_HOURS) els.selMaxAge.value = sets.MAX_NEWS_AGE_HOURS;
    }
}

async function saveSettings() {
    const updates = {
        "FETCH_INTERVAL_MINUTES": els.selInterval.value,
        "MAX_NEWS_AGE_HOURS": els.selMaxAge.value
    };

    const ogHtml = els.btnSaveSettings.innerHTML;
    els.btnSaveSettings.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> جاري الحفظ...`;

    const res = await api('/api/settings', 'POST', updates);

    els.btnSaveSettings.innerHTML = ogHtml;

    if (res && res.status === 'success') {
        showToast("تم حفظ الإعدادات بنجاح");
        toggleSettings(false);
    } else {
        showToast("تعذر حفظ الإعدادات", true);
    }
}

async function loadSources() {
    const sources = await api('/api/sources');
    if (!sources) return;

    els.sourcesList.innerHTML = sources.map(s => `
        <div class="flex justify-between items-center bg-white border border-gray-200 p-2 rounded text-xs pr-3">
            <div class="flex flex-col overflow-hidden w-2/3">
                <span class="font-bold truncate text-gray-700">${s.name}</span>
            </div>
            <div class="flex gap-2 items-center">
                <input type="checkbox" class="toggle-checkbox absolute block w-4 h-4 rounded-full bg-white border-4 appearance-none cursor-pointer" 
                       ${s.enabled ? 'checked' : ''} onchange="toggleSource(${s.id}, this.checked)" style="position:relative; right:auto;">
                <button onclick="deleteSource(${s.id})" class="text-gray-400 hover:text-red-500"><i class="fa-solid fa-trash"></i></button>
            </div>
        </div>
    `).join('');
}

window.toggleSource = async function (id, enabled) {
    await api(`/api/sources/${id}`, 'PUT', { enabled: enabled ? 1 : 0 });
}

window.deleteSource = async function (id) {
    if (!confirm("هل أنت متأكد من حذف المصدر؟")) return;
    await api(`/api/sources/${id}`, 'DELETE');
    loadSources();
}

async function addSource() {
    const name = els.inpSourceName.value.trim();
    const url = els.inpSourceUrl.value.trim();
    if (!name || !url) {
        alert("يرجى ملء الاسم والرابط");
        return;
    }
    const ogHtml = els.btnAddSource.innerHTML;
    els.btnAddSource.innerHTML = "...";

    const res = await api('/api/sources', 'POST', { name, url });
    els.btnAddSource.innerHTML = ogHtml;

    if (res && res.status === 'success') {
        els.inpSourceName.value = "";
        els.inpSourceUrl.value = "";
        loadSources();
        showToast("تم إضافة المصدر");
    }
}

// Bootstrap
init();
