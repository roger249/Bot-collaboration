"""Semantic embedding for PFS — embedder abstraction + similarity feature logic.

Logic Layer: no ``duckdb`` / ``httpx`` here.  Vector persistence lives in
``src.planbot.embeddings_store``.

Provides:

* ``Embedder`` protocol with the production ``SentenceTransformerEmbedder``.
* ``HashEmbedder`` — deterministic, dependency-free embedder used **only by unit
  tests** (no torch / model download).  It is NOT wired into the production path.
* ``get_embedder`` — process-wide singleton built from ``config_screener.yaml``.
* Pure helpers: content hash, cosine similarity, 0-10 score mapping.
* ``compute_similarity_features`` — the four PFS similarity dimensions.

All four features are mapped to a 0-10 scale by min-max normalising the cosine
similarity between the model's "irrelevant" floor and "strong match" ceiling
(``(sim − floor) / (ceiling − floor) × 10``).  The dislike feature is inverted
(``10 − score``) so a high score means "the client is comfortable with this
product".
"""

from __future__ import annotations

import hashlib
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np
import yaml

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_SCREENER_CONFIG_PATH = _ROOT_DIR / "config" / "config_screener.yaml"

# The four similarity dimensions appended to PFS.
SIMILARITY_DIMENSIONS = (
    "similarity_product_note_in_like_products",
    "similarity_product_note_in_dislike_products",
    "similarity_to_current_holding",
    "similarity_to_RM_note",
)

_NEUTRAL = 5.0


# ═══════════════════════════════════════════════════════════════════════════
# Embedder abstraction
# ═══════════════════════════════════════════════════════════════════════════


class Embedder(Protocol):
    @property
    def model_id(self) -> str: ...

    def embed(self, text: str, *, role: str | None = None) -> list[float]: ...


# Role → whether the field is a short query vs a long passage (for
# instruction-conditioned models like E5 / INSTRUCTOR).
def field_role(field_name: str) -> str:
    """Return the encoding role for a field: ``query`` (keyword) or ``passage``."""
    return "query" if field_name in ("like_products", "dislike_products") else "passage"


class HashEmbedder:
    """Deterministic, dependency-free embedder — **unit tests only**.

    Character n-gram + whole-word hashing trick.  Similar texts share tokens,
    so cosine similarity is meaningful without a trained model.  This is NOT
    used in production: a real model failure should surface (fail loudly), not
    silently degrade to hash embeddings.
    """

    def __init__(self, dim: int = 768, model_id: str = "hash"):
        self.dim = int(dim)
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    def embed(self, text: str, *, role: str | None = None) -> list[float]:
        # Role/instruction prefixes are model-specific (E5/INSTRUCTOR) and do
        # not apply to the deterministic hash fallback.
        if not text:
            return [0.0] * self.dim
        t = text.lower()
        vec = np.zeros(self.dim, dtype=np.float32)
        grams: list[str] = []
        for n in (3, 4):
            grams.extend(t[i : i + n] for i in range(len(t) - n + 1))
        grams.extend(re.findall(r"[a-z0-9]+", t))
        for g in grams:
            h = hashlib.sha256(g.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "big") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            vec[idx] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        return [float(x) for x in vec]


