from core.plugin_manager import BasePlugin
import logging, json, requests
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("nexus.plugins.language_coach")

PROGRESS_FILE = Path.home() / "NexusScripts" / "language_progress.json"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"


def _ollama(prompt: str) -> str:
    try:
        resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=60)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        return f"[Ollama error: {e}]"


def _load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_progress(data: dict):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _lang_entry(data: dict, language: str) -> dict:
    lang = language.lower()
    if lang not in data:
        data[lang] = {"language": language, "lessons_completed": 0, "words_learned": [], "last_session": None}
    return data[lang]


class LanguageCoachPlugin(BasePlugin):
    name = "language_coach"
    description = "AI language learning coach: translate, vocab, conversation, grammar, lessons, and quizzes."
    icon = "🌍"

    async def connect(self) -> bool:
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._connected = True
        self._status_message = "Ready"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "translate", "description": "Translate text between languages", "params": ["text", "target_language", "source_language"]},
            {"action": "learn_vocab", "description": "Generate 10 vocabulary words with translations and examples", "params": ["language", "topic"]},
            {"action": "practice_conversation", "description": "AI conversation partner for language practice", "params": ["language", "scenario"]},
            {"action": "grammar_check", "description": "Check grammar and explain errors", "params": ["text", "language"]},
            {"action": "get_progress", "description": "Show learning stats for a language", "params": ["language"]},
            {"action": "daily_lesson", "description": "Generate a mini daily lesson (vocab + phrase + grammar tip)", "params": ["language"]},
            {"action": "quiz_me", "description": "Generate a simple translation quiz", "params": ["language"]},
        ]

    async def execute(self, action: str, params: dict) -> str:
        try:
            if action == "translate":
                return await self._translate(params)
            elif action == "learn_vocab":
                return await self._learn_vocab(params)
            elif action == "practice_conversation":
                return await self._practice_conversation(params)
            elif action == "grammar_check":
                return await self._grammar_check(params)
            elif action == "get_progress":
                return await self._get_progress(params)
            elif action == "daily_lesson":
                return await self._daily_lesson(params)
            elif action == "quiz_me":
                return await self._quiz_me(params)
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.exception("LanguageCoach error")
            return f"Error in language_coach.{action}: {e}"

    async def _translate(self, params: dict) -> str:
        text = params.get("text", "")
        target = params.get("target_language", "Spanish")
        source = params.get("source_language", "English")
        if not text:
            return "No text provided."
        prompt = f"Translate the following text from {source} to {target}. Reply with only the translation.\n\nText: {text}"
        result = _ollama(prompt)
        data = _load_progress()
        entry = _lang_entry(data, target)
        entry["last_session"] = datetime.now().isoformat()
        _save_progress(data)
        return f"Translation ({source} -> {target}):\n{result}"

    async def _learn_vocab(self, params: dict) -> str:
        language = params.get("language", "Spanish")
        topic = params.get("topic", "everyday life")
        prompt = (
            f"Generate exactly 10 vocabulary words in {language} related to the topic: '{topic}'. "
            f"For each word, provide: the word in {language}, its English translation, and one example sentence in {language} with English translation. "
            f"Format each as: Word | Translation | Example | Example Translation"
        )
        result = _ollama(prompt)
        data = _load_progress()
        entry = _lang_entry(data, language)
        entry["lessons_completed"] += 1
        entry["last_session"] = datetime.now().isoformat()
        words = [line.split("|")[0].strip() for line in result.splitlines() if "|" in line]
        entry["words_learned"] = list(set(entry["words_learned"] + words))[:200]
        _save_progress(data)
        return f"Vocabulary lesson ({language} - {topic}):\n\n{result}"

    async def _practice_conversation(self, params: dict) -> str:
        language = params.get("language", "Spanish")
        scenario = params.get("scenario", "ordering food at a restaurant")
        prompt = (
            f"You are a {language} conversation partner. Play out a short conversation scenario: '{scenario}'. "
            f"Write a realistic back-and-forth dialogue of 6-8 lines in {language}, then provide an English translation below each line in parentheses."
        )
        result = _ollama(prompt)
        data = _load_progress()
        entry = _lang_entry(data, language)
        entry["lessons_completed"] += 1
        entry["last_session"] = datetime.now().isoformat()
        _save_progress(data)
        return f"Conversation Practice ({language} - {scenario}):\n\n{result}"

    async def _grammar_check(self, params: dict) -> str:
        text = params.get("text", "")
        language = params.get("language", "Spanish")
        if not text:
            return "No text provided."
        prompt = (
            f"Check the following {language} text for grammar errors. "
            f"List each error found, explain why it is wrong, and provide the corrected version. "
            f"If there are no errors, say so. Be educational and clear.\n\nText: {text}"
        )
        result = _ollama(prompt)
        return f"Grammar Check ({language}):\n\n{result}"

    async def _get_progress(self, params: dict) -> str:
        language = params.get("language", "")
        data = _load_progress()
        if language:
            entry = data.get(language.lower())
            if not entry:
                return f"No progress data found for {language}."
            return (
                f"Progress for {entry['language']}:\n"
                f"  Lessons completed: {entry['lessons_completed']}\n"
                f"  Words learned: {len(entry['words_learned'])}\n"
                f"  Last session: {entry.get('last_session', 'N/A')}"
            )
        if not data:
            return "No language progress tracked yet."
        lines = [f"Language Learning Progress:"]
        for lang, entry in data.items():
            lines.append(f"  {entry['language']}: {entry['lessons_completed']} lessons, {len(entry['words_learned'])} words")
        return "\n".join(lines)

    async def _daily_lesson(self, params: dict) -> str:
        language = params.get("language", "Spanish")
        prompt = (
            f"Create a short daily {language} lesson with three sections:\n"
            f"1. VOCABULARY: 3 useful words with translations\n"
            f"2. PHRASE OF THE DAY: one common phrase with translation and pronunciation tip\n"
            f"3. GRAMMAR TIP: one simple grammar rule with an example\n"
            f"Keep it concise and beginner-friendly."
        )
        result = _ollama(prompt)
        data = _load_progress()
        entry = _lang_entry(data, language)
        entry["lessons_completed"] += 1
        entry["last_session"] = datetime.now().isoformat()
        _save_progress(data)
        return f"Daily {language} Lesson ({datetime.now().strftime('%Y-%m-%d')}):\n\n{result}"

    async def _quiz_me(self, params: dict) -> str:
        language = params.get("language", "Spanish")
        data = _load_progress()
        entry = _lang_entry(data, language)
        known_words = entry.get("words_learned", [])
        word_hint = f" Use some of these words if possible: {', '.join(known_words[:10])}" if known_words else ""
        prompt = (
            f"Create a short {language} translation quiz with 5 questions. "
            f"Mix English-to-{language} and {language}-to-English translations.{word_hint} "
            f"Number each question and leave space for answers. After the questions, provide an ANSWER KEY section."
        )
        result = _ollama(prompt)
        return f"{language} Translation Quiz:\n\n{result}"
