#!/usr/bin/env python3
"""Costruisce i dati dell'app (docs/data/) a partire da data-raw/.

- Raggruppa le 155 zone urbanistiche nei 19 ex municipi (1977-2013) usando il numero
  iniziale del codice zona (es. 4a -> IV, 13f -> XIII). L'ex XIV (Fiumicino) non esiste piu'.
- Sceglie per ogni farmacia la coordinata piu' affidabile tra quella del Ministero e quella
  geocodificata con Nominatim (OpenStreetMap).
- Assegna a ogni farmacia zona urbanistica ed ex municipio in base alla posizione (punto nel poligono).
- Scrive un report dei casi dubbi in data-raw/report_qualita.md.

Uso:  python3 scripts/costruisci.py
"""
import collections
import csv
import json
import math
import re
from datetime import date
from pathlib import Path

from shapely.geometry import Point, Polygon, MultiPolygon, mapping, shape
from shapely.ops import polylabel, unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data-raw"
OUT = ROOT / "docs" / "data"

SEMPLIFICA = 0.00008       # gradi (~7 m): tolleranza di semplificazione dei confini
DECIMALI = 5               # ~1 m
SEGNAPOSTO_MIN = 5         # stessa coordinata per >= 5 farmacie = punto fittizio
DIST_ACCORDO_M = 400       # Ministero e OSM "concordano" se entro questa distanza
DIST_ZONA_VICINA_M = 300   # punto appena fuori dai confini (es. sulla costa): zona piu' vicina

ROMANI = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX",
          10: "X", 11: "XI", 12: "XII", 13: "XIII", 15: "XV", 16: "XVI", 17: "XVII",
          18: "XVIII", 19: "XIX", 20: "XX"}

# Denominazioni d'uso comune degli ex municipi (solo come aiuto all'orientamento).
NOMI_MUNICIPI = {
    1: "Centro Storico", 2: "Parioli, Flaminio, Salario", 3: "Nomentano, San Lorenzo",
    4: "Monte Sacro", 5: "Tiburtino", 6: "Prenestino, Casilino", 7: "Centocelle",
    8: "Delle Torri", 9: "Tuscolano, Appio Latino", 10: "Cinecittà, Don Bosco",
    11: "Ostiense, Garbatella", 12: "EUR", 13: "Ostia, Acilia", 15: "Portuense, Magliana",
    16: "Monteverde", 17: "Prati", 18: "Aurelio", 19: "Monte Mario, Primavalle",
    20: "Cassia, Flaminia",
}

# Refusi nel layer del geoportale.
CORREZIONI_NOMI = {"Aeropoprto dell' Urbe": "Aeroporto dell'Urbe"}


def metri(lat1, lon1, lat2, lon2) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def arrotonda(geom):
    def rnd(c):
        return [round(c[0], DECIMALI), round(c[1], DECIMALI)]
    g = mapping(geom)
    def walk(x):
        if isinstance(x[0], (int, float)):
            return rnd(x)
        return [walk(y) for y in x]
    return {"type": g["type"], "coordinates": walk(g["coordinates"])}


def poligoni(g):
    return list(g.geoms) if isinstance(g, MultiPolygon) else [g]


def riempi_buchi_piccoli(g, area_max=1e-7):
    """Elimina i buchi minuscoli dovuti a imprecisioni di digitalizzazione (non le enclave vere)."""
    out = []
    for p in poligoni(g):
        holes = [h for h in p.interiors if Polygon(h).area > area_max]
        out.append(Polygon(p.exterior, holes))
    return unary_union(out)


def nome_zona(n: str) -> str:
    n = CORREZIONI_NOMI.get(n, n)
    return re.sub(r"'\s+", "'", n).strip()


