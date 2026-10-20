"""Beschleunigung für Qwen3-TTS (Erzähler-Stimmen). Gemessen 2026-10-19: Die GPU ist nur ~22 % ausgelastet, der
Engpass ist Python-Verwaltung. Pro Tonschritt (12,5 je Sekunde Ton) rechnet ein kleines Hilfsmodell (code_predictor,
5 Schichten) 15-mal vorwärts – 129 ms pro Tonschritt, fast nur Verwaltung; für Echtzeit sind 80 ms erlaubt.

Lösung: Jeder der 15 Rechenschritte des Hilfsmodells wird einmal als CUDA Graph aufgezeichnet (fester Zwischenspeicher
für Schlüssel/Werte, feste Masken und Positionen) und danach nur noch abgespielt. Das Ziehen der Codes (top-k/top-p/
Temperatur) bleibt außerhalb der Graphen, das Ergebnis ist rechnerisch dasselbe. Nur unser eigener Code – die
installierte Bibliothek bleibt unverändert. Klappt etwas nicht, bleibt die Original-Funktion.

    from tts_schnell import beschleunigen
    beschleunigen(modell)   # modell = Qwen3TTSModel.from_pretrained(..., device_map="cuda:0")
"""
from types import SimpleNamespace

import torch


def _ziehen(logits: torch.Tensor, do_sample: bool, top_k: int, top_p: float, temperatur: float) -> torch.Tensor:
    if not do_sample:
        return logits.argmax(-1)
    logits = logits.float() / max(float(temperatur or 1.0), 1e-5)
    if top_k and top_k > 0:
        werte, idx = torch.topk(logits, min(int(top_k), logits.shape[-1]))
        if top_p is not None and top_p < 1.0:
            probs = torch.softmax(werte, -1)
            werte = werte.masked_fill(probs.cumsum(-1) - probs > top_p, float("-inf"))
        return idx.gather(-1, torch.multinomial(torch.softmax(werte, -1), 1)).squeeze(-1)
    return torch.multinomial(torch.softmax(logits, -1), 1).squeeze(-1)


class _FesterCache:
    """Minimaler Schlüssel/Werte-Speicher mit fester Länge – nur update(), wie es die Attention-Schichten brauchen."""

    def __init__(self, schichten: int, kv_koepfe: int, laenge: int, kopf_dim: int, dtype, geraet):
        self.k = [torch.zeros(1, kv_koepfe, laenge, kopf_dim, dtype=dtype, device=geraet) for _ in range(schichten)]
        self.v = [torch.zeros_like(x) for x in self.k]

    def update(self, key, value, layer_idx, cache_kwargs=None):
        pos = cache_kwargs["cache_position"]
        self.k[layer_idx].index_copy_(2, pos, key)
        self.v[layer_idx].index_copy_(2, pos, value)
        return self.k[layer_idx], self.v[layer_idx]


