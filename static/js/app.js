/* ==========================================================================
   Lumivia – comportamenti dell'interfaccia
   Tutto funziona anche senza JavaScript: qui ci sono solo miglioramenti
   (animazioni, conferme, filtri senza ricaricare la pagina).
   ========================================================================== */
(() => {
    "use strict";

    const $ = (sel, el = document) => el.querySelector(sel);
    const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
    const movimentoRidotto = matchMedia("(prefers-reduced-motion: reduce)").matches;

    // ----------------------------------------------------------------------
    // Tema chiaro / scuro (la scelta viene ricordata nel browser)
    // ----------------------------------------------------------------------
    function salvaTema(tema) {
        try { localStorage.setItem("tema", tema); } catch (_) { /* navigazione privata */ }
    }
    document.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-tema-btn]");
        if (!btn) return;
        const nuovo = document.documentElement.dataset.tema === "scuro" ? "chiaro" : "scuro";
        const applica = () => { document.documentElement.dataset.tema = nuovo; };
        // transizione "a cerchio" che parte dal bottone, dove supportata
        if (document.startViewTransition && !movimentoRidotto) {
            const r = btn.getBoundingClientRect();
            document.documentElement.style.setProperty("--tx", `${r.left + r.width / 2}px`);
            document.documentElement.style.setProperty("--ty", `${r.top + r.height / 2}px`);
            document.documentElement.classList.add("cambio-tema");
            const t = document.startViewTransition(applica);
            t.finished.finally(() => document.documentElement.classList.remove("cambio-tema"));
        } else {
            applica();
        }
        salvaTema(nuovo);
    });

    // ----------------------------------------------------------------------
    // Barra di navigazione
    // ----------------------------------------------------------------------
    const barra = $(".barra");
    const aggiornaBarra = () => barra && barra.classList.toggle("scorsa", scrollY > 4);
    addEventListener("scroll", aggiornaBarra, { passive: true });
    aggiornaBarra();

    // pillola che scivola sotto la voce attiva e segue il mouse
    const nav = $(".nav");
    const pillola = $(".nav-pillola");
    if (nav && pillola) {
        const attiva = $('a[aria-current="page"]', nav);
        const vaiA = (link, subito) => {
            if (!link) { pillola.style.opacity = "0"; return; }
            if (subito) pillola.style.transition = "none";
            pillola.style.width = link.offsetWidth + "px";
            pillola.style.transform = `translateX(${link.offsetLeft}px)`;
            pillola.style.opacity = "1";
            if (subito) { pillola.offsetWidth; pillola.style.transition = ""; }
        };
        vaiA(attiva, true);
        $$("a", nav).forEach((a) => a.addEventListener("mouseenter", () => vaiA(a)));
        nav.addEventListener("mouseleave", () => vaiA(attiva));
        addEventListener("resize", () => vaiA(attiva, true));
        document.fonts && document.fonts.ready.then(() => vaiA(attiva, true));
    }

    // menu mobile
    const menuBtn = $(".menu-mobile-btn");
    const navWrap = $(".nav-wrap");
    if (menuBtn && navWrap) {
        menuBtn.addEventListener("click", () => {
            const aperto = navWrap.classList.toggle("aperta");
            menuBtn.setAttribute("aria-expanded", aperto);
        });
    }

    // menu utente
    const utenteBtn = $(".utente-btn");
    const tendina = $(".tendina");
    if (utenteBtn && tendina) {
        const chiudi = () => { tendina.classList.remove("aperta"); utenteBtn.setAttribute("aria-expanded", "false"); };
        utenteBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            const aperta = tendina.classList.toggle("aperta");
            utenteBtn.setAttribute("aria-expanded", aperta);
        });
        document.addEventListener("click", (e) => { if (!tendina.contains(e.target)) chiudi(); });
        document.addEventListener("keydown", (e) => { if (e.key === "Escape") chiudi(); });
    }

    // ----------------------------------------------------------------------
    // Onda al click sui bottoni
    // ----------------------------------------------------------------------
    document.addEventListener("pointerdown", (e) => {
        const btn = e.target.closest(".btn");
        if (!btn || movimentoRidotto) return;
        const r = btn.getBoundingClientRect();
        const lato = Math.max(r.width, r.height) * 2;
        const onda = document.createElement("span");
        onda.className = "onda";
        onda.style.cssText = `width:${lato}px;height:${lato}px;left:${e.clientX - r.left - lato / 2}px;top:${e.clientY - r.top - lato / 2}px`;
        btn.appendChild(onda);
        onda.addEventListener("animationend", () => onda.remove());
    });

    // ----------------------------------------------------------------------
    // Toast: spariscono dopo 5 secondi (si fermano col mouse sopra)
    // ----------------------------------------------------------------------
    function chiudiToast(t) {
        t.classList.add("via");
        t.addEventListener("animationend", () => t.remove(), { once: true });
    }
    $$(".toast").forEach((t) => {
        const barraTempo = $(".tempo", t);
        barraTempo && barraTempo.addEventListener("animationend", () => chiudiToast(t));
        $(".chiudi", t)?.addEventListener("click", () => chiudiToast(t));
    });

    // ----------------------------------------------------------------------
    // Conferma prima delle azioni distruttive: <form data-conferma="...">
    // ----------------------------------------------------------------------
    const dialogo = $("#dialogo-conferma");
    let formInAttesa = null;

    function chiudiDialogo() {
        dialogo.classList.add("chiude");
        dialogo.addEventListener("animationend", () => {
            dialogo.classList.remove("chiude");
            dialogo.close();
        }, { once: true });
    }

    document.addEventListener("submit", (e) => {
        const form = e.target;
        if (form.dataset.conferma && dialogo && !form.dataset.confermato) {
            e.preventDefault();
            formInAttesa = form;
            $("#dialogo-titolo", dialogo).textContent = form.dataset.confermaTitolo || "Sei sicuro?";
            $("#dialogo-testo", dialogo).textContent = form.dataset.conferma;
            $("#dialogo-ok", dialogo).textContent = form.dataset.confermaAzione || "Conferma";
            dialogo.showModal();
            $("#dialogo-annulla", dialogo).focus();
            return;
        }
        // bottone in caricamento mentre la pagina invia
        const btn = e.submitter;
        if (btn && btn.classList.contains("btn") && form.method.toLowerCase() === "post") {
            setTimeout(() => btn.setAttribute("aria-busy", "true"), 0);
        }
    });

    if (dialogo) {
        $("#dialogo-annulla", dialogo).addEventListener("click", chiudiDialogo);
        $("#dialogo-ok", dialogo).addEventListener("click", () => {
            if (!formInAttesa) return;
            formInAttesa.dataset.confermato = "1";
            $("#dialogo-ok", dialogo).setAttribute("aria-busy", "true");
            formInAttesa.requestSubmit();
        });
        dialogo.addEventListener("cancel", (e) => { e.preventDefault(); chiudiDialogo(); });
        dialogo.addEventListener("click", (e) => { if (e.target === dialogo) chiudiDialogo(); });
    }

    // ----------------------------------------------------------------------
    // Numeri che contano: <span data-conta="7.51" data-decimali="2">
    // ----------------------------------------------------------------------
    function conta(el) {
        const fine = parseFloat(el.dataset.conta);
        const decimali = parseInt(el.dataset.decimali || "0", 10);
        const formato = (v) => v.toLocaleString("it-IT", { minimumFractionDigits: decimali, maximumFractionDigits: decimali });
        if (isNaN(fine) || movimentoRidotto) { el.textContent = formato(fine || 0); return; }
        const durata = 1100;
        const inizio = performance.now() + (parseInt(el.dataset.ritardo || "0", 10));
        const passo = (ora) => {
            const t = Math.min(1, Math.max(0, (ora - inizio) / durata));
            const e = 1 - Math.pow(1 - t, 4);
            el.textContent = formato(fine * e);
            if (t < 1) requestAnimationFrame(passo);
        };
        el.textContent = formato(0);
        requestAnimationFrame(passo);
    }
    // barre che crescono: <div data-larghezza="42">
    function cresci(el) {
        requestAnimationFrame(() => requestAnimationFrame(() => {
            el.style.width = el.dataset.larghezza + "%";
        }));
    }
    function cresciBarre(radice = document) { $$("[data-larghezza]", radice).forEach(cresci); }

    // contatori e barre partono quando entrano nello schermo
    if ("IntersectionObserver" in window) {
        const ossAnim = new IntersectionObserver((voci) => {
            voci.forEach((v) => {
                if (!v.isIntersecting) return;
                v.target.dataset.conta !== undefined ? conta(v.target) : cresci(v.target);
                ossAnim.unobserve(v.target);
            });
        }, { threshold: 0.2 });
        $$("[data-conta], [data-larghezza]").forEach((el) => ossAnim.observe(el));
    } else {
        $$("[data-conta]").forEach(conta);
        cresciBarre();
    }

    // ----------------------------------------------------------------------
    // Elementi che compaiono quando entrano nello schermo: data-rivela
    // ----------------------------------------------------------------------
    if ("IntersectionObserver" in window) {
        const oss = new IntersectionObserver((voci) => {
            voci.forEach((v) => {
                if (v.isIntersecting) { v.target.classList.add("visibile"); oss.unobserve(v.target); }
            });
        }, { rootMargin: "0px 0px -8% 0px" });
        $$("[data-rivela]").forEach((el) => oss.observe(el));
    } else {
        $$("[data-rivela]").forEach((el) => el.classList.add("visibile"));
    }

    // ----------------------------------------------------------------------
    // Filtri "dal vivo": <form data-filtro-live data-aggiorna="#a,#b">
    // La pagina chiede la stessa URL al server e sostituisce solo le parti
    // indicate, così la tabella cambia senza ricaricare tutto.
    // ----------------------------------------------------------------------
    $$("form[data-filtro-live]").forEach((form) => {
        const parti = form.dataset.aggiorna.split(",").map((s) => s.trim());
        let timer, controllore;

        async function aggiorna() {
            const params = new URLSearchParams(new FormData(form));
            [...params.keys()].forEach((k) => { if (!params.get(k)) params.delete(k); });
            const url = form.action.split("?")[0] + (params.toString() ? "?" + params : "");

            controllore?.abort();
            controllore = new AbortController();
            form.classList.add("in-caricamento");
            try {
                const r = await fetch(url, { signal: controllore.signal, headers: { Accept: "text/html" } });
                const doc = new DOMParser().parseFromString(await r.text(), "text/html");
                const sostituisci = () => parti.forEach((sel) => {
                    const nuovo = $(sel, doc), vecchio = $(sel);
                    if (nuovo && vecchio) vecchio.replaceWith(nuovo);
                });
                sostituisci();  // le nuove righe hanno già la loro animazione di ingresso
                cresciBarre();
                history.replaceState(null, "", url);
            } catch (err) {
                if (err.name !== "AbortError") form.submit();
            } finally {
                form.classList.remove("in-caricamento");
            }
        }

        form.addEventListener("submit", (e) => { e.preventDefault(); aggiorna(); });
        form.addEventListener("change", aggiorna);
        form.addEventListener("input", (e) => {
            if (e.target.type !== "search" && e.target.type !== "number") return;
            clearTimeout(timer);
            timer = setTimeout(aggiorna, 300);
        });
        form.addEventListener("reset", () => setTimeout(aggiorna, 0));
    });

    // mostra / nascondi password
    document.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-mostra-password]");
        if (!btn) return;
        const input = btn.parentElement.querySelector("input");
        const visibile = input.type === "password";
        input.type = visibile ? "text" : "password";
        btn.classList.toggle("attivo", visibile);
        btn.setAttribute("aria-label", visibile ? "Nascondi password" : "Mostra password");
        input.focus();
    });

    // scorciatoia: "/" porta alla ricerca
    document.addEventListener("keydown", (e) => {
        if (e.key !== "/" || /input|textarea|select/i.test(document.activeElement.tagName)) return;
        const cerca = $('input[type="search"]');
        if (cerca) { e.preventDefault(); cerca.focus(); }
    });
})();
