import ollama
import os
import json
import pyttsx3
import speech_recognition as sr
import threading
import subprocess
import time
from ddgs import DDGS

# --- 1. GLOBAL STATE ---
is_processing = False 
stop_event = threading.Event()
voice_lock = threading.Lock()
chat_history = []

def speak(text):
    if not text: return
    with voice_lock:
        print(f"\nJARVIS: {text}")
        engine = pyttsx3.init()
        engine.setProperty('rate', 190)
        engine.say(text)
        engine.runAndWait()
        engine.stop()

# --- 2. TOOLS ---
class JARVISTools:
    @staticmethod
    def run_system_command(command):
        try:
            subprocess.Popen(f'powershell -WindowStyle Hidden -Command "{command}"', shell=True)
            return "System task executed."
        except Exception as e:
            return f"System error: {e}"

    @staticmethod
    def web_search(query):
        """Fetches only the first snippet for speed."""
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=1))
                if not results: return "No live data found."
                return results[0].get('body', '')[:250]
        except Exception as e:
            return f"Search offline: {e}"

# --- 3. THE REASONING BRAIN (With Memory) ---
def run_jarvis_brain(user_input):
    global is_processing, chat_history
    is_processing = True
    stop_event.clear()
    
    # System Prompt
    system_instructions = {
        'role': 'system', 
        'content': """Your name is JARVIS. 
        - System task: {"tool": "run_system_command", "arg": "powershell_cmd"}
        - Live facts/News: {"tool": "web_search", "arg": "query"}
        - VERBAL RULES: Return ONLY the direct answer. No labels.
        - CONSTRAINT: Max 2 short sentences. Be cold and direct.
        - Use context from previous messages to answer follow-ups."""
    }
    
    # Build message list: [System, History..., Current User Input]
    messages = [system_instructions] + chat_history + [{'role': 'user', 'content': user_input}]
    
    try:
        response = ollama.chat(
            model='llama3.2', 
            options={'temperature': 0, 'num_predict': 60}, 
            messages=messages
        )
        
        if stop_event.is_set(): return
        raw = response.get('message', {}).get('content', "").strip()
        
        if "{" in raw and "}" in raw:
            try:
                json_match = raw[raw.find("{"):raw.rfind("}")+1]
                data = json.loads(json_match)
                tool, arg = data.get('tool'), data.get('arg')
                
                if tool == "run_system_command":
                    speak("Executing protocol.")
                    JARVISTools.run_system_command(arg)
                elif tool == "web_search":
                    result = JARVISTools.web_search(arg)
                    speak(result)
                    # Add search result to history so JARVIS remembers the facts found
                    chat_history.append({'role': 'assistant', 'content': result})
            except: 
                speak(raw)
        else:
            speak(raw)
            # Add verbal response to history
            chat_history.append({'role': 'assistant', 'content': raw})
        
        # Add the user input to history
        chat_history.append({'role': 'user', 'content': user_input})
        
        # Keep history short (last 6 items) to prevent lag and confusion
        if len(chat_history) > 6:
            chat_history = chat_history[-6:]

    finally:
        is_processing = False

# --- 4. SESSION MANAGEMENT ---
def start_session(r, source):
    global is_processing, chat_history
    speak("Systems online. Memory engaged.")
    
    while True:
        try:
            r.pause_threshold = 3.5
            
            if is_processing:
                print("\rJARVIS is Thinking...", end="", flush=True)
            else:
                print("\nListening...", end="", flush=True)
            
            audio = r.listen(source, timeout=10, phrase_time_limit=5)
            command = r.recognize_google(audio).lower()
            print(f"\nYou: {command}")

            # NEW: Manual memory clear
            if "clear memory" in command or "forget context" in command:
                chat_history = []
                speak("Memory banks cleared, sir.")
                continue

            if any(w in command for w in ["exit", "bye", "quit"]):
                speak("Goodbye, sir.")
                os._exit(0)

            if is_processing:
                speak("Busy. Stop?")
                conf_audio = r.listen(source, timeout=5)
                conf = r.recognize_google(conf_audio).lower()
                if "yes" in conf or "stop" in conf:
                    stop_event.set()
                    is_processing = False
                    speak("Resetting.")
                    continue

            threading.Thread(target=run_jarvis_brain, args=(command,), daemon=True).start()

        except sr.WaitTimeoutError: continue
        except sr.UnknownValueError: continue
        except Exception: break

def main():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("Calibrating...")
        r.adjust_for_ambient_noise(source, duration=1)
        speak("JARVIS in standby.")
        while True:
            try:
                audio = r.listen(source, timeout=None, phrase_time_limit=3)
                if "jarvis" in r.recognize_google(audio).lower():
                    start_session(r, source)
            except: continue

if __name__ == "__main__":
    main()