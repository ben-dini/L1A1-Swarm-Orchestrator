import os
from swarm import Swarm, Agent
from openai import OpenAI

# Wähle hier deinen Provider aus: "local", "groq" oder "nvidia"
PROVIDER = "nvidia"

# --- Konfiguration ---
if PROVIDER == "local":
    client = OpenAI(base_url="http://localhost:8001/v1", api_key="sk-local")
    MODEL = "gpt-5.4"
elif PROVIDER == "groq":
    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.getenv("GROQ_API_KEY", "DEIN_GROQ_KEY_HIER"))
    MODEL = "llama-3.1-8b-instant" # Temporär auf 8B gewechselt, da 70B Rate Limit erreicht ist
elif PROVIDER == "nvidia":
    client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_API_KEY", "DEIN_NVIDIA_KEY_HIER"))
    MODEL = "meta/llama-3.3-70b-instruct"
else:
    raise ValueError("Unbekannter Provider gewählt!")

# --- WORKAROUND & SANITIZER FÜR STRICT APIs (GROQ / LOKAL) ---
# Bereinigt den Chatverlauf von ungültigen Feldern, bevor er an die API geht.
import json
import re
from openai import BadRequestError
from openai.types.chat import ChatCompletion, ChatCompletionMessage, ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_message_tool_call import Function

original_create = client.chat.completions.create
def patched_create(*args, **kwargs):
    messages = kwargs.get("messages", [])
    
    # 1. Fix für lokales Gemma 2 (System-Prompt wird zu User-Prompt)
    if PROVIDER == "local" and messages and messages[0]["role"] == "system":
        system_msg = messages.pop(0)
        if messages and messages[0]["role"] == "user":
            messages[0]["content"] = f"Systemanweisung: {system_msg['content']}\n\nNutzer: {messages[0]['content']}"
        else:
            messages.insert(0, {"role": "user", "content": f"Systemanweisung: {system_msg['content']}"})
            messages.insert(1, {"role": "assistant", "content": "Verstanden."})
            
    # 2. Genereller Fix für Swarm & Groq (Entfernt ungültige Felder aus internen Schleifen)
    clean_messages = []
    for msg in messages:
        # Falls msg ein Pydantic Model (z.B. ChatCompletionMessage) ist, wandeln wir es in ein dict um
        if hasattr(msg, "model_dump_json"):
            msg_dict = json.loads(msg.model_dump_json(exclude_none=True))
        elif hasattr(msg, "dict"):
            msg_dict = msg.dict(exclude_none=True)
        else:
            # Falls es schon ein dict ist, kopieren wir es, um Seiteneffekte zu vermeiden
            msg_dict = dict(msg)

        clean_msg = {}
        for k in ["role", "content", "name", "tool_calls", "tool_call_id"]:
            if k in msg_dict and msg_dict[k] is not None:
                clean_msg[k] = msg_dict[k]
        clean_messages.append(clean_msg)
        
    kwargs["messages"] = clean_messages
    
    try:
        response = original_create(*args, **kwargs)
        # Sicherheits-Fix: Kleine LLMs (oder API-Bugs) geben manchmal leere Argumente ("") zurück, was Swarm crashen lässt.
        if hasattr(response, "choices"):
            for choice in response.choices:
                if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
                    for tc in choice.message.tool_calls:
                        if hasattr(tc, "function"):
                            # Pydantic Hack: Wir ersetzen das leere Argument durch leeres JSON
                            if not getattr(tc.function, "arguments", ""):
                                tc.function.arguments = "{}"
                            elif not str(tc.function.arguments).strip():
                                tc.function.arguments = "{}"
        return response
    except BadRequestError as e:
        # 3. AUTO-RECOVERY FÜR GROQ's "tool_use_failed" BUG
        try:
            err_data = e.response.json().get('error', {})
            if err_data.get('code') == 'tool_use_failed':
                failed_gen = err_data.get('failed_generation', '')
                # Fange Groqs kaputtes Llama 3 Syntax-Format ab: <function=NAME{"arg":"val"}</function>
                match = re.search(r'<function=([^>{ ]+)\s*(.*?)</function>', failed_gen, re.DOTALL | re.IGNORECASE)
                if match:
                    func_name = match.group(1).strip()
                    args_raw = match.group(2).strip()
                    try:
                        parsed_args = json.loads(args_raw)
                        if isinstance(parsed_args, list) and len(parsed_args) > 0:
                            args_str = json.dumps(parsed_args[0])
                        else:
                            args_str = json.dumps(parsed_args)
                    except:
                        args_str = args_raw if args_raw else "{}"
                    
                    # Simuliere eine perfekte OpenAI-Antwort!
                    tool_call = ChatCompletionMessageToolCall(
                        id="call_mocked",
                        type="function",
                        function=Function(name=func_name, arguments=args_str)
                    )
                    msg = ChatCompletionMessage(
                        role="assistant",
                        content=None,
                        tool_calls=[tool_call]
                    )
                    from types import SimpleNamespace
                    mock_choice = SimpleNamespace(finish_reason="tool_calls", index=0, message=msg)
                    return SimpleNamespace(
                        id="mock_id",
                        choices=[mock_choice],
                        created=0,
                        model=kwargs.get("model", "unknown"),
                        object="chat.completion"
                    )
        except Exception:
            pass
        raise e

