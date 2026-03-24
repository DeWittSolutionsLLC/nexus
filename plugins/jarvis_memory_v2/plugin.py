from core.plugin_manager import BasePlugin
import logging, json, uuid, requests
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger("nexus.plugins.jarvis_memory_v2")

MEMORY_FILE  = Path.home() / "NexusScripts" / "jarvis_memory_v2.json"
INSIGHTS_LOG = Path.home() / "NexusScripts" / "jarvis_insights.json"
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"
CATEGORIES   = {"personal", "preference", "fact", "event", "goal", "relationship", "work", "insight"}
SLEEP_CYCLE_AGE_DAYS = 30   # memories older than this are eligible for consolidation

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    _st_model = SentenceTransformer("all-MiniLM-L6-v2")
    HAS_ST = True
    logger.info("sentence_transformers loaded — using embedding similarity")
except Exception:
    HAS_ST = False
    _st_model = None
    logger.info("sentence_transformers not available — using keyword similarity")


def _ollama(prompt: str, timeout: int = 60) -> str:
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        return f"[Ollama error: {e}]"


def _load() -> list:
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(data: list):
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _keyword_similarity(text1: str, text2: str) -> float:
    w1 = set(text1.lower().split())
    w2 = set(text2.lower().split())
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)


def _embed(text: str) -> list | None:
    if not HAS_ST or _st_model is None:
        return None
    try:
        return _st_model.encode(text).tolist()
    except Exception:
        return None


def _cosine_similarity(a: list, b: list) -> float:
    try:
        import numpy as np
        va = np.array(a)
        vb = np.array(b)
        denom = (np.linalg.norm(va) * np.linalg.norm(vb))
        if denom == 0:
            return 0.0
        return float(np.dot(va, vb) / denom)
    except Exception:
        return 0.0


def _score(query: str, memory: dict, query_emb=None) -> float:
    if HAS_ST and query_emb is not None and memory.get("embedding"):
        return _cosine_similarity(query_emb, memory["embedding"])
    return _keyword_similarity(query, memory.get("content", ""))


