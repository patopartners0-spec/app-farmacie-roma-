/* Farmacie di Roma per ex municipio — app statica (Leaflet). */
(function () {
  "use strict";

  var ROMANI = { 1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX",
    10: "X", 11: "XI", 12: "XII", 13: "XIII", 15: "XV", 16: "XVI", 17: "XVII", 18: "XVIII",
    19: "XIX", 20: "XX" };
  var MAX_RISULTATI = 150;
  var DESKTOP = window.matchMedia("(min-width: 900px)");

  var stato = { municipio: null, query: "", selezionata: null };
  var dati = { farmacie: [], zone: {}, municipi: {}, geoMunicipi: null };
  var el = {
    pannello: document.getElementById("pannello"),
    maniglia: document.getElementById("maniglia"),
    contenuto: document.getElementById("contenuto"),
    ricerca: document.getElementById("ricerca"),
    filtro: document.getElementById("filtro-municipio"),
    info: document.getElementById("info"),
  };

  // ------------------------------------------------------------------ utilità
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function normalizza(s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "")
      .toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }
  function plurale(n, uno, molti) { return n + " " + (n === 1 ? uno : molti); }
  function nomeMunicipio(num) {
    var m = dati.municipi[num];
    return "Ex municipio " + ROMANI[num] + (m ? " · " + m.nome : "");
  }
  function nomeZona(cod) { return cod + " " + (dati.zone[cod] || ""); }
  function capitalizza(s) {
    // Molti nomi nel file del Ministero sono tutti in maiuscolo: li rendo più leggibili.
    if (s !== s.toUpperCase()) return s;
    return s.toLowerCase().replace(/(^|[\s'’(\-\/."])([a-zà-ù])/g, function (m, p, c) { return p + c.toUpperCase(); })
      .replace(/\b(S\.?r\.?l|S\.?n\.?c|S\.?a\.?s|S\.?p\.?a)\b\.?/gi, function (m) { return m.toUpperCase(); });
  }

  // ------------------------------------------------------------------ mappa
  var mappa = L.map("map", { zoomControl: !matchMedia("(pointer: coarse)").matches, preferCanvas: false })
    .setView([41.89, 12.49], 11);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(mappa);
  mappa.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');

  var livelloMunicipi, livelloZone = null, etichette = L.layerGroup().addTo(mappa);
  var gruppo = L.markerClusterGroup({
    showCoverageOnHover: false,
    maxClusterRadius: 48,
    disableClusteringAtZoom: 16,
    spiderfyOnMaxZoom: true,
    chunkedLoading: true,
    iconCreateFunction: function (c) {
      return L.divIcon({ html: "<div>" + c.getChildCount() + "</div>", className: "cluster", iconSize: [40, 40] });
    },
  }).addTo(mappa);
  var markerAttivo = null, markerPosizione = null;

  function iconaFarmacia(f, attiva) {
    return L.divIcon({
      className: "",
      html: '<div class="marker-farmacia' + (f.p ? "" : " approssimata") + (attiva ? " attiva" : "") + '">+</div>',
      iconSize: [22, 22], iconAnchor: [11, 11],
    });
  }

  function stileMunicipio(feature) {
    var sel = stato.municipio, num = feature.properties.num;
    var attivo = sel === num;
    return {
      color: attivo ? "#0a4f3e" : "#0f6e56",
      weight: attivo ? 3 : 1.5,
      opacity: sel && !attivo ? 0.45 : 0.9,
      fillColor: "#0f6e56",
      fillOpacity: sel ? (attivo ? 0.06 : 0.0) : 0.05,
    };
  }

  // Spazio occupato dal pannello, per inquadrare la mappa nella parte visibile.
  function padding() {
    if (DESKTOP.matches) return { tl: [420, 30], br: [30, 30] };
    return { tl: [20, 20], br: [20, altezzaPannello() + 20] };
  }
  function inquadra(bounds, maxZoom) {
    var p = padding();
    mappa.fitBounds(bounds, { paddingTopLeft: p.tl, paddingBottomRight: p.br, maxZoom: maxZoom || 16 });
  }

  // ------------------------------------------------------------------ pannello (bottom sheet)
  var STATI = ["stato-basso", "stato-medio", "stato-alto"];
  function statoPannello() {
    for (var i = 0; i < STATI.length; i++) if (el.pannello.classList.contains(STATI[i])) return i;
    return 1;
  }
  function altezze() { var h = window.innerHeight; return [132, Math.round(h * 0.45), Math.round(h * 0.88)]; }
  function altezzaPannello() { return DESKTOP.matches ? 0 : altezze()[statoPannello()]; }
  function impostaPannello(i) {
    STATI.forEach(function (s) { el.pannello.classList.remove(s); });
    el.pannello.classList.add(STATI[i]);
    document.documentElement.style.setProperty("--altezza-pannello", altezzaPannello() + "px");
    document.body.classList.toggle("pannello-alto", i === 2 && !DESKTOP.matches);
  }

  (function trascinamento() {
    var inizioY = null, inizioH = 0, mosso = false;
    function giu(e) {
      if (DESKTOP.matches) return;
      if (e.target.closest("input, select, button:not(.maniglia)")) return;
      inizioY = e.clientY; inizioH = altezzaPannello(); mosso = false;
      el.pannello.classList.add("trascina");
    }
    function muovi(e) {
      if (inizioY === null) return;
      var dy = inizioY - e.clientY;
      if (Math.abs(dy) > 6) mosso = true;
      var a = altezze(), h = Math.max(a[0] - 40, Math.min(a[2], inizioH + dy));
      el.pannello.style.setProperty("--altezza-visibile", h + "px");
    }
    function su(e) {
      if (inizioY === null) return;
      el.pannello.classList.remove("trascina");
      var dy = inizioY - e.clientY, h = inizioH + dy, a = altezze();
      inizioY = null;
      el.pannello.style.removeProperty("--altezza-visibile");
      if (!mosso) {
        if (e.target.closest(".maniglia")) impostaPannello((statoPannello() + 1) % 3);
        return;
      }
      var migliore = 0;
      a.forEach(function (v, i) { if (Math.abs(v - h) < Math.abs(a[migliore] - h)) migliore = i; });
      impostaPannello(migliore);
    }
    [el.maniglia, el.pannello.querySelector(".testata")].forEach(function (n) {
      n.addEventListener("pointerdown", giu);
    });
    window.addEventListener("pointermove", muovi);
    window.addEventListener("pointerup", su);
    window.addEventListener("pointercancel", su);
  })();

  // ------------------------------------------------------------------ filtri
  function risultati() {
    var parole = normalizza(stato.query).split(" ").filter(Boolean);
    return dati.farmacie.filter(function (f) {
      if (stato.municipio && f.m !== stato.municipio) return false;
      for (var i = 0; i < parole.length; i++) if (f._cerca.indexOf(parole[i]) === -1) return false;
      return true;
    });
  }

  // Nella vista d'insieme (nessun filtro, mappa lontana) mostro solo i municipi con i conteggi:
  // i marker compaiono scegliendo un municipio, cercando o avvicinando la mappa.
  var ZOOM_MARKER = 13;
  function vistaInsieme() {
    return !stato.municipio && !stato.query && !stato.selezionata && mappa.getZoom() < ZOOM_MARKER;
  }
  var ultimaLista = [];
  function aggiornaMarker(lista) {
    if (lista) ultimaLista = lista;
    gruppo.clearLayers();
    if (!vistaInsieme()) gruppo.addLayers(ultimaLista.map(function (f) { return f._marker; }));
  }

  function aggiornaZone() {
    if (livelloZone) { mappa.removeLayer(livelloZone); livelloZone = null; }
    if (!stato.municipio || !dati.geoZone) return;
    livelloZone = L.geoJSON(dati.geoZone, {
      filter: function (ft) { return ft.properties.num === stato.municipio; },
      style: { color: "#0f6e56", weight: 1, dashArray: "4 4", fillOpacity: 0, opacity: 0.8 },
      interactive: true,
      onEachFeature: function (ft, layer) {
        layer.bindTooltip(esc(ft.properties.codice + " " + ft.properties.nome) +
          " · " + plurale(ft.properties.farmacie, "farmacia", "farmacie"), { sticky: true, className: "tooltip-zona" });
      },
    }).addTo(mappa);
    gruppo.bringToFront && gruppo.bringToFront();
  }

  function aggiornaEtichette() {
    etichette.clearLayers();
    if (!vistaInsieme() || !dati.geoMunicipi) return;
    dati.geoMunicipi.features.forEach(function (ft) {
      var p = ft.properties;
      L.marker([p.lp[0], p.lp[1]], {
        interactive: false, keyboard: false,
        icon: L.divIcon({ className: "", iconSize: null,
          html: '<div class="etichetta-municipio" style="transform:translate(-50%,-50%)">' + p.romano +
            "<small>" + p.farmacie + "</small></div>" }),
      }).addTo(etichette);
    });
  }

  function impostaMunicipio(num, opz) {
    opz = opz || {};
    stato.municipio = num || null;
    stato.selezionata = null;
    el.filtro.value = stato.municipio ? String(stato.municipio) : "";
    livelloMunicipi.setStyle(stileMunicipio);
    aggiornaZone();
    aggiornaEtichette();
    aggiorna();
    if (opz.inquadra !== false) {
      if (stato.municipio) inquadra(dati.municipi[stato.municipio].bounds, 15);
      else inquadra(livelloMunicipi.getBounds(), 13);
    }
  }

  // ------------------------------------------------------------------ rendering pannello
  function rendiMunicipi() {
    var tot = dati.farmacie.length, max = 0;
    var nums = Object.keys(ROMANI).map(Number);
    nums.forEach(function (n) { max = Math.max(max, dati.municipi[n].farmacie); });
    var h = '<div class="riepilogo"><h2>Farmacie per ex municipio</h2><span class="totale">' +
      tot + " in totale</span></div><ul class=\"lista\">";
    nums.forEach(function (n) {
      var m = dati.municipi[n];
      h += '<li><button class="voce" type="button" data-municipio="' + n + '">' +
        '<span class="badge">' + ROMANI[n] + "</span>" +
        '<span class="voce-testo"><span class="voce-titolo">' + esc(m.nome) + "</span>" +
        '<span class="voce-sotto">' + plurale(m.zone, "zona urbanistica", "zone urbanistiche") + "</span>" +
        '<span class="barra"><i style="width:' + (100 * m.farmacie / max).toFixed(1) + '%"></i></span></span>' +
        '<span class="voce-num">' + m.farmacie + "<small>farmacie</small></span></button></li>";
    });
    return h + "</ul>";
  }

  function voceFarmacia(f) {
    return '<li><button class="voce" type="button" data-farmacia="' + esc(f.id) + '">' +
      '<span class="icona-farmacia' + (f.p ? "" : " approssimata") + '" aria-hidden="true">+</span>' +
      '<span class="voce-testo"><span class="voce-titolo">' + esc(f._nome) + "</span>" +
      '<span class="voce-sotto">' + esc(f.i) + " · " + esc(dati.zone[f.z] || f.z) +
      (stato.municipio ? "" : " · " + ROMANI[f.m]) + "</span></span></button></li>";
  }

  function rendiRisultati(lista) {
    var titolo = stato.municipio ? nomeMunicipio(stato.municipio) : "Tutti gli ex municipi";
    var sotto = plurale(lista.length, "farmacia", "farmacie") + (stato.query ? " per “" + esc(stato.query) + "”" : "");
    var h = '<div class="intestazione-risultati"><div><h2>' + esc(titolo) + "</h2><p>" + sotto + "</p></div>" +
      '<button class="btn-link" type="button" data-azione="azzera">Azzera</button></div>';
    if (!lista.length) return h + '<p class="vuoto">Nessuna farmacia trovata. Prova con meno parole o un altro municipio.</p>';
    h += '<ul class="lista">' + lista.slice(0, MAX_RISULTATI).map(voceFarmacia).join("") + "</ul>";
    if (lista.length > MAX_RISULTATI)
      h += '<p class="altri">Mostrate le prime ' + MAX_RISULTATI + " su " + lista.length + ". Affina la ricerca o scegli un municipio.</p>";
    return h;
  }

  function rendiScheda(f) {
    var indirizzo = f.i + ", " + f.c + " Roma";
    var h = '<div class="scheda"><button class="btn-link indietro" type="button" data-azione="indietro">‹ Indietro</button>' +
      "<h2>" + esc(f._nome) + "</h2>" +
      '<p class="indirizzo">' + esc(f.i) + "<br>" + esc(f.c) + " Roma" + (f.fr ? " (" + esc(f.fr) + ")" : "") + "</p>";
    if (!f.p) h += '<p class="avviso">Posizione sulla mappa approssimata: il punto potrebbe non corrispondere esattamente al civico.</p>';
    h += '<dl class="dati">' +
      "<dt>Ex municipio</dt><dd>" + esc(nomeMunicipio(f.m).replace("Ex municipio ", "")) + "</dd>" +
      "<dt>Zona urbanistica</dt><dd>" + esc(nomeZona(f.z)) + "</dd>" +
      (f.t ? "<dt>Tipologia</dt><dd>" + esc(f.t) + "</dd>" : "") +
      (f.d ? "<dt>Attiva dal</dt><dd>" + esc(f.d) + "</dd>" : "") +
      "<dt>Cod. ministeriale</dt><dd>" + esc(f.id) + "</dd></dl>" +
      '<div class="azioni">' +
      '<a class="btn-primario" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&amp;destination=' +
      f.la + "," + f.lo + '">Indicazioni</a>' +
      '<button class="btn-secondario" type="button" data-azione="copia" data-testo="' + esc(indirizzo) + '">Copia indirizzo</button>' +
      "</div></div>";
    return h;
  }

  function aggiorna() {
    var lista = risultati();
    aggiornaMarker(lista);
    var html;
    if (stato.selezionata) html = rendiScheda(stato.selezionata);
    else if (stato.municipio || stato.query) html = rendiRisultati(lista);
    else html = rendiMunicipi();
    el.contenuto.innerHTML = html;
    el.contenuto.scrollTop = 0;
    aggiornaEtichette();
    aggiornaHash();
    return lista;
  }

  // ------------------------------------------------------------------ scheda e marker attivo
  function evidenzia(f) {
    if (markerAttivo) markerAttivo.setIcon(iconaFarmacia(markerAttivo._farmacia, false));
    markerAttivo = f ? f._marker : null;
    if (markerAttivo) markerAttivo.setIcon(iconaFarmacia(f, true));
  }

  function apriScheda(f, opz) {
    opz = opz || {};
    stato.selezionata = f;
    aggiorna();
    if (!DESKTOP.matches && statoPannello() !== 1) impostaPannello(1);
    gruppo.zoomToShowLayer(f._marker, function () {
      evidenzia(f);
      if (opz.inquadra !== false) inquadra(L.latLngBounds([f._marker.getLatLng()]), 17);
    });
  }

  function chiudiScheda() {
    stato.selezionata = null;
    evidenzia(null);
    aggiorna();
  }

  // ------------------------------------------------------------------ URL condivisibile (#m=4, #f=19519)
  var aggiornandoHash = false;
  function aggiornaHash() {
    var h = stato.selezionata ? "f=" + encodeURIComponent(stato.selezionata.id)
      : [stato.municipio ? "m=" + stato.municipio : "", stato.query ? "q=" + encodeURIComponent(stato.query) : ""]
        .filter(Boolean).join("&");
    aggiornandoHash = true;
    history.replaceState(null, "", h ? "#" + h : location.pathname + location.search);
    aggiornandoHash = false;
  }
  function leggiHash() {
    var p = {};
    location.hash.replace(/^#/, "").split("&").forEach(function (kv) {
      var i = kv.indexOf("="); if (i > 0) p[kv.slice(0, i)] = decodeURIComponent(kv.slice(i + 1));
    });
    return p;
  }

  // ------------------------------------------------------------------ eventi
  el.contenuto.addEventListener("click", function (e) {
    var b = e.target.closest("[data-municipio],[data-farmacia],[data-azione]");
    if (!b) return;
    if (b.dataset.municipio) impostaMunicipio(Number(b.dataset.municipio));
    else if (b.dataset.farmacia) apriScheda(dati.perId[b.dataset.farmacia]);
    else if (b.dataset.azione === "indietro") chiudiScheda();
    else if (b.dataset.azione === "azzera") {
      stato.query = ""; el.ricerca.value = "";
      impostaMunicipio(null);
    } else if (b.dataset.azione === "copia") {
      var t = b.dataset.testo;
      (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(function () {
        b.textContent = "Copiato ✓";
      }, function () { window.prompt("Copia l'indirizzo:", t); });
    }
  });

  var timerRicerca, timerInquadra;
  el.ricerca.addEventListener("input", function () {
    clearTimeout(timerRicerca); clearTimeout(timerInquadra);
    timerRicerca = setTimeout(function () {
      stato.query = el.ricerca.value.trim();
      stato.selezionata = null; evidenzia(null);
      var lista = aggiorna();
      timerInquadra = setTimeout(function () {
        if (stato.query.length >= 3 && lista.length > 0 && lista.length <= 60)
          inquadra(L.latLngBounds(lista.map(function (f) { return [f.la, f.lo]; })), 16);
      }, 500);
    }, 120);
  });
  el.ricerca.addEventListener("focus", function () { if (!DESKTOP.matches) impostaPannello(2); });
  el.ricerca.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { el.ricerca.blur(); if (!DESKTOP.matches) impostaPannello(1); }
  });
  el.filtro.addEventListener("change", function () { impostaMunicipio(Number(el.filtro.value) || null); });

  document.getElementById("btn-info").addEventListener("click", function () {
    if (el.info.showModal) el.info.showModal(); else el.info.setAttribute("open", "");
  });
  el.info.addEventListener("click", function (e) { if (e.target === el.info) el.info.close(); });

  document.getElementById("btn-posizione").addEventListener("click", function () {
    if (!navigator.geolocation) { alert("Geolocalizzazione non disponibile su questo dispositivo."); return; }
    navigator.geolocation.getCurrentPosition(function (pos) {
      var ll = [pos.coords.latitude, pos.coords.longitude];
      if (markerPosizione) markerPosizione.setLatLng(ll);
      else markerPosizione = L.marker(ll, { interactive: false,
        icon: L.divIcon({ className: "", html: '<div class="marker-posizione"></div>', iconSize: [16, 16] }) }).addTo(mappa);
      inquadra(L.latLng(ll).toBounds(900), 16);
    }, function () { alert("Non riesco a ottenere la tua posizione. Controlla i permessi del browser."); },
    { enableHighAccuracy: true, timeout: 10000 });
  });

  var eraInsieme = null;
  mappa.on("zoomend", function () {
    var ora = vistaInsieme();
    if (ora !== eraInsieme) { eraInsieme = ora; aggiornaMarker(); aggiornaEtichette(); }
  });
  window.addEventListener("resize", function () { impostaPannello(statoPannello()); });
  window.addEventListener("hashchange", function () { if (!aggiornandoHash) applicaHash(); });

  function applicaHash() {
    var p = leggiHash();
    if (p.f && dati.perId[p.f]) {
      var f = dati.perId[p.f];
      stato.municipio = null; el.filtro.value = "";
      livelloMunicipi.setStyle(stileMunicipio);
      apriScheda(f);
      return true;
    }
    if (p.q) { stato.query = p.q; el.ricerca.value = p.q; }
    if (p.m && ROMANI[p.m]) { impostaMunicipio(Number(p.m)); return true; }
    if (p.q) { aggiorna(); return true; }
    return false;
  }

  // ------------------------------------------------------------------ avvio
  function json(url) {
    return fetch(url).then(function (r) { if (!r.ok) throw new Error(url + ": " + r.status); return r.json(); });
  }

  Promise.all([json("data/farmacie.json"), json("data/ex_municipi.geojson")]).then(function (res) {
    var fa = res[0], gm = res[1];
    dati.zone = fa.zone;
    dati.geoMunicipi = gm;
    dati.perId = {};
    dati.farmacie = fa.farmacie.map(function (f) {
      f._nome = capitalizza(f.n);
      f._cerca = normalizza([f.n, f.i, f.c, f.fr, f.z, fa.zone[f.z]].join(" "));
      f._marker = L.marker([f.la, f.lo], { icon: iconaFarmacia(f, false), title: f._nome, keyboard: false });
      f._marker._farmacia = f;
      f._marker.on("click", function () { apriScheda(f, { inquadra: false }); });
      dati.perId[f.id] = f;
      return f;
    });

    document.getElementById("info-fonte").textContent = fa.fonte;
    document.getElementById("info-data").textContent = fa.aggiornamento.split("-").reverse().join("/");

    var opzioni = '<option value="">Tutti gli ex municipi (' + dati.farmacie.length + ")</option>";
    gm.features.forEach(function (ft) {
      var p = ft.properties;
      dati.municipi[p.num] = p;
      opzioni += '<option value="' + p.num + '">' + p.romano + " · " + esc(p.nome) + " (" + p.farmacie + ")</option>";
    });
    el.filtro.innerHTML = opzioni;

    livelloMunicipi = L.geoJSON(gm, {
      style: stileMunicipio,
      onEachFeature: function (ft, layer) {
        dati.municipi[ft.properties.num].bounds = layer.getBounds();
        layer.on("click", function () {
          if (stato.municipio !== ft.properties.num) impostaMunicipio(ft.properties.num);
        });
      },
    }).addTo(mappa);

    impostaPannello(DESKTOP.matches ? 1 : 1);
    if (!applicaHash()) { aggiorna(); inquadra(livelloMunicipi.getBounds(), 12); }
    aggiornaEtichette();

    // Le zone urbanistiche servono solo quando si sceglie un municipio: le carico dopo.
    json("data/zone_urbanistiche.geojson").then(function (gz) { dati.geoZone = gz; aggiornaZone(); });
  }).catch(function (err) {
    el.contenuto.innerHTML = '<p class="vuoto">Impossibile caricare i dati. Ricarica la pagina.</p>';
    console.error(err);
  });
})();
