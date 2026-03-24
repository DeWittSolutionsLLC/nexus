# Nexus ML Algorithms & Self-Improvement System

## Overview

Nexus implements a layered self-improvement architecture that operates continuously in the background. The system follows a **Research → Plan → Implement → Validate → Learn** cycle coordinated by the `self_improver` plugin. Each cycle draws on four complementary subsystems:

- **autonomous_ml** — reinforcement learning and hyperparameter optimisation
- **explainability** — SHAP/LIME-style transparency into AI decisions
- **data_augmentation** — synthetic data and text augmentation pipelines
- **ml_research** — live paper retrieval from arXiv to ground improvements in current research

All algorithms are implemented using only the Python standard library (no numpy, scipy, sklearn, or torch).

---

## Algorithm Classes

### 1. Reinforcement Learning (Q-Learning)

**Plugin:** `autonomous_ml`

#### How it works in Nexus

Every user interaction is stored in an *experience buffer* as a tuple of `(state_features, action, reward)`. The state is discretised into a string key encoding time-of-day slot, input length category, whether the query contained a question mark, a command word, or was complex. The reward combines explicit user feedback (−1 to +1) with a computed success score.

The Q-value update rule applied after each learning pass:

```
Q(s, a) ← Q(s, a) + α · [r + γ · max_a' Q(s', a') − Q(s, a)]
```

Where:
- `α = 0.1` (learning rate)
- `γ = 0.9` (discount factor)
- `ε = 0.1` (exploration rate — probability of choosing a random action)

After enough examples accumulate for a state, adaptation rules are inferred: if the same action succeeds ≥ 60 % of the time in a given state, it becomes the rule-based preference for that state.

#### Strengths
- Requires no labelled dataset upfront; learns purely from live usage.
- Handles delayed rewards naturally via the discount factor.
- Lightweight: Q-table fits in memory even with thousands of state-action pairs.

#### Weaknesses
- Discretisation of continuous state features loses information.
- Convergence is slow when the state space is large or sparsely visited.
- Reward shaping is heuristic; poorly designed rewards can mislead learning.

#### Applications in Nexus
- Recommending the best plugin action for a given user context.
- Learning which response style (creative vs. factual) suits each user and time of day.
- Feeding reward signals back to the hyperparameter optimisers.

---

### 2. Hyperparameter Optimisation

**Plugin:** `autonomous_ml` (actions: `grid_search`, `bayesian_optimize`, `get_optimization_results`)

The optimised parameters are:
| Parameter | Search Space |
|-----------|-------------|
| `temperature` | 0.1, 0.3, 0.5, 0.7, 0.9 |
| `top_p` | 0.7, 0.8, 0.9, 0.95, 1.0 |
| `routing_threshold` | 0.3, 0.5, 0.7 |

The scoring function correlates each combination with high-reward interactions from the experience buffer, rewarding temperature/top_p values that match the complexity profile of successful interactions.

#### Grid Search

**How it works:** Enumerates every combination of the three parameter grids (5 × 5 × 3 = 75 combinations). Each combination is scored by the `_score_hyperparams` method. The full result table is saved to `~/NexusScripts/grid_search_results.json`.

**Strengths:** Exhaustive — guaranteed to find the global optimum within the discrete grid. Simple to implement and reason about.

**Weaknesses:** Exponential in the number of parameters (the "curse of dimensionality"). With 75 combinations it is fast, but adding a fourth parameter axis would multiply cost by the size of that axis.

**Applications:** Best used when the parameter space is small and a full audit of all combinations is desired (e.g., after a major model update).

#### Bayesian Optimisation

**How it works:** Uses a lightweight surrogate model — a Gaussian-kernel-weighted average of past observations — plus an UCB (Upper Confidence Bound) acquisition function:

```
UCB(x) = μ(x) + κ · β(x)
```

Where `μ(x)` is the surrogate mean estimate and `β(x)` is an exploration bonus inversely proportional to how many times similar points have been evaluated. `κ = 2.0` balances exploration vs. exploitation.

The optimiser seeds with three hand-picked points, then runs 30 iterations of: generate 20 random candidates → pick the one with the highest UCB score → evaluate → update observations. Results persist to `~/NexusScripts/bayesian_results.json`.

**Strengths:** Sample-efficient — typically finds near-optimal parameters in far fewer evaluations than grid search. The UCB acquisition function naturally handles the exploration-exploitation trade-off.

**Weaknesses:** The surrogate model here is a simple kernel regression, not a full Gaussian Process, so uncertainty estimates are approximate. Overhead of the acquisition loop grows with the number of past observations.

**Applications:** Ongoing tuning as new interaction data accumulates. Particularly useful when the scoring function is expensive (e.g., if extended to run actual Ollama inference).

---

### 3. Explainability Methods

**Plugin:** `explainability`

#### SHAP (SHapley Additive exPlanations) — Nexus Lightweight Implementation

