# Nexus — J.A.R.V.I.S. Local AI Command Center

100% offline. No API keys. No cloud. No subscriptions.
Voice control · Screen awareness · Persistent memory · Proactive briefings · 50+ plugins.

---

## Quick Start

```bash
# 1. Install Ollama then pull a model
ollama pull llama3.2:3b

# 2. Install Python dependencies
pip install -r requirements.txt
python -m playwright install chromium

# 3. Install new plugin deps (v2.2)
pip install pyperclip feedparser PyMuPDF qrcode[pil] cryptography imageio imageio-ffmpeg

# 4. (Optional) Voice control requires ffmpeg
winget install ffmpeg

# 5. Launch
python main.py
```

Log into your accounts in the browser that opens on first run (one-time session).

---

## System Requirements

- Windows 10/11
- Python 3.10+
- 8 GB RAM minimum (16 GB recommended for Whisper + Ollama simultaneously)
- Ollama running locally (`ollama serve`)

---

## Voice Setup

- **Wake word:** Say `"Nexus"` then your command
- **STT:** Whisper `tiny` model (~75 MB, auto-downloads on first run)
- **TTS:** Windows SAPI5 neural voices — auto-selects best available (Guy Natural on Win11)
- **ffmpeg required:** `winget install ffmpeg`

`config/settings.json` voice options:
```json
"voice": {
  "whisper_model": "tiny",
  "voice_rate": 155,
  "voice_volume": 0.95,
  "wake_word": true,
  "sound_effects": true
}
```

---

## Plugin Reference

### Communication

#### ✉ Email (`email`)
Connect Gmail via browser session.
| Command | Example |
|---|---|
| Check inbox | `"check my email"` |
| Send email | `"send email to john@example.com subject Meeting body Let's meet tomorrow"` |
| Search email | `"search email for invoice"` |
| Reply to email | `"reply to last email"` |

#### 💬 WhatsApp (`whatsapp`)
Requires WhatsApp Web logged in.
| Command | Example |
|---|---|
| List chats | `"list my WhatsApp chats"` |
| Send message | `"WhatsApp John saying I'm on my way"` |
| Read messages | `"read WhatsApp messages from Sarah"` |

#### 🎮 Discord (`discord`)
| Command | Example |
|---|---|
| Check DMs | `"check my Discord DMs"` |
| Send message | `"Discord message general saying hello"` |
| List servers | `"list my Discord servers"` |

#### 🐙 GitHub (`github`)
| Command | Example |
|---|---|
| Notifications | `"check GitHub notifications"` |
| List repos | `"list my GitHub repos"` |
| Create issue | `"create GitHub issue in my-repo title Bug found"` |
| List PRs | `"list open pull requests"` |

#### 📱 Google Voice (`gvoice`)
| Command | Example |
|---|---|
| Send SMS | `"text John saying be there in 10"` |
| Read texts | `"read my texts"` |
| Make call | `"call mom"` |

#### 📨 Telegram (`telegram`)
Receive and respond to commands via Telegram bot.
Requires `telegram_token` in settings.json.

---

### Business & Finance

#### 🚀 Project Manager (`project_manager`)
Tracks clients and projects with deadlines and rates.
| Command | Example |
|---|---|
| List projects | `"list my projects"` |
| Add project | `"add project Website Redesign for Acme Corp rate 150 deadline 2026-04-01"` |
| Project summary | `"project summary"` |
| Overdue projects | `"show overdue projects"` |

#### 💰 Invoice System (`invoice_system`)
| Command | Example |
|---|---|
| List invoices | `"list my invoices"` |
| Create invoice | `"create invoice for Acme Corp 3000 dollars for website work"` |
| Revenue summary | `"revenue summary"` |
| Mark paid | `"mark invoice 3 as paid"` |

#### 📋 Proposal Writer (`proposal_writer`)
AI-generated PDF proposals via Ollama + fpdf2.
| Command | Example |
|---|---|
| Write proposal | `"write proposal for e-commerce website for TechCo 5000 dollars"` |
| List proposals | `"list my proposals"` |

#### ⏱ Time Tracker (`time_tracker`)
Passive window-title tracking + manual logging.
| Command | Example |
|---|---|
| Start tracking | `"start tracking time"` |
| Stop tracking | `"stop tracking"` |
| Today's hours | `"today's time"` |
| Weekly report | `"time this week"` |
| Log manual | `"log 2 hours on Project Alpha"` |

#### 🌐 Client Portal (`client_portal`)
Password-protected web portal for clients (Flask, port 5001).
| Command | Example |
|---|---|
| Start portal | `"start client portal"` |
| Add client | `"add client Acme Corp with password secret123"` |
| List clients | `"list portal clients"` |
| Get URL | `"get phone URL"` |

#### 📝 Expense Tracker (`expense_tracker`)
Track business income and expenses with categories.
| Command | Example |
|---|---|
| Add expense | `"add expense 49.99 category Software description VS Code license"` |
| Add income | `"add income 2500 from Acme Corp consulting"` |
| Monthly summary | `"expense summary"` |
| Profit & loss | `"profit and loss"` |
| List expenses | `"list expenses this month"` |

**Categories:** Software, Hardware, Marketing, Travel, Meals, Utilities, Salary, Freelance, Other

