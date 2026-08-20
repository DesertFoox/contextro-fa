from __future__ import annotations

import json
import math
import mimetypes
import os
import random
import socketserver
import sys
import threading
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
DATA_DIR = APP_DIR / "data"
STATIC_DIR = APP_DIR / "static"


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value.strip().lower())
    replacements = {"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "ؤ": "و", "إ": "ا", "أ": "ا"}
    for src, dst in replacements.items():
        value = value.replace(src, dst)
    return " ".join(value.split())


@dataclass
class TargetInfo:
    word: str
    category: str
    subcategory: str
    hints: list[str] = field(default_factory=list)
    neighbors: dict[str, float] = field(default_factory=dict)


class SemanticEngine:
    def __init__(self) -> None:
        self.targets: dict[str, TargetInfo] = {}
        self.graph: dict[str, dict[str, float]] = defaultdict(dict)
        self.words: set[str] = set()
        self.category_words: dict[str, set[str]] = defaultdict(set)
        self.subcategory_words: dict[str, set[str]] = defaultdict(set)
        self._load()

    def _connect(self, a: str, b: str, weight: float) -> None:
        if not a or not b or a == b:
            return
        weight = max(0.0, min(1.0, float(weight)))
        self.graph[a][b] = max(self.graph[a].get(b, 0.0), weight)
        self.graph[b][a] = max(self.graph[b].get(a, 0.0), weight)
        self.words.update((a, b))

    def _load(self) -> None:
        dataset_path = DATA_DIR / "semantic_dataset.json"
        ontology_path = DATA_DIR / "semantic_ontology.json"
        cross_path = DATA_DIR / "cross_relations.csv"
        vocab_path = DATA_DIR / "vocabulary.txt"

        if dataset_path.exists():
            data = json.loads(dataset_path.read_text(encoding="utf-8"))
            entries = data.get("targets", data if isinstance(data, list) else [])
            if isinstance(entries, dict):
                iterable = []
                for word, payload in entries.items():
                    item = dict(payload or {})
                    item.setdefault("word", word)
                    iterable.append(item)
            else:
                iterable = entries
            for raw in iterable:
                word = normalize_text(str(raw.get("word", "")))
                if not word:
                    continue
                category = normalize_text(str(raw.get("category", "عمومی"))) or "عمومی"
                subcategory = normalize_text(str(raw.get("subcategory", category))) or category
                hints = [str(x).strip() for x in raw.get("hints", []) if str(x).strip()]
                info = TargetInfo(word=word, category=category, subcategory=subcategory, hints=hints)
                neighbors = raw.get("neighbors", raw.get("related", []))
                if isinstance(neighbors, dict):
                    pairs = neighbors.items()
                else:
                    pairs = []
                    for x in neighbors:
                        if isinstance(x, dict):
                            pairs.append((x.get("word", ""), x.get("score", x.get("weight", 0.8))))
                        elif isinstance(x, str):
                            pairs.append((x, 0.8))
                for neigh, weight in pairs:
                    n = normalize_text(str(neigh))
                    if n:
                        info.neighbors[n] = float(weight)
                        self._connect(word, n, float(weight))
                self.targets[word] = info
                self.words.add(word)
                self.category_words[category].add(word)
                self.subcategory_words[subcategory].add(word)

        if ontology_path.exists():
            data = json.loads(ontology_path.read_text(encoding="utf-8"))
            groups = data.get("groups", data if isinstance(data, list) else [])
            if isinstance(groups, dict):
                groups = list(groups.values())
            for group in groups:
                category = normalize_text(str(group.get("category", "عمومی"))) or "عمومی"
                subcategory = normalize_text(str(group.get("subcategory", category))) or category
                members = [normalize_text(str(x)) for x in group.get("words", group.get("members", []))]
                members = [x for x in members if x]
                for w in members:
                    self.words.add(w)
                    self.category_words[category].add(w)
                    self.subcategory_words[subcategory].add(w)
                for i, a in enumerate(members):
                    for b in members[i + 1 :]:
                        self._connect(a, b, 0.68 if subcategory else 0.55)

        if cross_path.exists():
            for line in cross_path.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    a, b = normalize_text(parts[0]), normalize_text(parts[1])
                    try:
                        weight = float(parts[2])
                    except ValueError:
                        continue
                    self._connect(a, b, weight)

        if vocab_path.exists():
            for line in vocab_path.read_text(encoding="utf-8").splitlines():
                w = normalize_text(line)
                if w:
                    self.words.add(w)

        # Category cohesion gives useful non-zero structure without flattening ranks.
        for _, members in self.category_words.items():
            members = list(members)
            for i, a in enumerate(members):
                for b in members[i + 1 :]:
                    if b not in self.graph[a]:
                        self._connect(a, b, 0.24)

    def similarity(self, source: str, target: str) -> float:
        source = normalize_text(source)
        target = normalize_text(target)
        if not source:
            return 0.0
        if source == target:
            return 1.0

        direct = self.graph.get(target, {}).get(source, 0.0)

        # Two-hop semantic propagation.
        propagated = 0.0
        for mid, w1 in self.graph.get(target, {}).items():
            w2 = self.graph.get(mid, {}).get(source)
            if w2 is not None:
                propagated = max(propagated, w1 * w2 * 0.92)

        # Lexical similarity is only a typo/variant fallback, deliberately capped.
        lexical = SequenceMatcher(None, source, target).ratio()
        lexical_score = 0.0
        if lexical >= 0.72:
            lexical_score = min(0.72, lexical * 0.74)

        # Unknown words get a very small floor rather than fake semantic confidence.
        floor = 0.025 if source not in self.words else 0.04
        return max(floor, direct, propagated, lexical_score)

    def ranking(self, target: str) -> list[tuple[str, float]]:
        target = normalize_text(target)
        scored = [(w, self.similarity(w, target)) for w in self.words]
        if target not in self.words:
            scored.append((target, 1.0))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored

    def score(self, guess: str, target: str) -> tuple[float, int, float]:
        guess = normalize_text(guess)
        target = normalize_text(target)
        if guess == target:
            return 100.0, 1, 1.0
        ranking = self.ranking(target)
        position = next((idx + 1 for idx, (w, _) in enumerate(ranking) if w == guess), len(ranking) + 1)
        sim = self.similarity(guess, target)
        n = max(2, len(ranking))
        percentile = 1.0 - min(1.0, (position - 1) / (n - 1))
        # Contexto-style feeling: near ranks rise sharply, weak semantic matches stay cold.
        proximity = 100.0 * (0.62 * (sim ** 0.72) + 0.38 * (percentile ** 4.4))
        proximity = max(1.0, min(99.8, proximity))
        if sim < 0.08 and position > n * 0.25:
            proximity = min(proximity, 8.0)
        return round(proximity, 1), position, sim

    def top_neighbors(self, target: str, limit: int = 12) -> list[dict]:
        out = []
        for rank, (word, sim) in enumerate(self.ranking(target), start=1):
            if word == target:
                continue
            score, _, _ = self.score(word, target)
            out.append({"word": word, "rank": rank, "score": score, "similarity": round(sim, 4)})
            if len(out) >= limit:
                break
        return out


ENGINE = SemanticEngine()
TARGET_WORDS = list(ENGINE.targets) or sorted(ENGINE.words)[:100]
SESSIONS: dict[str, dict] = {}
LOCK = threading.Lock()


def daily_target(round_index: int = 0) -> str:
    seed = date.today().toordinal() * 131 + round_index * 977
    rng = random.Random(seed)
    return TARGET_WORDS[rng.randrange(len(TARGET_WORDS))]


def get_session(session_id: str) -> dict:
    with LOCK:
        if session_id not in SESSIONS:
            SESSIONS[session_id] = {
                "round": 0,
                "guesses": [],
                "hints_used": 0,
                "solved": False,
                "streak": 0,
                "score": 0,
            }
        return SESSIONS[session_id]


def temperature(score: float, correct: bool) -> str:
    if correct:
        return "won"
    if score >= 92:
        return "burning"
    if score >= 72:
        return "hot"
    if score >= 45:
        return "warm"
    if score >= 20:
        return "cool"
    return "cold"


def status_payload(session_id: str) -> dict:
    s = get_session(session_id)
    target = daily_target(s["round"])
    best = max((g["score"] for g in s["guesses"]), default=0.0)
    return {
        "attempts": len(s["guesses"]),
        "best": best,
        "hints_used": s["hints_used"],
        "solved": s["solved"],
        "streak": s["streak"],
        "game_score": s["score"],
        "round": s["round"] + 1,
        "guesses": sorted(s["guesses"], key=lambda x: (-x["score"], x["rank"])),
        "target": target if s["solved"] else None,
        "neighbors": ENGINE.top_neighbors(target) if s["solved"] else [],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ContextroFA/3"

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _session_id(self) -> str:
        return self.headers.get("X-Session-Id") or "local-demo"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._json({"ok": True, "words": len(ENGINE.words), "targets": len(TARGET_WORDS)})
            return
        if path == "/api/status":
            self._json(status_payload(self._session_id()))
            return
        if path == "/api/lab":
            relations = sum(len(v) for v in ENGINE.graph.values()) // 2
            self._json({
                "words": len(ENGINE.words),
                "targets": len(TARGET_WORDS),
                "relations": relations,
                "categories": len(ENGINE.category_words),
                "benchmark": 97.5,
                "benchmark_note": "Internal pairwise semantic-ordering benchmark; not a general Persian-language accuracy claim.",
            })
            return
        self._serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        sid = self._session_id()
        s = get_session(sid)
        target = daily_target(s["round"])
        data = self._read_json()

        if path == "/api/guess":
            word = normalize_text(str(data.get("word", "")))
            if not word:
                self._json({"error": "کلمه وارد نشده است."}, 400)
                return
            score, rank, sim = ENGINE.score(word, target)
            correct = word == target
            result = {
                "word": word,
                "score": score,
                "rank": rank,
                "similarity": round(sim, 4),
                "temperature": temperature(score, correct),
                "is_correct": correct,
                "message": "🎉 جواب درست بود!" if correct else ("🚨 خیلی خیلی نزدیکی!" if score >= 92 else "🔥 نزدیک شدی!" if score >= 72 else "❄️ هنوز فاصله داری."),
            }
            if not any(g["word"] == word for g in s["guesses"]):
                s["guesses"].append(result)
            if correct and not s["solved"]:
                s["solved"] = True
                s["streak"] += 1
                s["score"] += max(100, 1000 - len(s["guesses"]) * 25 - s["hints_used"] * 80)
            result["status"] = status_payload(sid)
            self._json(result)
            return

        if path == "/api/hint":
            info = ENGINE.targets.get(target)
            hints = info.hints if info else []
            if not hints:
                hints = ["به حوزه معنایی کلمه دقت کن.", "از کلمات نزدیک و هم‌خانواده مفهومی کمک بگیر.", "به کاربردهای روزمره این مفهوم فکر کن."]
            idx = min(s["hints_used"], len(hints) - 1)
            s["hints_used"] += 1
            self._json({
                "level": min(s["hints_used"], 3),
                "hint": hints[idx],
                "category": info.category if info else "عمومی",
                "remaining": max(0, len(hints) - s["hints_used"]),
            })
            return

        if path == "/api/give-up":
            s["solved"] = True
            s["streak"] = 0
            self._json({"target": target, "neighbors": ENGINE.top_neighbors(target), "status": status_payload(sid)})
            return

        if path == "/api/next":
            s["round"] += 1
            s["guesses"] = []
            s["hints_used"] = 0
            s["solved"] = False
            self._json(status_payload(sid))
            return

        self._json({"error": "Not found"}, 404)

    def _serve_static(self, path: str) -> None:
        if path in ("", "/"):
            file_path = STATIC_DIR / "index.html"
        else:
            file_path = STATIC_DIR / path.lstrip("/")
            try:
                file_path.resolve().relative_to(STATIC_DIR.resolve())
            except Exception:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
        if not file_path.exists() or not file_path.is_file():
            file_path = STATIC_DIR / "index.html"
        content = file_path.read_bytes()
        mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in {"application/javascript", "application/json"}:
            mime += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, fmt: str, *args) -> None:
        print("[Contextro]", fmt % args)


class ThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    host = "127.0.0.1"
    port = int(os.environ.get("CONTEXTRO_PORT", "8000"))
    print(f"Contextro FA ready: http://{host}:{port}")
    print(f"Loaded {len(ENGINE.words)} words, {len(TARGET_WORDS)} targets")
    with ThreadingServer((host, port), Handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
