/* app.js — Global yardımcılar */

// Tüm fetch isteklerine otomatik cookie ekle (credentials: "same-origin" zaten default)
// 401 gelirse login'e yönlendir
const _origFetch = window.fetch;
window.fetch = async function(...args) {
    const res = await _origFetch(...args);
    if (res.status === 401) {
        window.location.href = "/auth/login";
    }
    return res;
};
