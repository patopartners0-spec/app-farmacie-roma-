# Farmacie di Roma per ex municipio

Web app per informatori scientifici del farmaco (ISF): mappa interattiva delle farmacie del
Comune di Roma, suddivise nei **19 ex municipi** in vigore fino al 2013 (I–XIII e XV–XX;
l'ex XIV è diventato il Comune di Fiumicino nel 1992).

App statica (HTML, CSS, JavaScript): nessun server, nessun database. Si pubblica gratis con
GitHub Pages dalla cartella `docs/`.

## Funzioni

- Mappa con i confini dei 19 ex municipi e, scegliendo un municipio, delle sue zone urbanistiche.
- Conteggio delle farmacie per ex municipio (e per zona urbanistica, passando sulla zona).
- Filtro per ex municipio (menu, elenco o tocco sulla mappa).
- Ricerca per nome, indirizzo, CAP o zona (senza distinzione di maiuscole e accenti).
- Scheda farmacia: nome, indirizzo, CAP, ex municipio, zona urbanistica, tipologia, codice
  ministeriale, pulsanti «Indicazioni» e «Copia indirizzo».
- Pulsante «La mia posizione».
- Link condivisibili: `#m=4` (ex municipio IV), `#f=19519` (scheda di una farmacia), `#q=trullo` (ricerca).
- Interfaccia per smartphone (pannello a scorrimento dal basso) e desktop (pannello laterale).

## Fonti dei dati

| Dato | Fonte | Licenza |
|---|---|---|
| Elenco farmacie | [Ministero della Salute – Open Data, dataset «Farmacie»](https://www.dati.salute.gov.it/it/dataset/farmacie/) | IODL 2.0 |
| Zone urbanistiche (155) | [Geoportale di Roma Capitale](https://geoportale.comune.roma.it/), WFS, layer `DIPDIT:ZoneUrbanistiche` | dati aperti Roma Capitale |
| Correzione coordinate | [Nominatim](https://nominatim.openstreetmap.org/), © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright) | ODbL |
| Mappa di base | © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright) | ODbL |

Filtri applicati all'elenco del Ministero: codice ISTAT del comune `058091` (Roma) e
`data_fine_validita` vuota (nel file è scritta come `-`).

### Zone urbanistiche → ex municipi

Il numero iniziale del codice zona coincide con l'ex municipio (es. `4A` → IV, `13F` → XIII,
`20O` → XX). Le zone con lettera `X`/`Y` sono parchi, aree archeologiche o aree speciali e sono
assegnate allo stesso modo. La tabella completa è in `data-raw/report_qualita.md`.

### Coordinate delle farmacie

Le coordinate del Ministero sono spesso mancanti o sbagliate (centinaia di farmacie sullo stesso
punto fittizio, vie omonime in altri comuni). Per ogni farmacia lo script sceglie:

1. la posizione OpenStreetMap al **numero civico**, se trovata;
2. altrimenti la coordinata del Ministero, se è plausibile (dentro Roma, non un punto condiviso
   da molte farmacie) e coerente con la via trovata su OpenStreetMap;
3. altrimenti la posizione approssimata (centro della via): in mappa compare in **arancione**.

Zona ed ex municipio sono assegnati in base alla posizione (punto nel poligono), non al CAP.
I casi dubbi sono elencati in `data-raw/report_qualita.md`.

## Struttura

```
docs/                 sito pubblicato (GitHub Pages)
  index.html
  css/app.css
  js/app.js
  data/               dati generati: farmacie.json, ex_municipi.geojson, zone_urbanistiche.geojson
  vendor/             Leaflet 1.9.4 e Leaflet.markercluster 1.5.3 (copie locali)
scripts/
  scarica_dati.py     scarica farmacie (Ministero) e zone urbanistiche (geoportale)
  geocodifica.py      geocodifica gli indirizzi con Nominatim (1 richiesta/secondo, con cache)
  costruisci.py       unisce le zone negli ex municipi, sceglie le coordinate, genera docs/data
data-raw/             dati sorgente, cache della geocodifica e report qualità
```

## Aggiornare i dati

Servono Python 3.10+, `curl` e i pacchetti `requests` e `shapely`:

```bash
pip install requests shapely
```

```bash
python3 scripts/scarica_dati.py
```

```bash
python3 scripts/geocodifica.py
```

```bash
python3 scripts/costruisci.py
```

La geocodifica interroga solo le farmacie nuove o con indirizzo cambiato (le altre sono in
`data-raw/geocodifica_cache.json`), rispettando il limite di 1 richiesta al secondo di Nominatim.
Poi controllare `data-raw/report_qualita.md` e fare commit.

## Pubblicare su GitHub Pages

Nel repository: **Settings → Pages → Build and deployment → Source: Deploy from a branch**,
scegliere il branch e la cartella **`/docs`**, salvare. Dopo un minuto il sito è online
all'indirizzo `https://<utente>.github.io/<repository>/`.

Per provarlo in locale:

```bash
python3 -m http.server -d docs 8000
```

e aprire http://localhost:8000.
