"""Stimmdienst des Diavortrags (aus dem Projekt „Rollenspiel“ übernommen): die Sprecherstimmen live (erzaehler.py –
Qwen3-TTS Base, geklont, mit CUDA-Graph-Beschleunigung etwa so schnell wie Echtzeit). Läuft in der eigenen qwen-tts-venv
auf Port 8431 und wird vom Diashow-Server beim Start eines Vortrags gestartet. Ohne Anfrage beendet er sich nach
15 Minuten selbst und gibt die ~5 GB Grafikspeicher wieder frei.

POST /sprechen {"text": ..., "stimme": "erzaehler1", "sprache": "German"}  ->  audio/wav
POST /ende                                             ->  Dienst beendet sich
GET  /status                                           ->  {"bereit": true}
"""
import io
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import soundfile as sf

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8431
_zustand = {"erzaehler": None, "bereit": False, "fehler": "", "zuletzt": time.time()}
_sperre = threading.Lock()
RUHE_ENDE = 15 * 60   # ohne Anfrage beendet sich der Dienst selbst (gibt den Grafikspeicher frei)


def waechter():
    while True:
        time.sleep(30)
        if time.time() - _zustand["zuletzt"] > RUHE_ENDE:
            print(f"{time.strftime('%H:%M:%S')} lange nichts zu tun – Stimmdienst beendet sich", flush=True)
            os._exit(0)


def laden():
    try:
        from erzaehler import Erzaehler
        e = Erzaehler()
        _zustand.update(erzaehler=e, bereit=True)
        print(f"{time.strftime('%H:%M:%S')} Stimmdienst bereit – Stimmen {list(e.stimmen)}, beschleunigt: {e.beschleunigt}",
              flush=True)
    except Exception as exc:  # noqa: BLE001
        _zustand["fehler"] = f"{type(exc).__name__}: {exc}"
        print(f"Stimmdienst: {_zustand['fehler']}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, daten):
        body = json.dumps(daten).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/status"):
            # version 2: versteht "sprache" – der Diashow-Server ersetzt einen älteren Dienst, der nur Deutsch kann
            return self._json(200, {"bereit": _zustand["bereit"], "fehler": _zustand["fehler"], "version": 2})
        self.send_error(404)

    def do_POST(self):
        if self.path.startswith("/ende"):   # der Spielserver braucht den Grafikspeicher (auch nach seinem Neustart)
            self._json(200, {"ende": True})
            threading.Timer(0.2, lambda: os._exit(0)).start()
            return
        if not self.path.startswith("/sprechen"):
            return self.send_error(404)
        _zustand["zuletzt"] = time.time()
        try:
            anfrage = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except ValueError:
            return self._json(400, {"fehler": "Ungültiges JSON"})
        text = str(anfrage.get("text", "")).strip()[:600]
        if not _zustand["bereit"] or not text:
            return self._json(503, {"fehler": _zustand["fehler"] or "Stimme lädt noch"})
        t = time.perf_counter()
        with _sperre:   # die Graphen sind nicht für gleichzeitige Aufrufe gebaut
            wav, sr = _zustand["erzaehler"].sprechen(text, str(anfrage.get("stimme") or "erzaehler1"),
                                                     str(anfrage.get("sprache") or "German"))
        puffer = io.BytesIO()
        sf.write(puffer, wav, sr, format="WAV")
        body = puffer.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Rechenzeit", f"{time.perf_counter() - t:.2f}")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    threading.Thread(target=laden, daemon=True).start()
    threading.Thread(target=waechter, daemon=True).start()
    ThreadingHTTPServer.allow_reuse_address = False
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