def carica_zone():
    gj = json.loads((RAW / "zone_urbanistiche.geojson").read_text(encoding="utf-8"))
    zone, anomalie = [], []
    for f in gj["features"]:
        p = f["properties"]
        codice = p["ZONA_URBANISTICA"].strip()
        m = re.fullmatch(r"(\d+)([a-zA-Z])", codice)
        if not m:
            anomalie.append(f"Codice zona non riconosciuto: {codice!r}")
            continue
        num = int(m.group(1))
        if num not in ROMANI:
            anomalie.append(f"Zona {codice} con numero di municipio inesistente ({num})")
            continue
        geom = shape(f["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        zone.append({
            "codice": codice.upper(),
            "nome": nome_zona(p["DENOMINAZIONE"]),
            "municipio": num,
            "speciale": m.group(2).lower() in "xy",
            "geom": geom,
        })
    return zone, anomalie


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    zone, anomalie_zone = carica_zone()
    report = ["# Report qualità dati", "", f"Generato il {date.today():%d/%m/%Y}.", ""]

    # ---------- Ex municipi ----------
    per_mun = collections.defaultdict(list)
    for z in zone:
        per_mun[z["municipio"]].append(z)
    roma = unary_union([z["geom"] for z in zone])
    tree = STRtree([z["geom"] for z in zone])

    report += ["## Zone urbanistiche → ex municipi", "",
               f"- Zone lette: {len(zone)} (attese 155)",
               f"- Gruppi (ex municipi): {len(per_mun)} (attesi 19)", ""]
    report += [f"- {a}" for a in anomalie_zone]
    report += ["", "| Ex municipio | N. zone | Zone |", "|---|---|---|"]
    for num in sorted(per_mun):
        zz = sorted(per_mun[num], key=lambda z: (z["codice"][-1] in "XY", z["codice"]))
        report.append(f"| {ROMANI[num]} | {len(zz)} | " +
                      ", ".join(f"{z['codice']} {z['nome']}" for z in zz) + " |")
    speciali = [z for z in zone if z["speciale"]]
    report += ["", f"Zone con lettera X/Y (parchi, aree archeologiche o di servizio): {len(speciali)}", ""]
    report += [f"- {z['codice']} {z['nome']} → ex {ROMANI[z['municipio']]}" for z in
               sorted(speciali, key=lambda z: (z['municipio'], z['codice']))]
    report.append("")

    # ---------- Farmacie ----------
    with (RAW / "farmacie_roma_attive.csv").open(encoding="utf-8") as f:
        righe = list(csv.DictReader(f, delimiter=";"))
    geo = json.loads((RAW / "geocodifica_cache.json").read_text(encoding="utf-8"))

    def num(s):
        s = (s or "").strip()
        return None if s in ("", "-") else float(s.replace(",", "."))

    conteggio_coord = collections.Counter(
        (r["latitudine"], r["longitudine"]) for r in righe if num(r["latitudine"]) is not None)

    def zona_di(lat, lon):
        pt = Point(lon, lat)
        for i in tree.query(pt, predicate="intersects"):
            return zone[i], 0.0
        i = tree.nearest(pt)
        z = zone[i]
        d = z["geom"].exterior.distance(pt) if isinstance(z["geom"], Polygon) else z["geom"].distance(pt)
        return z, d * 111000 * math.cos(math.radians(lat))

    farmacie, dubbi, escluse = [], [], []
    stat = collections.Counter()
    for r in righe:
        mlat, mlon = num(r["latitudine"]), num(r["longitudine"])
        motivo_m = None
        if mlat is None:
            motivo_m = "assenti"
        elif conteggio_coord[(r["latitudine"], r["longitudine"])] >= SEGNAPOSTO_MIN:
            motivo_m = "punto fittizio condiviso"
        elif not roma.contains(Point(mlon, mlat)):
            motivo_m = "fuori dal Comune di Roma"
        m_ok = motivo_m is None

        g = geo.get(r["cod_farmacia"], {})
        glat, glon = g.get("lat"), g.get("lon")
        g_ok = glat is not None and roma.buffer(0.003).contains(Point(glon, glat))
        g_civico = g_ok and g.get("civico_trovato")

        nota = None
        if g_civico and m_ok:
            d = metri(mlat, mlon, glat, glon)
            lat, lon, fonte, precisione = glat, glon, "osm", "civico"
            if d > DIST_ACCORDO_M:
                nota = f"Ministero e OSM distano {d:.0f} m: usata OSM (civico)"
        elif g_civico:
            lat, lon, fonte, precisione = glat, glon, "osm", "civico"
        elif m_ok and g_ok:
            d = metri(mlat, mlon, glat, glon)
            if d <= 1500:
                lat, lon, fonte, precisione = mlat, mlon, "ministero", "civico"
            else:
                lat, lon, fonte, precisione = mlat, mlon, "ministero", "approssimata"
                nota = f"Civico non trovato su OSM e via OSM a {d:.0f} m dal punto del Ministero"
        elif m_ok:
            lat, lon, fonte, precisione = mlat, mlon, "ministero", "approssimata"
            nota = "Indirizzo non trovato su OSM: usata solo la coordinata del Ministero"
        elif g_ok:
            lat, lon, fonte, precisione = glat, glon, "osm", "approssimata"
            nota = f"Coordinate Ministero {motivo_m}; su OSM trovata solo la via (posizione al centro della via)"
        else:
            escluse.append((r, f"Coordinate Ministero {motivo_m}; indirizzo non trovato su OSM"))
            continue
        stat[(fonte, precisione)] += 1

        z, dz = zona_di(lat, lon)
        if dz > DIST_ZONA_VICINA_M:
            escluse.append((r, f"Punto a {dz:.0f} m fuori dai confini comunali"))
            continue
        if dz > 0:
            nota = (nota + "; " if nota else "") + f"punto {dz:.0f} m fuori dai confini, assegnato alla zona più vicina"

        cap_osm = g.get("cap_trovato")
        if g_ok and cap_osm and r["cap"] and cap_osm != r["cap"] and fonte == "osm":
            nota = (nota + "; " if nota else "") + f"CAP Ministero {r['cap']} ≠ CAP OSM {cap_osm}"

        fraz = r["frazione"].strip()
        if fraz.lower() in ("-", "roma"):
            fraz = ""
        f = {
            "id": r["cod_farmacia"],
            "n": r["descrizione_farmacia"].strip(),
            "i": r["indirizzo"].strip().rstrip(","),
            "c": r["cap"].strip(),
            "fr": fraz.title(),
            "t": r["descrizione_tipologia"] if r["descrizione_tipologia"] not in ("", "-") else "",
            "d": r["data_inizio_validita"],
            "la": round(lat, 6), "lo": round(lon, 6),
            "z": z["codice"], "m": z["municipio"],
            "p": 1 if precisione == "civico" else 0,
        }
        farmacie.append(f)
        if nota:
            dubbi.append((f, nota))

    farmacie.sort(key=lambda f: (f["m"], f["n"].lower()))
    cont_mun = collections.Counter(f["m"] for f in farmacie)
    cont_zona = collections.Counter(f["z"] for f in farmacie)

    # ---------- Output geografici ----------
    feats_mun = []
    for numm in sorted(per_mun):
        g = riempi_buchi_piccoli(unary_union([z["geom"] for z in per_mun[numm]]))
        g = g.simplify(SEMPLIFICA, preserve_topology=True)
        principale = max(poligoni(g), key=lambda p: p.area)
        lp = polylabel(principale, tolerance=0.0005)  # punto interno per l'etichetta
        feats_mun.append({"type": "Feature", "properties": {
            "num": numm, "romano": ROMANI[numm], "nome": NOMI_MUNICIPI[numm],
            "lp": [round(lp.y, 5), round(lp.x, 5)],
            "zone": len(per_mun[numm]), "farmacie": cont_mun.get(numm, 0)},
            "geometry": arrotonda(g)})
    feats_zone = []
    for z in sorted(zone, key=lambda z: (z["municipio"], z["codice"])):
        feats_zone.append({"type": "Feature", "properties": {
            "codice": z["codice"], "nome": z["nome"], "num": z["municipio"],
            "farmacie": cont_zona.get(z["codice"], 0)},
            "geometry": arrotonda(z["geom"].simplify(SEMPLIFICA, preserve_topology=True))})

    def scrivi(nome, obj):
        (OUT / nome).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                                encoding="utf-8")

    fonte = json.loads((RAW / "fonte_farmacie.json").read_text(encoding="utf-8"))
    scrivi("ex_municipi.geojson", {"type": "FeatureCollection", "features": feats_mun})
    scrivi("zone_urbanistiche.geojson", {"type": "FeatureCollection", "features": feats_zone})
    scrivi("farmacie.json", {
        "aggiornamento": date.today().isoformat(),
        "fonte": fonte["file"],
        "zone": {z["codice"]: z["nome"] for z in zone},
        "farmacie": farmacie,
    })

    # ---------- Report ----------
    report += ["## Farmacie", "",
                f"- Attive nel Comune di Roma (file Ministero `{fonte['file']}`): {len(righe)}",
                f"- Sulla mappa: {len(farmacie)}",
                f"- Escluse (posizione non determinabile): {len(escluse)}", "",
                "Origine delle coordinate usate:", ""]
    etichette = {("osm", "civico"): "OpenStreetMap, numero civico",
                 ("ministero", "civico"): "Ministero, confermata da OSM (stessa via)",
                 ("ministero", "approssimata"): "Ministero, non confermata",
                 ("osm", "approssimata"): "OpenStreetMap, solo via (approssimata)"}
    report += [f"- {etichette[k]}: {v}" for k, v in sorted(stat.items(), key=lambda x: -x[1])]
    report += ["", "| Ex municipio | Farmacie |", "|---|---|"]
    report += [f"| {ROMANI[k]} | {cont_mun.get(k, 0)} |" for k in sorted(ROMANI)]
    report += ["", f"### Farmacie escluse ({len(escluse)})", ""]
    report += [f"- {r['cod_farmacia']} {r['descrizione_farmacia']} — {r['indirizzo']} {r['cap']}: {m}"
               for r, m in escluse]
    report += ["", f"### Casi da verificare ({len(dubbi)})", "",
               "| Cod. | Farmacia | Indirizzo | Ex mun. | Nota |", "|---|---|---|---|---|"]
    report += [f"| {f['id']} | {f['n']} | {f['i']} {f['c']} | {ROMANI[f['m']]} | {n} |" for f, n in dubbi]
    (RAW / "report_qualita.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(f"Zone: {len(zone)}  Ex municipi: {len(per_mun)}")
    print(f"Farmacie sulla mappa: {len(farmacie)}  escluse: {len(escluse)}  da verificare: {len(dubbi)}")
    for k, v in stat.items():
        print(f"  {k}: {v}")
    for k in sorted(ROMANI):
        print(f"  {ROMANI[k]:>5}: {cont_mun.get(k, 0)}")


if __name__ == "__main__":
    main()