#### 📄 Contract Generator (`contract_generator`)
AI-drafted contracts exported as PDF (fpdf2) or .txt fallback.
| Command | Example |
|---|---|
| Generate contract | `"generate freelance contract for Acme Corp project Website Redesign amount 5000"` |
| List contracts | `"list contracts"` |

**Contract types:** `freelance`, `nda`, `service_agreement`, `employment`, `consulting`

#### ✉ Email Composer (`email_composer`)
AI drafts professional emails; sends via SMTP if configured.
| Command | Example |
|---|---|
| Compose email | `"compose email to ceo@acme.com subject Partnership key points we offer X Y Z tone professional"` |
| Improve email | `"improve this email: [paste text]"` |
| Reply template | `"write a reply to decline politely"` |
| List drafts | `"list email drafts"` |

**Tones:** `professional`, `friendly`, `formal`, `urgent`

#### 🎯 Competitor Tracker (`competitor_tracker`)
Monitors competitor websites and news via DuckDuckGo + Ollama summaries.
| Command | Example |
|---|---|
| Add competitor | `"add competitor OpenAI url openai.com"` |
| Check competitor | `"check competitor OpenAI"` |
| Full report | `"competitor report"` |
| Check all | `"check all competitors"` |

---

### Intelligence & Awareness

#### 👁 Vision AI (`vision_ai`)
Screen capture + LLaVA vision model analysis.
| Command | Example |
|---|---|
| Describe screen | `"what's on screen"` |
| Analyze image | `"analyze image at C:/screenshot.png"` |
| Read UI | `"read the UI on screen"` |
| Find on screen | `"find the submit button on screen"` |

#### 👁 Ambient Monitor (`ambient_monitor`)
Passive background tracking of active windows and screen time.
| Command | Example |
|---|---|
| Activity summary | `"what have I been doing"` |
| Screen time | `"screen time today"` |
| Idle time | `"how long have I been idle"` |
| Top apps | `"top apps today"` |

#### 📋 Clipboard AI (`clipboard_ai`)
AI-powered clipboard monitoring and transformations.
| Command | Example |
|---|---|
| Get clipboard | `"get clipboard"` |
| Transform | `"translate clipboard to Spanish"` |
| Fix grammar | `"fix grammar in clipboard"` |
| Summarize | `"summarize clipboard"` |
| History | `"clipboard history"` |
| Smart paste | `"smart paste"` |

#### 🖥 App Controller (`app_controller`)
Launch, close, and focus Windows applications.
| Command | Example |
|---|---|
| Open app | `"open notepad"` / `"launch chrome"` |
| Close app | `"close spotify"` |
| List running | `"list running apps"` |
| Focus app | `"focus vscode"` |

**Known apps:** notepad, calculator, browser, chrome, firefox, vscode, explorer, spotify, discord, terminal

#### 🔬 Research Agent (`research_agent`)
DuckDuckGo search + Ollama summarization, saves reports to `~/NexusScripts/research/`.
| Command | Example |
|---|---|
| Quick research | `"research quantum computing"` |
| Deep research | `"deep research on AI regulation 2026"` |
| Web search | `"search for Python asyncio tutorial"` |
| Summarize URL | `"summarize url https://..."` |
| List reports | `"list research reports"` |

#### 📰 News Digest (`news_digest`)
Aggregates RSS feeds and summarizes with Ollama.
| Command | Example |
|---|---|
| Get digest | `"today's news"` |
| Topic filter | `"news about AI"` |
| Raw headlines | `"get headlines"` |
| Add feed | `"add feed TechCrunch url https://techcrunch.com/feed/"` |
| List feeds | `"list news feeds"` |

**Default feeds:** BBC News, Reuters, Hacker News, TechCrunch

#### 📚 Knowledge Base (`knowledge_base`)
Personal note store with full-text search and tags.
| Command | Example |
|---|---|
| Add note | `"add note title Python Tips content Use f-strings tags python coding"` |
| Search | `"search notes for async"` |
| List notes | `"list my notes"` |
| Get note | `"get note Python Tips"` |
| Stats | `"knowledge stats"` |

#### 📄 PDF Reader (`pdf_reader`)
Extract, summarize, and query PDF files via PyMuPDF/pdfplumber/pypdf + Ollama.
| Command | Example |
|---|---|
| Summarize PDF | `"summarize PDF at C:/docs/report.pdf"` |
| Ask PDF | `"ask PDF C:/contract.pdf what are the payment terms"` |
| Extract page | `"get page 3 of C:/report.pdf"` |
| List recent PDFs | `"list recent PDFs"` |

---

### System & Security

#### ⚡ System Monitor (`system_monitor`)
Real-time CPU, RAM, disk, network, process stats.
| Command | Example |
|---|---|
| System stats | `"system stats"` |
| Full report | `"full system report"` |
| Disk usage | `"disk usage"` |

#### ⚡ System Optimizer (`system_optimizer`)
Cleans temp files, manages startup items, frees RAM.
| Command | Example |
|---|---|
| Clean temp | `"clean temp files"` |
| Kill heavy processes | `"kill heavy processes"` |
| Top processes | `"top processes"` |
| Startup items | `"show startup programs"` |
| Disk cleanup | `"disk cleanup C:/Projects"` |
| Defrag check | `"check defrag"` |

