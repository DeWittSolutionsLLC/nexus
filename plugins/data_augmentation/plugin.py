"""
Data Augmentation Plugin — text augmentation and synthetic data generation.

Uses only Python stdlib: json, pathlib, datetime, random, re, urllib,
collections, logging.  No numpy / torch / sklearn.
"""

import json
import logging
import random
import re
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.data_augmentation")

OLLAMA_API    = "http://localhost:11434/api/generate"
KB_FILE       = Path(__file__).parent.parent.parent / "memory" / "knowledge_base.json"
SYNTH_DIR     = Path.home() / "NexusScripts" / "synthetic_data"
STATS_FILE    = Path.home() / "NexusScripts" / "data_augmentation_stats.json"

# ── Mini synonym dictionary (~60 common words) ────────────────────────────────
_SYNONYMS: dict = {
    "good":        ["great", "excellent", "fine", "solid", "positive"],
    "bad":         ["poor", "terrible", "awful", "negative", "weak"],
    "big":         ["large", "huge", "enormous", "vast", "substantial"],
    "small":       ["little", "tiny", "minor", "compact", "slight"],
    "fast":        ["quick", "rapid", "swift", "speedy", "prompt"],
    "slow":        ["gradual", "leisurely", "unhurried", "sluggish", "delayed"],
    "easy":        ["simple", "straightforward", "effortless", "uncomplicated", "trivial"],
    "hard":        ["difficult", "challenging", "tough", "complex", "demanding"],
    "use":         ["utilise", "employ", "apply", "leverage", "deploy"],
    "make":        ["create", "build", "construct", "produce", "generate"],
    "get":         ["obtain", "retrieve", "acquire", "fetch", "collect"],
    "show":        ["display", "present", "reveal", "demonstrate", "exhibit"],
    "find":        ["locate", "discover", "identify", "detect", "uncover"],
    "start":       ["begin", "initiate", "launch", "commence", "kick off"],
    "stop":        ["halt", "cease", "terminate", "end", "discontinue"],
    "help":        ["assist", "support", "aid", "facilitate", "guide"],
    "change":      ["modify", "alter", "adjust", "update", "revise"],
    "remove":      ["delete", "eliminate", "erase", "discard", "clear"],
    "add":         ["append", "insert", "include", "attach", "incorporate"],
    "check":       ["verify", "confirm", "validate", "inspect", "review"],
    "run":         ["execute", "perform", "carry out", "operate", "process"],
    "send":        ["transmit", "dispatch", "deliver", "forward", "submit"],
    "receive":     ["get", "obtain", "collect", "accept", "retrieve"],
    "open":        ["launch", "activate", "access", "start", "initiate"],
    "close":       ["shut", "terminate", "exit", "end", "finish"],
    "read":        ["view", "examine", "parse", "inspect", "peruse"],
    "write":       ["compose", "draft", "author", "record", "produce"],
    "save":        ["store", "persist", "preserve", "retain", "keep"],
    "load":        ["import", "fetch", "retrieve", "read", "pull"],
    "print":       ["output", "display", "render", "show", "emit"],
    "system":      ["platform", "environment", "infrastructure", "framework", "setup"],
    "data":        ["information", "content", "records", "entries", "values"],
    "file":        ["document", "resource", "asset", "item", "artifact"],
    "task":        ["job", "operation", "action", "activity", "work"],
    "error":       ["fault", "issue", "problem", "failure", "exception"],
    "result":      ["outcome", "output", "finding", "response", "answer"],
    "important":   ["critical", "essential", "key", "significant", "vital"],
    "new":         ["fresh", "recent", "novel", "modern", "updated"],
    "old":         ["previous", "prior", "outdated", "legacy", "former"],
    "main":        ["primary", "core", "central", "principal", "key"],
    "current":     ["present", "existing", "active", "live", "ongoing"],
    "next":        ["following", "subsequent", "upcoming", "ensuing", "later"],
    "final":       ["last", "ultimate", "concluding", "terminal", "closing"],
    "basic":       ["fundamental", "elementary", "core", "essential", "primary"],
    "advanced":    ["complex", "sophisticated", "expert", "higher-level", "elaborate"],
    "specific":    ["particular", "precise", "exact", "defined", "targeted"],
    "general":     ["broad", "overall", "universal", "common", "standard"],
    "process":     ["procedure", "workflow", "operation", "method", "approach"],
    "method":      ["approach", "technique", "strategy", "procedure", "way"],
    "option":      ["choice", "alternative", "setting", "parameter", "selection"],
    "value":       ["score", "figure", "number", "metric", "quantity"],
    "list":        ["collection", "set", "array", "sequence", "group"],
    "step":        ["stage", "phase", "action", "move", "iteration"],
    "model":       ["algorithm", "system", "network", "engine", "framework"],
    "training":    ["learning", "fitting", "optimising", "teaching", "developing"],
}


