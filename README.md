# L1A1 Swarm Orchestrator 🐝

Ein robustes, fehlertolerantes Agenten-Netzwerk auf Basis des OpenAI Swarm Frameworks, optimiert für lokale Ausführung auf macOS mit Anbindung an NVIDIA NIM, Groq und lokale Modelle.

## 🔥 Features

- **Multi-Agent Architektur:** Beinhaltet spezialisierte Agenten für Web-Recherche (Tavily), System-Administration (Terminal-Ausführung), Datenbank-Abfragen (SQLite) und einen technischen Projektmanager, der als Orchestrator fungiert.
- **Smart Context Trimmer:** Verhindert explodierende Token-Kosten und API-Rate-Limits (429 Errors), indem versteckte System-Logs und Tool-Dumps automatisch aus dem Chatverlauf entfernt werden. Nur relevante Nutzer- und Assistant-Nachrichten bleiben im "Langzeitgedächtnis".
- **Groq Auto-Recovery Parser:** Behebt einen bekannten Bug, bei dem Llama-3 Modelle ungültige XML-Tags (`<function=...`) anstelle von JSON-Argumenten generieren. Das Skript fängt diese Fehler (z.B. `tool_use_failed`) per Regex ab und wandelt sie on-the-fly in gültiges JSON für Swarm um.
- **Pydantic Crash Protection:** Fängt fehlerhafte leere Argumente (`""`) kleinerer Sprachmodelle ab und wandelt sie in gültige `{}` JSON-Objekte um, bevor der Pydantic-Parser abstürzen kann (`JSONDecodeError: Expecting value`).
- **NVIDIA Llama 3.3 Integration:** Nutzt out-of-the-box das leistungsstarke `meta/llama-3.3-70b-instruct` Modell über die NVIDIA API (OpenAI-kompatibel).
- **L1A1 UI-Terminal:** Grafisch aufbereitetes Terminal-Interface (ASCII-Logo, farbige Boxen, Lade-Animationen und Status-Updates in Echtzeit).

---

## 🛠️ Installation & Setup

### Voraussetzungen
- macOS (für die `.command`-Datei empfohlen)
- Python 3.14+ (oder eine andere moderne Python 3 Version)
- API Keys für den gewünschten Provider (NVIDIA oder Groq) und Tavily.

### 1. Repository klonen
```bash
git clone https://github.com/ben-dini/L1A1-Swarm-Orchestrator.git
cd L1A1-Swarm-Orchestrator
```

### 2. Abhängigkeiten installieren
Das Framework benötigt das offizielle (aber oft nicht auf PyPI verfügbare) OpenAI Swarm Framework. Wir installieren es direkt aus dem GitHub Repository.
```bash
pip install -r requirements.txt
```

### 3. API Keys hinterlegen
Öffne die Datei `app.py` in deinem Lieblings-Editor und trage (falls nicht schon geschehen) deine API-Schlüssel ein:
```python
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "tvly-dein-key-hier")
# Sowie deine Keys unter den jeweiligen Providern (NVIDIA oder GROQ).
```

### 4. Ausführen
Auf macOS kannst du das Netzwerk einfach über einen Doppelklick auf die Starter-Datei starten:
```bash
chmod +x Start_L1A1_Swarm.command
./Start_L1A1_Swarm.command
```
Alternativ direkt über Python:
```bash
python3 app.py
```

---

## 🧠 Architektur der Agenten

- **Manager Agent:** Der Kopf des Systems. Er nimmt deine Fragen entgegen, analysiert sie (bekommt immer das tagesaktuelle Datum injiziert) und delegiert sie an den passenden Sub-Agenten.
- **Web Search Agent:** Ausgestattet mit Tavily. Durch striktes Prompt-Engineering (Zwangsjacke) ist es ihm verboten, Fragen aus seinem eigenen (oft veralteten) Gedächtnis zu beantworten. Er *muss* das Internet absuchen. Ein MacOS SSL-Bypass sorgt dafür, dass die Zertifikate problemlos verifiziert werden.
- **System Agent:** Kann Terminal-Befehle (z.B. `ls`, `mkdir`, `cat`) ausführen.
- **Database Agent:** Verbindet sich mit der lokalen `test.db` SQLite-Datenbank.

---

## 🚀 Bekannte Probleme (und wie sie hier gelöst wurden)
- **Tavily `SSL: CERTIFICATE_VERIFY_FAILED`:** Standard macOS Python-Installationen haben oft keine Root-Zertifikate. Die `app.py` nutzt einen Bypass (`ssl.CERT_NONE`), um das Problem zu umgehen.
- **API Rate Limit Exceeded:** Groq limitiert das 70B Modell auf 100k Tokens/Tag. Der eingebaute *Context Trimmer* reduziert den Token-Verbrauch drastisch um über 90% pro Interaktion.
- **NVIDIA `404 page not found`:** Alte `llama3-70b-instruct` Endpunkte wurden aktualisiert. Das Repo verweist standardmäßig auf das aktuelle `meta/llama-3.3-70b-instruct`.

Viel Spaß beim Orchestrieren deines eigenen L1A1 Schwarms! 🐝