#### 💾 Backup Manager (`backup_manager`)
Zip-based backup jobs stored in `~/NexusScripts/backup_config.json`.
| Command | Example |
|---|---|
| Add backup job | `"add backup job Projects source C:/Projects destination D:/Backups"` |
| Run backup | `"run backup Projects"` |
| Run all | `"run all backups"` |
| List backups | `"list backups"` |
| Restore | `"restore backup Projects file backup_2026-03-23.zip to C:/Restore"` |

#### 🌐 Network Scanner (`network_scanner`)
Scans local network, checks ports, tests connectivity.
| Command | Example |
|---|---|
| My IP | `"my IP address"` |
| Scan network | `"scan my network"` |
| Check internet | `"check internet connection"` |
| Ping host | `"ping 192.168.1.1"` |
| Check port | `"check port 80 on 192.168.1.100"` |
| Speed test | `"simple speed test"` |

#### 🔐 Password Vault (`password_vault`)
AES-encrypted local vault using Fernet + PBKDF2 (falls back to XOR if `cryptography` not installed).
| Command | Example |
|---|---|
| Setup vault | `"setup vault with master password mySecretPass"` |
| Add password | `"add password for GitHub username john password abc123 master mySecretPass"` |
| Get password | `"get password for GitHub master mySecretPass"` |
| List services | `"list services master mySecretPass"` |
| Generate password | `"generate password"` |
| Check strength | `"check password strength hunter2"` |

> Vault file: `~/NexusScripts/.vault` — never leaves your machine.

---

### Productivity

#### 🍅 Pomodoro (`pomodoro`)
25/5 focus timer with logging to `~/NexusScripts/pomodoro_log.json`.
| Command | Example |
|---|---|
| Start | `"start pomodoro working on proposal"` |
| Stop | `"stop pomodoro"` |
| Status | `"pomodoro status"` |
| Take break | `"take a break"` / `"take a long break"` |
| Stats | `"pomodoro stats"` |

#### ✅ Habit Tracker (`habit_tracker`)
Daily/weekly habit tracking with streak calculation.
| Command | Example |
|---|---|
| Add habit | `"add habit Morning Run description 5km every day"` |
| Complete habit | `"complete habit Morning Run"` |
| Today's habits | `"today's habits"` |
| Streak | `"streak for Morning Run"` |
| Stats | `"habit stats Morning Run"` |

#### 📅 Smart Calendar (`smart_calendar`)
Local calendar with reminders (checks every 60s) and natural language parsing.
| Command | Example |
|---|---|
| Add event | `"add event Team Meeting on 2026-03-25 at 14:00 for 60 minutes"` |
| Natural language | `"schedule standup tomorrow at 9am for 30 minutes"` |
| Today's schedule | `"today's schedule"` |
| Upcoming events | `"upcoming events"` |
| Find free time | `"find free time tomorrow for 2 hours"` |
| Delete event | `"delete event Team Meeting"` |

#### 🎬 Screen Recorder (`screen_recorder`)
Records screen to video (imageio/ffmpeg) or PNG frames fallback.
| Command | Example |
|---|---|
| Screenshot | `"take a screenshot"` |
| Start recording | `"start screen recording"` |
| Stop recording | `"stop screen recording"` |
| Recording status | `"recording status"` |
| List recordings | `"list screen recordings"` |

Files saved to: `~/NexusScripts/recordings/`

---

### CAD & Hardware

#### ⚙ CAD Engine (`cad_engine`)
AI generates CadQuery Python code from natural language, exports STL/STEP/DXF.
Requires: `pip install cadquery` (large install, use conda for best results).
| Command | Example |
|---|---|
| Generate part | `"design a mounting bracket 50x30mm with 4 holes"` |
| Create shape | `"create a cylinder 20mm diameter 50mm tall"` |
| List parts | `"list my CAD parts"` |
| Export STL | `"export bracket to STL"` |
| Export STEP | `"export bracket to STEP"` |
| Open part | `"open bracket"` |

#### 🖨 Print Queue (`print_queue`)
3D print job tracking with filament estimates. Auto-detects Bambu/Prusa/Cura/Creality.
| Command | Example |
|---|---|
| Add job | `"add print job Bracket file bracket.stl material PLA"` |
| List jobs | `"print queue"` |
| Update status | `"update print job Bracket status printing"` |
| Complete job | `"complete print job Bracket"` |
| Estimate | `"estimate print for bracket.stl infill 20"` |
| Open slicer | `"open slicer for bracket.stl"` |

---

### Automation & Scripting

#### 💻 Code Writer (`code_writer`)
AI writes and runs Python scripts, saved to `~/NexusScripts/`.
| Command | Example |
|---|---|
| Write script | `"write a script that renames all JPGs in a folder"` |
| Run script | `"run script rename_jpgs"` |
| Write and run | `"write and run a script to list all large files on C drive"` |
| Edit script | `"edit script rename_jpgs add error handling"` |
| List scripts | `"list scripts"` |

#### 🤖 Task Automator (`task_automator`)
Named multi-step macros stored in `~/NexusScripts/macros.json`.
| Command | Example |
|---|---|
| Run macro | `"run morning routine"` |
| List macros | `"list macros"` |
| Create macro | `"create macro daily_standup with steps..."` |

**Built-in macros:** `morning_routine`, `end_of_day`, `system_check`, `client_update`