**Theory:** In game theory, the Shapley value of a player is their average marginal contribution across all possible coalitions. Applied to ML, each input feature's Shapley value measures its average contribution to the model output across all possible feature subsets.

**Nexus implementation:** Because running the LLM hundreds of times per explanation is impractical, Nexus uses a *frequency-contrast* proxy: for each word appearing in the experience buffer, compute:

```
importance(word) = P(word | high_score) − P(word | low_score)
```

Where "high score" means `success_score ≥ 0.65` and "low score" means `success_score ≤ 0.40`. A strongly positive importance means the word co-occurs far more often with successful interactions; strongly negative means the opposite.

**Strengths:** Zero additional LLM calls. Operates entirely on cached interaction history. Returns interpretable word-level scores.

**Weaknesses:** Correlation, not causation — a word may score high simply because it appears in longer queries that tend to succeed. Does not capture feature interactions. Requires a reasonably large experience buffer for reliable estimates.

**Actions:** `analyze_decision_factors` → returns `{word: importance_score}` dict.

#### LIME (Local Interpretable Model-agnostic Explanations) — Nexus Lightweight Implementation

**Theory:** LIME fits a simple (linear) interpretable model in the local neighbourhood of a prediction point. The local model approximates the complex model's behaviour for inputs similar to the query.

**Nexus implementation:**
1. Find the 20 past interactions most similar to the query (Jaccard similarity on word tokens).
2. Extract four features per interaction: `token_similarity`, `query_length`, `has_question_mark`, `has_command_word`.
3. Fit a per-feature ordinary least-squares (OLS) linear regression against `success_score` using pure Python (no numpy).
4. Return OLS slopes as feature coefficients (positive = increases predicted success).
5. Predict the query's success score by averaging per-feature predictions.

**Strengths:** Provides a per-query explanation rather than a global one. The local linear model is easy to inspect and communicate. No LLM calls required.

**Weaknesses:** Four hand-crafted features capture only a fraction of what makes a query succeed. OLS per-feature (rather than multivariate) ignores feature correlations. Neighbourhood definition via Jaccard is coarse.

**Actions:** `lime_explain` (params: `query`) → predicted score + coefficient dict.

---

### 4. Data Augmentation

**Plugin:** `data_augmentation`

#### Text Augmentation Techniques

| Technique | Description | Best use case |
|-----------|-------------|---------------|
| `synonym_swap` | Replaces ~40 % of eligible words with synonyms from a 60-word dictionary. | Expanding training variety while preserving meaning. |
| `back_translation_sim` | Reorders clauses and attempts basic active↔passive voice swap. | Teaching the system to be robust to syntactic variation. |
| `mixup` | Interleaves sentences from the original text with a synonym-swapped variant. | Creating blended examples for boundary-region training. |
| `random_deletion` | Randomly removes ~10 % of words. | Simulating noisy or truncated queries. |
| `random_swap` | Randomly transposes adjacent word pairs ~10 % of the time. | Robustness to minor word-order variation. |

**Strengths:** No external dependencies or API calls. Instantaneous. Controllable via the `techniques` parameter.

**Weaknesses:** Synonym swaps use a static, limited dictionary — domain-specific vocabulary will not be covered. Back-translation simulation is rule-based and will not capture genuine paraphrase diversity.

#### Synthetic Data Generation (GAN-inspired)

**How it works:** Nexus uses the local Ollama LLM (llama3.2:3b) as a *generator*: given a topic, it is prompted to produce N question-answer pairs with varied question styles. The output is parsed from a structured `Q: / A:` format and saved to `~/NexusScripts/synthetic_data/{topic}.json`.

This loosely mirrors the GAN generator role (producing new plausible examples) but without a discriminator network — quality filtering relies on the LLM's own coherence.

**Strengths:** Can produce topically targeted Q&A without any human annotation. Integrates directly with the knowledge base augmentation pipeline.

**Weaknesses:** Quality depends entirely on the base LLM. The 3B parameter model may hallucinate or produce repetitive pairs. No adversarial discriminator to filter low-quality outputs (unlike a true GAN).

**Applications:** Pre-populating the knowledge base for a new domain. Augmenting the experience buffer with synthetic interactions to bootstrap Q-learning.

---

### 5. Self-Improvement Orchestration

**Plugin:** `self_improver`

#### Research → Plan → Implement → Validate → Learn Cycle

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  ml_research │────▶│ self_improver │────▶│evolution_engine│
│  (arXiv)    │     │  (planner)   │     │  (code gen)   │
└─────────────┘     └──────┬───────┘     └───────────────┘
                           │ feedback
                    ┌──────▼───────┐
                    │ autonomous_ml │
                    │  (RL learner) │
                    └──────────────┘
