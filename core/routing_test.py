"""
core/routing_test.py — Does JARVIS pick the right tool? (2.6)

~140 everyday phrases, each with the tool(s) that should handle it. Each phrase
goes to a small, cheap Gemini model together with EXACTLY what the voice model
sees (the same tool list + core/prompt.txt), and we check which tool it picks
(through more_tools, the tool named inside it). Wrong picks are listed so the
tool's description or the prompt can be fixed before you ever hit the problem.

Note: your live voice model is a different Gemini model, so this is a close
stand-in, not a perfect copy — it catches confusing tool descriptions and
overlaps, which is what usually causes wrong picks.

Cost: every phrase sends the whole tool list (~10k tokens) to the small model —
  quick (40 phrases) ≈ 3 US cents · full (all) ≈ 10–15 US cents.
"""
import json
import random
import threading
import time

# (phrase, acceptable tools)
CASES = [
    # holograms & gestures — the mix-up that happened before
    ("make a DNA hologram in teal", ("holograms",)),
    ("show me a galaxy hologram", ("holograms",)),
    ("remove all the holograms", ("holograms",)),
    ("explode the hologram", ("holograms",)),
    ("what hologram shapes are there", ("holograms",)),
    ("let me control the holograms with my hands", ("holograms",)),
    ("hologram gesture mode", ("holograms",)),
    ("switch to PC gesture mode", ("holograms", "gesture_control")),
    ("start gesture control so I can change the volume with my hand", ("gesture_control", "holograms")),
    ("turn off hand gestures", ("holograms", "gesture_control")),
    ("calibrate my gestures", ("gesture_calibration",)),
    ("my gestures aren't being recognised well, tune them to my hand", ("gesture_calibration",)),
    ("control the orb with my hand", ("orb_hand_control",)),
    # apps, web, weather
    ("open notepad", ("open_app",)),
    ("open Spotify", ("open_app", "music_control")),
    ("what's the weather in Pune", ("weather_report",)),
    ("will it rain tomorrow", ("weather_report", "rain_alert")),
    ("who won the last IPL final", ("web_search", "live_info")),
    ("search the web for the best budget laptops", ("web_search", "browser_control")),
    ("go to amazon.in", ("browser_control", "open_app")),
    ("scroll down", ("computer_control", "browser_control", "computer_settings")),
    # computer
    ("turn the volume up", ("computer_settings",)),
    ("set brightness to 50 percent", ("computer_settings",)),
    ("minimise all windows", ("computer_settings", "computer_control")),
    ("take a screenshot", ("computer_control", "computer_settings")),
    ("type hello world", ("computer_control", "computer_settings")),
    ("mute yourself", ("mic_control",)),
    ("stop listening for a while", ("mic_control",)),
    ("how's my computer doing", ("system_status", "pc_care", "system_alerts")),
    ("how much disk space is left", ("system_alerts", "system_status", "pc_care", "file_controller")),
    ("change my wallpaper", ("desktop_control",)),
    ("clean my temp files", ("pc_care",)),
    ("battery saver mode", ("system_plus", "computer_settings")),
    ("shut down the PC in 30 minutes", ("system_plus",)),
    ("close JARVIS", ("shutdown_jarvis",)),
    # media
    ("play Believer by Imagine Dragons", ("music_control", "youtube_video")),
    ("pause the music", ("music_control",)),
    ("next song", ("music_control",)),
    ("summarise this YouTube video", ("youtube_video",)),
    ("search YouTube for minecraft videos", ("youtube_video",)),
    ("play some study music", ("entertainment", "music_control")),
    ("tune my guitar", ("music_creative",)),
    ("start a metronome at 100", ("music_creative",)),
    # time & reminders
    ("remind me in 20 minutes to drink water", ("reminder", "timers_alarms")),
    ("set a timer for 10 minutes", ("timers_alarms",)),
    ("set an alarm for 6:30 am", ("timers_alarms",)),
    ("what time is it in Tokyo", ("world_clock",)),
    ("start focus mode for 30 minutes", ("focus_mode",)),
    ("start a pomodoro", ("pomodoro",)),
    # people & messages
    ("send a WhatsApp to Rahul saying I'm late", ("send_message",)),
    ("call Mom", ("make_phone_call",)),
    ("send this link to my phone", ("phone_tools",)),
    ("send Rahul happy birthday tomorrow at 9 am", ("comms_plus",)),
    ("control JARVIS from my phone with Telegram", ("telegram_bot",)),
    # Google
    ("what's on my calendar today", ("google_calendar",)),
    ("add a meeting tomorrow at 4 pm called science project", ("google_calendar",)),
    ("read my unread emails", ("gmail",)),
    ("reply to the last email saying thanks", ("gmail",)),
    # making things
    ("make a PowerPoint on the solar system", ("generate_ppt",)),
    ("write a Word document about climate change", ("generate_word_doc",)),
    ("make an Excel sheet of my timetable", ("generate_excel_sheet",)),
    ("generate an image of a robot on Mars", ("generate_image",)),
    ("edit the last image to make it night time", ("generate_image",)),
    ("write a python calculator", ("code_helper", "dev_agent")),
    ("build me a complete flask website project with several files", ("dev_agent", "code_helper")),
    # screen, files
    ("read what's on my screen", ("read_screen", "screen_process")),
    ("what do you see through my webcam", ("screen_process",)),
    ("close the camera", ("close_camera",)),
    ("find the photo of my dog", ("file_finder",)),
    ("move all PDFs from downloads to documents", ("file_controller", "downloads_tidy", "file_plus")),
    ("tidy up my downloads folder", ("downloads_tidy",)),
    ("what's in the file I just dropped", ("file_processor",)),
    ("merge the PDFs in my documents folder", ("file_plus",)),
    ("compress the photos in my pictures folder", ("media_plus",)),
    ("translate this window into Hindi", ("translate_window",)),
    ("clipboard history", ("clipboard_history",)),
    # writing & knowledge
    ("make this formal", ("writing_studio",)),
    ("summarise my clipboard", ("writing_studio",)),
    ("define photosynthesis", ("knowledge",)),
    ("explain gravity like I'm five", ("knowledge",)),
    ("solve 2x plus 5 equals 17", ("math_tools",)),
    ("what is 15 percent of 2400", ("math_tools", "desk_tools")),
    ("convert 5 miles to kilometres", ("desk_tools",)),
    ("Reliance share price", ("live_info",)),
    ("bitcoin price", ("live_info",)),
    ("India cricket score", ("cricket_scores",)),
    ("follow the India match", ("cricket_scores",)),
    ("where is the ISS right now", ("space_tracker",)),
    ("what's the moon phase tonight", ("space_tracker",)),
    ("my news digest", ("news_interests",)),
    ("find flights from Mumbai to Delhi next Friday", ("flight_finder",)),
    # school & learning
    ("quiz me on photosynthesis", ("study_mode", "learning_tools")),
    ("start a python lesson", ("python_tutor",)),
    ("practise Spanish with me", ("language_tutor",)),
    ("help with my homework, look at the worksheet I'm holding", ("homework_helper",)),
    ("add maths exam on 20 October", ("school_planner",)),
    ("record this lecture and make notes", ("lecture_notes",)),
    ("start dictation for my essay", ("dictation",)),
    ("record a voice memo", ("notes_tools",)),
    # life
    ("I spent 200 rupees on books", ("money_tracker",)),
    ("add a habit: read 20 minutes a day", ("habit_tracker",)),
    ("Rahul's birthday is on 5 March", ("birthdays",)),
    ("count my squats", ("workout_coach",)),
    ("breathing exercise", ("wellness",)),
    ("water reminders every hour", ("wellness",)),
    ("how long did I spend on Chrome today", ("screen_time",)),
    ("limit YouTube to one hour a day", ("app_limits",)),
    ("block instagram for an hour", ("site_blocker",)),
    ("add buy milk to my to-do list", ("todo_list",)),
    ("what's on my to-do list", ("todo_list",)),
    ("plan my day", ("planner_plus",)),
    ("wrap up my day", ("day_summary",)),
    ("start cooking mode for pasta", ("cooking_mode",)),
    ("interpret between me and my grandma, she speaks Marathi", ("interpreter_mode",)),
    # home & hardware
    ("turn on the bedroom lights", ("smart_lights", "home_arduino")),
    ("turn on the suit's eyes", ("hardware_control",)),
    ("what's the temperature in my room", ("home_arduino",)),
    ("watch my room while I'm away", ("security_watch",)),
    # games & fun
    ("play tic tac toe", ("games_plus",)),
    ("start a quiz show for Rahul and Priya", ("fun_games",)),
    ("tell me an adventure story where I choose what happens", ("story_mode",)),
    ("update my Steam games", ("game_updater",)),
    # modes & memory
    ("turn on demo mode", ("demo_mode_control",)),
    ("turn on demon mode", ("demon_mode_control",)),
    ("switch to the funny personality", ("personality",)),
    ("activate gaming protocol", ("protocols",)),
    ("what did we talk about yesterday", ("chat_history", "recall")),
    ("what did I say about my science project last week", ("recall", "recall_memory")),
    ("remember that my favourite colour is blue", ("save_memory",)),
    ("undo that", ("undo",)),
    ("find the weather and then email it to Dad", ("agent_task",)),
    # JARVIS itself
    ("run diagnostics", ("diagnostics",)),
    ("check for updates", ("jarvis_update",)),
    ("install the update I downloaded", ("jarvis_update",)),
    ("undo the last update", ("jarvis_update",)),
    ("make a bug report", ("bug_report",)),
    ("that didn't work, something went wrong, report it", ("bug_report",)),
    ("which tools do I use the most", ("tool_usage",)),
    ("switch off the tools I never use", ("tool_usage",)),
    ("test your tool routing", ("routing_test",)),
    ("only three heads-ups a day", ("heads_up",)),
    ("warn me 15 minutes before meetings", ("heads_up",)),
    ("back up JARVIS now", ("auto_backup", "github_save")),
    ("save my code to GitHub", ("github_save",)),
    ("make a zip of the whole Jarvis folder", ("github_save",)),
]
QUICK = 40


