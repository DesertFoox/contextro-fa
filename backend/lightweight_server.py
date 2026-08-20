from __future__ import annotations

import csv
import hashlib
import json
import math
import mimetypes
import re
import threading
import webbrowser
from collections import defaultdict
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
STATIC = BASE / 'app' / 'static'
VOCAB = BASE / 'app' / 'data' / 'vocabulary.txt'
DAILY = BASE / 'app' / 'data' / 'daily_words.txt'
TRAIN = BASE / 'training' / 'train_pairs.csv'
EVAL = BASE / 'training' / 'eval_pairs.csv'
ONTOLOGY_PAIRS = BASE / 'training' / 'ontology_pairs.csv'
SEMANTIC = BASE / 'app' / 'data' / 'semantic_dataset.json'
ONTOLOGY = BASE / 'app' / 'data' / 'semantic_ontology.json'
CROSS = BASE / 'app' / 'data' / 'cross_relations.csv'
BENCHMARK = BASE / 'training' / 'benchmark_results.json'


def normalize_fa(text: str) -> str:
    text = text.strip().lower().replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', ' ')
    text = text.replace('ۀ', 'ه').replace('ة', 'ه')
    text = re.sub(r'[^\w\u0600-\u06FF ]+', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def char_ngrams(word: str, n: int = 2) -> set[str]:
    normalized = normalize_fa(word).replace('آ', 'ا')
    w = f'^{normalized}$'
    return {w[i:i+n] for i in range(max(0, len(w)-n+1))}


def lexical_similarity(a: str, b: str) -> float:
    aa, bb = char_ngrams(a), char_ngrams(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


class LightweightSemanticEngine:
    """Offline Contexto-like semantic ranker.

    The engine combines a Persian ontology, weighted semantic relations, cross-domain
    associations and sparse semantic vectors. The displayed score is a calibrated
    proximity score; rank is computed against the entire bundled vocabulary.
    """

    def __init__(self):
        self.graph: dict[str, dict[str, float]] = defaultdict(dict)
        self.words: set[str] = set()
        self.semantic_data = self._load_semantic_dataset()
        self.ontology = self._load_ontology()
        self.word_categories: dict[str, set[str]] = defaultdict(set)
        self.word_subgroups: dict[str, set[tuple[str, str]]] = defaultdict(set)
        self._index_ontology()
        for file in (TRAIN, EVAL, ONTOLOGY_PAIRS):
            self._load_pairs(file)
        self._load_cross_relations()
        self.vocabulary = [normalize_fa(x) for x in VOCAB.read_text(encoding='utf-8').splitlines() if x.strip()]
        self.vocabulary = list(dict.fromkeys(self.vocabulary))
        self.words.update(self.vocabulary)
        self._vectors = {w: self._semantic_vector(w) for w in self.vocabulary}
        self._rank_cache: dict[str, list[tuple[str, float]]] = {}

    def _add_edge(self, a: str, b: str, score: float):
        a, b = normalize_fa(a), normalize_fa(b)
        if not a or not b or a == b:
            return
        score = max(0.0, min(0.995, float(score)))
        self.words.update((a, b))
        if score >= 0.18:
            self.graph[a][b] = max(score, self.graph[a].get(b, 0.0))
            self.graph[b][a] = max(score, self.graph[b].get(a, 0.0))

    def _load_semantic_dataset(self) -> dict:
        if not SEMANTIC.exists():
            return {}
        raw = json.loads(SEMANTIC.read_text(encoding='utf-8'))
        out = {}
        for target, meta in raw.items():
            t = normalize_fa(target)
            rel = {normalize_fa(w): float(s) for w, s in meta.get('related', {}).items() if normalize_fa(w)}
            out[t] = {**meta, 'related': rel}
        return out

    def _load_ontology(self) -> dict:
        if not ONTOLOGY.exists():
            return {'categories': {}}
        return json.loads(ONTOLOGY.read_text(encoding='utf-8'))

    def _index_ontology(self):
        for category, subgroups in self.ontology.get('categories', {}).items():
            cat = normalize_fa(category)
            for subgroup, words in subgroups.items():
                sg = normalize_fa(subgroup)
                normalized = [normalize_fa(w) for w in words if normalize_fa(w)]
                for w in normalized:
                    self.word_categories[w].add(cat)
                    self.word_subgroups[w].add((cat, sg))
                    self.words.add(w)
        for target, meta in self.semantic_data.items():
            for w, s in meta.get('related', {}).items():
                self._add_edge(target, w, s)

    def _load_pairs(self, path: Path):
        if not path.exists():
            return
        with path.open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                a = normalize_fa(row.get('sentence1') or row.get('word1') or row.get('text1') or '')
                b = normalize_fa(row.get('sentence2') or row.get('word2') or row.get('text2') or '')
                raw = row.get('score') or row.get('label') or row.get('similarity') or '0'
                try:
                    s = float(raw)
                except ValueError:
                    continue
                if s > 1:
                    s /= 100.0
                self._add_edge(a, b, s)

    def _load_cross_relations(self):
        if not CROSS.exists():
            return
        with CROSS.open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                try:
                    s = float(row['score'])
                except Exception:
                    continue
                self._add_edge(row['word1'], row['word2'], s)

    def _semantic_vector(self, word: str) -> dict[str, float]:
        word = normalize_fa(word)
        vec: dict[str, float] = {f'w:{word}': 0.75}
        for cat in self.word_categories.get(word, set()):
            vec[f'cat:{cat}'] = 0.52
        for cat, sg in self.word_subgroups.get(word, set()):
            vec[f'sg:{cat}/{sg}'] = 0.95
        for n1, s1 in self.graph.get(word, {}).items():
            vec[f'n:{n1}'] = max(vec.get(f'n:{n1}', 0), s1)
            if s1 >= 0.70:
                for n2, s2 in self.graph.get(n1, {}).items():
                    if n2 != word and s2 >= 0.55:
                        vec[f'n:{n2}'] = max(vec.get(f'n:{n2}', 0), s1 * s2 * 0.42)
        return vec

    @staticmethod
    def _cos_sparse(a: dict[str, float], b: dict[str, float]) -> float:
        if len(a) > len(b):
            a, b = b, a
        dot = sum(v * b.get(k, 0.0) for k, v in a.items())
        na = math.sqrt(sum(v*v for v in a.values()))
        nb = math.sqrt(sum(v*v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    def _ontology_similarity(self, a: str, b: str) -> float:
        sga, sgb = self.word_subgroups.get(a, set()), self.word_subgroups.get(b, set())
        if sga & sgb:
            return 0.72
        ca, cb = self.word_categories.get(a, set()), self.word_categories.get(b, set())
        if ca & cb:
            return 0.38
        return 0.0

    def _nearest_known(self, word: str) -> tuple[str | None, float]:
        best_word, best = None, 0.0
        for candidate in self.vocabulary:
            sim = lexical_similarity(word, candidate)
            if sim > best:
                best_word, best = candidate, sim
        return best_word, best

    def similarity(self, left: str, right: str, allow_typo: bool = True) -> float:
        a, b = normalize_fa(left), normalize_fa(right)
        if not a or not b:
            return 0.015
        if a == b:
            return 1.0
        direct = max(self.graph.get(a, {}).get(b, 0.0), self.graph.get(b, {}).get(a, 0.0))
        ontology = self._ontology_similarity(a, b)
        va = self._vectors.get(a) or self._semantic_vector(a)
        vb = self._vectors.get(b) or self._semantic_vector(b)
        vector = self._cos_sparse(va, vb)
        lexical = lexical_similarity(a, b)
        typo_score = 0.0
        if allow_typo and a not in self.words:
            nearest, spelling = self._nearest_known(a)
            if nearest and spelling >= 0.40:
                typo_score = self.similarity(nearest, b, allow_typo=False) * (0.56 + 0.38 * spelling)
        score = max(direct, ontology, vector * 0.90, lexical * 0.34, typo_score)
        return max(0.015, min(0.995, score))

    def ranking(self, target: str) -> list[tuple[str, float]]:
        target = normalize_fa(target)
        if target not in self._rank_cache:
            values = [(w, 1.0 if w == target else self.similarity(w, target, allow_typo=False)) for w in self.vocabulary]
            values.sort(key=lambda x: (-x[1], x[0]))
            self._rank_cache[target] = values
        return self._rank_cache[target]

    def rank(self, guess: str, target: str) -> int:
        g, t = normalize_fa(guess), normalize_fa(target)
        ranking = self.ranking(t)
        if g in self.vocabulary:
            for idx, (w, _) in enumerate(ranking, start=1):
                if w == g:
                    return idx
        gs = self.similarity(g, t)
        return 1 + sum(1 for _, s in ranking if s > gs + 1e-9)

    def hint(self, target: str, level: int) -> dict:
        meta = self.semantic_data.get(normalize_fa(target), {})
        hints = list(meta.get('hints', []))
        if not hints:
            cats = sorted(self.word_categories.get(normalize_fa(target), set()))
            category = cats[0] if cats else 'واژگان عمومی'
            hints = [f'به حوزه «{category}» مربوط است.', 'به ارتباط معنایی کلمات فکر کن.', 'یکی از واژه‌های روزمره و نسبتاً شناخته‌شده است.']
        idx = min(max(level-1, 0), len(hints)-1)
        return {'level': idx+1, 'hint': hints[idx], 'category': meta.get('category', '')}


ENGINE = LightweightSemanticEngine()
SESSIONS: dict[str, dict] = {}
DAILY_WORDS = [normalize_fa(x) for x in DAILY.read_text(encoding='utf-8').splitlines() if x.strip()]


def daily_start_index() -> int:
    digest = hashlib.sha256(date.today().isoformat().encode()).hexdigest()
    return int(digest[:8], 16) % len(DAILY_WORDS)


def _new_session() -> dict:
    return {'history': [], 'solved': False, 'gave_up': False, 'hints_used': 0, 'target_index': daily_start_index(), 'round': 1, 'score': 0, 'streak': 0}


def target_for_session(session_id: str) -> str:
    sess = SESSIONS.setdefault(session_id, _new_session())
    return DAILY_WORDS[int(sess.get('target_index', daily_start_index())) % len(DAILY_WORDS)]


def calibrated_proximity(sim: float, rank: int, vocab_size: int) -> float:
    x = max(0.0, min(1.0, sim))
    anchors = [(0.0,1.0),(0.05,3.0),(0.15,9.0),(0.30,22.0),(0.45,40.0),(0.60,61.0),(0.72,76.0),(0.82,87.0),(0.90,94.0),(0.97,98.5),(1.0,100.0)]
    base = 1.0
    for (x0,y0),(x1,y1) in zip(anchors,anchors[1:]):
        if x <= x1:
            t = (x-x0)/(x1-x0) if x1 > x0 else 0
            base = y0 + t*(y1-y0)
            break
    percentile = max(0.0, 1.0-(rank-1)/max(1, vocab_size-1))
    rank_bonus = max(0.0, (percentile-0.90)/0.10)*3.5
    return round(min(99.8, base+rank_bonus), 1)


def temp(score: float) -> str:
    if score >= 100:
        return 'won'
    if score >= 88:
        return 'burning'
    if score >= 70:
        return 'hot'
    if score >= 45:
        return 'warm'
    if score >= 22:
        return 'cool'
    return 'cold'


def message(score: float, exact: bool) -> str:
    if exact:
        return '🎉 بردی! کلمه را پیدا کردی.'
    if score >= 88:
        return '🚨 تقریباً رسیدی!'
    if score >= 70:
        return '🔥 خیلی نزدیکی.'
    if score >= 45:
        return '🙂 مسیرت خوبه؛ نزدیک شدی.'
    if score >= 22:
        return '❄️ کمی ارتباط معنایی وجود داره.'
    return '🥶 دوری؛ یک مسیر معنایی متفاوت امتحان کن.'


def guess(session_id: str, word: str) -> dict:
    clean = normalize_fa(word)
    target = target_for_session(session_id)
    exact = clean == target
    cosine = 1.0 if exact else ENGINE.similarity(clean, target)
    rank = 1 if exact else ENGINE.rank(clean, target)
    score = 100.0 if exact else calibrated_proximity(cosine, rank, len(ENGINE.vocabulary))
    item = {'word': clean, 'proximity': score, 'cosine_similarity': round(cosine,4), 'rank': rank, 'temperature': temp(score), 'is_correct': exact, 'message': message(score, exact)}
    sess = SESSIONS.setdefault(session_id, _new_session())
    sess['history'] = [x for x in sess['history'] if x['word'] != clean]
    sess['history'].append(item)
    sess['history'].sort(key=lambda x: (-x['proximity'], x['rank']))
    if exact and not sess.get('solved'):
        sess['solved'] = True
        earned = calculate_round_score(sess)
        sess['score'] = int(sess.get('score', 0)) + earned
        sess['streak'] = int(sess.get('streak', 0)) + 1
        item['round_score'] = earned
        item['total_score'] = sess['score']
    else:
        sess['solved'] = sess['solved'] or exact
    return item


def calculate_round_score(sess: dict) -> int:
    guesses = len(sess.get('history', []))
    hints = int(sess.get('hints_used', 0))
    speed = max(0, 120 - max(0, guesses - 1) * 4)
    return max(10, speed - hints * 12)


def top_neighbors(target: str, limit: int = 12) -> list[dict]:
    rows = []
    for idx, (word, sim) in enumerate(ENGINE.ranking(target)[:limit + 1], start=1):
        if word == target:
            continue
        rank = idx
        rows.append({'word': word, 'rank': rank, 'similarity': round(sim, 4), 'proximity': calibrated_proximity(sim, rank, len(ENGINE.vocabulary))})
        if len(rows) >= limit:
            break
    return rows


def benchmark_payload() -> dict:
    if BENCHMARK.exists():
        try:
            data = json.loads(BENCHMARK.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {'results': data}
        except Exception:
            pass
    return {'note': 'benchmark file unavailable'}


class Handler(BaseHTTPRequestHandler):
    server_version = 'ContextroFA/1.0'

    def log_message(self, fmt, *args):
        print('[HTTP]', fmt % args)

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sid(self):
        return self.headers.get('X-Session-Id', 'demo')

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            return self._json({'status': 'ok', 'mode': 'offline-contexto-v2', 'engine': 'semantic-vector-ranker', 'vocabulary': len(ENGINE.vocabulary), 'targets': len(DAILY_WORDS)})
        if path == '/api/lab':
            return self._json({'engine': 'semantic-vector-ranker-v3', 'vocabulary': len(ENGINE.vocabulary), 'targets': len(DAILY_WORDS), 'relations': sum(len(v) for v in ENGINE.graph.values()) // 2, 'categories': len(ENGINE.ontology.get('categories', {})), 'benchmark': benchmark_payload()})
        if path == '/api/status':
            sess = SESSIONS.get(self._sid()) or _new_session()
            hist = sess['history']
            return self._json({'date': date.today().isoformat(), 'guesses': len(hist), 'solved': sess['solved'], 'best_proximity': max([x['proximity'] for x in hist], default=0), 'history': hist, 'engine': 'semantic-vector-ranker', 'hints_used': sess.get('hints_used', 0), 'max_hints': 3, 'round': int(sess.get('round', 1)), 'can_next': bool(sess.get('solved') or sess.get('gave_up')), 'target_reveal': target_for_session(self._sid()) if (sess.get('solved') or sess.get('gave_up')) else None, 'gave_up': bool(sess.get('gave_up')), 'score': int(sess.get('score', 0)), 'streak': int(sess.get('streak', 0)), 'top_neighbors': top_neighbors(target_for_session(self._sid())) if (sess.get('solved') or sess.get('gave_up')) else []})
        if path in ('/', '/index.html'):
            file = STATIC / 'index.html'
        elif path.startswith('/static/'):
            file = STATIC / path.removeprefix('/static/')
        else:
            return self._json({'detail': 'Not found'}, 404)
        try:
            body = file.read_bytes()
        except FileNotFoundError:
            return self._json({'detail': 'Not found'}, 404)
        ctype = mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
        self.send_response(200)
        self.send_header('Content-Type', ctype + ('; charset=utf-8' if ctype.startswith('text/') or ctype == 'application/javascript' else ''))
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/hint':
            sess = SESSIONS.setdefault(self._sid(), _new_session())
            if sess.get('solved'):
                return self._json({'detail': 'کلمه را پیدا کرده‌اید؛ دیگر نیازی به راهنمایی نیست.'}, 409)
            used = int(sess.get('hints_used', 0))
            if used >= 3:
                return self._json({'detail': 'هر روز حداکثر ۳ راهنمایی دارید.'}, 409)
            used += 1
            sess['hints_used'] = used
            payload = ENGINE.hint(target_for_session(self._sid()), used)
            payload['remaining'] = 3 - used
            return self._json(payload)
        if path == '/api/give-up':
            sess = SESSIONS.setdefault(self._sid(), _new_session())
            if sess.get('solved'):
                return self._json({'detail': 'این راند را قبلاً حل کرده‌اید.'}, 409)
            sess['gave_up'] = True
            sess['streak'] = 0
            return self._json({'ok': True, 'answer': target_for_session(self._sid()), 'top_neighbors': top_neighbors(target_for_session(self._sid()))})
        if path == '/api/next':
            sess = SESSIONS.setdefault(self._sid(), _new_session())
            if not (sess.get('solved') or sess.get('gave_up')):
                return self._json({'detail': 'اول کلمه فعلی را حل کنید یا تسلیم شوید.'}, 409)
            sess['target_index'] = (int(sess.get('target_index', daily_start_index())) + 1) % len(DAILY_WORDS)
            sess['round'] = int(sess.get('round', 1)) + 1
            sess['history'] = []
            sess['solved'] = False
            sess['gave_up'] = False
            sess['hints_used'] = 0
            return self._json({'ok': True, 'round': sess['round']})
        if path != '/api/guess':
            return self._json({'detail': 'Not found'}, 404)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            data = json.loads(self.rfile.read(length).decode('utf-8'))
            word = str(data.get('word', '')).strip()
            if not word:
                return self._json({'detail': 'کلمه را وارد کنید.'}, 422)
            return self._json(guess(self._sid(), word))
        except Exception as exc:
            return self._json({'detail': f'خطا: {exc}'}, 500)


def main():
    host, port = '127.0.0.1', 8000
    print('=' * 50)
    print(' Contextro FA - OFFLINE SEMANTIC V2')
    print(' No pip / Docker / Node / model download required')
    print(f' Semantic space: {len(ENGINE.vocabulary)} words / {sum(len(v) for v in ENGINE.graph.values()) // 2} weighted relations')
    print(f' Open: http://{host}:{port}')
    print('=' * 50)
    server = ThreadingHTTPServer((host, port), Handler)
    threading.Timer(1.0, lambda: webbrowser.open(f'http://{host}:{port}')).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