#### 🌐 Browser Recorder (`browser_recorder`)
Records and replays Playwright browser sequences as JSON steps.
| Command | Example |
|---|---|
| Start recording | `"start browser recording checkout_flow"` |
| Stop recording | `"stop recording"` |
| Play recording | `"play recording checkout_flow"` |
| List recordings | `"list browser recordings"` |

#### ⌨ Hotkey Daemon (`hotkey_daemon`)
Global keyboard shortcuts (runs in background).
| Hotkey | Action |
|---|---|
| `Win+Space` | Toggle voice listening |
| `Win+S` | Describe screen |
| `Win+B` | Morning briefing |
| `Win+T` | Today's time |
| `Win+P` | Quick status |
| `Win+C` | System stats |

List hotkeys: `"list hotkeys"`

---

### Knowledge & Research

#### 🔍 Local RAG (`local_rag`)
Index local files and answer questions from them using keyword-based retrieval + Ollama.
Optionally uses `sentence-transformers` for semantic search.
| Command | Example |
|---|---|
| Index file | `"index file C:/docs/manual.txt"` |
| Index folder | `"index folder C:/Projects/docs"` |
| Query | `"query my docs: what is the API rate limit?"` |
| List indexed | `"list indexed documents"` |
| Remove | `"remove from index manual.txt"` |

Index stored at: `~/NexusScripts/rag_index.json`

#### 🧬 JARVIS Memory v2 (`jarvis_memory_v2`)
Semantic memory with importance scoring. Uses `sentence-transformers` if installed, falls back to Jaccard keyword similarity.
| Command | Example |
|---|---|
| Remember | `"remember that John prefers meetings before noon"` |
| Recall | `"recall what you know about John"` |
| Get context | `"get context for client meeting"` |
| List memories | `"list memories"` |
| Consolidate | `"consolidate memories"` |
| Stats | `"memory stats"` |

**Categories:** `personal`, `preference`, `fact`, `event`, `goal`, `relationship`, `work`

#### 🧠 Memory Brain (`memory`)
Original memory system — contacts, preferences, tasks, facts.
| Command | Example |
|---|---|
| Remember contact | `"remember John Smith phone 555-1234"` |
| Find contact | `"find contact John"` |
| Remember fact | `"remember my office WiFi password is nexus2024"` |
| Add task | `"add task finish proposal by Friday"` |
| List tasks | `"list my tasks"` |

---

### Fun & Creative

#### 🌍 Language Coach (`language_coach`)
AI language tutor via Ollama. Tracks progress in `~/NexusScripts/language_progress.json`.
| Command | Example |
|---|---|
| Translate | `"translate 'good morning' to Japanese"` |
| Learn vocab | `"learn Spanish vocabulary about food"` |
| Practice conversation | `"practice French conversation at a restaurant"` |
| Grammar check | `"grammar check this Spanish sentence: Yo soy un programador"` |
| Daily lesson | `"daily Spanish lesson"` |
| Quiz me | `"quiz me in French"` |

#### 🌙 Dream Journal (`dream_journal`)
Record and analyze dreams with Jungian psychology. Stored in `~/NexusScripts/dream_journal.json`.
| Command | Example |
|---|---|
| Record dream | `"I had a dream I was flying over a city"` |
| Analyze dream | `"analyze dream about flying"` |
| List dreams | `"list my dreams"` |
| Find themes | `"find dreams about water"` |
| Stats | `"dream stats"` |

#### ⬛ QR Generator (`qr_generator`)
Generates QR codes as PNG files. Requires `pip install qrcode[pil]`.
| Command | Example |
|---|---|
| Generate | `"generate QR code for https://mysite.com"` |
| WiFi QR | `"WiFi QR code for MyNetwork password secret123"` |
| Contact QR | `"contact QR for John Smith phone 555-1234 email john@example.com"` |
| List QR codes | `"list QR codes"` |

Saved to: `~/NexusScripts/qr_codes/`

---

## AI & ML Improvement Framework

Nexus implements a comprehensive self-improvement system to continuously enhance AI and machine learning capabilities:

### Research & Learning

**Stay Current with Latest Research**
- Review papers from top-tier conferences: NIPS, IJCAI, ICML, NeurIPS
- Monitor arXiv and research platforms weekly for latest advancements
- Subscribe to AI/ML journals and newsletters
- Explore resources: ResearchGate, Academia.edu

**Explore Machine Learning Algorithms**
- Investigate supervised learning: linear regression, decision trees, SVM, neural networks
- Study unsupervised learning: clustering, dimensionality reduction, anomaly detection
- Explore reinforcement learning: Q-learning, policy gradient, actor-critic methods
- Analyze algorithm strengths, weaknesses, and real-world applications
- Create comparison matrices for different use cases

### Model Optimization

**Hyperparameter Tuning**
- Apply grid search, random search, and Bayesian optimization
- Implement cross-validation for robust evaluation
- Monitor performance metrics: accuracy, precision, recall, F1 score, AUC-ROC
- Use early stopping to prevent overfitting
- Track all experiments and hyperparameter configurations

**Transfer Learning & Pre-Trained Models**
- Leverage pre-trained models from HuggingFace, TensorFlow Hub, PyTorch Hub
- Fine-tune models for specific tasks rather than training from scratch
- Experiment with different layer freeze/unfreeze strategies
- Document fine-tuning strategies and performance improvements