```

1. **Research** (`ml_research.fetch_arxiv_papers`) — pulls recent papers relevant to the current focus area.
2. **Analyze** (`self_improver.analyze_system`) — runs `evolution_engine.reflect_on_code` and `autonomous_ml.analyze_performance` to establish a baseline.
3. **Plan** (`self_improver.create_improvement_plan`) — scores candidate improvements by `impact / (effort + 1)` and selects the top 3.
4. **Implement** (`self_improver.execute_phase`) — delegates to `evolution_engine.create_plugin` or `evolution_engine.apply_refactors`.
5. **Validate** (`self_improver.validate_improvements`) — re-runs performance metrics and compares.
6. **Learn** — results are logged back to `autonomous_ml` as interactions so future planning improves.

#### Additional maintenance actions

| Action | What it does |
|--------|-------------|
| `find_dry_violations` | AST-based scan for duplicate function bodies and identical class method signatures across all plugin files. |
| `find_performance_bottlenecks` | Regex + AST scan for sync I/O in async functions, blocking HTTP calls, large list comprehensions, and unguarded `execute()` awaits. |
| `consolidate_memory` | Jaccard-similarity deduplication of `interaction_log.json` and `tasks.json` (threshold 0.85). |
| `categorize_knowledge` | Tag standardisation (lowercase, underscore-normalised, synonym-group merging) across all `memory/knowledge*.json` files. |

---

## Usage Examples

```
# Hyperparameter optimisation
"Run a grid search to find the best temperature settings"
  → autonomous_ml.grid_search

"Use Bayesian optimisation to tune Nexus parameters"
  → autonomous_ml.bayesian_optimize

"What are the best hyperparameters found so far?"
  → autonomous_ml.get_optimization_results

# Explainability
"Why does Nexus perform better on some queries than others?"
  → explainability.analyze_decision_factors

"Explain why this query might succeed: 'create a Python script to sort files'"
  → explainability.lime_explain {"query": "create a Python script to sort files"}

"Are there any systematic biases in how Nexus responds?"
  → explainability.find_biases

"Give me a full explainability report"
  → explainability.get_explainability_report

# Data augmentation
"Augment this text with synonym swaps and random deletion"
  → data_augmentation.augment_text {"text": "...", "techniques": ["synonym_swap", "random_deletion"]}

"Generate 10 synthetic Q&A pairs about reinforcement learning"
  → data_augmentation.generate_synthetic_qa {"topic": "reinforcement learning", "count": 10}

# ML Research
"Fetch recent papers on transformer efficiency"
  → ml_research.fetch_arxiv_papers {"query": "transformer efficiency attention", "max_results": 5}

"Search for NeurIPS papers on meta-learning"
  → ml_research.search_conference_papers {"conference": "NeurIPS", "topic": "meta-learning"}

# Self-improvement
"Find duplicate code across plugins"
  → self_improver.find_dry_violations

"Check for performance bottlenecks"
  → self_improver.find_performance_bottlenecks

"Clean up duplicate memory entries"
  → self_improver.consolidate_memory

"Standardise knowledge base tags"
  → self_improver.categorize_knowledge

"Run the full autonomous improvement cycle"
  → self_improver.auto_improve {"focus_area": "ml_accuracy"}
```

---

## Research Connections

| Algorithm | arXiv category | Key papers |
|-----------|---------------|------------|
| Q-Learning | cs.LG, cs.AI | Watkins & Dayan 1992 (foundational); Mnih et al. 2015 (DQN) |
| Bayesian Optimisation | cs.LG, stat.ML | Snoek et al. 2012 (Practical BO); Frazier 2018 (tutorial) |
| SHAP | cs.LG, stat.ML | Lundberg & Lee 2017 (NeurIPS) |
| LIME | cs.LG | Ribeiro et al. 2016 (KDD) |
| Text Augmentation | cs.CL | Wei & Zou 2019 "EDA" (EMNLP); Sennrich et al. 2016 (back-translation) |
| Synthetic QA | cs.CL, cs.AI | Goodfellow et al. 2014 (GAN); Brown et al. 2020 (GPT-3 few-shot) |

Use `ml_research.search_conference_papers` with `conference="NeurIPS"` or `"ICML"` and any of the topic names above to pull live papers from arXiv.

---

## Performance Metrics

| Metric | Source | Interpretation |
|--------|--------|----------------|
| `average_q_value` | `autonomous_ml.analyze_performance` | Higher (closer to 1.0) = learned policy is making better decisions. |
| `total_learned_actions` | `autonomous_ml.analyze_performance` | More entries = richer exploration of the state-action space. |
| `adaptation_rules` | `autonomous_ml.analyze_performance` | Rules with `confidence > 0.6` are reliable; below 0.5 need more data. |
| `best_score` (grid/bayes) | `autonomous_ml.get_optimization_results` | Score in [0, 1]; above 0.7 is a well-tuned configuration. |
| `predicted_success_score` | `explainability.lime_explain` | Estimate of how likely the LLM is to answer a query well. |
| DRY violations | `self_improver.find_dry_violations` | Zero duplicates is the target; each violation is a refactor candidate. |
| Bottleneck findings | `self_improver.find_performance_bottlenecks` | Any `sync_io_in_async` or `blocking_http_in_async` finding should be addressed to prevent UI freezes. |
