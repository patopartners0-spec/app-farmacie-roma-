#!/usr/bin/env python3
"""Geocodifica gli indirizzi delle farmacie con Nominatim (OpenStreetMap).

Le coordinate del file del Ministero sono spesso mancanti o sbagliate (centinaia di farmacie
sullo stesso punto fittizio, vie omonime in altri comuni). Geocodifico quindi tutti gli
indirizzi; lo script di costruzione decide poi quale coordinata usare.

- Rispetta la policy di Nominatim: al massimo 1 richiesta al secondo, User-Agent identificativo,
  risultati salvati in cache (data-raw/geocodifica_cache.json) per non ripetere le richieste.
- Tentativi in ordine: via + civico + CAP, ricerca libera con civico, via senza iniziali;
  se il civico non si trova: solo via (posizione approssimata).

Dati © OpenStreetMap contributors, licenza ODbL.

Uso:  python3 scripts/geocodifica.py
"""
import csv
import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data-raw"
CACHE = RAW / "geocodifica_cache.json"
URL = "https://nominatim.openstreetmap.org/search"
UA = "geocodifica-farmacie-opendata/1.0"
VERSIONE = 4  # cambia quando cambia la strategia: rifa' solo i casi non risolti
PAUSA = 1.5  # secondi tra due richieste (limite Nominatim: 1 al secondo)

_ultima = 0.0


def separa_indirizzo(indirizzo: str) -> tuple[str, str | None]:
    """'Via Dei Velieri, 71/81' -> ('Via Dei Velieri', '71')."""
    s = re.sub(r"\(.*?\)", " ", indirizzo)
    s = " ".join(s.split())
    # "Via Via Luigi Sica" -> "Via Luigi Sica"
    s = re.sub(r"^(\w+)\s+\1\b", r"\1", s, flags=re.I)
    civico = None
    via = s
    if "," in s:
        via, resto = s.split(",", 1)
        m = re.search(r"\d+", resto)
        if m and not re.search(r"km", resto, re.I):
            civico = m.group()
    else:
        m = re.match(r"^(.*?\D)\s+(\d+)\s*[\w/\-]*$", s)
        if m:
            via, civico = m.group(1), m.group(2)
    via = re.sub(r"\s+\d+.*$", "", via.strip()) or via.strip()
    return via.strip(" ,"), civico


def chiedi(params: dict) -> list:
    global _ultima
    attesa = PAUSA - (time.monotonic() - _ultima)
    if attesa > 0:
        time.sleep(attesa)
    for tentativo in range(4):
        try:
            r = requests.get(URL, params=params, headers={"User-Agent": UA}, timeout=60)
            _ultima = time.monotonic()
            if r.status_code == 200:
                return r.json()
            print(f"    HTTP {r.status_code}, riprovo")
        except requests.RequestException as e:
            _ultima = time.monotonic()
            print(f"    errore {e}, riprovo")
        time.sleep(5 * (tentativo + 1))
    return []


def senza_iniziali(via: str) -> str:
    """'Via G.B. Morgagni' -> 'Via Morgagni' (Nominatim non trova le iniziali puntate)."""
    v = re.sub(r"\b(?:[A-Za-z]\.\s*)+", " ", via)
    return " ".join(v.split())


# Riquadro del Comune di Roma: senza questo limite Nominatim con "Roma" accetta anche vie omonime
# negli altri comuni della Citta' metropolitana (Anzio, Campagnano, Lanuvio...).
VIEWBOX = "12.23,42.15,12.86,41.65"
TOPONIMI = r"^(via|viale|piazza|piazzale|largo|vicolo|circonvallazione|lungotevere|corso|borgo|salita|clivo|passeggiata|galleria)\s+"


def a_roma(r: dict) -> bool:
    """Accetto solo risultati nel Comune di Roma (non negli altri comuni della Citta' metropolitana).
    Non uso il CAP: in OSM alcune vie di Roma hanno CAP errati (es. 00011 a Corcolle)."""
    return r.get("address", {}).get("city") == "Roma"