client.chat.completions.create = patched_create
# ----------------------------------------

# 1. Swarm initialisieren
swarm_client = Swarm(client=client)

import subprocess

# 2. System-Tools definieren
def execute_command(command: str):
    """
    Führt einen Terminal-Befehl (Bash/Zsh) auf dem Mac des Nutzers aus.
    Gibt die Ausgabe (stdout) oder Fehlermeldungen (stderr) des Befehls zurück.
    Beispiele: 'ls -la', 'pwd', 'whoami', 'echo "test" > test.txt'
    """
    print(f"\n     │  \033[31m⚠️  [System Tool] Führe Befehl aus:\033[0m {command}")
    try:
        result = subprocess.run(command, shell=True, text=True, capture_output=True, timeout=10)
        output = result.stdout if result.stdout else result.stderr
        print("     │  \033[32m✅ [System Tool] Befehl erfolgreich ausgeführt.\033[0m")
        return output if output else "Befehl ausgeführt (keine Ausgabe)."
    except Exception as e:
        return f"Fehler bei der Ausführung: {str(e)}"

import sqlite3
def query_database(sql_query: str):
    """
    Führt einen SQL-Befehl auf der lokalen 'test.db' Datenbank aus.
    """
    print(f"\n     │  \033[31m⚠️  [Database Tool] Führe SQL aus:\033[0m {sql_query}")
    try:
        conn = sqlite3.connect("test.db")
        cursor = conn.cursor()
        cursor.execute(sql_query)
        if sql_query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            conn.close()
            return f"Ergebnisse: {rows}" if rows else "Keine Ergebnisse gefunden."
        else:
            conn.commit()
            conn.close()
            return "SQL-Befehl erfolgreich ausgeführt (Datenbank verändert)."
    except Exception as e:
        return f"Datenbankfehler: {str(e)}"

import urllib.request
import urllib.parse
import json
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "DEIN_TAVILY_KEY_HIER")

