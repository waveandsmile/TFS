HIIT Trainer (Python)

Simple command-line HIIT trainer.

Features
- Add/list exercises (persisted to `exercises.json`)
- Start a live HIIT session: choose duration (20/40/60 min), work/rest durations, and focus group
- Controls during session: `p` pause/resume, `s` skip, `q` quit

Run

Open PowerShell in the project folder and run:

```powershell
python .\hiit.py
```

Notes
- The app persists exercises to `exercises.json` in the same folder.
- By default the script adds a few sample exercises if none exist.
- The implementation uses `msvcrt` for keypress detection on Windows; a Unix fallback is included but may require running the terminal in a compatible mode.

Extending
- Add more exercise fields if you want (difficulty, equipment, etc.).
- Replace random selection with a deterministic round-robin or configured workout templates.
- Add sound/beep with `winsound.Beep` (Windows) or `print('\a')`.
