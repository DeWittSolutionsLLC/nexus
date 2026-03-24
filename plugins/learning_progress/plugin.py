"""
Learning Progress Plugin — Track AI/ML improvements and self-enhancement metrics.

Monitors progress on:
- Model performance improvements
- Code quality and refactoring
- Knowledge base optimization
- Research and learning activities
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.learning_progress")

PROGRESS_FILE = Path.home() / "NexusScripts" / "learning_progress.json"


def _load_progress() -> dict:
    """Load learning progress data."""
    if not PROGRESS_FILE.exists():
        return _init_progress()
    try:
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to load progress: {e}")
        return _init_progress()


def _init_progress() -> dict:
    """Initialize empty progress structure."""
    return {
        "created": datetime.now().isoformat(),
        "model_performance": [],
        "code_quality": [],
        "knowledge_improvements": [],
        "research_activities": [],
        "refactoring_history": [],
        "memory_consolidations": [],
        "milestones": []
    }


def _save_progress(data: dict):
    """Save learning progress data."""
    try:
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROGRESS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to save progress: {e}")


class LearningProgressPlugin(BasePlugin):
    name = "learning_progress"
    description = "Track AI/ML improvements, model performance, code quality, and knowledge base optimization"
    icon = "📈"

    async def connect(self) -> bool:
        """Connect and initialize progress tracking."""
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not PROGRESS_FILE.exists():
            _save_progress(_init_progress())
        self._connected = True
        self._status_message = "Learning progress tracking active"
        return True

    async def execute(self, action: str, params: dict) -> str:
        """Execute learning progress commands."""
        try:
            if action == "log_model_improvement":
                return self._log_model_improvement(params)
            elif action == "log_code_improvement":
                return self._log_code_improvement(params)
            elif action == "log_research":
                return self._log_research(params)
            elif action == "log_memory_consolidation":
                return self._log_memory_consolidation(params)
            elif action == "log_refactoring":
                return self._log_refactoring(params)
            elif action == "add_milestone":
                return self._add_milestone(params)
            elif action == "get_summary":
                return self._get_summary(params)
            elif action == "get_weekly_report":
                return self._get_weekly_report()
            elif action == "get_monthly_report":
                return self._get_monthly_report()
            elif action == "get_all_milestones":
                return self._get_all_milestones()
            elif action == "get_improvement_areas":
                return self._get_improvement_areas()
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as e:
            logger.error(f"Action {action} failed: {e}")
            return json.dumps({"error": str(e)})

    def _log_model_improvement(self, params: dict) -> str:
        """Log model performance improvement."""
        progress = _load_progress()
        
        improvement = {
            "timestamp": datetime.now().isoformat(),
            "model": params.get("model", "unknown"),
            "metric": params.get("metric", "accuracy"),
            "before": float(params.get("before", 0)),
            "after": float(params.get("after", 0)),
            "improvement_pct": float(params.get("after", 0)) - float(params.get("before", 0)),
            "technique": params.get("technique", ""),
            "description": params.get("description", "")
        }
        
        progress["model_performance"].append(improvement)
        _save_progress(progress)
        
        return json.dumps({
            "status": "logged",
            "improvement_pct": improvement["improvement_pct"],
            "message": f"Logged {improvement['improvement_pct']:.2f}% improvement on {improvement['model']} {improvement['metric']}"
        })

    def _log_code_improvement(self, params: dict) -> str:
        """Log code quality or performance improvement."""
        progress = _load_progress()
        
        improvement = {
            "timestamp": datetime.now().isoformat(),
            "area": params.get("area", "general"),
            "type": params.get("type", "refactoring"),  # refactoring, optimization, bugfix
            "before_metric": float(params.get("before_metric", 0)),
            "after_metric": float(params.get("after_metric", 0)),
            "improvement": float(params.get("after_metric", 0)) - float(params.get("before_metric", 0)),
            "metric_name": params.get("metric_name", "performance"),
            "description": params.get("description", "")
        }
        
        progress["code_quality"].append(improvement)
        _save_progress(progress)
        
        return json.dumps({
            "status": "logged",
            "improvement": improvement["improvement"],
            "message": f"Logged code improvement: {improvement['description']}"
        })

    def _log_research(self, params: dict) -> str:
        """Log research activity."""
        progress = _load_progress()
        
        research = {
            "timestamp": datetime.now().isoformat(),
            "topic": params.get("topic", ""),
            "type": params.get("type", "paper"),  # paper, conference, resource, experiment
            "key_findings": params.get("key_findings", []),
            "relevance": params.get("relevance", "medium"),  # low, medium, high
            "application": params.get("application", ""),
            "source": params.get("source", "")
        }
        
        progress["research_activities"].append(research)
        _save_progress(progress)
        
        return json.dumps({
            "status": "logged",
            "message": f"Logged research on {research['topic']} from {research['source']}"
        })

    def _log_memory_consolidation(self, params: dict) -> str:
        """Log memory optimization activity."""
        progress = _load_progress()
        
        consolidation = {
            "timestamp": datetime.now().isoformat(),
            "duplicates_removed": int(params.get("duplicates_removed", 0)),
            "entries_consolidated": int(params.get("entries_consolidated", 0)),
            "categories_improved": int(params.get("categories_improved", 0)),
            "total_entries": int(params.get("total_entries", 0)),
            "storage_reduction_mb": float(params.get("storage_reduction_mb", 0)),
            "notes": params.get("notes", "")
        }
        
        progress["memory_consolidations"].append(consolidation)
        _save_progress(progress)
        
        return json.dumps({
            "status": "logged",
            "duplicates_removed": consolidation["duplicates_removed"],
            "message": f"Memory optimized: {consolidation['duplicates_removed']} duplicates removed"
        })

    def _log_refactoring(self, params: dict) -> str:
        """Log code refactoring activity."""
        progress = _load_progress()
        
        refactor = {
            "timestamp": datetime.now().isoformat(),
            "component": params.get("component", ""),
            "type": params.get("type", "general"),  # general, performance, cleanup, documentation
            "lines_changed": int(params.get("lines_changed", 0)),
            "complexity_reduction": float(params.get("complexity_reduction", 0)),
            "performance_improvement_pct": float(params.get("performance_improvement_pct", 0)),
            "description": params.get("description", ""),
            "tests_passed": params.get("tests_passed", True)
        }
        
        progress["refactoring_history"].append(refactor)
        _save_progress(progress)
        
        return json.dumps({
            "status": "logged",
            "message": f"Refactoring logged for {refactor['component']}"
        })

    def _add_milestone(self, params: dict) -> str:
        """Add a learning milestone."""
        progress = _load_progress()
        
        milestone = {
            "timestamp": datetime.now().isoformat(),
            "title": params.get("title", ""),
            "category": params.get("category", "general"),
            "achievement": params.get("achievement", ""),
            "impact": params.get("impact", ""),
            "next_goals": params.get("next_goals", [])
        }
        
        progress["milestones"].append(milestone)
        _save_progress(progress)
        
        return json.dumps({
            "status": "logged",
            "message": f"Milestone added: {milestone['title']}"
        })

    def _get_summary(self, params: dict) -> str:
        """Get learning progress summary."""
        progress = _load_progress()
        period = params.get("period", 30)  # days
        
        cutoff = datetime.now() - timedelta(days=period)
        cutoff_iso = cutoff.isoformat()
        
        # Filter recent entries
        recent_model_improvements = [e for e in progress["model_performance"] if e["timestamp"] > cutoff_iso]
        recent_code_improvements = [e for e in progress["code_quality"] if e["timestamp"] > cutoff_iso]
        recent_research = [e for e in progress["research_activities"] if e["timestamp"] > cutoff_iso]
        recent_consolidations = [e for e in progress["memory_consolidations"] if e["timestamp"] > cutoff_iso]
        
        # Calculate stats
        avg_model_improvement = sum(e["improvement_pct"] for e in recent_model_improvements) / len(recent_model_improvements) if recent_model_improvements else 0
        total_code_improvements = len(recent_code_improvements)
        total_research_items = len(recent_research)
        total_duplicates_removed = sum(e["duplicates_removed"] for e in recent_consolidations)
        
        summary = {
            "period_days": period,
            "model_improvements": {
                "count": len(recent_model_improvements),
                "avg_improvement_pct": round(avg_model_improvement, 2),
                "top_improvements": sorted(recent_model_improvements, key=lambda x: x["improvement_pct"], reverse=True)[:3]
            },
            "code_improvements": {
                "count": total_code_improvements,
                "recent": recent_code_improvements[:5]
            },
            "research": {
                "count": total_research_items,
                "topics": list(set(r["topic"] for r in recent_research)),
                "recent": recent_research[:5]
            },
            "memory_optimization": {
                "consolidations": len(recent_consolidations),
                "duplicates_removed": total_duplicates_removed
            },
            "milestones": [m for m in progress["milestones"] if m["timestamp"] > cutoff_iso]
        }
        
        return json.dumps(summary, indent=2)

    def _get_weekly_report(self) -> str:
        """Get weekly learning report."""
        progress = _load_progress()
        week_ago = datetime.now() - timedelta(days=7)
        week_iso = week_ago.isoformat()
        
        report = {
            "period": "Last 7 days",
            "model_improvements": [e for e in progress["model_performance"] if e["timestamp"] > week_iso],
            "code_improvements": [e for e in progress["code_quality"] if e["timestamp"] > week_iso],
            "research_activities": [e for e in progress["research_activities"] if e["timestamp"] > week_iso],
            "memory_work": [e for e in progress["memory_consolidations"] if e["timestamp"] > week_iso],
            "refactoring": [e for e in progress["refactoring_history"] if e["timestamp"] > week_iso]
        }
        
        # Generate narrative
        narrative = []
        if report["model_improvements"]:
            narrative.append(f"✓ {len(report['model_improvements'])} model improvements logged")
        if report["code_improvements"]:
            narrative.append(f"✓ {len(report['code_improvements'])} code optimizations completed")
        if report["research_activities"]:
            narrative.append(f"✓ Researched {len(report['research_activities'])} topics")
        if report["memory_work"]:
            narrative.append(f"✓ Memory consolidation: {sum(m['duplicates_removed'] for m in report['memory_work'])} duplicates removed")
        
        report["narrative"] = narrative
        return json.dumps(report, indent=2)

    def _get_monthly_report(self) -> str:
        """Get monthly learning report."""
        progress = _load_progress()
        month_ago = datetime.now() - timedelta(days=30)
        month_iso = month_ago.isoformat()
        
        report = {
            "period": "Last 30 days",
            "model_improvements": [e for e in progress["model_performance"] if e["timestamp"] > month_iso],
            "code_improvements": [e for e in progress["code_quality"] if e["timestamp"] > month_iso],
            "research_activities": [e for e in progress["research_activities"] if e["timestamp"] > month_iso],
            "memory_consolidations": [e for e in progress["memory_consolidations"] if e["timestamp"] > month_iso],
            "refactoring_history": [e for e in progress["refactoring_history"] if e["timestamp"] > month_iso],
            "milestones": [e for e in progress["milestones"] if e["timestamp"] > month_iso]
        }
        
        # Calculate improvements
        avg_model_improvement = sum(e["improvement_pct"] for e in report["model_improvements"]) / len(report["model_improvements"]) if report["model_improvements"] else 0
        total_duplicates = sum(m["duplicates_removed"] for m in report["memory_consolidations"])
        total_refactoring_lines = sum(r["lines_changed"] for r in report["refactoring_history"])
        
        report["statistics"] = {
            "avg_model_improvement_pct": round(avg_model_improvement, 2),
            "total_duplicates_removed": total_duplicates,
            "total_refactoring_lines": total_refactoring_lines,
            "research_topics": len(set(r["topic"] for r in report["research_activities"]))
        }
        
        return json.dumps(report, indent=2)

    def _get_all_milestones(self) -> str:
        """Get all recorded milestones."""
        progress = _load_progress()
        milestones = sorted(progress["milestones"], key=lambda x: x["timestamp"], reverse=True)
        
        return json.dumps({
            "total_milestones": len(milestones),
            "milestones": milestones
        }, indent=2)

    def _get_improvement_areas(self) -> str:
        """Identify areas with most improvement."""
        progress = _load_progress()
        
        # Analyze trends
        areas = {
            "model_performance": len(progress["model_performance"]),
            "code_quality": len(progress["code_quality"]),
            "research": len(progress["research_activities"]),
            "memory_optimization": len(progress["memory_consolidations"]),
            "refactoring": len(progress["refactoring_history"])
        }
        
        # Sort by activity
        sorted_areas = sorted(areas.items(), key=lambda x: x[1], reverse=True)
        
        # Get top improvements by metric
        if progress["model_performance"]:
            top_model = max(progress["model_performance"], key=lambda x: x["improvement_pct"])
        else:
            top_model = None
            
        if progress["code_quality"]:
            top_code = max(progress["code_quality"], key=lambda x: x["improvement"])
        else:
            top_code = None
        
        return json.dumps({
            "activity_by_area": dict(sorted_areas),
            "top_model_improvement": top_model,
            "top_code_improvement": top_code,
            "recommendation": self._get_recommendation(sorted_areas)
        }, indent=2)

    def _get_recommendation(self, sorted_areas: list) -> str:
        """Generate recommendations based on progress."""
        if not sorted_areas:
            return "Start tracking learning progress"
        
        top_area = sorted_areas[0][0]
        
        recommendations = {
            "model_performance": "Continue focusing on model optimization. Consider exploring hyperparameter tuning further.",
            "code_quality": "Great code quality focus! Consider balancing with more research activities.",
            "research": "Excellent research engagement. Remember to apply findings to model improvements.",
            "memory_optimization": "Strong memory consolidation. Consider expanding research activities.",
            "refactoring": "Good refactoring discipline. Balance with research and model improvements."
        }
        
        return recommendations.get(top_area, "Continue current improvement trajectory")
