#!/usr/bin/env python3
"""Scarica i dati sorgente in data-raw/.

1. Elenco farmacie dal portale open data del Ministero della Salute
   (il nome del file cambia a ogni aggiornamento: lo ricavo dalla pagina del dataset).
   Salvo solo le farmacie del Comune di Roma ancora attive (data fine validita' vuota).
2. Zone urbanistiche (155, suddivisione storica) dal WFS del geoportale di Roma Capitale,
   layer DIPDIT:ZoneUrbanistiche, in GeoJSON WGS84.

Uso:  python3 scripts/scarica_dati.py
"""
import csv
import html
import io
import json
import sys
from pathlib import Path

import subprocess
import urllib.parse

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data-raw"

MINSAL_BASE = "https://www.dati.salute.gov.it"
MINSAL_PAGE_DATA = MINSAL_BASE + "/page-data/it/dataset/farmacie/page-data.json"

WFS_URL = "https://geoportale.comune.roma.it/geoserver/ows"
WFS_LAYER = "DIPDIT:ZoneUrbanistiche"

COD_ISTAT_ROMA = "058091"
UA = "app-farmacie-roma/1.0 (preparazione dati open data)"


def scarica(url: str, params: dict | None = None) -> bytes:
    """Scarico con curl: il server del Ministero ha una configurazione TLS che la libreria
    'requests' di Python rifiuta, mentre curl la accetta."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    return subprocess.run(
        ["curl", "-sS", "--fail", "-L", "--retry", "3", "-m", "600", "-A", UA, url],
        check=True, capture_output=True,
    ).stdout


def ripara_testo(s: str) -> str:
    """Il CSV del Ministero contiene testo codificato due volte in UTF-8 (es. 'Ã²' al posto di 'ò')
    ed entita' HTML (&amp;). Provo a ripararlo."""
    s = html.unescape(s)
    for _ in range(3):
        if "Ã" not in s and "Â" not in s:
            break
        try:
            s = s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
    return " ".join(s.replace(" ", " ").split())


def scarica_farmacie() -> None:
    meta = json.loads(scarica(MINSAL_PAGE_DATA))
    nodo = meta["result"]["data"]["allNodeDataset"]["nodes"][0]
    file_csv = nodo["relationships"]["field_listafile"][0]
    url = MINSAL_BASE + file_csv["url"]
    print(f"Scarico {url}")
    testo = scarica(url).decode("utf-8")
    righe = list(csv.DictReader(io.StringIO(testo), delimiter=";"))
    print(f"  righe totali nel file: {len(righe)}")

    attive = [
        rr for rr in righe
        if rr["cod_comune"] == COD_ISTAT_ROMA
        and rr["data_fine_validita"].strip() in ("", "-")
    ]
    print(f"  farmacie attive nel Comune di Roma: {len(attive)}")

    out = RAW / "farmacie_roma_attive.csv"
    campi = list(righe[0].keys())
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campi, delimiter=";")
        w.writeheader()
        for rr in attive:
            w.writerow({k: ripara_testo(v or "") for k, v in rr.items()})
    (RAW / "fonte_farmacie.json").write_text(json.dumps({
        "url": url,
        "file": file_csv["filename"],
        "licenza": nodo.get("field_licenza"),
        "farmacie_attive_roma": len(attive),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  salvato {out.relative_to(ROOT)}")


def scarica_zone() -> None:
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": WFS_LAYER,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
    }
    print(f"Scarico {WFS_LAYER} da {WFS_URL}")
    gj = json.loads(scarica(WFS_URL, params))
    n = len(gj["features"])
    print(f"  zone urbanistiche: {n}")
    if n != 155:
        print("  ATTENZIONE: attese 155 zone", file=sys.stderr)
    out = RAW / "zone_urbanistiche.geojson"
    out.write_text(json.dumps(gj, ensure_ascii=False), encoding="utf-8")
    print(f"  salvato {out.relative_to(ROOT)}")


if __name__ == "__main__":
    RAW.mkdir(exist_ok=True)
    scarica_farmacie()
    scarica_zone()