class SentenceTransformerEmbedder:
    """Sentence encoder via ``sentence-transformers``.

    Any model loadable by ``SentenceTransformer`` (MiniLM, BGE, instructor-*,
    e5, etc.) works — switch by changing ``embedding.model`` in
    ``config_screener.yaml``.  The ``model_id`` is used as the cache namespace,
    so switching models automatically separates their vectors in the store.

    Instruction-conditioned models (E5, INSTRUCTOR) require a role prefix on
    every encode (``query:`` for short search terms, ``passage:`` for long
    documents).  ``query_prefix`` / ``passage_prefix`` are empty for symmetric
    models (MiniLM/BGE), so ``embed()`` is unchanged for them.
    """

    def __init__(
        self,
        model_name: str,
        device: str = "auto",
        *,
        query_prefix: str = "",
        passage_prefix: str = "",
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "sentence-transformers is not installed. Install with: "
                "`uv pip install sentence-transformers`"
            ) from exc
        # "auto" → None so SentenceTransformer picks cuda/mps/cpu itself.
        resolved_device = None if device in (None, "auto") else device
        self._model = SentenceTransformer(model_name, device=resolved_device)
        self._model_name = model_name
        self._query_prefix = query_prefix
        self._passage_prefix = passage_prefix

    @property
    def model_id(self) -> str:
        return self._model_name

    def embed(self, text: str, *, role: str | None = None) -> list[float]:
        if role == "query" and self._query_prefix:
            text = self._query_prefix + text
        elif role == "passage" and self._passage_prefix:
            text = self._passage_prefix + text
        vec = self._model.encode([text])
        return [float(x) for x in vec[0]]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Return the process-wide embedder singleton from ``config_screener.yaml``.

    Fails loudly if the model cannot be loaded — there is deliberately no
    silent hash fallback.  Callers that wish to tolerate an unavailable model
    (e.g. ``product_tool``) catch the exception and degrade to neutral scores
    with an explicit warning.
    """
    emb = resolve_embedding_config()
    model = emb.get("model", "sentence-transformers/all-MiniLM-L6-v2")
    return SentenceTransformerEmbedder(
        model,
        device=emb.get("device", "auto"),
        query_prefix=emb.get("query_prefix", ""),
        passage_prefix=emb.get("passage_prefix", ""),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Pure helpers
# ═══════════════════════════════════════════════════════════════════════════


@lru_cache(maxsize=1)
def load_screener_config() -> dict:
    """Load ``config/config_screener.yaml`` (cached per process)."""
    if not _SCREENER_CONFIG_PATH.exists():
        LOGGER.warning("config_screener.yaml not found; using embedding defaults")
        return {}
    return yaml.safe_load(_SCREENER_CONFIG_PATH.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def resolve_embedding_config() -> dict:
    """Return the effective ``embedding`` config, resolving the named preset.

    When ``embedding.semantic_model_config`` names a preset in
    ``semantic_model_configs``, that preset's keys are merged over the base
    ``embedding`` section (preset wins) — so switching models is a single
    name change, not several edits.  Inline keys remain supported as a fallback.
    """
    config = load_screener_config()
    base = dict(config.get("embedding", {}) or {})
    preset_name = base.get("semantic_model_config")
    if not preset_name:
        return base

    presets = config.get("semantic_model_configs", {}) or {}
    preset = presets.get(preset_name)
    if preset is None:
        LOGGER.warning(
            "semantic_model_config=%r not found in semantic_model_configs; "
            "using inline embedding settings", preset_name,
        )
        return base

    merged = dict(base)
    merged.update(preset)  # preset overrides inline values
    return merged


def compute_content_hash(text: str) -> str:
    """SHA-256 over the embedded free text (change-detection signal)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cosine_sim(a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
    """Cosine similarity in [-1, 1]; 0 for zero vectors."""
    av = np.asarray(a, dtype=np.float32)
    bv = np.asarray(b, dtype=np.float32)
    na = float(np.linalg.norm(av))
    nb = float(np.linalg.norm(bv))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(av, bv) / (na * nb))