class JarvisMemoryV2Plugin(BasePlugin):
    name = "jarvis_memory_v2"
    description = "Upgraded memory system with semantic search, categories, importance scoring, and AI consolidation."
    icon = "🧬"

    async def connect(self) -> bool:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._connected = True
        memories = _load()
        mode = "embedding" if HAS_ST else "keyword"
        self._status_message = f"Ready ({len(memories)} memories, {mode} similarity)"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "remember", "description": "Store a memory with category, importance, and tags", "params": ["content", "category", "importance", "tags"]},
            {"action": "recall", "description": "Semantic search for most relevant memories", "params": ["query", "n"]},
            {"action": "forget", "description": "Remove a memory by id or query match", "params": ["id", "query"]},
            {"action": "list_memories", "description": "List memories, optionally filtered by category", "params": ["category", "limit"]},
            {"action": "get_context", "description": "Get most relevant memories for a situation", "params": ["situation"]},
            {"action": "update_importance", "description": "Update importance score of a memory", "params": ["id", "importance"]},
            {"action": "get_stats", "description": "Memory statistics by category and importance", "params": []},
            {"action": "consolidate", "description": "AI reviews memories and suggests merges/removals", "params": []},
            {"action": "sleep_cycle", "description": "Summarise old memories, remove redundancies, and generate high-level insights", "params": []},
        ]

    async def execute(self, action: str, params: dict) -> str:
        try:
            if action == "remember":
                return await self._remember(params)
            elif action == "recall":
                return await self._recall(params)
            elif action == "forget":
                return await self._forget(params)
            elif action == "list_memories":
                return await self._list_memories(params)
            elif action == "get_context":
                return await self._get_context(params)
            elif action == "update_importance":
                return await self._update_importance(params)
            elif action == "get_stats":
                return await self._get_stats(params)
            elif action == "consolidate":
                return await self._consolidate(params)
            elif action == "sleep_cycle":
                return await self._sleep_cycle(params)
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.exception("JarvisMemoryV2 error")
            return f"Error in jarvis_memory_v2.{action}: {e}"

    async def _remember(self, params: dict) -> str:
        content = params.get("content", "").strip()
        if not content:
            return "No content provided."
        category = params.get("category", "fact").lower()
        if category not in CATEGORIES:
            category = "fact"
        importance = max(1, min(5, int(params.get("importance", 3))))
        tags = params.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        embedding = _embed(content)
        memory = {
            "id": str(uuid.uuid4())[:8],
            "content": content,
            "category": category,
            "importance": importance,
            "timestamp": datetime.now().isoformat(),
            "tags": tags,
        }
        if embedding:
            memory["embedding"] = embedding
        data = _load()
        data.append(memory)
        _save(data)
        return (
            f"Memory stored (ID: {memory['id']})\n"
            f"  Category: {category} | Importance: {importance}/5\n"
            f"  Tags: {', '.join(tags) or 'none'}\n"
            f"  Embedding: {'yes' if embedding else 'no (keyword fallback)'}"
        )

    async def _recall(self, params: dict) -> str:
        query = params.get("query", "").strip()
        n = int(params.get("n", 5))
        if not query:
            return "No query provided."
        data = _load()
        if not data:
            return "No memories stored."
        query_emb = _embed(query)
        scored = [(m, _score(query, m, query_emb)) for m in data]
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:n]
        if not top or top[0][1] == 0:
            return "No relevant memories found."
        lines = [f"Top {len(top)} memories for '{query}':"]
        for mem, score in top:
            lines.append(
                f"\n  [{mem['id']}] (score: {score:.3f}, importance: {mem['importance']}/5, category: {mem['category']})\n"
                f"  {mem['content']}\n"
                f"  Tags: {', '.join(mem.get('tags', [])) or 'none'} | {mem['timestamp'][:10]}"
            )
        return "\n".join(lines)

    async def _forget(self, params: dict) -> str:
        mem_id = params.get("id", "").strip()
        query = params.get("query", "").strip()
        data = _load()
        if mem_id:
            new_data = [m for m in data if m["id"] != mem_id]
            if len(new_data) == len(data):
                return f"No memory found with ID: {mem_id}"
            _save(new_data)
            return f"Memory {mem_id} forgotten."
        elif query:
            query_emb = _embed(query)
            scored = [(m, _score(query, m, query_emb)) for m in data]
            scored.sort(key=lambda x: x[1], reverse=True)
            if not scored or scored[0][1] == 0:
                return "No matching memory found."
            best = scored[0][0]
            new_data = [m for m in data if m["id"] != best["id"]]
            _save(new_data)
            return f"Forgot memory [{best['id']}]: {best['content'][:80]}..."
        return "Provide id or query."

    async def _list_memories(self, params: dict) -> str:
        category = params.get("category", "").lower().strip()
        limit = int(params.get("limit", 20))
        data = _load()
        if not data:
            return "No memories stored."
        filtered = [m for m in data if not category or m.get("category") == category]
        filtered.sort(key=lambda m: (m["importance"], m["timestamp"]), reverse=True)
        shown = filtered[:limit]
        lines = [f"Memories ({len(shown)} of {len(filtered)}{f', category={category}' if category else ''}):"]
        for m in shown:
            lines.append(
                f"  [{m['id']}] [{m['category']}] [{m['importance']}/5] {m['content'][:80]}"
                + ("..." if len(m["content"]) > 80 else "")
                + f" | {m['timestamp'][:10]}"
            )
        return "\n".join(lines)

    async def _get_context(self, params: dict) -> str:
        situation = params.get("situation", "").strip()
        if not situation:
            return "No situation provided."
        data = _load()
        if not data:
            return "No memories stored."
        query_emb = _embed(situation)
        scored = [(m, _score(situation, m, query_emb) * m["importance"]) for m in data]
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:10]
        lines = [f"Relevant context for: '{situation}'"]
        for mem, score in top:
            if score == 0:
                break
            lines.append(f"  [{mem['category']}] {mem['content']}")
        return "\n".join(lines) if len(lines) > 1 else "No relevant context found."

    async def _update_importance(self, params: dict) -> str:
        mem_id = params.get("id", "").strip()
        importance = max(1, min(5, int(params.get("importance", 3))))
        if not mem_id:
            return "No id provided."
        data = _load()
        for m in data:
            if m["id"] == mem_id:
                old = m["importance"]
                m["importance"] = importance
                _save(data)
                return f"Updated memory {mem_id} importance: {old} -> {importance}"
        return f"Memory not found: {mem_id}"

    async def _get_stats(self, params: dict) -> str:
        data = _load()
        if not data:
            return "No memories stored."
        by_category: dict = {}
        for m in data:
            cat = m.get("category", "unknown")
            by_category[cat] = by_category.get(cat, 0) + 1
        top_important = sorted(data, key=lambda m: m["importance"], reverse=True)[:5]
        lines = [
            f"Memory Statistics:",
            f"  Total memories: {len(data)}",
            f"  By category:",
        ]
        for cat, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"    {cat}: {count}")
        lines.append(f"  Top important memories:")
        for m in top_important:
            lines.append(f"    [{m['id']}] [{m['importance']}/5] {m['content'][:60]}...")
        return "\n".join(lines)

    async def _consolidate(self, params: dict) -> str:
        data = _load()
        if not data:
            return "No memories to consolidate."
        memory_list = "\n".join(
            f"[{m['id']}] ({m['category']}, importance={m['importance']}): {m['content']}"
            for m in data[:50]
        )
        prompt = (
            f"Review the following memories from an AI assistant and suggest:\n"
            f"1. Which memories are duplicates or redundant (list their IDs)\n"
            f"2. Which low-importance memories could be removed (list IDs)\n"
            f"3. Which memories could be merged into a single summary\n"
            f"4. Any gaps or important things that should be remembered\n\n"
            f"Memories:\n{memory_list}"
        )
        result = _ollama(prompt)
        return f"Memory Consolidation Report ({len(data)} memories reviewed):\n\n{result}"

    async def _sleep_cycle(self, params: dict) -> str:
        """
        Feature 5 — Memory Sleep Cycle.

        1. Identify memories older than SLEEP_CYCLE_AGE_DAYS
        2. Group them by category
        3. Ask Ollama to produce a concise insight summary for each group
        4. Save those summaries as new 'insight' category memories (importance=5)
        5. Delete the raw old memories that were summarised
        6. Report the operation
        """
        data = _load()
        if not data:
            return "The memory banks are empty, sir. Nothing to consolidate."

        cutoff = (datetime.now() - timedelta(days=SLEEP_CYCLE_AGE_DAYS)).isoformat()
        old_memories = [m for m in data if m.get("timestamp", "") < cutoff]

        if not old_memories:
            return (
                f"No memories older than {SLEEP_CYCLE_AGE_DAYS} days found, sir. "
                "The memory banks are already in excellent order."
            )

        # Group by category
        by_category: dict[str, list] = {}
        for m in old_memories:
            cat = m.get("category", "fact")
            by_category.setdefault(cat, []).append(m)

        insights_created = 0
        ids_to_remove: set[str] = set()
        new_insights: list[dict] = []

        for category, memories in by_category.items():
            if len(memories) < 2:
                continue  # A single memory isn't worth summarising

            batch_text = "\n".join(
                f"- [{m['id']}] {m['content']}" for m in memories[:40]
            )
            prompt = (
                f"The following are memories from an AI assistant in the '{category}' category.\n"
                f"Write ONE concise, high-level insight (2-4 sentences) that captures the most\n"
                f"important patterns or facts. Be specific and factual.\n\n"
                f"Memories:\n{batch_text}\n\n"
                f"High-level insight:"
            )
            insight_text = _ollama(prompt, timeout=90)
            if not insight_text or insight_text.startswith("[Ollama error"):
                continue

            new_insight = {
                "id": str(uuid.uuid4())[:8],
                "content": f"[INSIGHT — {category}] {insight_text}",
                "category": "insight",
                "importance": 5,
                "timestamp": datetime.now().isoformat(),
                "tags": [category, "sleep_cycle", "auto_generated"],
                "source_ids": [m["id"] for m in memories],
            }
            embedding = _embed(new_insight["content"])
            if embedding:
                new_insight["embedding"] = embedding

            new_insights.append(new_insight)
            ids_to_remove.update(m["id"] for m in memories)
            insights_created += 1

        if not insights_created:
            return (
                "I reviewed the older memories, sir, but found nothing worth consolidating "
                "into insights at this time."
            )

        # Remove the raw old memories and add the new insights
        pruned = [m for m in data if m["id"] not in ids_to_remove]
        pruned.extend(new_insights)
        _save(pruned)

        # Persist insights log for reference
        try:
            existing_log = json.loads(INSIGHTS_LOG.read_text(encoding="utf-8")) if INSIGHTS_LOG.exists() else []
            existing_log.extend(new_insights)
            INSIGHTS_LOG.write_text(json.dumps(existing_log, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        removed_count = len(ids_to_remove)
        return (
            f"◆ Sleep Cycle complete, sir.\n"
            f"  {insights_created} high-level insight(s) distilled from {removed_count} raw memories.\n"
            f"  The insight category now holds the essential patterns — the raw data has been archived.\n"
            f"  Total memories: {len(pruned)} (was {len(data)})."
        )
