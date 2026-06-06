"""Vérifie que les 4 outils MCP fonctionnent — en direct et via HTTP.

Usage :
    python verify_tools.py                 # test en-process (aucun serveur requis)
    python verify_tools.py --http          # test via http://localhost:8010 (serveur lancé)
    python verify_tools.py --http --base http://127.0.0.1:8010

Sortie : une ligne PASS/FAIL par outil + un code de sortie non nul si échec.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

FACTS = [
    (1, "user: Bonjour, je suis Marie Dupont, cliente premium chez TechCorp."),
    (3, "user: Mon numéro de contrat est CTR-2024-8847."),
    (5, "user: La facture de mars affiche 149,90 € au lieu de 99,90 €."),
    (7, "user: Bug mobile signalé le 12 février sur l'application iOS."),
    (9, "user: Email de contact : marie.dupont@email.fr."),
]
PARAPHRASE = ("référence légale du dossier client", "CTR-2024-8847")
MODELS = ["claude-opus-4-8", "claude-sonnet-4-6"]

_passed = 0
_failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _passed, _failed
    mark = "PASS" if ok else "FAIL"
    if ok:
        _passed += 1
    else:
        _failed += 1
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


# --------------------------------------------------------------------------- #
# Test en-process (appelle directement MemoryTools)
# --------------------------------------------------------------------------- #
def test_in_process() -> None:
    print("=== Test en-process (MemoryTools) ===")
    from memory_mcp.stats import get_stats, reset_stats
    from memory_mcp.tools import MemoryTools

    reset_stats()
    tools = MemoryTools()

    # memory_store (le 1er tour déclare le modèle de l'agent)
    ids = [
        tools.memory_store(c, tags=["fact"], session="verify", turn=t,
                           model=("claude-opus-4-8" if i == 0 else None))
        for i, (t, c) in enumerate(FACTS)
    ]
    check("memory_store", all(r["stored"] for r in ids), f"{len(ids)} entrées")

    # memory_search (paraphrase → bon top-1)
    res = tools.memory_search(PARAPHRASE[0], top_k=3, session="verify")
    top_ok = bool(res["results"]) and PARAPHRASE[1] in res["results"][0]["content"]
    check("memory_search", top_ok,
          f"top1={res['results'][0]['content'][:48] if res['results'] else 'vide'}")

    # memory_keys (index clé→valeur) + store avec clé
    tools.memory_store("Marie Dupont", key="nom_client", session="verify", turn=11)
    keys = tools.memory_keys(session="verify")
    by_key = {k["key"]: k["content"] for k in keys["keys"] if k["key"]}
    check("memory_keys", keys["count"] >= 1 and by_key.get("nom_client") == "Marie Dupont",
          f"{keys['count']} entrées, {keys['with_key']} avec clé, nom_client={by_key.get('nom_client')}")

    # memory_summarize (conserve les faits clés)
    summ = tools.memory_summarize(session="verify")
    text = summ["summary"].lower()
    keeps = all(k in text for k in ["marie", "ctr-2024-8847"])
    check("memory_summarize", keeps and summ["compressed_chars"] > 0,
          f"{summ['compressed_chars']} car., faits clés={'oui' if keeps else 'non'}")

    # memory_stats (+ coût multi-modèles via models.dev)
    stats = tools.memory_stats(model=MODELS)
    cost = stats.get("cost", {})
    cost_ok = cost.get("pricing_found") and cost["total"]["total_cost"] >= 0
    check("memory_stats", stats["entries_count"] == len(FACTS) and cost_ok,
          f"entrées={stats['entries_count']}, coût total={cost.get('total', {}).get('total_cost')} USD")

    # modèle déclaré + chiffrage attendu vs économie (champs du tableau de bord)
    auto = tools.memory_stats()  # sans slug : doit retomber sur active_model
    check("active_model + naive_tokens",
          auto.get("active_model") == "claude-opus-4-8"
          and auto.get("naive_tokens", 0) >= auto.get("membridge_tokens", 0)
          and (auto.get("cost") or {}).get("pricing_found", False),
          f"actif={auto.get('active_model')}, naive={auto.get('naive_tokens')}")

    # Gain de tokens sur une session réaliste (objectif ≥ 70 %) + série temporelle
    reset_stats()
    tools = MemoryTools()
    for i in range(30):
        tools.memory_store(
            f"Fait #{i}: référence REF-{1000 + i}, montant {i * 10 + 5},90 €, "
            f"contact user{i}@corp.fr, échéance le {1 + i % 28} mars.",
            session="gain", turn=i, model="claude-opus-4-8")
    for _ in range(20):
        tools.memory_search("quelle est la référence du dossier client", top_k=3, session="gain")
    g = tools.memory_stats()
    check("gain ≥ 70% (session réaliste)", g["gain_pct"] >= 70,
          f"gain={g['gain_pct']}% sur {g['turns']} tours "
          f"(naïf={g['naive_tokens']} → MemBridge={g['membridge_tokens']} tokens)")

    ts = get_stats().timeseries("hour")
    last = ts["points"][-1] if ts["points"] else {}
    check("timeseries (par heure)", bool(ts["points"]) and last.get("gain_pct", 0) >= 70,
          f"{len(ts['points'])} tranche(s), gain final={last.get('gain_pct')}%")


# --------------------------------------------------------------------------- #
# Test HTTP (serveur memory-mcp-http lancé)
# --------------------------------------------------------------------------- #
def _req(method: str, url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def test_http(base: str) -> None:
    print(f"=== Test HTTP ({base}) ===")
    try:
        health = _req("GET", f"{base}/health")
        check("health", health.get("status") == "ok", str(health))
    except Exception as e:
        check("health", False, f"serveur injoignable : {e}")
        return

    _req("POST", f"{base}/api/v1/reset?clear=true")
    stored = [_req("POST", f"{base}/api/v1/store",
                   {"content": c, "tags": ["fact"], "session": "verify-http", "turn": t})
              for t, c in FACTS]
    check("POST /store", all(s["stored"] for s in stored), f"{len(stored)} entrées")

    res = _req("POST", f"{base}/api/v1/search",
               {"query": PARAPHRASE[0], "top_k": 3, "session": "verify-http"})
    top_ok = res["count"] > 0 and PARAPHRASE[1] in res["results"][0]["content"]
    check("POST /search", top_ok, f"count={res['count']}")

    summ = _req("POST", f"{base}/api/v1/summarize", {"session": "verify-http"})
    keeps = all(k in summ["summary"].lower() for k in ["marie", "ctr-2024-8847"])
    check("POST /summarize", keeps, f"{summ['compressed_chars']} car.")

    qs = "&".join(f"model={m}" for m in MODELS)
    stats = _req("GET", f"{base}/api/v1/stats?{qs}")
    cost = stats.get("cost") or {}
    check("GET /stats", stats["entries_count"] >= 0 and cost.get("pricing_found", False),
          f"coût total={cost.get('total', {}).get('total_cost')} USD, gain={stats.get('gain_pct')}%")

    ts = _req("GET", f"{base}/api/v1/timeseries?bucket=day")
    check("GET /timeseries", ts.get("bucket") == "day" and isinstance(ts.get("points"), list),
          f"{len(ts.get('points', []))} tranche(s)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true", help="teste aussi le serveur HTTP")
    ap.add_argument("--base", default="http://localhost:8010")
    args = ap.parse_args()

    test_in_process()
    if args.http:
        print()
        test_http(args.base)

    print(f"\nRésultat : {_passed} PASS / {_failed} FAIL")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