def map_sim_to_score(
    sim: float, *, invert: bool = False, floor: float = 0.0, ceiling: float = 1.0
) -> float:
    """Map cosine similarity to a 0-10 score via min-max normalisation.

    Dense sentence embeddings are anisotropic: *every* text sits in a narrow
    positive cosine band (e.g. E5 puts nonsense at ~0.6 and a strong match at
    ~0.84), so a naive ``5 × (1 + sim)`` collapses all scores into a tiny
    range.  Min-max re-scales that band onto the full 0-10 scale using the
    model's empirically-observed bounds.

    Parameters
    ----------
    sim : float
        Raw cosine similarity.
    invert : bool
        Invert the direction (used for dislike/comfort): a high similarity
        becomes a low score and vice-versa.
    floor : float
        The model's "irrelevant" cosine floor (unrelated text still scores
        ~this much).  ``sim <= floor`` maps to score 0.
    ceiling : float
        The model's "strong match" cosine ceiling.  ``sim >= ceiling`` maps to
        score 10.

    Formula (clipped to ``[0, 10]``)::

        score = (sim − floor) / (ceiling − floor) × 10

    Inverted: ``score = 10 − score``.  With ``floor = 0``, ``ceiling = 1`` this
    reduces to the identity ``10 × sim``.
    """
    lo = float(floor)
    hi = float(ceiling)
    if hi <= lo:
        return _NEUTRAL
    s = max(lo, min(hi, float(sim)))
    score = (s - lo) / (hi - lo) * 10.0
    if invert:
        score = 10.0 - score
    return round(max(0.0, min(10.0, score)), 2)


# Short feature key → SIMILARITY_DIMENSIONS name.  Used to look up per-feature
# floor/ceiling bounds from config.
_FEATURE_KEYS = {
    "like": "similarity_product_note_in_like_products",
    "dislike": "similarity_product_note_in_dislike_products",
    "holding": "similarity_to_current_holding",
    "rm": "similarity_to_RM_note",
}


def get_similarity_bounds() -> dict[str, tuple[float, float]]:
    """Return per-feature (floor, ceiling) cosine bounds from the config.

    Keyed by the short feature names (``like`` / ``dislike`` / ``holding`` /
    ``rm``); any unset feature defaults to the identity mapping ``(0.0, 1.0)``.
    """
    emb = resolve_embedding_config()
    cfg = emb.get("similarity_bounds") or {}

    def _pair(value: object) -> tuple[float, float]:
        if isinstance(value, dict):
            try:
                return (
                    float(value.get("floor", 0.0)),
                    float(value.get("ceiling", 1.0)),
                )
            except (TypeError, ValueError):
                pass
        return (0.0, 1.0)

    return {key: _pair(cfg.get(key)) for key in _FEATURE_KEYS}