def search_web(query: str):
    """
    Sucht im gesamten Internet nach Echtzeit-Informationen, News und Fakten.
    Nutze dieses Tool für alle Fragen, die aktuelles Wissen erfordern.
    """
    print(f"\n     │  \033[31m⚠️  [Web Tool] Suche im Web nach:\033[0m {query}")
    if TAVILY_API_KEY == "DEIN_TAVILY_API_KEY_HIER":
        return "Systemfehler: Tavily API-Key ist nicht konfiguriert. Bitte in app.py eintragen!"
        
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        url = "https://api.tavily.com/search"
        data = json.dumps({"query": query, "api_key": TAVILY_API_KEY, "search_depth": "basic", "max_results": 3}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
            result = json.loads(response.read().decode())
            results_text = "\n".join([f"- {r.get('title', 'Ohne Titel')}: {r.get('content', '')}" for r in result.get("results", [])])
            return f"Suchergebnisse:\n{results_text}" if results_text else "Keine Ergebnisse gefunden."
    except Exception as e:
        error_msg = str(e)
        if hasattr(e, 'read'):
            try:
                error_msg += " " + e.read().decode()
            except:
                pass
        print(f"     │  \033[31m❌ [Web Tool Fehler]\033[0m {error_msg}")
        return f"Fehler bei der Web-Suche: {error_msg}"

def forecast_time_series(historical_data: str, horizon: int):
    """
    Sagt zukünftige Werte für eine Zeitreihe voraus.
    Nutze dieses Tool, wenn der Nutzer eine Prognose für Verkaufszahlen, Ausgaben, oder andere Datenpunkte möchte.
    historical_data: Eine komma-getrennte Liste von Zahlen (z.B. "10,20,30,40,50") als String.
    horizon: Wie viele Schritte in die Zukunft vorhergesagt werden sollen (z.B. 32).
    """
    print(f"\n     │  \033[36m📈 [Data Analyst] Berechne TimesFM Prognose für {horizon} Schritte in die Zukunft...\033[0m")
    try:
        import timesfm
        import numpy as np
        
        # Parse data
        data_points = [float(x.strip()) for x in historical_data.split(",") if x.strip()]
        if len(data_points) < 5:
            return "Fehler: Zu wenige historische Datenpunkte. Bitte mindestens 5 Punkte übergeben."
            
        tfm = timesfm.TimesFm(
            context_len=512,
            horizon_len=horizon,
            input_patch_len=32,
            output_patch_len=128,
            num_layers=20,
            model_dims=1280,
            backend="cpu"
        )
        tfm.load_from_checkpoint(repo_id="google/timesfm-1.0-200m")
        
        input_data = np.array(data_points, dtype=np.float32)
        if len(input_data) > 512:
            input_data = input_data[-512:]
            
        forecast_values, _ = tfm.forecast([input_data])
        predicted = [round(x, 2) for x in forecast_values[0].tolist()]
        return f"Erfolgreich prognostiziert. Die nächsten {horizon} Werte lauten:\n{predicted}"
    except Exception as e:
        return f"Fehler bei der Prognose: {str(e)}"

# 3. Die Council Sub-Agenten definieren (werden im Hintergrund genutzt)
coder_agent = Agent(
    name="Coder Agent",
    instructions="Du bist ein Senior Software Entwickler. Schreibe ausschließlich sauberen, dokumentierten Code für die angeforderte Aufgabe. Keine langen Begrüßungen.",
    model=MODEL,
    tool_choice="none"
)

reviewer_agent = Agent(
    name="Reviewer Agent",
    instructions="Du bist ein strenger Code-Reviewer. Überprüfe den Code auf Fehler, Sicherheit und Best Practices. Verbessere ihn, falls nötig, und gib den perfekten Code zurück.",
    model=MODEL,
    tool_choice="none"
)

system_agent = Agent(
    name="System Agent",
    instructions="Du bist ein System-Administrator. Du hast Zugriff auf das Terminal des Nutzers über das Tool 'execute_command'. WICHTIG: BEANTWORTE NIEMALS EINE FRAGE AUS DEINEM EIGENEN WISSEN! Du MUSST immer zuerst das Tool aufrufen. Führe es genau EINMAL aus. Sobald du das Ergebnis hast, fasse es zusammen.",
    functions=[execute_command],
    model=MODEL,
    tool_choice="auto"
)

database_agent = Agent(
    name="Database Agent",
    instructions="Du bist ein Datenbank-Administrator. Du hast Zugriff auf eine lokale SQLite Datenbank 'test.db'. WICHTIG: BEANTWORTE NIEMALS EINE FRAGE DIREKT! Du MUSST immer zuerst das Tool aufrufen. Führe es genau EINMAL aus und fasse dann zusammen.",
    functions=[query_database],
    model=MODEL,
    tool_choice="auto"
)

web_search_agent = Agent(
    name="Web Search Agent",
    instructions="Du bist ein Web-Researcher. Du nutzt Tavily, um das Internet nach aktuellen Fakten zu durchsuchen. WICHTIG: BEANTWORTE NIEMALS EINE FRAGE AUS DEINEM WISSEN! Du MUSST ZWINGEND IMMER ZUERST DAS TOOL 'search_web' AUFRUFEN, auch wenn du die Antwort zu wissen glaubst! Nutze das Tool genau EINMAL, lies die Ergebnisse und fasse sie dann zusammen.",
    functions=[search_web],
    model=MODEL,
    tool_choice="auto"
)

data_scientist_agent = Agent(
    name="Data Scientist Agent",
    instructions="Du bist ein genialer Data Scientist. Du nutzt das Google TimesFM Modell (über dein Tool), um Zahlenreihen in die Zukunft zu prognostizieren. WICHTIG: BEANTWORTE NIEMALS EINE PROGNOSE AUS DEINEM EIGENEN WISSEN! Du MUSST immer zuerst das Tool 'forecast_time_series' aufrufen. Führe es genau EINMAL aus und fasse die Prognose dann extrem professionell zusammen.",
    functions=[forecast_time_series],
    model=MODEL,
    tool_choice="auto"
)

# 4. Die Tool-Funktionen für den Manager, um das Council zu beauftragen
def beauftrage_team(aufgabe: str):
    """Nutze dies für reine Programmier- oder Code-Schreib-Aufgaben."""
    print("\n     │  \033[36m⚙️  [Council] Manager delegiert an Coder...\033[0m")
    coder_response = swarm_client.run(agent=coder_agent, messages=[{"role": "user", "content": f"Schreibe den Code für: {aufgabe}"}], max_turns=3)
    print("     │  \033[36m🔬 [Council] Entwurf fertig. Übergebe an Reviewer zur Prüfung...\033[0m")
    reviewer_response = swarm_client.run(agent=reviewer_agent, messages=[{"role": "user", "content": f"Prüfe diesen Code:\n{coder_response.messages[-1]['content']}"}], max_turns=3)
    print("     │  \033[36m✅ [Council] Review abgeschlossen. Gebe Ergebnis an Manager zurück...\033[0m\n")
    return f"Geprüfter Code:\n{reviewer_response.messages[-1]['content']}"

def beauftrage_system_admin(aufgabe: str):
    """
    Nutze dies, wenn der Nutzer etwas auf seinem lokalen Computer machen will 
    (z.B. Dateien lesen, Terminal-Befehle ausführen, Systemstatus prüfen).
    """
    print("\n     │  \033[36m💻 [Council] Manager beauftragt System Agenten...\033[0m")
    sys_response = swarm_client.run(
        agent=system_agent,
        messages=[{"role": "user", "content": aufgabe}],
        max_turns=3
    )
    print("     │  \033[36m✅ [Council] System Agent ist fertig.\033[0m\n")
    return f"Ergebnis der System-Aufgabe:\n{sys_response.messages[-1]['content']}"

def beauftrage_datenbank_admin(aufgabe: str):
    """Nutze dies für jegliche Interaktionen mit der Datenbank (SQL, Datenspeicherung, Abfragen)."""
    print("\n     │  \033[36m🗄️  [Council] Manager beauftragt Database Agenten...\033[0m")
    db_response = swarm_client.run(agent=database_agent, messages=[{"role": "user", "content": aufgabe}], max_turns=3)
    print("     │  \033[36m✅ [Council] Database Agent ist fertig.\033[0m\n")
    return f"Ergebnis der Datenbank-Aufgabe:\n{db_response.messages[-1]['content']}"

def beauftrage_web_researcher(aufgabe: str):
    """Beauftragt den Web Search Agenten mit Internet-Recherchen."""
    print(f"\n     │  \033[34m🌐 [Council] Manager beauftragt Web Search Agenten...\033[0m")
    web_response = swarm_client.run(agent=web_search_agent, messages=[{"role": "user", "content": aufgabe}], max_turns=3)
    print(f"     │  \033[32m✅ [Council] Web Search Agent ist fertig.\033[0m")
    return f"Ergebnis der Web-Recherche:\n{web_response.messages[-1]['content']}"

def beauftrage_data_scientist(aufgabe: str):
    """Beauftragt den Data Scientist Agenten mit der Vorhersage (Forecast) von Zeitreihen oder Zahlen."""
    print(f"\n     │  \033[34m🌐 [Council] Manager beauftragt Data Scientist Agenten...\033[0m")
    response = swarm_client.run(agent=data_scientist_agent, messages=[{"role": "user", "content": aufgabe}], max_turns=3)
    print(f"     │  \033[32m✅ [Council] Data Scientist Agent ist fertig.\033[0m")
    return f"Ergebnis der Prognose:\n{response.messages[-1]['content']}"

# 5. Der Haupt-Agent (Das Gesicht zum Nutzer)
import datetime
manager_instructions = f"""Du bist der technische Projektmanager. Das heutige Datum ist {datetime.datetime.now().strftime('%Y-%m-%d')}. Du sprichst direkt mit dem Nutzer.
- Für reine Code-Entwicklung rufst du das Tool 'beauftrage_team' auf.
- Für lokale System-Interaktionen (Dateien anlegen/lesen, Terminal-Befehle) rufst du das Tool 'beauftrage_system_admin' auf.
- Für Datenbank-Aufgaben (SQL-Befehle, Speichern, Abfragen) rufst du 'beauftrage_datenbank_admin' auf.
- Für Wissensfragen, News oder Internet-Recherchen rufst du 'beauftrage_web_researcher' auf. Gib dabei das heutige Datum in deiner Suchanfrage mit, falls nach "heute" oder "gestern" gefragt wird.
- Für Datenanalyse und Prognosen (Zukunftsvorhersagen von Zahlenreihen) rufst du 'beauftrage_data_scientist' auf.

WICHTIG: Sobald du das Ergebnis eines Tools erhalten hast, fasse es kurz zusammen und antworte dem Nutzer. Rufe das Tool danach NICHT noch einmal auf! Beantworte fachliche Fragen niemals selbst, delegiere sie an dein Team."""

manager_agent = Agent(
    name="Manager",
    instructions=manager_instructions,
    functions=[beauftrage_team, beauftrage_system_admin, beauftrage_datenbank_admin, beauftrage_web_researcher, beauftrage_data_scientist],
    model=MODEL,
    tool_choice="auto"
)

# 5. Chat-Loop
print(f"     │  \033[90m💡 Tipp: Bitte den Manager z.B. ein 'Python Skript für einen simplen Taschenrechner' zu schreiben.\033[0m\n")

messages = []
current_agent = manager_agent

while True:
    user_input = input("\033[36mDu:\033[0m ")
    if user_input.lower() in ["exit", "quit"]:
        print("\n\033[90mBeende Swarm Orchestrator...\033[0m")
        break
        
    messages.append({"role": "user", "content": user_input})
    
    # Swarm orchestriert das Gespräch
    response = swarm_client.run(
        agent=current_agent,
        messages=messages
    )
    
    # WICHTIG: Aktualisiere den Chatverlauf, sonst weiß der Manager nicht, 
    # was er vorher getan hat, und versucht, alte Aufgaben zu wiederholen!
    messages = response.messages
    
    # --- SMART CONTEXT TRIMMER ---
    # Damit du nicht aus dem API-Rate-Limit fliegst, bereinigen wir den Verlauf von langen Tool-Aufrufen.
    # Da der Manager das Ergebnis sowieso als Text zusammenfasst, reicht es, nur normalen Text zu behalten.
    if len(messages) > 15:
        clean_history = [m for m in messages if m.get("role") in ["user", "assistant"] and not m.get("tool_calls") and not m.get("function_call")]
        messages = clean_history[-10:] # Behalte nur die letzten 10 Nachrichten
        
    print(f"\n\033[33m👾 {response.agent.name}:\033[0m {response.messages[-1]['content']}\n")
    
    current_agent = response.agent