class _GraphPredictor:
    def __init__(self, cp, schritte: int = 15):
        p = next(cp.parameters())
        self.dtype, self.geraet = p.dtype, p.device
        modell = cp.model
        cfg = modell.config
        self.cp, self.modell, self.schritte = cp, modell, schritte
        self.schichten = list(modell.layers[: cfg.num_hidden_layers])
        kopf_dim = getattr(cfg, "head_dim", cfg.hidden_size // cfg.num_attention_heads)
        laenge = schritte + 1                      # Vorlauf (2 Positionen) + 14 Einzelschritte = Positionen 0..15
        self.cache = _FesterCache(len(self.schichten), cfg.num_key_value_heads, laenge, kopf_dim, self.dtype, self.geraet)
        einbettungen = modell.get_input_embeddings()
        ein_dim = einbettungen[0].embedding_dim
        self.ein_embeds = torch.zeros(1, 2, ein_dim, dtype=self.dtype, device=self.geraet)
        self.ein_id = torch.zeros(1, 1, dtype=torch.long, device=self.geraet)
        tief = torch.finfo(self.dtype).min
        self.positionen, self.masken, self.cos_sin, self.logits = [], [], [], []
        for i in range(schritte):
            pos = torch.arange(0, 2, device=self.geraet) if i == 0 else torch.tensor([i + 1], device=self.geraet)
            maske = torch.full((1, 1, len(pos), laenge), tief, dtype=self.dtype, device=self.geraet)
            for z, q in enumerate(pos.tolist()):
                maske[0, 0, z, : q + 1] = 0
            dummy = torch.zeros(1, len(pos), cfg.hidden_size, dtype=self.dtype, device=self.geraet)
            cos, sin = modell.rotary_emb(dummy, pos.unsqueeze(0))
            self.positionen.append(pos)
            self.masken.append(maske)
            self.cos_sin.append((cos.contiguous(), sin.contiguous()))
            self.logits.append(None)
        self.graphen = []
        self._aufzeichnen()

    def _schritt(self, i: int):
        if i == 0:
            x = self.cp.small_to_mtp_projection(self.ein_embeds)
        else:
            x = self.cp.small_to_mtp_projection(self.modell.get_input_embeddings()[i - 1](self.ein_id))
        for schicht in self.schichten:
            x = schicht(x, attention_mask=self.masken[i], past_key_values=self.cache, cache_position=self.positionen[i],
                        position_embeddings=self.cos_sin[i])[0]
        x = self.modell.norm(x)
        aus = self.cp.lm_head[i](x[:, -1:, :])
        if self.logits[i] is None:
            self.logits[i] = torch.empty_like(aus)
        self.logits[i].copy_(aus)

    @torch.no_grad()
    def _aufzeichnen(self):
        nebenstrom = torch.cuda.Stream()
        nebenstrom.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(nebenstrom):
            for _ in range(2):
                for i in range(self.schritte):
                    self._schritt(i)
        torch.cuda.current_stream().wait_stream(nebenstrom)
        pool = None
        for i in range(self.schritte):
            g = torch.cuda.CUDAGraph()
            with torch.cuda.graph(g, pool=pool):
                self._schritt(i)
            pool = g.pool()
            self.graphen.append(g)

    @torch.no_grad()
    def generate(self, inputs_embeds, max_new_tokens, do_sample, top_p, top_k, temperature):
        self.ein_embeds.copy_(inputs_embeds)
        self.graphen[0].replay()
        tok = _ziehen(self.logits[0][:, -1, :], do_sample, top_k, top_p, temperature)
        gezogen = [tok]
        for i in range(1, max_new_tokens):
            self.ein_id.copy_(tok[:, None])
            self.graphen[i].replay()
            tok = _ziehen(self.logits[i][:, -1, :], do_sample, top_k, top_p, temperature)
            gezogen.append(tok)
        return SimpleNamespace(sequences=torch.stack(gezogen, dim=1))


def beschleunigen(modell) -> bool:
    """Ersetzt generate() des Hilfsmodells durch die aufgezeichneten Graphen. True, wenn es geklappt hat."""
    wurzel = modell.model if hasattr(modell, "model") else modell
    talker = next((m for _, m in wurzel.named_modules() if hasattr(m, "code_predictor")), None)
    if talker is None or not torch.cuda.is_available():
        return False
    cp = talker.code_predictor
    original = cp.generate
    schritte = talker.config.num_code_groups - 1
    try:
        gp = _GraphPredictor(cp, schritte)
    except Exception as exc:  # noqa: BLE001 – dann eben ohne Beschleunigung
        print(f"Beschleunigung nicht möglich: {type(exc).__name__}: {exc}")
        return False

    def generate(inputs_embeds=None, max_new_tokens=schritte, do_sample=True, top_p=1.0, top_k=50, temperature=0.9,
                 **kwargs):
        if inputs_embeds is None or inputs_embeds.shape[0] != 1 or inputs_embeds.shape[1] != 2 \
                or max_new_tokens != schritte:
            return original(inputs_embeds=inputs_embeds, max_new_tokens=max_new_tokens, do_sample=do_sample,
                            top_p=top_p, top_k=top_k, temperature=temperature, **kwargs)
        return gp.generate(inputs_embeds, max_new_tokens, do_sample, top_p, top_k, temperature)

    cp.generate = generate
    cp._schnell_original = original
    return True