def _listify(value: object) -> list[str]:
    """Normalise a list-like / scalar field into a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    return [s] if s else []


# ═══════════════════════════════════════════════════════════════════════════
# Similarity feature computation (pure — no I/O)
# ═══════════════════════════════════════════════════════════════════════════


def similarity_scores_from_embeddings(
    *,
    prod_name_emb: list[float] | None,
    prod_note_emb: list[float] | None,
    like_embs: list[list[float]],
    dislike_embs: list[list[float]],
    hold_note_embs: list[list[float]],
    rm_emb: list[float] | None,
    bounds: dict[str, tuple[float, float]] | None = None,
) -> dict[str, float]:
    """Compute the four similarity scores from already-computed embeddings.

    This is the single source of truth for the scoring rules; both the pure
    ``compute_similarity_features`` (embedder-backed) and the integration path
    (store-cached embeddings) delegate here.

    The like/dislike features match the product's ``investment_note`` embedding
    (not the diluted product name) against each keyword — product names are
    dominated by boilerplate wrapper words that mean-pool to near-noise.

    ``similarity_to_RM_note`` matches the RM note against **both** the product
    name and its ``investment_note``, taking the max — the RM note is free text
    that may name a specific theme/sector (best caught by the name) or a broader
    suitability concern (best caught by the note).

    ``bounds`` maps a short feature key (``like`` / ``dislike`` / ``holding`` /
    ``rm``) to its ``(floor, ceiling)`` cosine bounds; an unset feature uses the
    identity mapping ``(0.0, 1.0)``.
    """
    b = bounds or {}
    like_floor, like_ceiling = b.get("like", (0.0, 1.0))
    dislike_floor, dislike_ceiling = b.get("dislike", (0.0, 1.0))
    holding_floor, holding_ceiling = b.get("holding", (0.0, 1.0))
    rm_floor, rm_ceiling = b.get("rm", (0.0, 1.0))

    scores: dict[str, float] = {}

    if prod_note_emb is not None and like_embs:
        sim = max(cosine_sim(prod_note_emb, e) for e in like_embs)
        scores["similarity_product_note_in_like_products"] = map_sim_to_score(
            sim, floor=like_floor, ceiling=like_ceiling
        )
    else:
        scores["similarity_product_note_in_like_products"] = _NEUTRAL

    if prod_note_emb is not None and dislike_embs:
        sim = max(cosine_sim(prod_note_emb, e) for e in dislike_embs)
        scores["similarity_product_note_in_dislike_products"] = map_sim_to_score(
            sim, invert=True, floor=dislike_floor, ceiling=dislike_ceiling
        )
    else:
        scores["similarity_product_note_in_dislike_products"] = _NEUTRAL

    if prod_note_emb is not None and hold_note_embs:
        sim = max(cosine_sim(prod_note_emb, e) for e in hold_note_embs)
        scores["similarity_to_current_holding"] = map_sim_to_score(
            sim, floor=holding_floor, ceiling=holding_ceiling
        )
    else:
        scores["similarity_to_current_holding"] = _NEUTRAL

    # RM note vs. product (name + investment_note), max of whichever surface
    # the RM's free text best aligns with.
    if rm_emb is not None and (prod_name_emb is not None or prod_note_emb is not None):
        sims: list[float] = []
        if prod_name_emb is not None:
            sims.append(cosine_sim(prod_name_emb, rm_emb))
        if prod_note_emb is not None:
            sims.append(cosine_sim(prod_note_emb, rm_emb))
        scores["similarity_to_RM_note"] = map_sim_to_score(
            max(sims), floor=rm_floor, ceiling=rm_ceiling
        )
    else:
        scores["similarity_to_RM_note"] = _NEUTRAL

    return scores


def compute_similarity_features(
    embedder: Embedder,
    client: dict,
    product: dict,
    holdings_products: list[dict],
    bounds: dict[str, tuple[float, float]] | None = None,
) -> dict[str, float]:
    """Compute the four similarity dimensions for one (client, product) pair.

    Embedder-backed convenience wrapper around
    :func:`similarity_scores_from_embeddings` — used for direct/test invocation.
    The integration path pre-computes store-cached embeddings and calls the
    underlying function directly.
    """
    like = _listify(client.get("like_products"))
    dislike = _listify(client.get("dislike_products"))
    rm_note = str(client.get("qualitative_profile") or client.get("RM_note") or "").strip()

    prod_name = str(product.get("name") or "").strip()
    prod_note = str(product.get("investment_note") or "").strip()

    prod_name_emb = embedder.embed(prod_name, role="passage") if prod_name else None
    prod_note_emb = embedder.embed(prod_note, role="passage") if prod_note else None

    like_embs = [embedder.embed(k, role="query") for k in like]
    dislike_embs = [embedder.embed(k, role="query") for k in dislike]
    hold_note_embs = [
        embedder.embed(str(hp.get("investment_note") or hp.get("name") or "").strip(), role="passage")
        for hp in holdings_products
        if str(hp.get("investment_note") or hp.get("name") or "").strip()
    ]
    rm_emb = embedder.embed(rm_note, role="passage") if rm_note else None

    return similarity_scores_from_embeddings(
        prod_name_emb=prod_name_emb,
        prod_note_emb=prod_note_emb,
        like_embs=like_embs,
        dislike_embs=dislike_embs,
        hold_note_embs=hold_note_embs,
        rm_emb=rm_emb,
        bounds=bounds,
    )
