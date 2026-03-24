"""
Autonomous ML Plugin — Reinforcement Learning for Continuous Self-Improvement.

Features:
  - Reinforcement learning from user interactions
  - Success/failure tracking and adaptation
  - Behavioral optimization based on feedback
  - Continuous model improvement through experience
"""

import json
import logging
import math
import random
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.autonomous_ml")

EXPERIENCE_FILE = Path.home() / "NexusScripts" / "autonomous_ml_experience.json"
POLICY_FILE = Path.home() / "NexusScripts" / "autonomous_ml_policy.json"

class AutonomousMLPlugin(BasePlugin):
    name = "autonomous_ml"
    description = "Reinforcement learning system for continuous AI self-improvement"
    icon = "🧠"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._experience_buffer = []
        self._policy = self._load_policy()
        self._learning_rate = 0.1
        self._discount_factor = 0.9
        self._exploration_rate = 0.1

    def _load_policy(self) -> dict:
        """Load learned policy from disk."""
        if POLICY_FILE.exists():
            try:
                return json.loads(POLICY_FILE.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Failed to load policy: {e}")
        return {
            "action_values": defaultdict(float),  # Q-values for action selection
            "state_action_counts": defaultdict(int),  # Visit counts for exploration
            "success_patterns": defaultdict(list),  # Successful interaction patterns
            "failure_patterns": defaultdict(list),  # Failed interaction patterns
            "adaptation_rules": {},  # Learned rules for behavior adaptation
            "last_updated": datetime.now().isoformat()
        }

    def _save_policy(self):
        """Save learned policy to disk."""
        try:
            POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
            self._policy["last_updated"] = datetime.now().isoformat()
            POLICY_FILE.write_text(json.dumps(dict(self._policy), indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save policy: {e}")

    async def connect(self) -> bool:
        """Initialize autonomous learning system."""
        self._connected = True
        self._status_message = f"Autonomous ML active - {len(self._policy['action_values'])} learned actions"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {
                "action": "log_interaction",
                "description": "Log user interaction for reinforcement learning",
                "params": ["user_input", "ai_response", "user_feedback", "success_score", "context"]
            },
            {
                "action": "learn_from_experience",
                "description": "Process experience buffer and update policy",
                "params": []
            },
            {
                "action": "get_optimal_action",
                "description": "Get best action recommendation based on current state",
                "params": ["state", "available_actions"]
            },
            {
                "action": "analyze_performance",
                "description": "Analyze learning performance and adaptation patterns",
                "params": []
            },
            {
                "action": "reset_learning",
                "description": "Reset learning progress (use with caution)",
                "params": []
            },
            {
                "action": "grid_search",
                "description": "Exhaustive grid search over Nexus hyperparameters (temperature, top_p, routing threshold)",
                "params": []
            },
            {
                "action": "bayesian_optimize",
                "description": "Lightweight Bayesian optimisation of hyperparameters using UCB acquisition",
                "params": []
            },
            {
                "action": "get_optimization_results",
                "description": "Return best hyperparameters found by grid search and/or Bayesian optimisation",
                "params": []
            }
        ]

    async def execute(self, action: str, params: dict) -> str:
        """Execute autonomous ML actions."""
        try:
            if action == "log_interaction":
                return self._log_interaction(params)
            elif action == "learn_from_experience":
                return await self._learn_from_experience()
            elif action == "get_optimal_action":
                return self._get_optimal_action(params)
            elif action == "analyze_performance":
                return self._analyze_performance()
            elif action == "reset_learning":
                return self._reset_learning()
            elif action == "grid_search":
                result = self._run_grid_search()
                # Persist grid search results
                grid_file = POLICY_FILE.parent / "grid_search_results.json"
                try:
                    POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
                    grid_file.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                         encoding="utf-8")
                except Exception as e:
                    logger.error(f"Failed to save grid search results: {e}")
                return json.dumps(result, indent=2)
            elif action == "bayesian_optimize":
                result = self._run_bayesian_optimization()
                return json.dumps(result, indent=2)
            elif action == "get_optimization_results":
                return json.dumps(self._get_optimization_results(), indent=2)
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"Autonomous ML error: {e}")
            return f"Error in autonomous_ml.{action}: {e}"

    def _log_interaction(self, params: dict) -> str:
        """Log an interaction for later learning."""
        interaction = {
            "timestamp": datetime.now().isoformat(),
            "user_input": params.get("user_input", ""),
            "ai_response": params.get("ai_response", ""),
            "user_feedback": params.get("user_feedback", 0),  # -1 to 1 scale
            "success_score": params.get("success_score", 0.5),  # 0 to 1 scale
            "context": params.get("context", {}),
            "state_features": self._extract_state_features(params)
        }

        self._experience_buffer.append(interaction)

        # Keep buffer size manageable
        if len(self._experience_buffer) > 1000:
            self._experience_buffer = self._experience_buffer[-500:]

        # Save to disk periodically
        if len(self._experience_buffer) % 50 == 0:
            self._save_experience_buffer()

        return f"Interaction logged. Buffer size: {len(self._experience_buffer)}"

    def _extract_state_features(self, params: dict) -> dict:
        """Extract relevant features from interaction state."""
        user_input = params.get("user_input", "").lower()
        context = params.get("context", {})

        features = {
            "input_length": len(user_input),
            "has_question": "?" in user_input,
            "has_command": any(word in user_input for word in ["create", "build", "make", "do", "run", "start"]),
            "time_of_day": datetime.now().hour,
            "is_complex": len(user_input.split()) > 10,
            "has_code": any(char in user_input for char in ["{", "(", "[", "="]),
            "plugin_context": context.get("active_plugin", ""),
            "conversation_length": context.get("conversation_length", 0)
        }

        return features

    async def _learn_from_experience(self) -> str:
        """Process experience buffer and update policy using reinforcement learning."""
        if not self._experience_buffer:
            return "No experiences to learn from."

        updated_actions = 0
        successful_patterns = 0
        failed_patterns = 0

        for experience in self._experience_buffer[-100:]:  # Learn from recent experiences
            reward = self._calculate_reward(experience)
            state = self._get_state_key(experience["state_features"])
            action = self._infer_action_from_response(experience["ai_response"])

            if action:
                # Q-learning update
                old_value = self._policy["action_values"].get(f"{state}:{action}", 0.0)
                self._policy["state_action_counts"][f"{state}:{action}"] += 1

                # Temporal difference learning
                new_value = old_value + self._learning_rate * (reward + self._discount_factor * self._get_max_future_value(state) - old_value)
                self._policy["action_values"][f"{state}:{action}"] = new_value
                updated_actions += 1

                # Pattern learning
                if reward > 0.5:
                    self._policy["success_patterns"][state].append({
                        "action": action,
                        "reward": reward,
                        "features": experience["state_features"]
                    })
                    successful_patterns += 1
                elif reward < -0.2:
                    self._policy["failure_patterns"][state].append({
                        "action": action,
                        "reward": reward,
                        "features": experience["state_features"]
                    })
                    failed_patterns += 1

        # Learn adaptation rules
        self._learn_adaptation_rules()

        self._save_policy()
        self._experience_buffer = []  # Clear processed experiences

        return f"Learning complete: {updated_actions} actions updated, {successful_patterns} success patterns, {failed_patterns} failure patterns learned."

    def _calculate_reward(self, experience: dict) -> float:
        """Calculate reward from interaction experience."""
        feedback = experience.get("user_feedback", 0)
        success = experience.get("success_score", 0.5)

        # Base reward from explicit feedback
        reward = (feedback + success - 1.0)  # Normalize to -1 to 1 range

        # Bonus for complex successful interactions
        if success > 0.8 and experience["state_features"]["is_complex"]:
            reward += 0.2

        # Penalty for failed simple interactions
        if success < 0.3 and not experience["state_features"]["is_complex"]:
            reward -= 0.3

        return max(-1.0, min(1.0, reward))  # Clamp to [-1, 1]

    def _get_state_key(self, features: dict) -> str:
        """Create a state key from features for Q-learning."""
        # Discretize continuous features
        time_slot = features["time_of_day"] // 6  # 0-3 (4 time slots)
        length_cat = min(3, features["input_length"] // 50)  # 0-3 length categories

        return f"t{time_slot}_l{length_cat}_q{int(features['has_question'])}_c{int(features['has_command'])}_x{int(features['is_complex'])}"

    def _infer_action_from_response(self, response: str) -> str:
        """Infer the action taken from AI response."""
        response_lower = response.lower()

        # Map response patterns to actions
        if "action" in response_lower and "plugin" in response_lower:
            return "plugin_action"
        elif "conversation" in response_lower:
            return "conversation"
        elif "multi_action" in response_lower:
            return "multi_step"
        elif "schedule" in response_lower:
            return "schedule_task"
        elif any(word in response_lower for word in ["created", "built", "generated", "wrote"]):
            return "creation"
        elif any(word in response_lower for word in ["searched", "found", "looked up"]):
            return "research"
        else:
            return "general_response"

    def _get_max_future_value(self, state: str) -> float:
        """Get maximum Q-value for state (for Q-learning)."""
        max_value = 0.0
        for key, value in self._policy["action_values"].items():
            if key.startswith(f"{state}:"):
                max_value = max(max_value, value)
        return max_value

    def _learn_adaptation_rules(self):
        """Learn rules for adapting behavior based on patterns."""
        # Analyze success patterns to create adaptation rules
        rules = {}

        for state, patterns in self._policy["success_patterns"].items():
            if len(patterns) >= 3:  # Need multiple examples
                # Find common successful actions for this state
                action_counts = defaultdict(int)
                for pattern in patterns[-10:]:  # Recent patterns
                    action_counts[pattern["action"]] += 1

                best_action = max(action_counts.items(), key=lambda x: x[1])[0]
                rules[state] = {
                    "preferred_action": best_action,
                    "confidence": action_counts[best_action] / len(patterns[-10:]),
                    "last_updated": datetime.now().isoformat()
                }

        self._policy["adaptation_rules"] = rules

    def _get_optimal_action(self, params: dict) -> str:
        """Recommend optimal action based on learned policy."""
        state_features = params.get("state", {})
        available_actions = params.get("available_actions", [])

        if not available_actions:
            return json.dumps({"error": "No available actions provided"})

        state_key = self._get_state_key(state_features)

        # Check learned adaptation rules first
        if state_key in self._policy["adaptation_rules"]:
            rule = self._policy["adaptation_rules"][state_key]
            if rule["preferred_action"] in available_actions and rule["confidence"] > 0.6:
                return json.dumps({
                    "recommended_action": rule["preferred_action"],
                    "confidence": rule["confidence"],
                    "reason": "learned_preference",
                    "state": state_key
                })

        # Fallback to Q-learning values
        best_action = None
        best_value = float('-inf')

        for action in available_actions:
            # Exploration vs exploitation
            if random.random() < self._exploration_rate:
                # Explore: random action
                candidate = random.choice(available_actions)
            else:
                # Exploit: best known action
                candidate = action

            value = self._policy["action_values"].get(f"{state_key}:{candidate}", 0.0)
            if value > best_value:
                best_value = value
                best_action = candidate

        return json.dumps({
            "recommended_action": best_action or available_actions[0],
            "confidence": min(1.0, best_value + 0.5),  # Scale confidence
            "reason": "q_learning",
            "state": state_key
        })

    def _analyze_performance(self) -> str:
        """Analyze learning performance and patterns."""
        total_actions = len(self._policy["action_values"])
        total_states = len(set(key.split(":")[0] for key in self._policy["action_values"].keys()))
        adaptation_rules = len(self._policy["adaptation_rules"])

        success_patterns = sum(len(patterns) for patterns in self._policy["success_patterns"].values())
        failure_patterns = sum(len(patterns) for patterns in self._policy["failure_patterns"].values())

        # Calculate learning statistics
        q_values = list(self._policy["action_values"].values())
        avg_q_value = sum(q_values) / len(q_values) if q_values else 0

        analysis = {
            "total_learned_actions": total_actions,
            "unique_states": total_states,
            "adaptation_rules": adaptation_rules,
            "success_patterns": success_patterns,
            "failure_patterns": failure_patterns,
            "average_q_value": round(avg_q_value, 3),
            "learning_progress": "good" if total_actions > 50 else "developing",
            "last_updated": self._policy.get("last_updated", "never")
        }

        return json.dumps(analysis, indent=2)

    def _reset_learning(self) -> str:
        """Reset all learned knowledge."""
        self._policy = {
            "action_values": defaultdict(float),
            "state_action_counts": defaultdict(int),
            "success_patterns": defaultdict(list),
            "failure_patterns": defaultdict(list),
            "adaptation_rules": {},
            "last_updated": datetime.now().isoformat()
        }
        self._experience_buffer = []
        self._save_policy()

        # Remove experience file
        if EXPERIENCE_FILE.exists():
            EXPERIENCE_FILE.unlink()

        return "Learning progress reset. Starting fresh."

    def _save_experience_buffer(self):
        """Save experience buffer to disk."""
        try:
            EXPERIENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(EXPERIENCE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._experience_buffer, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save experience buffer: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Grid Search & Bayesian Optimisation (new capabilities)
    # ─────────────────────────────────────────────────────────────────────────

    _GRID_TEMPERATURE = [0.1, 0.3, 0.5, 0.7, 0.9]
    _GRID_TOP_P       = [0.7, 0.8, 0.9, 0.95, 1.0]
    _GRID_THRESHOLD   = [0.3, 0.5, 0.7]

    def _score_hyperparams(self, temperature: float, top_p: float, threshold: float) -> float:
        """
        Score a hyperparameter combination by correlating with high-reward
        interactions stored in the experience buffer.

        Returns a float in [0, 1] — higher is better.
        """
        if not self._experience_buffer:
            # No data: use a simple heuristic favouring mid-range values
            t_score = 1.0 - abs(temperature - 0.5) * 2
            p_score = 1.0 - abs(top_p - 0.9) * 5
            th_score = 1.0 - abs(threshold - 0.5) * 2
            return (t_score + p_score + th_score) / 3.0

        total_reward = 0.0
        total_weight = 0.0

        for exp in self._experience_buffer:
            success = exp.get("success_score", 0.5)
            features = exp.get("state_features", {})
            is_complex = features.get("is_complex", False)

            # Weight each experience by how well these hyperparams match the
            # kind of interaction (heuristic proxy, no LLM calls needed).
            weight = 1.0
            if is_complex and temperature > 0.5:
                weight += 0.3   # creative tasks benefit from higher temperature
            if not is_complex and temperature < 0.5:
                weight += 0.3   # factual tasks benefit from lower temperature

            # top_p: high top_p rewards diversity; low rewards focus
            input_len = features.get("input_length", 50)
            if input_len > 100 and top_p >= 0.9:
                weight += 0.2
            if input_len <= 100 and top_p <= 0.8:
                weight += 0.2

            # threshold: mid-range thresholds are usually best
            th_penalty = abs(threshold - 0.5) * 0.4
            weight = max(0.1, weight - th_penalty)

            total_reward += success * weight
            total_weight += weight

        return total_reward / total_weight if total_weight > 0 else 0.5

    def _run_grid_search(self) -> dict:
        """Exhaustive grid search over hyperparameter space."""
        best_score = -1.0
        best_params: dict = {}
        results = []

        total = (len(self._GRID_TEMPERATURE) *
                 len(self._GRID_TOP_P) *
                 len(self._GRID_THRESHOLD))

        for temp in self._GRID_TEMPERATURE:
            for top_p in self._GRID_TOP_P:
                for thresh in self._GRID_THRESHOLD:
                    score = self._score_hyperparams(temp, top_p, thresh)
                    results.append({
                        "temperature": temp,
                        "top_p": top_p,
                        "routing_threshold": thresh,
                        "score": round(score, 4)
                    })
                    if score > best_score:
                        best_score = score
                        best_params = {
                            "temperature": temp,
                            "top_p": top_p,
                            "routing_threshold": thresh
                        }

        results.sort(key=lambda x: x["score"], reverse=True)
        return {
            "method": "grid_search",
            "total_combinations": total,
            "best_params": best_params,
            "best_score": round(best_score, 4),
            "top_10": results[:10],
            "timestamp": datetime.now().isoformat()
        }

    # ── Bayesian Optimisation ─────────────────────────────────────────────

    def _bayesian_surrogate(self, temperature: float, top_p: float,
                             threshold: float,
                             observations: list) -> tuple:
        """
        Lightweight surrogate model — no scipy/sklearn.

        Returns (mean_estimate, exploration_bonus).
        mean_estimate:      weighted average of nearby observed scores.
        exploration_bonus:  inversely proportional to visit count.
        """
        if not observations:
            base = self._score_hyperparams(temperature, top_p, threshold)
            return base, 0.5   # High bonus when no data

        weighted_sum = 0.0
        weight_total = 0.0
        visit_count = 0

        for obs in observations:
            # Euclidean distance in normalised hyperparameter space
            dt = (temperature - obs["temperature"]) / 0.8   # range ~0.8
            dp = (top_p - obs["top_p"]) / 0.3               # range ~0.3
            dth = (threshold - obs["threshold"]) / 0.4      # range ~0.4
            dist = (dt**2 + dp**2 + dth**2) ** 0.5

            # Gaussian-like kernel
            kernel = math.exp(-4.0 * dist**2) if dist < 2 else 0.0
            weighted_sum += kernel * obs["score"]
            weight_total += kernel

            if dist < 0.15:     # "visited" if close enough
                visit_count += 1

        if weight_total > 1e-9:
            mean_est = weighted_sum / weight_total
        else:
            mean_est = self._score_hyperparams(temperature, top_p, threshold)

        # Exploration bonus: high when unvisited
        exploration_bonus = 1.0 / (1.0 + visit_count * 3.0)
        return mean_est, exploration_bonus

    def _acquisition_function(self, temperature: float, top_p: float,
                               threshold: float, observations: list,
                               best_score: float, kappa: float = 2.0) -> float:
        """UCB (Upper Confidence Bound) acquisition function."""
        mean, bonus = self._bayesian_surrogate(temperature, top_p, threshold, observations)
        return mean + kappa * bonus

    def _run_bayesian_optimization(self, n_iterations: int = 30) -> dict:
        """
        Lightweight Bayesian optimisation over the same hyperparameter space.

        Uses random candidate generation + UCB acquisition.
        """
        import random as _rnd

        observations: list = []
        best_score = -1.0
        best_params: dict = {}

        # Seed with a few grid points first
        seed_points = [
            (0.5, 0.9, 0.5),
            (0.3, 0.8, 0.3),
            (0.7, 0.95, 0.7),
        ]
        for temp, top_p, thresh in seed_points:
            score = self._score_hyperparams(temp, top_p, thresh)
            obs = {"temperature": temp, "top_p": top_p,
                   "threshold": thresh, "score": score}
            observations.append(obs)
            if score > best_score:
                best_score = score
                best_params = {"temperature": temp, "top_p": top_p,
                               "routing_threshold": thresh}

        for _ in range(n_iterations):
            # Generate random candidates
            n_candidates = 20
            best_acq = -1.0
            best_candidate = None

            for _ in range(n_candidates):
                temp  = _rnd.choice(self._GRID_TEMPERATURE)
                top_p = _rnd.choice(self._GRID_TOP_P)
                thresh = _rnd.choice(self._GRID_THRESHOLD)
                acq = self._acquisition_function(temp, top_p, thresh,
                                                  observations, best_score)
                if acq > best_acq:
                    best_acq = acq
                    best_candidate = (temp, top_p, thresh)

            if best_candidate:
                temp, top_p, thresh = best_candidate
                score = self._score_hyperparams(temp, top_p, thresh)
                observations.append({"temperature": temp, "top_p": top_p,
                                      "threshold": thresh, "score": score})
                if score > best_score:
                    best_score = score
                    best_params = {"temperature": temp, "top_p": top_p,
                                   "routing_threshold": thresh}

        result = {
            "method": "bayesian_optimization",
            "iterations": n_iterations + len(seed_points),
            "best_params": best_params,
            "best_score": round(best_score, 4),
            "observations": sorted(observations, key=lambda x: x["score"], reverse=True)[:10],
            "timestamp": datetime.now().isoformat()
        }

        # Persist results
        out_file = POLICY_FILE.parent / "bayesian_results.json"
        try:
            POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save Bayesian results: {e}")

        return result

    def _get_optimization_results(self) -> dict:
        """Return best known parameters from all optimisation runs."""
        out_file = POLICY_FILE.parent / "bayesian_results.json"
        grid_file = POLICY_FILE.parent / "grid_search_results.json"

        results = {}

        if out_file.exists():
            try:
                results["bayesian"] = json.loads(out_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        if grid_file.exists():
            try:
                results["grid_search"] = json.loads(grid_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        if not results:
            return {"message": "No optimisation results yet. Run grid_search or bayesian_optimize first."}

        # Determine overall best
        candidates = []
        if "bayesian" in results:
            candidates.append(("bayesian", results["bayesian"]["best_score"],
                                results["bayesian"]["best_params"]))
        if "grid_search" in results:
            candidates.append(("grid_search", results["grid_search"]["best_score"],
                                results["grid_search"]["best_params"]))

        candidates.sort(key=lambda x: x[1], reverse=True)
        best_method, best_score, best_params = candidates[0]

        results["overall_best"] = {
            "method": best_method,
            "score": best_score,
            "params": best_params
        }
        return results