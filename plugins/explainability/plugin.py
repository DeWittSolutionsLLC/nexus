"""
Explainability Plugin — lightweight SHAP/LIME-style explanations for Nexus.

No heavy ML dependencies: uses only stdlib + pure Python maths.

SHAP-style: analyses the autonomous_ml experience buffer to compute word-level
importance scores by contrasting high-score vs low-score interactions.

LIME-style: fits a local linear model (pure-Python least squares) to predict
a query's success based on neighbourhood of similar past interactions.
"""

import json
import logging
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.explainability")

EXPERIENCE_FILE = Path.home() / "NexusScripts" / "autonomous_ml_experience.json"

# Score threshold separating "high" from "low" quality interactions
HIGH_SCORE_THRESHOLD = 0.65
LOW_SCORE_THRESHOLD  = 0.40


class ExplainabilityPlugin(BasePlugin):
    name = "explainability"
    description = "SHAP/LIME-style explainability for Nexus AI decisions"
    icon = "🔍"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._cached_experience: list = []
        self._cached_report: str = ""

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        self._connected = True
        self._status_message = "Explainability ready"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {
                "action": "analyze_decision_factors",
                "description": "SHAP-style word importance from past interactions",
                "params": []
            },
            {
                "action": "lime_explain",
                "description": "LIME-style local linear explanation for a query string",
                "params": ["query"]
            },
            {
                "action": "find_biases",
                "description": "Find systematic biases in the interaction history",
                "params": []
            },
            {
                "action": "get_explainability_report",
                "description": "Full explainability report (SHAP + LIME + biases)",
                "params": []
            }
        ]

    async def execute(self, action: str, params: dict) -> str:
        try:
            if action == "analyze_decision_factors":
                return self._analyze_decision_factors()
            elif action == "lime_explain":
                return self._lime_explain(params.get("query", ""))
            elif action == "find_biases":
                return self._find_biases()
            elif action == "get_explainability_report":
                return self._get_explainability_report()
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"explainability.{action} error: {e}")
            return f"Error in explainability.{action}: {e}"

    # ── Data loading ──────────────────────────────────────────────────────

    def _load_experience(self) -> list:
        """Load the autonomous_ml experience buffer from disk."""
        if self._cached_experience:
            return self._cached_experience

        if not EXPERIENCE_FILE.exists():
            return []

        try:
            data = json.loads(EXPERIENCE_FILE.read_text(encoding="utf-8"))
            self._cached_experience = data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to load experience: {e}")
            self._cached_experience = []

        return self._cached_experience

    # ── Tokenisation helpers ──────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list:
        """Simple word tokeniser: lowercase, strip punctuation."""
        return re.findall(r"[a-z][a-z']{1,}", text.lower())

    _STOP_WORDS = frozenset([
        "the", "a", "an", "is", "it", "in", "on", "at", "to", "for",
        "of", "and", "or", "but", "with", "this", "that", "was", "are",
        "be", "by", "as", "if", "so", "do", "me", "my", "you", "i",
        "we", "he", "she", "they", "have", "has", "had", "not", "can",
        "will", "would", "could", "should", "its", "from", "just", "also"
    ])

    def _meaningful_tokens(self, text: str) -> list:
        return [t for t in self._tokenize(text) if t not in self._STOP_WORDS]

    # ── SHAP-style importance ─────────────────────────────────────────────

    def _analyze_decision_factors(self) -> str:
        """
        Compute word-level importance by contrasting token frequencies in
        high-score vs low-score interactions (pseudo-SHAP Shapley proxy).
        """
        experiences = self._load_experience()
        if not experiences:
            return json.dumps({"error": "No experience data found.",
                               "hint": "Use autonomous_ml to log some interactions first."})

        high_freq: dict = defaultdict(int)
        low_freq:  dict = defaultdict(int)
        high_count = 0
        low_count  = 0

        for exp in experiences:
            score = exp.get("success_score", 0.5)
            text  = exp.get("user_input", "")
            tokens = self._meaningful_tokens(text)

            if score >= HIGH_SCORE_THRESHOLD:
                for t in tokens:
                    high_freq[t] += 1
                high_count += 1
            elif score <= LOW_SCORE_THRESHOLD:
                for t in tokens:
                    low_freq[t] += 1
                low_count += 1

        if high_count == 0 and low_count == 0:
            return json.dumps({"error": "Not enough labelled interactions to compute importance."})

        # Smooth counts to avoid div-by-zero
        h = max(high_count, 1)
        l = max(low_count, 1)

        all_words = set(high_freq) | set(low_freq)
        importance: dict = {}
        for word in all_words:
            p_high = high_freq.get(word, 0) / h
            p_low  = low_freq.get(word, 0)  / l
            # Positive score → more common in high-scoring; negative → low-scoring
            importance[word] = round(p_high - p_low, 4)

        # Sort descending by absolute importance
        sorted_imp = sorted(importance.items(), key=lambda x: abs(x[1]), reverse=True)

        top_positive = [(w, s) for w, s in sorted_imp if s > 0][:15]
        top_negative = [(w, s) for w, s in sorted_imp if s < 0][:15]

        result = {
            "method": "SHAP-style (frequency contrast)",
            "total_interactions": len(experiences),
            "high_score_interactions": high_count,
            "low_score_interactions":  low_count,
            "top_positive_words": top_positive,   # associated with success
            "top_negative_words": top_negative,   # associated with failure
            "all_importances": dict(sorted_imp[:40]),
            "timestamp": datetime.now().isoformat()
        }
        return json.dumps(result, indent=2)

    # ── LIME-style local linear model ─────────────────────────────────────

    @staticmethod
    def _jaccard(set_a: set, set_b: set) -> float:
        if not set_a and not set_b:
            return 1.0
        union = set_a | set_b
        inter = set_a & set_b
        return len(inter) / len(union)

    @staticmethod
    def _ols_1d(x_vals: list, y_vals: list) -> tuple:
        """Ordinary least squares for a single feature: returns (slope, intercept)."""
        n = len(x_vals)
        if n < 2:
            return 0.0, (sum(y_vals) / n if n else 0.0)

        mean_x = sum(x_vals) / n
        mean_y = sum(y_vals) / n

        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_vals, y_vals))
        den = sum((x - mean_x) ** 2 for x in x_vals)

        slope = num / den if abs(den) > 1e-12 else 0.0
        intercept = mean_y - slope * mean_x
        return slope, intercept

    def _lime_explain(self, query: str) -> str:
        """
        LIME-style local linear approximation.

        For the given query string:
        1. Find similar past interactions (neighbourhood).
        2. Build simple features: query_len, token_overlap, has_question, has_command.
        3. Fit per-feature OLS linear models against success_score.
        4. Return coefficients as feature importances.
        """
        experiences = self._load_experience()
        if not experiences:
            return json.dumps({"error": "No experience data available."})

        query_tokens = set(self._meaningful_tokens(query))
        has_question = 1 if "?" in query else 0
        has_command  = 1 if any(w in query.lower()
                                for w in ["create", "build", "make", "do", "run", "start", "find"]) else 0
        query_len = len(query.split())

        # Build neighbourhood (top-20 most similar past queries)
        scored = []
        for exp in experiences:
            past_tokens = set(self._meaningful_tokens(exp.get("user_input", "")))
            sim = self._jaccard(query_tokens, past_tokens)
            scored.append((sim, exp))

        scored.sort(key=lambda x: x[0], reverse=True)
        neighbourhood = scored[:20]

        if len(neighbourhood) < 3:
            return json.dumps({
                "method": "LIME",
                "query": query,
                "message": "Not enough similar interactions for local model.",
                "neighbourhood_size": len(neighbourhood)
            })

        # Extract feature vectors
        similarities   = []
        query_lengths  = []
        has_questions  = []
        has_commands   = []
        success_scores = []

        for sim, exp in neighbourhood:
            inp = exp.get("user_input", "")
            similarities.append(sim)
            query_lengths.append(len(inp.split()))
            has_questions.append(1 if "?" in inp else 0)
            has_commands.append(1 if any(w in inp.lower()
                                         for w in ["create", "build", "make", "do",
                                                   "run", "start", "find"]) else 0)
            success_scores.append(exp.get("success_score", 0.5))

        # Fit per-feature OLS (proxy for LIME coefficients)
        slope_sim,  int_sim  = self._ols_1d(similarities, success_scores)
        slope_len,  int_len  = self._ols_1d(query_lengths, success_scores)
        slope_q,    int_q    = self._ols_1d(has_questions, success_scores)
        slope_cmd,  int_cmd  = self._ols_1d(has_commands,  success_scores)

        # Predict score for THIS query using each single-feature model
        pred_sim  = slope_sim  * 1.0        + int_sim   # sim=1.0 (the query itself)
        pred_len  = slope_len  * query_len  + int_len
        pred_q    = slope_q    * has_question + int_q
        pred_cmd  = slope_cmd  * has_command  + int_cmd

        avg_pred = (pred_sim + pred_len + pred_q + pred_cmd) / 4.0
        avg_pred = max(0.0, min(1.0, avg_pred))

        result = {
            "method": "LIME (local linear approximation)",
            "query": query,
            "neighbourhood_size": len(neighbourhood),
            "predicted_success_score": round(avg_pred, 3),
            "feature_coefficients": {
                "token_similarity":      round(slope_sim, 4),
                "query_length":          round(slope_len, 4),
                "has_question_mark":     round(slope_q,   4),
                "has_command_word":      round(slope_cmd, 4)
            },
            "feature_values": {
                "token_similarity":      1.0,
                "query_length":          query_len,
                "has_question_mark":     has_question,
                "has_command_word":      has_command
            },
            "interpretation": (
                "Positive coefficient → feature increases predicted success. "
                "Negative coefficient → feature reduces predicted success."
            ),
            "timestamp": datetime.now().isoformat()
        }
        return json.dumps(result, indent=2)

    # ── Bias analysis ─────────────────────────────────────────────────────

    def _find_biases(self) -> str:
        """
        Scan the experience buffer for systematic biases:
          1. Topic-level biases (words consistently correlated with low scores).
          2. Time-of-day patterns (certain hours yielding lower scores).
          3. Query length correlations.
        """
        experiences = self._load_experience()
        if len(experiences) < 10:
            return json.dumps({
                "error": "Need at least 10 logged interactions to detect biases.",
                "current_count": len(experiences)
            })

        biases = {}

        # ── 1. Topic biases ───────────────────────────────────────────────
        word_scores: dict = defaultdict(list)
        for exp in experiences:
            score = exp.get("success_score", 0.5)
            for token in self._meaningful_tokens(exp.get("user_input", "")):
                word_scores[token].append(score)

        low_topics = {}
        high_topics = {}
        for word, scores in word_scores.items():
            if len(scores) >= 3:
                avg = sum(scores) / len(scores)
                if avg < LOW_SCORE_THRESHOLD:
                    low_topics[word] = round(avg, 3)
                elif avg > HIGH_SCORE_THRESHOLD:
                    high_topics[word] = round(avg, 3)

        biases["low_scoring_topics"] = dict(
            sorted(low_topics.items(), key=lambda x: x[1])[:10]
        )
        biases["high_scoring_topics"] = dict(
            sorted(high_topics.items(), key=lambda x: x[1], reverse=True)[:10]
        )

        # ── 2. Time-of-day patterns ───────────────────────────────────────
        hour_scores: dict = defaultdict(list)
        for exp in experiences:
            ts = exp.get("timestamp", "")
            try:
                hour = datetime.fromisoformat(ts).hour
                hour_scores[hour].append(exp.get("success_score", 0.5))
            except Exception:
                pass

        hour_avgs = {}
        for hour, scores in hour_scores.items():
            hour_avgs[hour] = round(sum(scores) / len(scores), 3)

        if hour_avgs:
            best_hour  = max(hour_avgs, key=hour_avgs.get)
            worst_hour = min(hour_avgs, key=hour_avgs.get)
            biases["time_of_day"] = {
                "per_hour_avg_score": {str(k): v for k, v in sorted(hour_avgs.items())},
                "best_hour":  best_hour,
                "worst_hour": worst_hour,
                "gap": round(hour_avgs[best_hour] - hour_avgs[worst_hour], 3)
            }

        # ── 3. Query length correlation ───────────────────────────────────
        lengths = [len(exp.get("user_input", "").split()) for exp in experiences]
        scores  = [exp.get("success_score", 0.5)          for exp in experiences]

        if len(lengths) >= 3:
            slope, _ = self._ols_1d(lengths, scores)
            mean_len = sum(lengths) / len(lengths)
            short = [s for l, s in zip(lengths, scores) if l <= mean_len]
            long_ = [s for l, s in zip(lengths, scores) if l > mean_len]
            biases["query_length"] = {
                "slope": round(slope, 4),
                "interpretation": (
                    "Positive slope → longer queries tend to score higher. "
                    "Negative slope → shorter queries score higher."
                ),
                "avg_score_short_queries": round(sum(short) / len(short), 3) if short else None,
                "avg_score_long_queries":  round(sum(long_) / len(long_), 3) if long_ else None
            }

        biases["total_interactions_analysed"] = len(experiences)
        biases["timestamp"] = datetime.now().isoformat()

        return json.dumps(biases, indent=2)

    # ── Full report ───────────────────────────────────────────────────────

    def _get_explainability_report(self) -> str:
        """Combine SHAP analysis, bias findings, and summary into a text report."""
        shap_raw  = self._analyze_decision_factors()
        bias_raw  = self._find_biases()

        try:
            shap_data = json.loads(shap_raw)
        except Exception:
            shap_data = {}

        try:
            bias_data = json.loads(bias_raw)
        except Exception:
            bias_data = {}

        lines = [
            "=" * 60,
            "NEXUS EXPLAINABILITY REPORT",
            f"Generated: {datetime.now().isoformat()}",
            "=" * 60,
            "",
            "── SHAP-STYLE WORD IMPORTANCE ──",
            f"Interactions analysed: {shap_data.get('total_interactions', 'N/A')}",
            f"High-score interactions: {shap_data.get('high_score_interactions', 'N/A')}",
            f"Low-score interactions:  {shap_data.get('low_score_interactions', 'N/A')}",
            "",
            "Words most associated with SUCCESS:",
        ]
        for word, score in (shap_data.get("top_positive_words") or [])[:10]:
            lines.append(f"  +{score:+.3f}  {word}")

        lines.append("")
        lines.append("Words most associated with FAILURE:")
        for word, score in (shap_data.get("top_negative_words") or [])[:10]:
            lines.append(f"  {score:+.3f}  {word}")

        lines += [
            "",
            "── BIAS ANALYSIS ──",
        ]

        if "low_scoring_topics" in bias_data:
            lines.append("Consistently low-scoring topics:")
            for topic, avg in bias_data["low_scoring_topics"].items():
                lines.append(f"  {topic}: avg score {avg}")

        if "time_of_day" in bias_data:
            tod = bias_data["time_of_day"]
            lines.append(f"\nTime-of-day: best hour = {tod['best_hour']}:00 "
                         f"({tod['per_hour_avg_score'].get(str(tod['best_hour']), '?')}), "
                         f"worst = {tod['worst_hour']}:00 "
                         f"({tod['per_hour_avg_score'].get(str(tod['worst_hour']), '?')})")

        if "query_length" in bias_data:
            ql = bias_data["query_length"]
            lines.append(f"\nQuery length slope: {ql['slope']} — {ql['interpretation']}")

        lines += ["", "=" * 60]
        report = "\n".join(lines)
        self._cached_report = report
        return report
