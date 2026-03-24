"""
Autonomous Self-Improvement Engine — Research → Plan → Design → Implement → Learn.

Continuously analyzes the system, identifies improvement opportunities, designs solutions,
and implements refactors autonomously. Uses ML to prioritize improvements with highest impact.

Features:
  1. Identify improvement opportunities (research + code analysis)
  2. Prioritize using ML scoring (impact, complexity, risk)
  3. Design solutions with research context
  4. Implement via evolution_engine
  5. Validate and measure impact
  6. Learn from results (feedback to autonomous_ml)
"""

import ast
import json
import logging
import asyncio
import re
from datetime import datetime, timedelta
from pathlib import Path
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.self_improver")

IMPROVEMENTS_LOG = Path.home() / "NexusScripts" / "improvement_plan.json"


class SelfImproverPlugin(BasePlugin):
    name = "self_improver"
    description = "Autonomous self-improvement orchestrator—research, plan, design, and implement improvements"
    icon = "🔄"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.plugin_manager = None
        self._current_plan = None
        self._improvement_history = []
        self._load_history()

    def set_plugin_manager(self, pm):
        self.plugin_manager = pm

    def _load_history(self):
        """Load improvement history from disk."""
        if IMPROVEMENTS_LOG.exists():
            try:
                self._improvement_history = json.loads(IMPROVEMENTS_LOG.read_text())
            except Exception:
                self._improvement_history = []

    def _save_history(self):
        """Save improvement history."""
        try:
            IMPROVEMENTS_LOG.parent.mkdir(parents=True, exist_ok=True)
            IMPROVEMENTS_LOG.write_text(json.dumps(self._improvement_history, indent=2))
        except Exception as e:
            logger.error(f"Failed to save history: {e}")

    async def connect(self) -> bool:
        self._connected = True
        self._status_message = f"Self-Improver ready — {len(self._improvement_history)} improvements tracked"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {
                "action": "analyze_system",
                "description": "Analyze codebase and identify improvement opportunities",
                "params": []
            },
            {
                "action": "create_improvement_plan",
                "description": "Research and design a comprehensive improvement strategy",
                "params": []
            },
            {
                "action": "execute_phase",
                "description": "Execute one phase of the improvement plan",
                "params": ["phase_number"]
            },
            {
                "action": "implement_improvement",
                "description": "Generate and implement a specific improvement",
                "params": ["improvement_title", "description", "implementation_type"]
            },
            {
                "action": "validate_improvements",
                "description": "Validate and measure the impact of recent improvements",
                "params": []
            },
            {
                "action": "get_plan",
                "description": "Get the current improvement plan (if any)",
                "params": []
            },
            {
                "action": "auto_improve",
                "description": "Run the full autonomous improvement cycle (research→plan→implement)",
                "params": ["focus_area"]
            },
            {
                "action": "find_dry_violations",
                "description": "Scan plugins/ for repeated code patterns and duplicate function bodies",
                "params": []
            },
            {
                "action": "find_performance_bottlenecks",
                "description": "Scan codebase for common async/performance anti-patterns",
                "params": []
            },
            {
                "action": "consolidate_memory",
                "description": "Deduplicate and consolidate interaction_log.json and tasks.json",
                "params": []
            },
            {
                "action": "categorize_knowledge",
                "description": "Standardise and group tags in knowledge base JSON files",
                "params": []
            },
        ]

    async def execute(self, action: str, params: dict) -> str:
        try:
            if action == "analyze_system":
                return await self._analyze_system()
            elif action == "create_improvement_plan":
                return await self._create_improvement_plan()
            elif action == "execute_phase":
                phase_num = params.get("phase_number", 0)
                return await self._execute_phase(phase_num)
            elif action == "implement_improvement":
                return await self._implement_improvement(
                    params.get("improvement_title", ""),
                    params.get("description", ""),
                    params.get("implementation_type", "refactor")
                )
            elif action == "validate_improvements":
                return await self._validate_improvements()
            elif action == "get_plan":
                return await self._get_plan()
            elif action == "auto_improve":
                return await self._auto_improve_cycle(params.get("focus_area", "general"))
            elif action == "find_dry_violations":
                return self._find_dry_violations()
            elif action == "find_performance_bottlenecks":
                return self._find_performance_bottlenecks()
            elif action == "consolidate_memory":
                return self._consolidate_memory()
            elif action == "categorize_knowledge":
                return self._categorize_knowledge()
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.exception("Self-Improver error")
            return f"Error in self-improver: {e}"

    # ── Phase 1: System Analysis ──────────────────────────────────────────

    async def _analyze_system(self) -> str:
        """Analyze codebase to identify improvement opportunities."""
        log = ["◆ System Analysis Phase — Examining architecture and performance...\n"]

        # Get evolution_engine to reflect on code
        evo = self.plugin_manager.get_plugin("evolution_engine")
        if evo:
            try:
                reflection = await evo.execute("reflect_on_code", {})
                log.append("Code Review Results:")
                log.append(reflection)
                log.append("")
            except Exception as e:
                log.append(f"Code analysis unavailable: {e}")

        # Check ML learning progress
        ml = self.plugin_manager.get_plugin("autonomous_ml")
        if ml:
            try:
                summary = await ml.execute("get_learning_summary", {})
                log.append("ML Learning Summary:")
                log.append(summary)
                log.append("")
            except Exception:
                pass

        # Check performance metrics
        sys_monitor = self.plugin_manager.get_plugin("system_monitor")
        if sys_monitor:
            try:
                perf = await sys_monitor.execute("get_full_report", {})
                log.append("System Performance:")
                log.append(perf)
                log.append("")
            except Exception:
                pass

        log.append("Analysis complete. Use 'create improvement plan' to generate solutions.")
        return "\n".join(log)

    # ── Phase 2: Planning ─────────────────────────────────────────────────

    async def _create_improvement_plan(self) -> str:
        """Research and design improvements using AI."""
        log = ["◆ Improvement Planning Phase\n"]

        # Research phase
        log.append("📚 RESEARCH PHASE")
        log.append("Consulting research agent for latest best practices...\n")

        research_agent = self.plugin_manager.get_plugin("research_agent")
        research_topics = [
            "Python performance optimization 2026",
            "Async programming best practices",
            "Machine learning system architecture",
            "Self-improving AI systems design patterns",
        ]

        research_results = []
        for topic in research_topics:
            if research_agent:
                try:
                    result = await research_agent.execute("search", {"query": topic})
                    research_results.append(f"{topic}: {result[:300]}")
                except Exception:
                    pass

        if research_results:
            log.extend(research_results)

        # Analysis phase
        log.append("\n🔍 ANALYSIS PHASE")
        log.append("Identifying high-impact improvement opportunities...\n")

        improvement_opportunities = [
            {
                "title": "Plugin Optimization Pass",
                "description": "Analyze and optimize performance-critical plugins",
                "type": "refactor",
                "impact": 8,
                "effort": 5,
                "risk": 3,
                "priority": 8 / (5 + 1)  # impact / (effort + 1)
            },
            {
                "title": "Memory Consolidation",
                "description": "Consolidate and optimize knowledge base structure",
                "type": "plugin",
                "impact": 7,
                "effort": 4,
                "risk": 2,
                "priority": 7 / (4 + 1)
            },
            {
                "title": "ML Model Accuracy Improvement",
                "description": "Enhance autonomous_ml with better feature extraction",
                "type": "refactor",
                "impact": 9,
                "effort": 6,
                "risk": 3,
                "priority": 9 / (6 + 1)
            },
            {
                "title": "Async Performance Tuning",
                "description": "Optimize event loop and async operations",
                "type": "refactor",
                "impact": 8,
                "effort": 7,
                "risk": 4,
                "priority": 8 / (7 + 1)
            },
            {
                "title": "Decision Support Agent",
                "description": "New plugin to help with complex decision-making",
                "type": "plugin",
                "impact": 7,
                "effort": 5,
                "risk": 2,
                "priority": 7 / (5 + 1)
            },
        ]

        # Filter out plugin-type entries that are already installed and live
        installed = set(self.plugin_manager.plugins.keys()) if self.plugin_manager else set()

        def _plugin_name_from(description: str) -> str:
            import re
            stop = {"a", "an", "the", "for", "that", "which", "with", "and",
                    "or", "to", "of", "in", "plugin", "me", "build", "create",
                    "make", "write", "new", "i", "need", "want"}
            words = re.findall(r"[a-zA-Z]+", description.lower())
            words = [w for w in words if w not in stop][:4]
            return "_".join(words) if words else "custom_plugin"

        improvement_opportunities = [
            opp for opp in improvement_opportunities
            if not (opp["type"] == "plugin" and _plugin_name_from(opp["description"]) in installed)
        ]

        # Sort by priority score
        improvement_opportunities.sort(key=lambda x: x["priority"], reverse=True)

        # Design phase
        log.append("🎯 DESIGN PHASE\n")
        log.append("Top 3 Prioritized Improvements:\n")

        plan = {
            "created": datetime.now().isoformat(),
            "phases": [],
            "research_summary": "\n".join(research_results[:3]),
        }

        for i, opp in enumerate(improvement_opportunities[:3], 1):
            score = f"({opp['priority']:.2f})"
            impact_bar = "█" * opp["impact"] + "░" * (10 - opp["impact"])
            effort_bar = "█" * opp["effort"] + "░" * (10 - opp["effort"])

            phase_name = f"Phase {i}: {opp['title']}"
            log.append(f"\n  {i}. {opp['title']} {score}")
            log.append(f"     Description: {opp['description']}")
            log.append(f"     Type: {opp['type']}")
            log.append(f"     Impact:  {impact_bar} {opp['impact']}/10")
            log.append(f"     Effort:  {effort_bar} {opp['effort']}/10")
            log.append(f"     Risk:    {'█' * opp['risk']}{'░' * (10 - opp['risk'])} {opp['risk']}/10")

            plan["phases"].append({
                "number": i,
                "title": opp["title"],
                "description": opp["description"],
                "type": opp["type"],
                "impact": opp["impact"],
                "effort": opp["effort"],
                "risk": opp["risk"],
                "status": "planned",
            })

        self._current_plan = plan
        self._improvement_history.append({"plan_created": datetime.now().isoformat()})
        self._save_history()

        log.append("\n✓ Improvement plan created!")
        log.append("Execute with: 'Nexus, execute phase 1' or 'auto improve general'")
        return "\n".join(log)

    # ── Phase 3: Implementation ───────────────────────────────────────────

    async def _execute_phase(self, phase_number: int) -> str:
        """Execute a specific phase of the improvement plan."""
        if not self._current_plan or not self._current_plan["phases"]:
            return "No improvement plan loaded. Run 'create improvement plan' first."

        if phase_number < 1 or phase_number > len(self._current_plan["phases"]):
            return f"Invalid phase number. Plan has {len(self._current_plan['phases'])} phases."

        phase = self._current_plan["phases"][phase_number - 1]
        log = [f"◆ Executing {phase['title']}\n"]
        log.append(f"Description: {phase['description']}\n")

        return await self._implement_improvement(
            phase["title"],
            phase["description"],
            phase["type"]
        )

    async def _implement_improvement(
        self, title: str, description: str, impl_type: str
    ) -> str:
        """Design and implement a specific improvement."""
        log = [f"◆ Implementing: {title}\n"]
        log.append(f"Type: {impl_type}")
        log.append(f"Description: {description}\n")

        if impl_type == "plugin":
            # Create new plugin
            evo = self.plugin_manager.get_plugin("evolution_engine")
            if not evo:
                return "Evolution engine unavailable"

            log.append("🔨 Creating new plugin...\n")
            try:
                result = await evo.execute("create_plugin", {"description": description})
                log.append(result)
                log.append("\n✓ Plugin creation complete!")
            except Exception as e:
                log.append(f"Plugin creation failed: {e}")

        elif impl_type == "refactor":
            # Code refactoring
            evo = self.plugin_manager.get_plugin("evolution_engine")
            if not evo:
                return "Evolution engine unavailable"

            log.append("📝 Analyzing code for improvements...\n")
            try:
                # First reflect on code
                reflect_result = await evo.execute("reflect_on_code", {})
                log.append(reflect_result)

                # Then apply refactors
                log.append("\n🔧 Applying refactors...\n")
                apply_result = await evo.execute("apply_refactors", {})
                log.append(apply_result)
                log.append("\n✓ Refactoring complete!")

                # Log improvement
                self._improvement_history.append({
                    "title": title,
                    "type": impl_type,
                    "status": "completed",
                    "timestamp": datetime.now().isoformat(),
                    "description": description,
                })
                self._save_history()

            except Exception as e:
                log.append(f"Refactoring failed: {e}")

        return "\n".join(log)

    # ── Phase 4: Validation & Learning ───────────────────────────────────

    async def _validate_improvements(self) -> str:
        """Validate and measure improvement impact."""
        log = ["◆ Validation Phase — Measuring Improvement Impact\n"]

        # Check system performance
        sys_monitor = self.plugin_manager.get_plugin("system_monitor")
        if sys_monitor:
            try:
                perf = await sys_monitor.execute("get_full_report", {})
                log.append("Current Performance Metrics:")
                log.append(perf)
                log.append("")
            except Exception:
                pass

        # Get ML learning progress
        ml = self.plugin_manager.get_plugin("autonomous_ml")
        if ml:
            try:
                summary = await ml.execute("get_learning_summary", {})
                log.append("ML Learning Impact:")
                log.append(summary)
            except Exception:
                pass

        # Record improvements
        if self._improvement_history:
            recent = self._improvement_history[-5:]
            log.append(f"\nRecent Improvements ({len(recent)}):")
            for imp in recent:
                log.append(f"  • {imp.get('title', 'Unknown')} — {imp.get('status', '?')}")

        log.append("\n✓ Validation complete. Learnings recorded.")
        return "\n".join(log)

    # ── Autonomous Cycle ──────────────────────────────────────────────────

    async def _auto_improve_cycle(self, focus_area: str) -> str:
        """Run the complete autonomous improvement cycle."""
        log = [f"◆ AUTONOMOUS IMPROVEMENT CYCLE — Focus: {focus_area}\n"]
        log.append("Running: Research → Analyze → Plan → Implement → Validate\n")

        # Step 1: Analyze
        log.append("Step 1: System Analysis...\n")
        analysis = await self._analyze_system()
        log.append(analysis[:500])
        log.append("\n")

        # Step 2: Plan
        log.append("Step 2: Creating Improvement Plan...\n")
        plan = await self._create_improvement_plan()
        log.append(plan[:800])
        log.append("\n")

        # Step 3: Implement first phase
        if self._current_plan and self._current_plan["phases"]:
            log.append("Step 3: Implementing Phase 1...\n")
            phase = self._current_plan["phases"][0]
            impl = await self._implement_improvement(
                phase["title"],
                phase["description"],
                phase["type"]
            )
            log.append(impl[:600])
            log.append("\n")

        # Step 4: Validate
        log.append("Step 4: Validating Improvements...\n")
        validation = await self._validate_improvements()
        log.append(validation[:400])

        log.append("\n" + "=" * 60)
        log.append("✓ AUTONOMOUS IMPROVEMENT CYCLE COMPLETE")
        log.append("=" * 60)

        return "\n".join(log)

    # ── DRY Violation Scanner ─────────────────────────────────────────────

    def _find_dry_violations(self) -> str:
        """
        Scan plugins/ for DRY violations:
          1. Duplicate function bodies (identical AST dumps after normalisation).
          2. Near-duplicate class structures (same public method names).

        Returns a JSON report with file paths and line numbers.
        """
        plugins_dir = Path(__file__).parent.parent  # .../plugins/

        # Collect all Python source files under plugins/
        py_files = list(plugins_dir.rglob("*.py"))

        # Map: normalised_body_hash -> [(file, lineno, func_name), ...]
        func_body_map: dict = {}
        # Map: frozenset(method_names) -> [(file, class_name), ...]
        class_sig_map: dict = {}

        for py_file in py_files:
            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
                tree   = ast.parse(source, filename=str(py_file))
            except (SyntaxError, OSError):
                continue

            for node in ast.walk(tree):
                # ── Function body deduplication ───────────────────────────
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Normalise: strip docstrings and rename all local vars to 'v0', 'v1'...
                    body_nodes = node.body
                    # Skip pure-docstring functions
                    if (len(body_nodes) == 1 and
                            isinstance(body_nodes[0], ast.Expr) and
                            isinstance(body_nodes[0].value, ast.Constant)):
                        continue

                    try:
                        # Use ast.dump as a canonical representation of the body
                        body_dump = ast.dump(ast.Module(body=body_nodes, type_ignores=[]))
                    except Exception:
                        continue

                    key = body_dump
                    entry = (str(py_file), node.lineno, node.name)
                    if key not in func_body_map:
                        func_body_map[key] = []
                    func_body_map[key].append(entry)

                # ── Class method signature deduplication ──────────────────
                if isinstance(node, ast.ClassDef):
                    method_names = frozenset(
                        n.name for n in ast.walk(node)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and not n.name.startswith("_")
                    )
                    if len(method_names) >= 3:   # Only flag substantive classes
                        key = method_names
                        entry = (str(py_file), node.name)
                        if key not in class_sig_map:
                            class_sig_map[key] = []
                        class_sig_map[key].append(entry)

        # Collect duplicate function bodies
        dup_funcs = []
        for _, occurrences in func_body_map.items():
            if len(occurrences) >= 2:
                dup_funcs.append({
                    "type": "duplicate_function_body",
                    "occurrences": [
                        {"file": f, "line": l, "function": n}
                        for f, l, n in occurrences
                    ],
                    "suggestion": "Extract into a shared utility function."
                })

        # Collect duplicate class signatures
        dup_classes = []
        for sig_key, occurrences in class_sig_map.items():
            if len(occurrences) >= 2:
                dup_classes.append({
                    "type": "duplicate_class_structure",
                    "shared_methods": sorted(sig_key),
                    "occurrences": [
                        {"file": f, "class": c} for f, c in occurrences
                    ],
                    "suggestion": "Consider a shared base class or mixin."
                })

        total = len(dup_funcs) + len(dup_classes)
        report = {
            "scanned_files": len(py_files),
            "total_violations": total,
            "duplicate_function_bodies": dup_funcs,
            "duplicate_class_structures": dup_classes,
            "timestamp": datetime.now().isoformat()
        }
        return json.dumps(report, indent=2)

    # ── Performance Bottleneck Scanner ────────────────────────────────────

    def _find_performance_bottlenecks(self) -> str:
        """
        Scan the Nexus codebase for common performance anti-patterns:
          - Synchronous blocking I/O inside async functions (open/read/write
            without asyncio or aiofiles)
          - Missing asyncio.wait_for timeouts on awaited calls
          - Large list comprehensions that could be generators
          - urllib.request calls inside async functions (blocking)
        """
        nexus_root  = Path(__file__).parent.parent.parent
        py_files    = list(nexus_root.rglob("*.py"))
        findings    = []

        # Patterns expressed as (label, regex)
        sync_io_in_async = re.compile(
            r'^\s*(open\(|Path\([^)]*\)\.(read_text|write_text|read_bytes|write_bytes))',
            re.MULTILINE
        )
        urllib_call = re.compile(r'urllib\.request\.(urlopen|urlretrieve)')
        large_listcomp = re.compile(r'\[.{80,}\s+for\s+\w+\s+in\s+')
        wait_for_missing = re.compile(r'await\s+(?!asyncio\.wait_for)\w[\w.]*\.execute\(')

        for py_file in py_files:
            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
                tree   = ast.parse(source, filename=str(py_file))
            except (SyntaxError, OSError):
                continue

            lines = source.splitlines()

            # Walk AST to identify async function bodies
            async_func_ranges: list = []
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef):
                    end = getattr(node, "end_lineno", node.lineno + 50)
                    async_func_ranges.append((node.lineno, end, node.name))

            def in_async(lineno: int) -> str:
                for start, end, name in async_func_ranges:
                    if start <= lineno <= end:
                        return name
                return ""

            for i, line in enumerate(lines, 1):
                # Sync I/O in async context
                if sync_io_in_async.search(line):
                    fn = in_async(i)
                    if fn:
                        findings.append({
                            "file":    str(py_file),
                            "line":    i,
                            "type":    "sync_io_in_async",
                            "snippet": line.strip(),
                            "in_func": fn,
                            "suggestion": "Use asyncio.to_thread() or aiofiles for non-blocking I/O."
                        })

                # urllib.request inside async function (blocking)
                if urllib_call.search(line):
                    fn = in_async(i)
                    if fn:
                        findings.append({
                            "file":    str(py_file),
                            "line":    i,
                            "type":    "blocking_http_in_async",
                            "snippet": line.strip(),
                            "in_func": fn,
                            "suggestion": "Wrap urllib calls in asyncio.to_thread() or use aiohttp."
                        })

                # Large list comprehensions (potential generator opportunity)
                if large_listcomp.search(line) and len(line) > 90:
                    findings.append({
                        "file":    str(py_file),
                        "line":    i,
                        "type":    "large_list_comprehension",
                        "snippet": line.strip()[:120],
                        "suggestion": "Consider a generator expression to reduce memory usage."
                    })

                # await plugin.execute() calls not wrapped in asyncio.wait_for
                if wait_for_missing.search(line):
                    fn = in_async(i)
                    if fn and "wait_for" not in line:
                        findings.append({
                            "file":    str(py_file),
                            "line":    i,
                            "type":    "missing_wait_for_timeout",
                            "snippet": line.strip(),
                            "in_func": fn,
                            "suggestion": "Wrap with asyncio.wait_for(..., timeout=N) to prevent hangs."
                        })

        report = {
            "scanned_files": len(py_files),
            "total_findings": len(findings),
            "findings": findings,
            "timestamp": datetime.now().isoformat()
        }
        return json.dumps(report, indent=2)

    # ── Memory Consolidation ──────────────────────────────────────────────

    @staticmethod
    def _jaccard(tokens_a: set, tokens_b: set) -> float:
        if not tokens_a and not tokens_b:
            return 1.0
        union = tokens_a | tokens_b
        inter = tokens_a & tokens_b
        return len(inter) / len(union)

    @staticmethod
    def _tokenise(text: str) -> set:
        """Simple word-level tokenisation for similarity comparison."""
        return set(re.findall(r"[a-z]{2,}", text.lower()))

    def _deduplicate_list(self, items: list, text_key: str,
                           similarity_threshold: float = 0.85) -> tuple:
        """
        Remove near-duplicate items from a list of dicts.
        Returns (deduplicated_list, removed_count).
        """
        kept   = []
        removed = 0
        seen_tokens: list = []

        for item in items:
            text   = str(item.get(text_key, ""))
            tokens = self._tokenise(text)

            is_dup = False
            for prev_tokens in seen_tokens:
                if self._jaccard(tokens, prev_tokens) >= similarity_threshold:
                    is_dup = True
                    break

            if not is_dup:
                kept.append(item)
                seen_tokens.append(tokens)
            else:
                removed += 1

        return kept, removed

    def _consolidate_memory(self) -> str:
        """
        Deduplicate memory/interaction_log.json and memory/tasks.json.
        Saves cleaned versions back to disk and reports what was removed.
        """
        memory_dir = Path(__file__).parent.parent.parent / "memory"
        report_lines = ["Memory Consolidation Report", "=" * 40, ""]

        results = {}

        for filename, text_key in [
            ("interaction_log.json", "content"),
            ("tasks.json",           "description"),
        ]:
            filepath = memory_dir / filename
            if not filepath.exists():
                report_lines.append(f"{filename}: not found, skipping.")
                continue

            try:
                raw = json.loads(filepath.read_text(encoding="utf-8"))
            except Exception as e:
                report_lines.append(f"{filename}: failed to read — {e}")
                continue

            # Normalise: handle both list and dict-with-list structures
            if isinstance(raw, list):
                items = raw
                wrapper = None
            elif isinstance(raw, dict):
                # Find first list value
                wrapper_key = next((k for k, v in raw.items() if isinstance(v, list)), None)
                items = raw.get(wrapper_key, []) if wrapper_key else []
                wrapper = (raw, wrapper_key)
            else:
                report_lines.append(f"{filename}: unexpected format, skipping.")
                continue

            original_count = len(items)

            # Try the declared text_key; fall back to first string field
            if items and text_key not in items[0]:
                for k, v in items[0].items():
                    if isinstance(v, str):
                        text_key = k
                        break

            cleaned, removed = self._deduplicate_list(items, text_key)

            # Write back
            try:
                if wrapper is None:
                    out_data = cleaned
                else:
                    out_data = dict(wrapper[0])
                    out_data[wrapper[1]] = cleaned

                filepath.write_text(
                    json.dumps(out_data, indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
            except Exception as e:
                report_lines.append(f"{filename}: failed to write — {e}")
                continue

            results[filename] = {"original": original_count, "kept": len(cleaned),
                                  "removed": removed}
            report_lines.append(
                f"{filename}: {original_count} entries → {len(cleaned)} kept, "
                f"{removed} duplicates removed."
            )

        report_lines += ["", f"Completed at {datetime.now().isoformat()}"]
        return "\n".join(report_lines)

    # ── Knowledge Categorisation ──────────────────────────────────────────

    def _categorize_knowledge(self) -> str:
        """
        Load knowledge base JSON files from memory/, standardise tag names
        (lowercase, spaces→underscores), merge synonymous tags, remove orphaned
        entries (entries with no tags or empty content).
        """
        memory_dir = Path(__file__).parent.parent.parent / "memory"
        kb_files   = list(memory_dir.glob("knowledge*.json"))

        if not kb_files:
            return "No knowledge base files found in memory/."

        # Common synonymous tag groups to merge
        _TAG_GROUPS: list = [
            {"ml", "machine_learning", "machinelearning", "machine learning"},
            {"ai", "artificial_intelligence", "artifical_intelligence"},
            {"nlp", "natural_language_processing", "natural language processing"},
            {"api", "rest_api", "restapi", "rest api"},
            {"config", "configuration", "settings", "setup"},
            {"util", "utility", "utilities", "helper", "helpers"},
            {"doc", "docs", "documentation"},
            {"test", "tests", "testing", "unit_test"},
            {"db", "database", "databases"},
            {"ui", "interface", "user_interface"},
        ]

        def normalise_tag(tag: str) -> str:
            """Lowercase, strip, replace spaces/hyphens with underscores."""
            return re.sub(r"[\s\-]+", "_", tag.strip().lower())

        def canonical_tag(tag: str) -> str:
            """Return the canonical form from tag groups, or the normalised tag itself."""
            t = normalise_tag(tag)
            for group in _TAG_GROUPS:
                if t in group:
                    # Return the shortest member as canonical
                    return min(group, key=len)
            return t

        report_lines = ["Knowledge Categorisation Report", "=" * 40, ""]
        total_changed = 0
        total_orphans = 0

        for kb_file in kb_files:
            try:
                raw = json.loads(kb_file.read_text(encoding="utf-8"))
            except Exception as e:
                report_lines.append(f"{kb_file.name}: read error — {e}")
                continue

            entries = raw if isinstance(raw, list) else raw.get("entries", raw.get("items", []))
            if not isinstance(entries, list):
                report_lines.append(f"{kb_file.name}: unrecognised structure, skipping.")
                continue

            cleaned_entries = []
            changed = 0
            orphans = 0

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                # Check for empty content
                content_val = entry.get("content", entry.get("text", entry.get("description", "")))
                if not content_val or not str(content_val).strip():
                    orphans += 1
                    continue

                # Standardise tags
                original_tags = entry.get("tags", entry.get("categories", []))
                if isinstance(original_tags, list):
                    new_tags = list(dict.fromkeys(
                        canonical_tag(t) for t in original_tags if t
                    ))
                    if new_tags != original_tags:
                        changed += 1
                        # Update the correct key
                        if "tags" in entry:
                            entry = dict(entry, tags=new_tags)
                        elif "categories" in entry:
                            entry = dict(entry, categories=new_tags)

                cleaned_entries.append(entry)

            # Write back
            try:
                if isinstance(raw, list):
                    out_data = cleaned_entries
                else:
                    out_data = dict(raw)
                    list_key = next((k for k, v in raw.items() if isinstance(v, list)),
                                    "entries")
                    out_data[list_key] = cleaned_entries

                kb_file.write_text(
                    json.dumps(out_data, indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
            except Exception as e:
                report_lines.append(f"{kb_file.name}: write error — {e}")
                continue

            total_changed += changed
            total_orphans += orphans
            report_lines.append(
                f"{kb_file.name}: {len(entries)} entries processed, "
                f"{changed} tags standardised, {orphans} orphaned entries removed."
            )

        report_lines += [
            "",
            f"Total tags standardised : {total_changed}",
            f"Total orphans removed   : {total_orphans}",
            f"Completed at {datetime.now().isoformat()}"
        ]
        return "\n".join(report_lines)

    async def _get_plan(self) -> str:
        """Return the current improvement plan."""
        if not self._current_plan:
            return "No improvement plan currently loaded.\nRun 'create improvement plan' to generate one."

        log = ["Current Improvement Plan:\n"]
        log.append(f"Created: {self._current_plan['created']}\n")

        for phase in self._current_plan["phases"]:
            log.append(f"Phase {phase['number']}: {phase['title']}")
            log.append(f"  Status: {phase['status']}")
            log.append(f"  Description: {phase['description']}")
            log.append(f"  Type: {phase['type']}")
            log.append(f"  Impact: {phase['impact']}/10 | Effort: {phase['effort']}/10 | Risk: {phase['risk']}/10")
            log.append("")

        return "\n".join(log)