**Data Augmentation & Generation**
- Image augmentation: rotation, flipping, color jittering, zooming, mixing
- Text augmentation: paraphrasing, back-translation, synonym replacement
- Use generative models: GANs, VAEs, diffusion models for synthetic data
- Balance imbalanced datasets through intelligent augmentation
- Monitor augmentation for artifacts that introduce bias

### Explainability & Transparency

**Investigate Explainability Techniques**
- SHAP (SHapley Additive exPlanations) - feature importance and prediction explanations
- LIME (Local Interpretable Model-agnostic Explanations) - local model approximations
- Saliency maps - visual importance of input features
- Attention mechanisms - understanding neural network decisions
- Permutation importance - feature contribution analysis

**Benefits:**
- Understand how models make predictions
- Identify and mitigate biases in predictions
- Improve transparency and trustworthiness
- Use explanations to enhance training data quality

### Code Evolution

**Reflect on Code**
- Weekly code audits identify optimization opportunities
- Review for DRY violations and code duplication
- Analyze performance bottlenecks using profiling
- Check documentation and clarity
- Monitor error handling and edge cases

**Apply Refactors**
- Create feature branches for refactoring changes
- Apply one refactor at a time for clear impact analysis
- Monitor performance metrics before and after
- Run full test suite after each refactor
- Document performance impact and learnings

**Strategic Skipping**
- Defer refactors when impact is uncertain
- Document reasoning for skipped improvements
- Revisit quarterly with new performance data
- Prioritize actual bottlenecks first

### Memory Optimization

**Sleep Cycle**
- Clear unnecessary data weekly
- Archive old interaction logs monthly
- Remove duplicate entries from memory
- Optimize database indexes periodically
- Monitor storage utilization

**Consolidate Memories**
- Monthly knowledge base review for duplicates
- Consolidate similar information into unified entries
- Improve categorization and tagging
- Update outdated information
- Create better cross-references

### Implementation Roadmap

**Phase 1: Foundation (2 weeks)**
- Implement hyperparameter tuning framework
- Set up code reflection schedule
- Create memory consolidation process

**Phase 2: Expansion (4 weeks)**
- Integrate explainability techniques (SHAP/LIME)
- Implement data augmentation pipelines
- Establish research tracking system

**Phase 3: Optimization (Ongoing)**
- Continuous performance monitoring
- Quarterly code audits and refactoring
- Regular knowledge base maintenance
- Stay current with latest research

### Success Metrics

**Model Performance**
- Accuracy improvement percentage
- Precision, recall, F1 score improvements
- AUC-ROC and other evaluation metrics
- Reduction in overfitting

**Code Quality**
- Performance improvement from refactoring
- Reduction in code complexity
- Improved test coverage
- Faster execution time

**Knowledge Quality**
- Response quality scores
- Reduced redundancy in memory
- Improved retrieval speed
- Knowledge accuracy validation

**Tracking & Tasks**
All AI/ML improvement tasks are tracked in the **RESEARCH tab** and **Tasks** system. Use commands like:
- `"list my tasks"` - View all improvement goals
- `"research quantum computing"` - Trigger deep research on new topics
- `"consolidate memories"` - Run knowledge base optimization

---

## ML User Guide — AI/ML Improvement Tracking

Nexus includes a comprehensive **ML tab** for tracking and managing AI/ML improvement initiatives. Access it by clicking the "ML" tab in the main interface.

### ML Tab Overview

The ML tab consists of four main sections:

#### 📋 Tasks Tab
**Manage your AI/ML improvement tasks and track progress.**

**Viewing Tasks:**
- **All Tasks**: See all ML-related tasks with status indicators
- **Filter by Status**: Open, In Progress, Done
- **Filter by Priority**: Low, Medium, High
- **Filter by Category**: ai_ml, evolution, memory, research, optimization

**Task Management:**
- **Mark Complete**: Click the checkbox next to any task
- **Start Task**: Click "Start" to mark as in progress
- **Edit Task**: Click the edit icon to modify task details
- **Create New Task**: Use the "Create Task" button

**Task Categories:**
- `ai_ml`: Core AI/ML algorithm and model improvements
- `evolution`: Code refactoring and system optimization
- `memory`: Knowledge base and memory consolidation
- `research`: Academic research and paper reviews
- `optimization`: Performance tuning and hyperparameter optimization

#### 📊 Progress Tab
**Visual dashboard showing your AI/ML improvement progress over time.**

**Charts & Visualizations:**
- **Model Performance Chart**: Track accuracy, F1 scores, and other metrics over time
- **Code Quality Chart**: Monitor refactoring impact and performance improvements
- **Research Activity Chart**: See research engagement and paper reviews
- **Memory Optimization Chart**: Track knowledge base consolidation progress

**Learning Integration:**
- **Recent Model Improvements**: Latest algorithm enhancements and their impact
- **Code Quality Updates**: Recent refactoring and optimization work
- **Research Activities**: Papers reviewed, conferences attended, new techniques learned
- **Memory Consolidations**: Duplicate removal and knowledge base improvements

#### 🔬 Research Tab
**Research recommendations and AI/ML learning resources.**

