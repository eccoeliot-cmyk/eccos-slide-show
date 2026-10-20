# diashow-vortrag — Diavortrag im Browser (LM Studio Plugin)

## Was es macht

Eine Webseite (http://127.0.0.1:8430), auf der du in der Mitte ein **Thema** eingibst, darunter mit einem
**Schieberegler die Länge (5–30 Minuten)** wählst und den **Projektor einschaltest**. Danach läuft ein vertonter
Diavortrag im Vollbild:

- **Titeldia** mit Titel und Untertitel – ohne Sprecher, die Musik beginnt.
- **Je Dia ein Bild (1024 × 1024, wie die alten Dias) und 2–4 gesprochene Sätze**, der gerade gesprochene Satz wird
  unter dem Bild hervorgehoben.
- **Diawechsel wie beim Diaprojektor**: das Dia wird mit einem Klacken hinausgeschoben, kurz leuchtet das leere
  Projektorlicht, das nächste Dia schiebt sich hinein.
- **Schlussdia „Ende“**, die Musik klingt aus.
- Oben rechts: **„Vortrag beenden“** – stoppt Stimme, Musik und die Erzeugung auf der Grafikkarte sofort.

Hintergrundmusik (Auswahl auf der Startseite):

| Auswahl | Was passiert |
|---|---|
| Aus dem Musikordner (Standard) | zufällige Stücke aus dem Musikordner, mit Überblendung |
| Passend erzeugen | ACE-Step erzeugt Musik passend zum Thema (nur wenn ACE-Step schon läuft); bis sie fertig ist, spielt Musik aus dem Ordner |
| Keine Musik | – |

Musikordner: `musik/` im Projekt (deine ausgewählten Stücke). Ist er leer, nimmt das Plugin
`%USERPROFILE%\LMStudioLocalPlugins\ACE-Step-1.5\.cache\acestep\tmp\api_audio`
(änderbar über die Umgebungsvariable `DIASHOW_MUSIK`).

## Wie es funktioniert

Aufbau übernommen aus dem Projekt **Rollenspiel**:

| Teil | Womit |
|---|---|
| Text (Gliederung + Sprechtext je Dia) | das in LM Studio **geladene** Sprachmodell (z. B. qwen3.8-9b-distill) über die LM-Studio-API (Token aus `case_files\lmstudio_token.txt`). Ist gar keins geladen, wird `qwen3.8-9b-distill` geladen – ein geladenes Modell wird nie gewechselt. |
| Bilder | ComfyUI mit FLUX.2 [klein] (distilliert, 4 Schritte). Läuft ComfyUI nicht, startet der Server es selbst. |
| Stimme | **Qwen3-TTS** (geklonte Sprecher aus dem Rollenspiel, CUDA-Graph-beschleunigt) – das Sprachmodell wählt je Thema einen von fünf Sprechern. Ersatz, falls Qwen3-TTS ausfällt: Piper (Thorsten). |
| Musik | Musikordner oder ACE-Step |

**Vorausschauend:** Text → Bild → Stimme laufen als Fließband in drei Threads und arbeiten bis zu 3 Dias vor dem
gerade gezeigten. Der Projektor startet, sobald Titelbild und die ersten 2 Dias fertig sind (gemessen 75–95 s); bis
dahin zeigt die Leinwand eine **Prozentanzeige** mit dem aktuellen Schritt und der vergangenen Zeit.

**Spannungsbogen:** Die Gliederung baut Neugier und Spannung bis zu einem **Höhepunkt** bei ~70–80 % des Vortrags auf,
danach ein ruhiger Ausklang und ein warmes, positives **Fazit**, damit der Zuschauer mit einem guten Gefühl geht. Jedes
Dia kennt seine Rolle (Aufbau, Höhepunkt, Ausklang, Schluss). Vor dem Höhepunkt wird das Projektorlicht kurz dunkel und
die Musik schwillt an; am Ende trägt die Musik das „Ende“-Dia und klingt dann aus. Wird die Zeit knapp, kommt zuerst der
Höhepunkt und gleich danach das Fazit – der Vortrag endet zur eingestellten Länge, ohne den Höhepunkt zu verlieren.

**Lektor:** Weil das Sprachmodell schwach ist, prüft ein zweiter Durchgang desselben Modells (nüchtern, Temperatur 0,3)
die Gliederung (Reihenfolge, Dopplungen, zweifelhafte Fakten, Spannungsbogen) und jedes Dia gegen ALLES bisher Gesagte
(Widersprüche, Logik, Wiederholungen, zweifelhafte Fakten, Rolle im Bogen) und bessert nach. Ändert er den Inhalt
deutlich, wird auch ein neuer Bildauftrag geschrieben. Jede Korrektur steht mit Begründung in `server.log`.
Grenze: Der Lektor ist dasselbe 9B-Modell – er fängt viel ab, kann aber selbst irren.

**Atmosphäre und Figuren:** Die KI entscheidet je Dia (im Lektor-Durchgang), ob ein Effekt passt – Schnee, Regen,
Sterne (All, Nacht), Funken (Feuer, Krieg), Nebel, Blasen (unter Wasser), Glühwürmchen oder Konfetti; der Browser
zeichnet ihn über das Dia. Außerdem plant die Gliederung 2–4 **Figuren** (Sprites, 100 × 50 px, im Stil des Vortrags,
in ihrer Bewegung gemalt: Vogel im Flug, Mensch im Schritt, Rakete mit Feuerstrahl; leblose Dinge wie sie sind), die ab
und zu passend über den Bildschirm fliegen, laufen, rollen, fallen, schweben oder schwimmen – nicht beim Höhepunkt und
nicht im Schluss. Freigestellt mit `rembg` (lädt beim allerersten Mal ~175 MB), sonst wird der weiße Hintergrund entfernt.

**Saal-Geräusche:** Während der Projektor sich aufwärmt, murmelt ein aufgeregtes Publikum; mit dem Titeldia wird es über
~10 s immer leiser. Der Diawechsel klingt nach echtem Projektor. Während des Vortrags hier und da (alle 25–60 s, leise,
irgendwo im Raum) ein Husten, Räuspern, Stühlerücken, Kleiderrascheln, Papier, Getuschel, Niesen – seltener eine
Plastiktüte, Gläser, eine Bierflasche, eine umkippende Flasche, Schritte oder eine Tür; nie beim Höhepunkt. Am Ende
Applaus. Alle Geräusche wurden einmalig mit **Woosh** (ComfyUI) erzeugt und liegen im Ordner **`sounds/`**
(`<art>_<nr>.flac`, mehrere Varianten je Art, damit sich nichts wiederholt); fehlt eine Art, bleibt es dort still.
Eigene Geräusche einfach dazulegen oder austauschen (z. B. `husten_4.flac`), danach neu installieren.

**Eigene Musik:** liegt im Ordner **`musik/`** (mp3/wav/flac/ogg/m4a) und wird statt des ACE-Step-Ordners verwendet.
Stücke dazulegen oder entfernen, danach neu installieren – das Plugin erkennt die Änderung und ersetzt den Server.

**Sprache:** Oben rechts auf der Startseite: Deutsch, English, Français, Español, Italiano, Português, Русский (gemerkt,
beim ersten Mal die Browsersprache). Gilt für die ganze Oberfläche UND den Vortrag: das Sprachmodell schreibt Titel,
Gliederung und Sprechtext in dieser Sprache, die geklonten Qwen3-TTS-Sprecher sprechen sie. Die Ersatzstimme Piper kann
nur Deutsch (in anderen Sprachen ohne Qwen3-TTS: nur Text). Kein Chinesisch/Japanisch/Koreanisch – Wortzählung und
Satztrennung brauchen Leerzeichen. Fehlermeldungen des Servers bleiben deutsch.

**Programm beenden:** Knopf unten auf der Startseite – beendet laufende Vorträge, den Stimmdienst (gibt ~5 GB
Grafikspeicher frei) und den Server. Beim nächsten Chat in LM Studio startet das Plugin ihn wieder.

**Abwechslung in den Bildern:** Jedes Dia bekommt eine eigene Kameraeinstellung (Totale, Detail, Menschen,
Vogelperspektive, Porträt, Stillleben, Silhouetten …, in zufälliger Folge; Höhepunkt und Schluss fest). Schreiber und
Lektor sehen die letzten Bildaufträge und müssen etwas sichtbar anderes zeigen. Der Stil wird von Motiven gesäubert
(stand darin z. B. „event horizon glows“, zeigte jedes Bild ein Schwarzes Loch).

**Extras abwählbar:** Auf der Startseite lassen sich „Wandernde Figuren“ und „Saal-Geräusche“ ausschalten (gemerkt).
Ohne Figuren werden auch keine gemalt; ohne Saal-Geräusche bleibt nur das leise Klacken beim Diawechsel.

**Musik-Lautstärke:** Regler unten rechts im Projektor (erscheint bei Mausbewegung), wirkt sofort und wird gemerkt.

**GPU-Ampel:** Stimme, Sprachmodell und Bilder teilen sich eine Grafikkarte. Gemessen: alles gleichzeitig bremst
massiv (Stimme bis 3,5× Echtzeit), Stimme + Sprachmodell gleichzeitig ebenfalls, Stimme + Bild und Bild + Text dagegen
sind gleichzeitig schneller als nacheinander. Die Ampel lässt deshalb je Art nur einen Auftrag zu, Stimme und
Sprachmodell nie gleichzeitig, und der Auftrag für das nächste zu zeigende Dia geht vor. Der Startpuffer wächst mit der
Vortragslänge (3–6 Dias). Arbeitet nebenher noch etwas anderes auf der Grafikkarte (z. B. ein Chat in LM Studio), wird
der Vortrag langsamer, und der Projektor kann kurz „Nächstes Dia wird eingelegt“ zeigen.

**Kein Server von Hand:** Das LM-Studio-Plugin startet den Diashow-Server (`vortrag/server.py`) automatisch, sobald
LM Studio das Plugin lädt – und zwar über WMI als eigenständigen Prozess. Grund: LM Studio beendet Plugins ~20 s nach
jeder Chat-Aktivität samt Kindprozessen; als Kindprozess verschwand der Server mitten im Vortrag. Der Server läuft aus
einer Kopie unter `diashow-daten\programm\<Version>` (nie aus dem Plugin-Ordner, sonst blockiert er `lms dev --install`)
und bleibt bis zum Herunterfahren von Windows an. Nach einer Neuinstallation ersetzt das Plugin einen veralteten Server
automatisch – aber nie mitten in einem Vortrag.
Die Startseite wärmt beim Öffnen schon die Stimme vor (~5 GB Grafikspeicher; ohne Vortrag gibt der Stimmdienst ihn
nach 15 Minuten selbst wieder frei).

Das Bild-Plugin `local-image-generation` (generate_image) wird nicht gebraucht. Anlassen schadet nicht (es hält ComfyUI
warm) – nur **nicht während eines Vortrags abschalten**, sonst beendet es ComfyUI mit, und im Chat nebenher keine
Bilder erzeugen (beide teilen sich die Grafikkarte).

## Verwendung

- Seite öffnen: http://127.0.0.1:8430 (Lesezeichen anlegen) – oder im LM-Studio-Chat sagen
  „Öffne die Diashow“ (Werkzeug `diashow_oeffnen`).
- Thema eingeben (gern mit Wünschen: „… für Kinder“, „… im Comic-Stil“), Länge wählen, **Projektor einschalten**.
- Strg+Enter im Themenfeld startet ebenfalls.

## Installation / nach Änderungen

```powershell
cd <Projektordner>
npm install
npm run build
lms dev --install
```

Danach in LM Studio: rechte Seitenleiste → **„Program"** → **„Plugins"** → `eliot/diashow-vortrag` aktivieren.
LM Studio startet Plugins erst bei Aktivität im Chat – danach läuft der Diashow-Server eigenständig weiter.

## Dateien

```
diashow/
├── manifest.json, package.json, tsconfig.json
├── src/                    LM-Studio-Plugin (TypeScript)
│   ├── index.ts            startet beim Laden den Diashow-Server
│   ├── server.ts           Server starten / Browser öffnen
│   └── toolsProvider.ts    Werkzeug diashow_oeffnen
├── vortrag/                der eigentliche Diavortrag (Python, nur Standardbibliothek)
│   ├── server.py           Webserver + Fließband (Gliederung, Text, Bild, Stimme, Musik)
│   ├── web/index.html      Startseite und Projektor
│   ├── tts_dienst.py       Qwen3-TTS-Stimmdienst (Port 8431, qwen-tts-venv)
│   ├── erzaehler.py, tts_schnell.py   Stimmen + Beschleunigung (aus dem Rollenspiel)
│   └── stimmen/            Referenzaufnahmen der fünf Sprecher
├── musik/                  deine Hintergrundmusik (wird mitinstalliert)
└── sounds/                 Saal-Geräusche <art>_<nr>.flac (wird mitinstalliert)
```

Erzeugte Bilder und Ton: `%USERPROFILE%\LMStudioLocalPlugins\diashow-daten\vortraege\` (die letzten 5 Vorträge bleiben,
ältere werden beim nächsten Start gelöscht). Protokolle: `diashow-daten\server.log`, `diashow-daten\stimmdienst.log`.

## Ports

| Port | Dienst |
|---|---|
| 8430 | Diashow-Seite |
| 8431 | Qwen3-TTS-Stimmdienst der Diashow |
| 8188 | ComfyUI |
| 1234 | LM Studio |
| 8001 | ACE-Step (optional) |
