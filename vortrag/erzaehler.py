"""Die Sprecherstimmen des Diavortrags (Qwen3-TTS 1.7B Base, geklont) – übernommen aus dem Projekt „Rollenspiel“.
Läuft in der eigenen qwen-tts-venv (über tts_dienst.py).

Warum geklont: VoiceDesign entwirft die Stimme bei jedem Aufruf neu aus der Beschreibung – die Klangfarbe schwankte von
Satz zu Satz. Das Base-Modell klont dagegen eine feste Referenzaufnahme (stimmen/<name>_referenz.wav + .txt), so klingt
jeder Satz nach derselben Person. Die Sprachmodell-Gliederung wählt je Thema einen der Sprecher (siehe server.py).
Beschleunigt mit CUDA Graphs (tts_schnell.py), sonst 2,5x langsamer als Echtzeit.
"""
import os
from pathlib import Path

import torch

HIER = Path(__file__).resolve().parent
MODELL = Path(os.environ.get("RS_TTS_MODELL", str(Path.home() / "LMStudioLocalPlugins" / "qwen-tts" / "modelle"
                                                   / "Qwen3-TTS-12Hz-1.7B-Base")))
STIMMEN_DIR = HIER / "stimmen"


class Erzaehler:
    def __init__(self):
        from qwen_tts import Qwen3TTSModel
        from tts_schnell import beschleunigen
        self.modell = Qwen3TTSModel.from_pretrained(str(MODELL), device_map="cuda:0", dtype=torch.bfloat16,
                                                    attn_implementation="sdpa")
        self.beschleunigt = beschleunigen(self.modell)
        self.stimmen = {}
        for wav in sorted(STIMMEN_DIR.glob("*_referenz.wav")):
            name = wav.name.replace("_referenz.wav", "")
            txt = wav.with_suffix(".txt")
            # ICL-Klon: Referenzton + Referenztext → Klangfarbe UND Sprechweise der Referenz
            self.stimmen[name] = self.modell.create_voice_clone_prompt(
                ref_audio=str(wav), ref_text=txt.read_text(encoding="utf-8").strip() if txt.is_file() else None,
                x_vector_only_mode=not txt.is_file())
        self.sprechen("Hallo.")   # aufwärmen (Graphen, Kernels)

    def sprechen(self, text: str, stimme: str = "erzaehler1", sprache: str = "German"):
        """-> (wav als numpy, Abtastrate). sprache: Qwen3-TTS-Sprachname (German, English, French …) – die geklonten
        Sprecher sprechen auch andere Sprachen."""
        prompt = self.stimmen.get(stimme) or next(iter(self.stimmen.values()))
        wavs, sr = self.modell.generate_voice_clone(text=text, language=sprache, voice_clone_prompt=prompt)
        return wavs[0], sr