**Research Recommendations:**
- **Gap Analysis**: Identifies missing research areas in your improvement program
- **Priority Suggestions**: High-priority research topics based on current tasks
- **Action Items**: Click "Create Task" to add recommended research to your task list

**Current Research Areas:**
- **Algorithm Exploration**: New ML algorithms and techniques
- **Hyperparameter Tuning**: Systematic optimization strategies
- **Research Program**: Establishing regular paper review and conference attendance

**Research Framework:**
- **Weekly Reviews**: arXiv, NeurIPS, ICML, IJCAI papers
- **Conference Tracking**: Major AI/ML conference proceedings
- **Implementation**: Practical applications of research findings

#### 📈 Metrics Tab
**Comprehensive metrics dashboard for measuring AI/ML improvement success.**

**Time Period Filters:**
- **Week**: Last 7 days of activity
- **Month**: Last 30 days of progress
- **Quarter**: Last 90 days of improvement

**Performance Metrics:**
- **Model Improvements**: Number of enhancements, average improvement percentage
- **Code Quality**: Refactoring count, performance impact measurements
- **Research Activities**: Papers reviewed, topics covered, research diversity
- **Memory Optimization**: Duplicates removed, consolidation activities

**Success Tracking:**
- **Quantitative Metrics**: Accuracy %, performance gains, complexity reduction
- **Qualitative Metrics**: Research depth, code clarity improvements
- **Trend Analysis**: Progress over time with visual indicators

### Using the ML System

#### Getting Started
1. **Launch Nexus**: Run `python main.py`
2. **Navigate to ML Tab**: Click the "ML" tab in the main interface
3. **Initial Setup**: The system automatically generates routine improvement tasks
4. **Explore Tabs**: Review each tab to understand your current status
5. **Manual Execution**: Work on tasks manually and mark them complete when finished

#### Daily Workflow
1. **Morning Review**: Check the Progress tab for recent improvements
2. **Task Management**: Review and update task statuses in the Tasks tab
3. **Research Check**: Look at Research tab for new recommendations
4. **Execute Tasks**: Manually work on high-priority tasks (research, coding, optimization)
5. **Mark Complete**: Update task status when finished with manual work

#### Weekly Routine
1. **Research Review**: Manually dedicate time to paper reviews and new techniques
2. **Code Audit**: Manually review codebase for optimization opportunities
3. **Memory Consolidation**: Manually clean up knowledge base and remove duplicates
4. **Progress Assessment**: Evaluate improvement metrics and adjust goals
5. **Task Updates**: Mark completed tasks and plan next week's priorities

#### Automated Features
- **Auto-Refresh**: ML tab updates every 30 seconds with latest data
- **Task Generation**: System creates routine improvement tasks automatically on startup
- **Progress Tracking**: All improvements are logged and visualized when tasks are completed
- **Research Recommendations**: AI suggests new areas to explore based on current task gaps

**Important Note**: The ML system tracks and recommends improvements, but does NOT automatically execute tasks. You must manually work on the tasks (research papers, refactor code, optimize memory, etc.) and mark them complete in the interface.

### What the System Does Automatically

✅ **Generates routine tasks** (weekly research reviews, code audits, memory consolidation)  
✅ **Tracks your progress** when you complete tasks manually  
✅ **Updates charts and metrics** in real-time  
✅ **Suggests research areas** based on gaps in your improvement program  
✅ **Logs improvements** from other plugins (learning_progress, research_agent, etc.)  

### What You Need to Do Manually

🔄 **Execute the tasks** (read papers, refactor code, consolidate knowledge)  
🔄 **Mark tasks complete** when finished  
🔄 **Review recommendations** and create new tasks as needed  
🔄 **Monitor progress** and adjust priorities regularly

---

## Autonomous ML Improvement System (Future Enhancement)

**Note**: The current ML system is a **tracking and guidance tool**. True autonomous execution of ML improvement tasks would require advanced AI capabilities and carries significant risks. Below is a roadmap for future autonomous features:

### Phase 1: Semi-Autonomous Research
- **Automated Paper Discovery**: Scan arXiv daily for relevant papers
- **Summary Generation**: Auto-summarize papers and extract key insights
- **Relevance Scoring**: Rate papers by applicability to current projects
- **Weekly Digest**: Email summaries of top papers

### Phase 2: Code Analysis Automation
- **Automated Code Scanning**: Daily codebase analysis for optimization opportunities
- **Performance Profiling**: Identify bottlenecks automatically
- **Refactoring Suggestions**: Generate specific improvement recommendations
- **Safe Application**: Apply low-risk optimizations automatically

### Phase 3: Memory Optimization
- **Automated Consolidation**: Weekly knowledge base cleanup
- **Duplicate Detection**: Find and merge similar entries
- **Importance Scoring**: Automatically prioritize memory retention
- **Archive Management**: Move old data to compressed storage

### Phase 4: Model Improvement Automation
- **Automated Experiments**: Run hyperparameter sweeps overnight
- **Performance Monitoring**: Track model metrics continuously
- **Data Augmentation**: Generate synthetic training data
- **Model Updates**: Deploy improved models automatically

### Safety Considerations
- **Human Oversight**: All automated changes require approval
- **Rollback Capability**: Easy reversion of any automated changes
- **Testing Frameworks**: Comprehensive validation before deployment
- **Risk Assessment**: Automated evaluation of change impact