def senza_toponimo(via: str) -> str:
    return re.sub(TOPONIMI, "", via, flags=re.I)


def _esito(r: dict, nome: str) -> dict:
    addr = r.get("address", {})
    return {
        "lat": float(r["lat"]), "lon": float(r["lon"]),
        "metodo": nome,
        "civico_trovato": "house_number" in addr or r.get("category") in ("amenity", "healthcare", "shop"),
        "via_trovata": addr.get("road"),
        "cap_trovato": addr.get("postcode"),
        "comune_trovato": addr.get("city") or addr.get("town") or addr.get("village"),
        "display_name": r.get("display_name"),
    }


def geocodifica(via: str, civico: str | None, cap: str) -> dict:
    base = {"format": "jsonv2", "addressdetails": 1, "limit": 3, "countrycodes": "it",
            "viewbox": VIEWBOX, "bounded": 1}
    strut = {"city": "Roma", "country": "Italia"}
    via2 = senza_iniziali(via)
    a_civico, a_via = [], []
    if civico:
        a_civico.append(("civico+cap", {**strut, "street": f"{civico} {via}", "postalcode": cap}))
        a_civico.append(("testo+civico", {"q": f"{via2} {civico}, {cap} Roma"}))
        if via2 != via:
            a_civico.append(("civico_senza_iniziali", {**strut, "street": f"{civico} {via2}"}))
        a_civico.append(("testo_senza_toponimo", {"q": f"{senza_toponimo(via2)} {civico}, {cap} Roma"}))
    a_via.append(("via+cap", {**strut, "street": via, "postalcode": cap}))
    a_via.append(("testo_via", {"q": f"{via2}, {cap} Roma"}))
    ripiego = None
    # 1) tentativi con il numero civico: mi fermo appena il civico e' trovato davvero
    for nome, extra in a_civico:
        ris = [r for r in chiedi({**base, **extra}) if a_roma(r)]
        if ris:
            e = _esito(ris[0], nome)
            if e["civico_trovato"]:
                return e
            ripiego = ripiego or e
    if ripiego:
        return ripiego
    # 2) solo la via (posizione approssimata)
    for nome, extra in a_via:
        ris = [r for r in chiedi({**base, **extra}) if a_roma(r)]
        if ris:
            e = _esito(ris[0], nome)
            e["civico_trovato"] = False  # cercata solo la via
            return e
    return {"lat": None, "lon": None, "metodo": "non_trovato"}


def main() -> None:
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    with (RAW / "farmacie_roma_attive.csv").open(encoding="utf-8") as f:
        righe = list(csv.DictReader(f, delimiter=";"))
    def da_rifare(r):
        c = cache.get(r["cod_farmacia"])
        if c is None or c.get("indirizzo") != r["indirizzo"]:
            return True
        # con una nuova strategia rifaccio solo i casi non risolti o finiti fuori Roma
        fuori = c.get("lat") is None or c.get("comune_trovato", "Roma") != "Roma" \
            or not (c.get("cap_trovato") or "001").startswith("001")
        return c.get("versione", 1) < VERSIONE and fuori
    da_fare = [r for r in righe if da_rifare(r)]
    print(f"Farmacie: {len(righe)}, da geocodificare: {len(da_fare)}")
    for i, r in enumerate(da_fare, 1):
        via, civico = separa_indirizzo(r["indirizzo"])
        esito = geocodifica(via, civico, r["cap"])
        esito.update({"indirizzo": r["indirizzo"], "via_cercata": via, "civico_cercato": civico,
                      "versione": VERSIONE})
        cache[r["cod_farmacia"]] = esito
        print(f"[{i}/{len(da_fare)}] {r['indirizzo']} -> {esito['metodo']}")
        if i % 20 == 0:
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Fatto.")


if __name__ == "__main__":
    main()