def pick_cases(quick: bool, available: set, seed: int | None = None) -> list:
    usable = [c for c in CASES if any(t in available for t in c[1])]
    if not quick:
        return usable
    rnd = random.Random(seed if seed is not None else int(time.time() // 86400))
    holo = [c for c in usable if any(t in ("holograms", "gesture_control", "gesture_calibration") for t in c[1])]
    rest = [c for c in usable if c not in holo]
    return holo[:6] + rnd.sample(rest, min(len(rest), QUICK - min(6, len(holo))))


def resolve(name: str, args: dict) -> str:
    """more_tools(tool=X) → X."""
    if name == "more_tools":
        return str((args or {}).get("tool") or "more_tools").strip().lower().replace(" ", "_")
    return name


def gemini_asker(decls: list, system: str, api_key: str, models: list):
    """Returns ask(phrase) → (tool name, args) using a small Gemini model."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key, http_options={"timeout": 45_000})
    fds = []
    for d in decls:
        try:
            params = d.get("parameters") if (d.get("parameters") or {}).get("properties") else None
            fds.append(types.FunctionDeclaration(name=d["name"], description=str(d.get("description", ""))[:4000],
                                                 **({"parameters": params} if params else {})))
        except Exception:
            pass
    cfg = types.GenerateContentConfig(
        system_instruction=system or None, tools=[types.Tool(function_declarations=fds)],
        tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="ANY")),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True), temperature=0.0)

    def ask(phrase: str):
        last = None
        for model in models:
            for attempt in range(4):
                try:
                    r = client.models.generate_content(model=model, contents=phrase, config=cfg)
                    calls = list(r.function_calls or [])
                    if calls:
                        return calls[0].name, dict(calls[0].args or {})
                    return "(no tool)", {}
                except Exception as e:
                    last = e
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        time.sleep(4 * (attempt + 1))       # free-tier rate limit → wait and retry
                        continue
                    break
        raise RuntimeError(str(last)[:160])
    return ask


def run(ask, cases: list, workers: int = 4, progress=None) -> dict:
    """ask(phrase) → (name, args). Returns {"passed", "total", "failures": [...], "errors": [...]}"""
    results = [None] * len(cases)
    idx = {"i": 0}
    lock = threading.Lock()

    def worker():
        while True:
            with lock:
                i = idx["i"]; idx["i"] += 1
            if i >= len(cases):
                return
            phrase, want = cases[i]
            try:
                name, args = ask(phrase)
                got = resolve(name, args)
                results[i] = ("ok" if got in want else "wrong", phrase, want, got)
            except Exception as e:
                results[i] = ("error", phrase, want, str(e))
            if progress:
                try:
                    progress(sum(1 for r in results if r), len(cases))
                except Exception:
                    pass
    ts = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, workers))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    ok = [r for r in results if r and r[0] == "ok"]
    return {"passed": len(ok), "total": len(cases),
            "failures": [{"phrase": r[1], "expected": list(r[2]), "got": r[3]} for r in results if r and r[0] == "wrong"],
            "errors": [{"phrase": r[1], "error": r[3]} for r in results if r and r[0] == "error"],
            "date": time.strftime("%Y-%m-%d %H:%M")}


def report_text(res: dict) -> str:
    tested = res["total"] - len(res["errors"])
    pct = res["passed"] / tested if tested else 0
    lines = [f"TOOL ROUTING TEST — {res.get('date', '')}",
             f"{res['passed']} of {tested} phrases went to the right tool ({pct:.0%})", ""]
    if res["failures"]:
        lines.append("WRONG TOOL:")
        lines += [f" ✗ \"{f['phrase']}\" → {f['got']}   (should be {' or '.join(f['expected'])})" for f in res["failures"]]
    if res["errors"]:
        lines += ["", f"COULDN'T TEST {len(res['errors'])} (network / key / rate limit):"]
        lines += [f" · \"{e['phrase']}\": {e['error'][:90]}" for e in res["errors"][:8]]
    if not res["failures"] and not res["errors"]:
        lines.append("Every phrase went to the right tool. ✓")
    lines += ["", "Stand-in check: a small Gemini model sees exactly the tools and prompt your voice model sees."]
    return "\n".join(lines)