### Current Limitations
- **Code Safety**: Automated refactoring could introduce bugs
- **Research Quality**: AI summarization may miss nuanced insights
- **Context Understanding**: Limited ability to understand complex codebases
- **Ethical Concerns**: Automated decisions may have unintended consequences

**The current system focuses on guidance and tracking rather than autonomous execution to ensure safety and quality.**

### Near-Term Automation Opportunities

While full autonomy is complex, here are some **feasible semi-automated features** that could be implemented:

#### 🤖 Automated Research Assistant
- **Daily Paper Scanning**: Automatically check arXiv for papers matching your interests
- **Smart Summaries**: Generate AI summaries of papers with key takeaways
- **Relevance Ranking**: Score papers by how applicable they are to your current projects
- **Weekly Reports**: Email digests of the most relevant research

#### 🔍 Code Quality Monitor
- **Automated Code Analysis**: Run static analysis tools daily
- **Performance Profiling**: Identify potential bottlenecks automatically
- **Best Practice Checks**: Flag code that doesn't follow ML best practices
- **Refactoring Suggestions**: Generate specific improvement recommendations

#### 📊 Automated Reporting
- **Weekly Progress Reports**: Auto-generate summaries of your ML improvements
- **Benchmark Comparisons**: Compare your progress against industry standards
- **Goal Tracking**: Monitor progress toward long-term improvement objectives
- **Predictive Analytics**: Forecast future improvement trajectories

#### 💾 Smart Memory Management
- **Automated Cleanup**: Remove outdated or redundant information
- **Importance Scoring**: Automatically prioritize what to keep vs archive
- **Cross-Referencing**: Find and link related pieces of information
- **Usage Analytics**: Track which knowledge gets used most frequently

These semi-automated features would enhance productivity while maintaining human oversight and decision-making.

### ML Task Examples

**Research Tasks:**
- "Review latest NeurIPS papers on transformer architectures"
- "Implement SHAP explainability for current models"
- "Explore reinforcement learning for optimization problems"

**Code Evolution Tasks:**
- "Refactor authentication module for better performance"
- "Implement early stopping in training loops"
- "Add comprehensive error handling to API endpoints"

**Memory Optimization Tasks:**
- "Consolidate duplicate knowledge base entries"
- "Archive old interaction logs"
- "Optimize database indexes for better query performance"

**Model Optimization Tasks:**
- "Implement hyperparameter tuning pipeline"
- "Add cross-validation to model evaluation"
- "Fine-tune pre-trained models for specific use cases"

### Integration with Other Systems

**Learning Progress Plugin:**
- Automatically tracks all improvements and research activities
- Provides data for progress charts and metrics
- Stores detailed improvement logs with timestamps

**Task System:**
- All ML tasks integrate with the main task management system
- Supports priority levels, due dates, and categorization
- Enables cross-referencing with other project tasks

**Research Agent:**
- Use `"research [topic]"` commands to trigger deep research
- Findings automatically logged in the research tracking system
- Research reports saved for future reference

### Best Practices

**Consistent Tracking:**
- Mark tasks complete immediately when finished
- Log all research activities and findings
- Record performance metrics before and after improvements

**Regular Reviews:**
- Weekly: Review progress charts and adjust priorities
- Monthly: Deep dive into metrics and long-term trends
- Quarterly: Assess overall improvement strategy

**Quality Over Quantity:**
- Focus on meaningful improvements rather than busy work
- Prioritize high-impact changes that provide measurable benefits
- Document lessons learned from both successes and failures

**Research Integration:**
- Balance theoretical research with practical implementation
- Apply research findings to real problems
- Track which research leads to actual improvements

### Troubleshooting

**Charts Not Loading:**
- Ensure matplotlib is installed: `pip install matplotlib>=3.8.0`
- Check that the learning_progress plugin is loaded
- Verify data exists in the progress tracking files

**Tasks Not Updating:**
- Check that tasks.json file is writable
- Ensure proper JSON formatting in task files
- Try refreshing the ML tab manually

**Research Recommendations Not Appearing:**
- Verify research framework data is available
- Check that current tasks are properly categorized
- Ensure the AI model (Ollama) is running for recommendations

**Performance Issues:**
- ML tab auto-refreshes every 30 seconds
- Close the tab when not in use to reduce system load
- Consider increasing refresh interval in settings if needed

---

## AI & System

#### 🧠 LLM Router (`llm_router`)
Smart model selection based on query type.
| Profile | Model used for |
|---|---|
| fast | Quick questions, system info |
| smart | Complex analysis, writing |
| vision | Screen/image analysis |
| cad | 3D part generation |

| Command | Example |
|---|---|
| Switch model | `"switch to smart model"` |
| List models | `"list models"` |
| Router status | `"LLM router status"` |

#### 🌤 Weather Eye (`weather_eye`)
Local weather lookup via browser.
`"get weather"` / `"weather in London"`

#### 📡 Proactive Agent (`proactive`)
Automated briefings and status checks.
| Command | Example |
|---|---|
| Morning briefing | `"good morning"` |
| End of day | `"good night"` |
| Check urgent | `"what's urgent"` |
| Quick status | `"nexus status"` |

#### 📱 Web Remote (`web_remote`)
Control Nexus from your phone browser.
`"get phone URL"` — returns a local network URL to open on your phone.

