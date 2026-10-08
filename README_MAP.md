# Zelda 3 — automatische Karten- & Daten-Extraktion

Dieses Verzeichnis enthält ein vollautomatisches Skript-Paket, das aus der
Original-ROM (`The Legend of Zelda - Göttin der Weisheit(T + Ger 3.01).sfc`)
alle Karten-Ebenen extrahiert, als JSON speichert, zu PNGs rendert und in einem
interaktiven Web-Prototyp darstellt.

## Voraussetzungen

```sh
python3 -m pip install -r requirements.txt   # Pillow + PyYAML
```

Die ROM muss im Repository-Root liegen (Standardname siehe oben). Alle Skripte
erkennen sie automatisch; ein abweichender Header/übersetzte ROM wird über
`rom_compat.py` tolerant behandelt.

## Die 5 Schritte

### Schritt 1 — Asset-Pipeline
```sh
python3 run_extract_assets.py          # entspricht extract_assets.bat
python3 run_extract_assets.py --no-build   # nur Extraktion, ohne .dat
```
Läuft die Upstream-Pipeline (`assets/restool.py`) gegen die ROM. Tabellen, die
in der deutschen Übersetzung verschoben/leer sind (Musik, Gegner-Sprites,
Dialogue), werden sauber übersprungen statt abzubrechen.

### Schritt 2 — Logik-Extraktor
```sh
python3 extract_map_logic.py
```
Erzeugt `extracted_assets/map_data.json` mit
* allen 14 Dungeons und ihren Räumen (ID, Name, Stockwerk),
* Verbindungen (Treppen, Falllöcher) inkl. Zielraum/-stockwerk,
* interaktiven Elementen (Truhen, Türen),
* Light-/Dark-World-Abmessungen, Eingängen und Löchern.

Die Dungeon-Zuordnung stammt direkt aus der Spiel-Tabelle
`kDungMap_FloorLayout` (Stockwerk-für-Stockwerk-Layout der Räume) – nicht aus
Heuristiken. Zusätzlich wird `map_viewer/data.js` geschrieben, damit der Viewer
auch per `file://` ohne Server funktioniert.

### Schritt 3 — Bild-Exporter
```sh
python3 render_maps.py
```
Schreibt nach `extracted_assets/images/`:
* `overworld_light.png` / `overworld_dark.png` (4096×4096) – **echte**
  Spielgrafik aus dem Mode-7-Weltkarten-Tileset + Palette der ROM,
* `room_000.png … room_255.png` – je ein sauberes Layout-Bild pro Raum.

### Schritt 4 — Validierung
```sh
python3 validate_data.py
```
Prüft: alle 256 Raum-Bilder vorhanden, alle Verbindungsziele existieren,
Treppen (weitgehend) bidirektional, keine verwaisten Koordinaten, alle
Overworld-Eingänge auflösbar. Gibt einen Bericht aus (Exit-Code ≠ 0 bei
Fehlern).

### Schritt 5 — Web-Prototyp
`map_viewer/index.html` im Browser öffnen (kein Server nötig). Features:
* Hauptkarte (Light/Dark World) mit markierten Dungeon-Eingängen, Zoom & Pan,
* Klick auf einen Dungeon-Eingang öffnet die Detailansicht,
* vertikaler Stockwerk-Slider (z. B. `B1 … 7F`),
* dynamisches Laden der passenden Raum-PNGs pro Stockwerk,
* SVG-Overlay, das beim Hovern über Treppen/Falllöcher eine Verbindungslinie
  zum Zielraum bzw. Zielstockwerk zieht,
* Filter-Checkboxen für Truhen, Treppen/Falllöcher, Türen und Bosse.

## Wichtige ROM-Erkenntnisse

Die Übersetzung ist eine reine Text-Übersetzung des US-ROMs, **mit Ausnahme**
einiger Tabellen, die neu verortet wurden und daher in den Upstream-Skripten
scheitern:

| Tabelle | Problem | Umgang |
| --- | --- | --- |
| Gegner-Sprite-Offsets (Bank 0x89) | Offsets ohne 0x8000-Seitenbit | `extract_map_logic.read_room` liest Räume ohne Sprite-Tabelle |
| Overworld-Item-Geheimnisse | Wert 255 außerhalb des gültigen Bereichs | toleranter Lookup |
| Eingänge 131/132 | mit 0xFF leer | werden übersprungen |
| Musik/Default-Rooms/Dialogue | verschoben | werden übersprungen |

## Einschränkungen

* Die **Dungeon-Raumbilder sind schematische Layout-Renderings** (Floors,
  Walls, Stairs, Pits, Truhen, Türen an ihren echten ROM-Positionen und mit
  Farbcodierung). Ein pixelgenaues Nachzeichnen des Dungeon-Hintergrunds würde
  den kompletten Tileset-Decompressor (3bpp→4bpp, Blocksets) benötigen.
* Die **Dark-World-Karte** ist die Weltkarte mit der Dark-World-Palette der
  ROM (die Dark World teilt die Geografie der Light World); das 1024-Byte
  Overlay der ROM ist noch nicht eingerechnet.
* Stockwerk-Labels sind aus dem ROM-Kartenlayout abgeleitet (unterste Reihe =
  `1F`), da das Spiel Stockwerke an Eingängen statt an Räumen speichert.