class DataAugmentationPlugin(BasePlugin):
    name = "data_augmentation"
    description = "Text augmentation and synthetic data generation"
    icon = "🔄"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._ollama_model = config.get("ollama_model", "llama3.2:3b")
        self._stats = self._load_stats()

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        self._connected = True
        self._status_message = "Data Augmentation ready"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {
                "action": "augment_text",
                "description": "Apply one or more augmentation techniques to a text string",
                "params": ["text", "techniques"]
            },
            {
                "action": "augment_knowledge_base",
                "description": "Load and augment the Nexus knowledge base with synonym swaps",
                "params": []
            },
            {
                "action": "generate_synthetic_qa",
                "description": "Generate synthetic Q&A pairs using Ollama on a given topic",
                "params": ["topic", "count"]
            },
            {
                "action": "apply_rotation",
                "description": "Shuffle and add noise to a list-of-dicts dataset",
                "params": ["data_json"]
            },
            {
                "action": "get_augmentation_stats",
                "description": "Return statistics on augmented datasets created so far",
                "params": []
            }
        ]

    async def execute(self, action: str, params: dict) -> str:
        try:
            if action == "augment_text":
                return self._augment_text(
                    text=params.get("text", ""),
                    techniques=params.get("techniques", ["synonym_swap"])
                )
            elif action == "augment_knowledge_base":
                return self._augment_knowledge_base()
            elif action == "generate_synthetic_qa":
                return await self._generate_synthetic_qa(
                    topic=params.get("topic", "machine learning"),
                    count=int(params.get("count", 5))
                )
            elif action == "apply_rotation":
                return self._apply_rotation(params.get("data_json", "[]"))
            elif action == "get_augmentation_stats":
                return json.dumps(self._stats, indent=2)
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"data_augmentation.{action} error: {e}")
            return f"Error in data_augmentation.{action}: {e}"

    # ── Stats helpers ─────────────────────────────────────────────────────

    def _load_stats(self) -> dict:
        if STATS_FILE.exists():
            try:
                return json.loads(STATS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"augmentations_applied": 0, "synthetic_datasets": [], "last_updated": ""}

    def _save_stats(self):
        try:
            STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
            self._stats["last_updated"] = datetime.now().isoformat()
            STATS_FILE.write_text(json.dumps(self._stats, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save stats: {e}")

    # ── Core augmentation techniques ──────────────────────────────────────

    def _synonym_swap(self, text: str) -> str:
        """Replace common words with synonyms at random."""
        words = text.split()
        result = []
        for word in words:
            # Strip punctuation for lookup, keep surrounding punctuation
            stripped = word.strip(".,!?;:\"'()")
            suffix   = word[len(stripped):]
            prefix   = word[:len(word) - len(stripped) - len(suffix)]
            key = stripped.lower()
            if key in _SYNONYMS and random.random() < 0.4:
                replacement = random.choice(_SYNONYMS[key])
                # Preserve capitalisation
                if stripped[0].isupper():
                    replacement = replacement.capitalize()
                result.append(prefix + replacement + suffix)
            else:
                result.append(word)
        return " ".join(result)

    def _back_translation_sim(self, text: str) -> str:
        """
        Simulate back-translation via simple heuristic paraphrasing:
        - Swap active↔passive-ish voice (basic pattern swap)
        - Reorder clauses separated by commas/conjunctions
        """
        # Clause splitting on commas and conjunctions
        clauses = re.split(r',\s*|\s+(?:and|but|then|so|or)\s+', text)
        clauses = [c.strip() for c in clauses if c.strip()]

        if len(clauses) > 1:
            # Reorder: move last clause first ~50% of the time
            if random.random() < 0.5:
                clauses = clauses[-1:] + clauses[:-1]
            text = ", ".join(clauses)

        # Basic active→passive approximation: "<subj> V <obj>" → "<obj> is V-ed by <subj>"
        # Only attempt on short sentences with simple patterns
        passive_pattern = re.compile(
            r'^([A-Z][a-z]+)\s+(creates?|builds?|generates?|runs?|sends?|uses?)\s+(.+)$'
        )
        m = passive_pattern.match(text.strip())
        if m and random.random() < 0.5:
            subj, verb, obj = m.group(1), m.group(2), m.group(3)
            verb_past = verb.rstrip("s") + "ed"
            text = f"{obj.capitalize()} is {verb_past} by {subj.lower()}"

        return text

    def _mixup(self, text_a: str, text_b: str) -> str:
        """Interleave sentences from two texts."""
        sents_a = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text_a) if s.strip()]
        sents_b = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text_b) if s.strip()]

        mixed = []
        i, j = 0, 0
        while i < len(sents_a) or j < len(sents_b):
            if i < len(sents_a):
                mixed.append(sents_a[i]); i += 1
            if j < len(sents_b):
                mixed.append(sents_b[j]); j += 1

        return " ".join(mixed)

    def _random_deletion(self, text: str, p: float = 0.1) -> str:
        """Randomly delete ~p fraction of words."""
        words = text.split()
        if len(words) <= 3:
            return text
        result = [w for w in words if random.random() > p]
        return " ".join(result) if result else text

    def _random_swap(self, text: str, p: float = 0.1) -> str:
        """Randomly swap adjacent word pairs ~p fraction of the time."""
        words = text.split()
        for i in range(len(words) - 1):
            if random.random() < p:
                words[i], words[i + 1] = words[i + 1], words[i]
        return " ".join(words)

    # ── augment_text dispatcher ───────────────────────────────────────────

    def _augment_text(self, text: str, techniques) -> str:
        """Apply a list of techniques and return augmented variants."""
        if not text:
            return json.dumps({"error": "No text provided."})

        if isinstance(techniques, str):
            techniques = [techniques]

        results: dict = {"original": text, "augmented": {}}

        for tech in techniques:
            tech = tech.strip().lower()
            if tech == "synonym_swap":
                results["augmented"]["synonym_swap"] = self._synonym_swap(text)
            elif tech == "back_translation_sim":
                results["augmented"]["back_translation_sim"] = self._back_translation_sim(text)
            elif tech == "mixup":
                # Mixup with itself (shuffled sentences) when only one text provided
                results["augmented"]["mixup"] = self._mixup(text, self._synonym_swap(text))
            elif tech == "random_deletion":
                results["augmented"]["random_deletion"] = self._random_deletion(text)
            elif tech == "random_swap":
                results["augmented"]["random_swap"] = self._random_swap(text)
            else:
                results["augmented"][tech] = f"Unknown technique: {tech}"

        self._stats["augmentations_applied"] = \
            self._stats.get("augmentations_applied", 0) + len(techniques)
        self._save_stats()

        return json.dumps(results, indent=2, ensure_ascii=False)

    # ── augment_knowledge_base ────────────────────────────────────────────

    def _augment_knowledge_base(self) -> str:
        """Load knowledge base JSON and augment each entry with synonym swap."""
        if not KB_FILE.exists():
            return f"Knowledge base file not found at {KB_FILE}."

        try:
            data = json.loads(KB_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            return f"Failed to load knowledge base: {e}"

        entries = data if isinstance(data, list) else data.get("entries", [])
        augmented = []
        for entry in entries:
            aug = dict(entry)
            for field in ("content", "text", "description", "summary"):
                if field in aug and isinstance(aug[field], str):
                    aug[f"{field}_augmented"] = self._synonym_swap(aug[field])
            augmented.append(aug)

        out_path = KB_FILE.parent / "knowledge_base_augmented.json"
        try:
            out_path.write_text(json.dumps(augmented, indent=2, ensure_ascii=False),
                                encoding="utf-8")
        except Exception as e:
            return f"Failed to save augmented knowledge base: {e}"

        self._stats["augmentations_applied"] = \
            self._stats.get("augmentations_applied", 0) + len(augmented)
        self._save_stats()

        return f"Augmented {len(augmented)} entries. Saved to {out_path}"

    # ── generate_synthetic_qa ─────────────────────────────────────────────

    async def _generate_synthetic_qa(self, topic: str, count: int = 5) -> str:
        """Generate synthetic Q&A pairs using Ollama."""
        prompt = (
            f"Generate {count} question-and-answer pairs about '{topic}'.\n"
            "Format each pair as:\n"
            "Q: <question>\nA: <answer>\n\n"
            "Make the questions varied and the answers factual and concise."
        )

        payload = json.dumps({
            "model": self._ollama_model,
            "prompt": prompt,
            "stream": False
        }).encode("utf-8")

        req = urllib.request.Request(
            OLLAMA_API,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            raw_text = body.get("response", "")
        except Exception as e:
            return f"Ollama request failed: {e}"

        # Parse Q/A pairs
        qa_pairs = []
        current_q = None
        for line in raw_text.splitlines():
            line = line.strip()
            if line.startswith("Q:"):
                current_q = line[2:].strip()
            elif line.startswith("A:") and current_q is not None:
                qa_pairs.append({"question": current_q, "answer": line[2:].strip()})
                current_q = None

        out = {
            "topic": topic,
            "count": len(qa_pairs),
            "pairs": qa_pairs,
            "generated_at": datetime.now().isoformat()
        }

        # Save to disk
        safe_topic = "".join(c if c.isalnum() or c in "-_" else "_" for c in topic)
        out_path = SYNTH_DIR / f"{safe_topic}.json"
        try:
            SYNTH_DIR.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save synthetic QA: {e}")

        stat_entry = {"topic": topic, "count": len(qa_pairs), "path": str(out_path),
                      "created_at": out["generated_at"]}
        if "synthetic_datasets" not in self._stats:
            self._stats["synthetic_datasets"] = []
        self._stats["synthetic_datasets"].append(stat_entry)
        self._save_stats()

        return json.dumps(out, indent=2, ensure_ascii=False)

    # ── apply_rotation ────────────────────────────────────────────────────

    def _apply_rotation(self, data_json: str) -> str:
        """Shuffle a list-of-dicts and add small noise to numeric / string fields."""
        try:
            data = json.loads(data_json)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})

        if not isinstance(data, list):
            return json.dumps({"error": "data_json must be a JSON array of objects."})

        # Shuffle order
        rotated = list(data)
        random.shuffle(rotated)

        noisy = []
        for record in rotated:
            if not isinstance(record, dict):
                noisy.append(record)
                continue

            new_record = {}
            for key, val in record.items():
                if isinstance(val, (int, float)):
                    # ±5% numeric noise
                    noise = val * random.uniform(-0.05, 0.05)
                    new_record[key] = round(val + noise, 6)
                elif isinstance(val, str):
                    new_record[key] = self._synonym_swap(val) if random.random() < 0.3 else val
                else:
                    new_record[key] = val
            noisy.append(new_record)

        self._stats["augmentations_applied"] = \
            self._stats.get("augmentations_applied", 0) + len(noisy)
        self._save_stats()

        return json.dumps({
            "original_count": len(data),
            "rotated_count":  len(noisy),
            "data": noisy
        }, indent=2, ensure_ascii=False)