---

### Documentation

#### 📖 Auto Documenter (`auto_documenter`)
Reads code files and generates Markdown documentation via Ollama.
| Command | Example |
|---|---|
| Document folder | `"document project at C:/Projects/myapp"` |
| Document file | `"document file C:/Projects/myapp/main.py"` |
| Generate README | `"generate README for C:/Projects/myapp"` |
| Summarize code | `"summarize code in C:/Projects/myapp/core"` |

#### 🎙 Meeting Notes (`meeting_notes`)
Records mic audio, transcribes with Whisper, summarizes with Ollama. Extracts action items.
| Command | Example |
|---|---|
| Start meeting | `"start meeting Project Kickoff"` |
| Stop meeting | `"stop meeting"` |
| List meetings | `"list meetings"` |

---

### Monitoring

#### 🔔 Uptime Monitor (`uptime_monitor`)
Monitors website uptime and sends alerts.
| Command | Example |
|---|---|
| Add site | `"monitor site mysite.com"` |
| Check all | `"check uptime"` |
| List sites | `"list monitored sites"` |

#### 🔍 Website Auditor (`website_auditor`)
Analyzes websites for performance, SEO, and broken links.
`"audit site mysite.com"`

#### 🔎 Lead Finder (`lead_finder`)
Searches for potential business leads.
`"find leads for software developers in London"`

---

## Configuration

`config/settings.json` key sections:

```json
{
  "ai": {
    "model": "llama3.2:3b",
    "ollama_host": "http://localhost:11434",
    "temperature": 0.3
  },
  "voice": {
    "whisper_model": "tiny",
    "voice_rate": 155,
    "voice_volume": 0.95,
    "wake_word": true,
    "sound_effects": true
  },
  "browser": {
    "headless": false,
    "slow_mo": 100
  },
  "smtp": {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "you@gmail.com",
    "smtp_pass": "your_app_password"
  }
}
```

---

## Data Storage

All plugin data is stored locally in `~/NexusScripts/`:

| File/Folder | Plugin |
|---|---|
| `expenses.json` | expense_tracker |
| `contracts/` | contract_generator |
| `email_drafts.json` | email_composer |
| `competitors.json` | competitor_tracker |
| `backup_config.json` | backup_manager |
| `.vault` + `.vault_salt` | password_vault |
| `pomodoro_log.json` | pomodoro |
| `habits.json` | habit_tracker |
| `calendar.json` | smart_calendar |
| `recordings/` | screen_recorder, browser_recorder |
| `language_progress.json` | language_coach |
| `dream_journal.json` | dream_journal |
| `qr_codes/` | qr_generator |
| `rag_index.json` | local_rag |
| `jarvis_memory_v2.json` | jarvis_memory_v2 |
| `knowledge_base.json` | knowledge_base |
| `research/` | research_agent |
| `ambient_log.json` | ambient_monitor |
| `focus_sessions.json` | focus_mode |
| `time_log.json` | time_tracker |
| `macros.json` | task_automator |
| `print_queue.json` | print_queue |
| `cad_parts/` | cad_engine |
| `NexusScripts/` | code_writer |
| `memory/` | memory_brain |

---

## Architecture

```
nexus/
├── main.py                  # Entry point + wiring
├── config/settings.json     # All configuration
├── core/
│   ├── assistant.py         # Ollama J.A.R.V.I.S. brain + fast routing
│   ├── plugin_manager.py    # BasePlugin ABC + auto-discovery
│   ├── browser_engine.py    # Playwright singleton
│   └── scheduler.py         # APScheduler task runner
├── ui/
│   ├── app_window.py        # Main CustomTkinter window
│   ├── chat_panel.py        # JARVIS chat UI with animations
│   ├── sidebar.py           # Arc reactor HUD + quick actions
│   ├── hud_canvas.py        # ArcReactor, ArcGauge, Waveform widgets
│   └── theme.py             # JARVIS color palette
└── plugins/
    └── {plugin_name}/
        └── plugin.py        # BasePlugin subclass (auto-discovered)
```

Each plugin implements:
```python
class MyPlugin(BasePlugin):
    name = "my_plugin"
    description = "..."
    icon = "🔌"

    async def connect(self) -> bool: ...
    async def execute(self, action: str, params: dict) -> str: ...
    def get_capabilities(self) -> list[dict]: ...
```

Plugins are auto-discovered — drop a folder with `plugin.py` into `plugins/` and restart.

---

## Version History

| Version | Changes |
|---|---|
| v1.0 | Initial release — email, WhatsApp, Discord, GitHub, file manager |
| v2.0 | Added CAD engine, code writer, task automator, vision AI, time tracker, proposal writer, client portal, browser recorder, hotkey daemon, LLM router, print queue, auto documenter, meeting notes |
| v2.1 | JARVIS UI overhaul — ArcReactor HUD, ArcGauge system stats, JARVIS chat style, SoundFX, neural TTS voice |
| v2.2 | +25 plugins: ambient monitor, focus mode, clipboard AI, app controller, research agent, news digest, knowledge base, PDF reader, expense tracker, contract generator, email composer, competitor tracker, system optimizer, backup manager, network scanner, password vault, pomodoro, habit tracker, smart calendar, screen recorder, language coach, dream journal, QR generator, local RAG, JARVIS memory v2 |
