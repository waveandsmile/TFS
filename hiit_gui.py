"""
HIIT Trainer GUI using tkinter with HMI-style interface.
- Dark theme with accent colors
- Large, readable session window with Swedish labels
- Sound and visual feedback on transitions
- Exercise management (add, list, persist to JSON)
- Robust scheduling with weakref protection

Run: python hiit_gui.py
"""

import json
import os
import random
import time
import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont
import weakref

try:
    import winsound
except ImportError:
    winsound = None


DATA_FILE = os.path.join(os.path.dirname(__file__), 'exercises.json')


def _safe_tick(controller_ref):
    """Top-level safe caller for scheduled controller ticks (prevents Tcl errors)."""
    controller = controller_ref()
    if controller is None:
        return
    try:
        controller._tick()
    except Exception:
        pass


def clamp(v, a, b):
    """Clamp value v between a and b."""
    return max(a, min(b, v))


class Exercise:
    """Represents a single exercise with name, group, and time range."""
    def __init__(self, name, group, min_time=10, max_time=60, description=''):
        self.name = name
        self.group = group
        self.min_time = int(min_time)
        self.max_time = int(max_time)
        self.description = description

    def to_dict(self):
        return {
            'name': self.name,
            'group': self.group,
            'min_time': self.min_time,
            'max_time': self.max_time,
            'description': self.description,
        }

    @staticmethod
    def from_dict(d):
        return Exercise(
            d['name'],
            d['group'],
            d.get('min_time', 10),
            d.get('max_time', 60),
            d.get('description', '')
        )


def load_exercises():
    """Load exercises from JSON file."""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [Exercise.from_dict(x) for x in data]
    except Exception:
        return []


def save_exercises(ex_list):
    """Save exercises to JSON file."""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump([e.to_dict() for e in ex_list], f, indent=2, ensure_ascii=False)
    except Exception:
        pass


class SessionWindow(tk.Toplevel):
    """Large HMI-style session window showing current exercise, countdown, and next exercise."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title('HIIT Session')
        self.geometry('1000x700')

        # Fonts
        default_font = tkfont.nametofont('TkDefaultFont')
        self.title_font = tkfont.Font(family=default_font.actual('family'), size=24, weight='bold')
        self.big_font = tkfont.Font(family=default_font.actual('family'), size=60, weight='bold')
        self.mid_font = tkfont.Font(family=default_font.actual('family'), size=22, weight='bold')
        self.small_font = tkfont.Font(family=default_font.actual('family'), size=16)

        # Colors
        self.panel_color = '#111111'
        self.accent = '#ffbd2e'
        self.work_flash = '#223344'
        self.rest_flash = '#1a3322'

        self.configure(bg=self.panel_color)

        # Top: Total remaining time
        top = tk.Frame(self, bg=self.panel_color)
        top.pack(fill='x', pady=(18, 6))
        self.total_label = tk.Label(
            top, text='TRÄNINGSTID KVAR: 00:00',
            fg='white', bg=self.panel_color, font=self.title_font
        )
        self.total_label.pack()

        # Center: Current exercise and countdown
        center = tk.Frame(self, bg=self.panel_color)
        center.pack(fill='both', expand=True)
        self.current_label = tk.Label(
            center, text='NUVARANDE TRÄNING:',
            fg='gray80', bg=self.panel_color, font=self.mid_font
        )
        self.current_label.pack(pady=(10, 6))
        self.current_name = tk.Label(
            center, text='-', fg='white', bg=self.panel_color, font=self.big_font
        )
        self.current_name.pack(pady=(6, 10))
        self.current_time = tk.Label(
            center, text='00', fg=self.accent, bg=self.panel_color, font=self.big_font
        )
        self.current_time.pack()

        # Bottom: Next exercise preview
        bottom = tk.Frame(self, bg=self.panel_color)
        bottom.pack(fill='x', pady=18)
        self.next_label = tk.Label(
            bottom, text='NÄSTA TRÄNING: -',
            fg='gray80', bg=self.panel_color, font=self.small_font
        )
        self.next_label.pack()

        # Control buttons
        ctrl = tk.Frame(self, bg=self.panel_color)
        ctrl.pack(fill='x', pady=(6, 18))
        self.pause_btn = ttk.Button(ctrl, text='PAUSE', width=12)
        self.pause_btn.pack(side='left', padx=10)
        self.skip_btn = ttk.Button(ctrl, text='SKIP', width=12)
        self.skip_btn.pack(side='left', padx=10)
        self.stop_btn = ttk.Button(ctrl, text='STOP', width=12)
        self.stop_btn.pack(side='left', padx=10)

        self.transient(parent)
        self.grab_set()
        self._orig_bg = self.panel_color

    def _play_beep(self, freq=880, dur=120):
        """Play a beep sound (Windows only)."""
        try:
            if winsound:
                winsound.Beep(int(freq), int(dur))
        except Exception:
            pass

    def play_transition(self, kind='transition'):
        """Play a transition sound based on phase type."""
        if kind == 'start':
            self._play_beep(760, 110)
        elif kind == 'rest':
            self._play_beep(520, 110)
        elif kind == 'end':
            self._play_beep(980, 220)
        elif kind == 'tick':
            self._play_beep(1000, 60)
        else:
            self._play_beep(800, 100)

    def flash(self, color, duration=220):
        """Flash the background to a given color for a duration (ms)."""
        try:
            if not self.winfo_exists():
                return
            widgets = [self.total_label, self.current_label, self.current_name, self.current_time, self.next_label]
            self.config(bg=color)
            for w in widgets:
                try:
                    w.config(bg=color)
                except Exception:
                    pass
            self.after(duration, lambda: self._restore_flash(widgets))
        except Exception:
            pass

    def _restore_flash(self, widgets):
        """Restore background color after flash."""
        try:
            if not self.winfo_exists():
                return
            self.config(bg=self._orig_bg)
            for w in widgets:
                try:
                    w.config(bg=self._orig_bg)
                except Exception:
                    pass
        except Exception:
            pass

    def update_total(self, seconds):
        """Update total remaining time display."""
        try:
            if not self.winfo_exists():
                return
            m = seconds // 60
            s = seconds % 60
            self.total_label.config(text=f'TRÄNINGSTID KVAR: {m:02d}:{s:02d}')
        except Exception:
            pass

    def update_current(self, name):
        """Update current exercise name."""
        try:
            if not self.winfo_exists():
                return
            self.current_name.config(text=name)
        except Exception:
            pass

    def update_time(self, seconds):
        """Update countdown timer."""
        try:
            if not self.winfo_exists():
                return
            self.current_time.config(text=f'{seconds}s')
        except Exception:
            pass

    def update_next(self, name):
        """Update next exercise preview."""
        try:
            if not self.winfo_exists():
                return
            self.next_label.config(text=f'NÄSTA TRÄNING: {name}')
        except Exception:
            pass

    def close(self):
        """Close the session window gracefully."""
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


class SessionController:
    """Controls HIIT session timing, transitions, and updates."""
    def __init__(self, root, pool, period_minutes, work_sec, rest_sec, session_win=None):
        self.root = root
        self.pool = pool[:]
        self.period_seconds = int(period_minutes) * 60
        self.work_sec = int(work_sec)
        self.rest_sec = int(rest_sec)
        self.running = False
        self.paused = False
        self.skip_flag = False
        self._start_time = None
        self._elapsed = 0
        self.current_phase = None  # 'work' or 'rest'
        self.current_ex = None
        self.phase_remaining = 0.0
        self._last_whole = None  # Track last whole second for countdown beeps
        self.session_win = session_win

        # Register a persistent Tcl command to avoid callback loss
        try:
            self._tcl_name = self.root.register(lambda: _safe_tick(weakref.ref(self)))
        except Exception:
            self._tcl_name = None

    def start(self):
        """Start the session."""
        self.running = True
        self._start_time = time.time()
        self._elapsed = 0
        self._next_item()
        if self.session_win:
            try:
                self.session_win.play_transition('start')
                self.session_win.flash(self.session_win.work_flash, 180)
            except Exception:
                pass
        self._tick()

    def _next_item(self):
        """Pick a random exercise and start a work phase."""
        self.current_ex = random.choice(self.pool)
        self.phase_work = clamp(self.work_sec, self.current_ex.min_time, self.current_ex.max_time)
        self.current_phase = 'work'
        self.phase_remaining = float(self.phase_work)
        self._last_whole = None

        if self.session_win:
            self.session_win.update_current(self.current_ex.name)
            self.session_win.update_time(int(self.phase_remaining))
            next_ex = random.choice(self.pool)
            self.session_win.update_next(next_ex.name)
            try:
                self.session_win.play_transition('start')
                self.session_win.flash(self.session_win.work_flash, 220)
            except Exception:
                pass

    def _start_rest(self):
        """Start a rest phase."""
        self.current_phase = 'rest'
        self.phase_remaining = float(self.rest_sec)
        self._last_whole = None

        if self.session_win:
            self.session_win.update_current('VILA')
            self.session_win.update_time(int(self.phase_remaining))
            try:
                self.session_win.play_transition('rest')
                self.session_win.flash(self.session_win.rest_flash, 220)
            except Exception:
                pass

    def toggle_pause(self):
        """Toggle pause state."""
        self.paused = not self.paused

    def skip(self):
        """Skip to end of current phase."""
        self.skip_flag = True

    def stop(self):
        """Stop the session."""
        self.running = False
        if self.session_win:
            try:
                self.session_win.close()
            except Exception:
                pass
        if getattr(self, '_tcl_name', None):
            try:
                self.root.deletecommand(self._tcl_name)
            except Exception:
                pass

    def _tick(self):
        """Main update tick (called ~250ms)."""
        if not self.running:
            if self.session_win:
                try:
                    self.session_win.close()
                except Exception:
                    pass
            try:
                self.root.pause_btn.config(state='disabled')
                self.root.skip_btn.config(state='disabled')
                self.root.stop_btn.config(state='disabled')
            except Exception:
                pass
            return

        # Update elapsed time
        if not self.paused:
            dt = 0.25
            self.phase_remaining -= dt
            self._elapsed = int(time.time() - self._start_time)

        remaining_total = max(0, self.period_seconds - self._elapsed)

        # Update session window display
        if self.session_win:
            self.session_win.update_total(remaining_total)
            if self.paused:
                self.session_win.update_time(int(self.phase_remaining))
            else:
                rem = max(0, int(self.phase_remaining) + (1 if self.phase_remaining % 1 > 0 else 0))
                self.session_win.update_time(rem)
                # Countdown beeps for last 3 seconds
                try:
                    whole = int(self.phase_remaining)
                    if whole != self._last_whole and 0 < whole <= 3:
                        self._last_whole = whole
                        self.session_win.play_transition('tick')
                except Exception:
                    pass

        # Handle skip
        if self.skip_flag:
            self.skip_flag = False
            self.phase_remaining = 0

        # Handle phase transitions and completion
        if not self.paused and self.phase_remaining <= 0:
            if self.current_phase == 'work':
                if self._elapsed >= self.period_seconds:
                    self.running = False
                    if self.session_win:
                        try:
                            self.session_win.update_current('Passet klart!')
                            messagebox.showinfo('Klar', 'Passet färdigt! Bra jobbat!')
                        except Exception:
                            pass
                    return
                else:
                    self._start_rest()
            elif self.current_phase == 'rest':
                if self._elapsed >= self.period_seconds:
                    self.running = False
                    if self.session_win:
                        try:
                            self.session_win.update_current('Passet klart!')
                            messagebox.showinfo('Klar', 'Passet färdigt! Bra jobbat!')
                        except Exception:
                            pass
                    return
                else:
                    self._next_item()

        # Schedule next tick
        try:
            if getattr(self, '_tcl_name', None):
                self.root.after(250, self._tcl_name)
            else:
                self._after_cb = lambda cref=weakref.ref(self): _safe_tick(cref)
                self.root.after(250, self._after_cb)
        except Exception:
            try:
                self.root.after(250, self._tick)
            except Exception:
                pass


class HIITApp(tk.Tk):
    """Main HIIT trainer application window."""
    def __init__(self):
        super().__init__()
        self.title('HIIT Trainer')
        self.geometry('1000x600')

        self.style = ttk.Style(self)
        default_font = tkfont.nametofont('TkDefaultFont')
        self.large_font = tkfont.Font(family=default_font.actual('family'), size=16, weight='bold')
        self.hmi_font = tkfont.Font(family=default_font.actual('family'), size=12)
        self.style.configure('HMI.TLabelframe', font=self.large_font, padding=10)
        self.style.configure('HMI.TButton', font=self.hmi_font, padding=6)

        self.exercises = load_exercises()
        if not self.exercises:
            self._ensure_sample()

        self._build_ui()
        self._session = None

    def _ensure_sample(self):
        """Load sample exercises if none exist."""
        self.exercises.extend([
            Exercise('Push-ups', 'arms', 30, 60, 'Standard push-ups'),
            Exercise('Squats', 'legs', 30, 60, 'Bodyweight squats'),
            Exercise('Plank', 'core', 20, 60, 'Forearm plank'),
            Exercise('Jumping jacks', 'cardio', 20, 45, 'Full body cardio'),
        ])
        save_exercises(self.exercises)

    def _build_ui(self):
        """Build the main UI."""
        container = ttk.Frame(self)
        container.pack(fill='both', expand=True, padx=12, pady=12)
        container.columnconfigure(0, weight=0)
        container.columnconfigure(1, weight=1)

        # Left: Options panel
        frame_opts = ttk.LabelFrame(container, text='Session Options', style='HMI.TLabelframe')
        frame_opts.grid(row=0, column=0, sticky='ns', padx=(0, 10), pady=4)

        # Period selection
        period_frame = ttk.Frame(frame_opts)
        period_frame.pack(anchor='w', pady=6)
        ttk.Label(period_frame, text='Välj period:').pack(side='left')
        self.period_var = tk.IntVar(value=20)
        for val, txt in ((20, '20 min'), (40, '40 min'), (60, '60 min')):
            ttk.Radiobutton(period_frame, text=txt, value=val, variable=self.period_var).pack(side='left', padx=6)

        # Intensity settings
        intensity_frame = ttk.Frame(frame_opts)
        intensity_frame.pack(anchor='w', pady=6)
        ttk.Label(intensity_frame, text='Träna (s)').pack(side='left')
        self.work_var = tk.IntVar(value=30)
        ttk.Spinbox(intensity_frame, from_=5, to=300, textvariable=self.work_var, width=6).pack(side='left', padx=6)
        ttk.Label(intensity_frame, text='Vila (s)').pack(side='left')
        self.rest_var = tk.IntVar(value=15)
        ttk.Spinbox(intensity_frame, from_=5, to=300, textvariable=self.rest_var, width=6).pack(side='left', padx=6)

        # Focus group selection
        focus_frame = ttk.Frame(frame_opts)
        focus_frame.pack(anchor='w', pady=6)
        ttk.Label(focus_frame, text='Fokus:').pack(side='left')
        self.focus_var = tk.StringVar(value='Mixed')
        self._refresh_focus_menu()
        self.focus_menu = tk.OptionMenu(focus_frame, self.focus_var, 'Mixed')
        self.focus_menu.pack(side='left', padx=6)
        # Populate menu
        menu = self.focus_menu['menu']
        menu.delete(0, 'end')
        for choice in self.focus_choices:
            menu.add_command(label=choice, command=lambda v=choice: self.focus_var.set(v))

        # Control buttons
        btn_frame = ttk.Frame(frame_opts)
        btn_frame.pack(anchor='w', pady=12)
        ttk.Button(btn_frame, text='Starta träning', command=self.on_start, style='HMI.TButton').pack(side='left', pady=6)
        ttk.Button(btn_frame, text='Lägg till träningstyp', command=self.on_add_exercise, style='HMI.TButton').pack(side='left', padx=6)
        ttk.Button(btn_frame, text='Uppdatera', command=self.refresh_exercises, style='HMI.TButton').pack(side='left', padx=6)

        # Right: Exercise list and session controls
        right = ttk.Frame(container)
        right.grid(row=0, column=1, sticky='nswe')

        preview_frame = ttk.LabelFrame(right, text='Översikt', style='HMI.TLabelframe')
        preview_frame.pack(fill='both', expand=True, padx=6, pady=4)
        self.preview_info = tk.Label(preview_frame, text='Klar för träning', font=self.large_font, anchor='center')
        self.preview_info.pack(fill='both', expand=True, padx=12, pady=12)

        list_frame = ttk.LabelFrame(right, text='Träningstyper', style='HMI.TLabelframe')
        list_frame.pack(fill='both', expand=True, padx=6, pady=4)
        self.ex_listbox = tk.Listbox(list_frame, height=12, font=self.hmi_font)
        self.ex_listbox.pack(side='left', fill='both', expand=True, padx=(6, 0), pady=6)
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.ex_listbox.yview)
        scrollbar.pack(side='left', fill='y')
        self.ex_listbox.config(yscrollcommand=scrollbar.set)
        self._populate_listbox()

        ctrl = ttk.Frame(right)
        ctrl.pack(fill='x', padx=6, pady=6)
        self.pause_btn = ttk.Button(ctrl, text='Pausa', command=self.on_pause, state='disabled', style='HMI.TButton')
        self.pause_btn.pack(side='left', padx=6)
        self.skip_btn = ttk.Button(ctrl, text='Hoppa', command=self.on_skip, state='disabled', style='HMI.TButton')
        self.skip_btn.pack(side='left', padx=6)
        self.stop_btn = ttk.Button(ctrl, text='Stoppa', command=self.on_stop, state='disabled', style='HMI.TButton')
        self.stop_btn.pack(side='left', padx=6)

    def _refresh_focus_menu(self):
        """Refresh available exercise groups."""
        groups = sorted(set(e.group for e in self.exercises))
        self.focus_choices = ['Mixed'] + groups
        if self.focus_var.get() not in self.focus_choices:
            self.focus_var.set('Mixed')

    def _populate_listbox(self):
        """Populate exercise listbox."""
        self.ex_listbox.delete(0, tk.END)
        for e in self.exercises:
            self.ex_listbox.insert(tk.END, f"{e.name} [{e.group}] {e.min_time}s-{e.max_time}s")

    def refresh_exercises(self):
        """Reload exercises and update UI."""
        self.exercises = load_exercises()
        self._refresh_focus_menu()
        menu = self.focus_menu['menu']
        menu.delete(0, 'end')
        for choice in self.focus_choices:
            menu.add_command(label=choice, command=lambda v=choice: self.focus_var.set(v))
        self._populate_listbox()
        self.preview_info.config(text=f'{len(self.exercises)} träningstyper')

    def on_add_exercise(self):
        """Open add exercise dialog."""
        dlg = AddExerciseDialog(self)
        self.wait_window(dlg)
        if dlg.saved:
            self.exercises.append(dlg.exercise)
            save_exercises(self.exercises)
            self.refresh_exercises()

    def on_start(self):
        """Start a new session."""
        if self._session and self._session.running:
            messagebox.showinfo('Körs redan', 'Ett pass körs redan')
            return
        period = self.period_var.get()
        work = self.work_var.get()
        rest = self.rest_var.get()
        focus = self.focus_var.get()

        if focus == 'Mixed':
            focus_groups = sorted(set(e.group for e in self.exercises))
        else:
            focus_groups = [focus]

        pool = [e for e in self.exercises if e.group in focus_groups]
        if not pool:
            messagebox.showwarning('Ingen träning', 'Inga träningstyper matchar vald fokus')
            return

        session_win = SessionWindow(self)
        self._session = SessionController(self, pool, period, work, rest, session_win)
        session_win.pause_btn.config(command=self._session.toggle_pause)
        session_win.skip_btn.config(command=self._session.skip)
        session_win.stop_btn.config(command=self._session.stop)
        self._session.start()

        self.pause_btn.config(state='normal')
        self.skip_btn.config(state='normal')
        self.stop_btn.config(state='normal')

    def on_pause(self):
        """Toggle pause."""
        if not self._session:
            return
        self._session.toggle_pause()

    def on_skip(self):
        """Skip current phase."""
        if self._session:
            self._session.skip()

    def on_stop(self):
        """Stop session."""
        if self._session:
            self._session.stop()
            self._session = None
            self.preview_info.config(text='Klar för träning')
            self.pause_btn.config(state='disabled')
            self.skip_btn.config(state='disabled')
            self.stop_btn.config(state='disabled')


class AddExerciseDialog(tk.Toplevel):
    """Dialog to add a new exercise."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title('Lägg till träningstyp')
        self.saved = False
        self.exercise = None
        self.transient(parent)
        self.grab_set()

        ttk.Label(self, text='Träningsnamn').grid(row=0, column=0, sticky='w', padx=6, pady=4)
        self.e_name = ttk.Entry(self, width=40)
        self.e_name.grid(row=0, column=1, padx=6, pady=4)

        ttk.Label(self, text='Grupp').grid(row=1, column=0, sticky='w', padx=6, pady=4)
        self.e_group = ttk.Entry(self, width=20)
        self.e_group.grid(row=1, column=1, sticky='w', padx=6, pady=4)

        ttk.Label(self, text='Min sekunder').grid(row=2, column=0, sticky='w', padx=6, pady=4)
        self.e_min = ttk.Spinbox(self, from_=5, to=600, width=8)
        self.e_min.set(30)
        self.e_min.grid(row=2, column=1, sticky='w', padx=6, pady=4)

        ttk.Label(self, text='Max sekunder').grid(row=3, column=0, sticky='w', padx=6, pady=4)
        self.e_max = ttk.Spinbox(self, from_=5, to=600, width=8)
        self.e_max.set(60)
        self.e_max.grid(row=3, column=1, sticky='w', padx=6, pady=4)

        ttk.Label(self, text='Beskrivning').grid(row=4, column=0, sticky='w', padx=6, pady=4)
        self.e_desc = ttk.Entry(self, width=40)
        self.e_desc.grid(row=4, column=1, padx=6, pady=4)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=8)
        ttk.Button(btn_frame, text='Spara', command=self.on_save).pack(side='left', padx=6)
        ttk.Button(btn_frame, text='Avbryt', command=self.destroy).pack(side='left', padx=6)

    def on_save(self):
        """Validate and save exercise."""
        name = self.e_name.get().strip()
        group = self.e_group.get().strip() or 'general'
        try:
            min_t = int(self.e_min.get())
            max_t = int(self.e_max.get())
        except ValueError:
            messagebox.showerror('Invalid', 'Min/Max must be numbers')
            return
        if not name:
            messagebox.showerror('Invalid', 'Name required')
            return
        if min_t <= 0 or max_t <= 0 or min_t > max_t:
            messagebox.showerror('Invalid', 'Min/Max range invalid')
            return
        desc = self.e_desc.get().strip()
        self.exercise = Exercise(name, group, min_t, max_t, desc)
        self.saved = True
        self.destroy()


if __name__ == '__main__':
    app = HIITApp()
    app.mainloop()



def load_exercises():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [Exercise.from_dict(x) for x in data]
    except Exception:
        return []


def save_exercises(ex_list):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump([e.to_dict() for e in ex_list], f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def clamp(v, a, b):
    return max(a, min(b, v))


class SessionWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title('HIIT Session')
        self.geometry('1000x700')
        default_font = tkfont.nametofont('TkDefaultFont')
        self.title_font = tkfont.Font(family=default_font.actual('family'), size=24, weight='bold')
        self.big_font = tkfont.Font(family=default_font.actual('family'), size=60, weight='bold')
        self.mid_font = tkfont.Font(family=default_font.actual('family'), size=22, weight='bold')
        self.small_font = tkfont.Font(family=default_font.actual('family'), size=16)
        self.panel_color = '#111111'
        self.accent = '#ffbd2e'
        self.work_flash = '#223344'
        self.rest_flash = '#1a3322'
        self.configure(bg=self.panel_color)
        top = tk.Frame(self, bg=self.panel_color)
        top.pack(fill='x', pady=(18, 6))
        self.total_label = tk.Label(top, text='TRÄNINGSTID KVAR: 00:00', fg='white', bg=self.panel_color, font=self.title_font)
        self.total_label.pack()
        center = tk.Frame(self, bg=self.panel_color)
        center.pack(fill='both', expand=True)
        self.current_label = tk.Label(center, text='NUVARANDE TRÄNING:', fg='gray80', bg=self.panel_color, font=self.mid_font)
        self.current_label.pack(pady=(10, 6))
        self.current_name = tk.Label(center, text='-', fg='white', bg=self.panel_color, font=self.big_font)
        self.current_name.pack(pady=(6, 10))
        self.current_time = tk.Label(center, text='00', fg=self.accent, bg=self.panel_color, font=self.big_font)
        self.current_time.pack()
        bottom = tk.Frame(self, bg=self.panel_color)
        bottom.pack(fill='x', pady=18)
        self.next_label = tk.Label(bottom, text='NÄSTA TRÄNING: -', fg='gray80', bg=self.panel_color, font=self.small_font)
        self.next_label.pack()
        ctrl = tk.Frame(self, bg=self.panel_color)
        ctrl.pack(fill='x', pady=(6, 18))
        self.pause_btn = ttk.Button(ctrl, text='PAUSE', width=12)
        self.pause_btn.pack(side='left', padx=10)
        self.skip_btn = ttk.Button(ctrl, text='SKIP', width=12)
        self.skip_btn.pack(side='left', padx=10)
        self.stop_btn = ttk.Button(ctrl, text='STOP', width=12)
        self.stop_btn.pack(side='left', padx=10)
        self.transient(parent)
        self.grab_set()
        self._orig_bg = self.panel_color

    def _play_beep(self, freq=880, dur=120):
        try:
            if winsound:
                winsound.Beep(int(freq), int(dur))
        except Exception:
            pass

    def play_transition(self, kind='transition'):
        if kind == 'start':
            self._play_beep(760, 110)
        elif kind == 'rest':
            self._play_beep(520, 110)
        elif kind == 'end':
            self._play_beep(980, 220)
        elif kind == 'tick':
            self._play_beep(1000, 60)
        else:
            self._play_beep(800, 100)

    def flash(self, color, duration=220):
        try:
            if not self.winfo_exists():
                return
            widgets = [self.total_label, self.current_label, self.current_name, self.current_time, self.next_label]
            self.config(bg=color)
            for w in widgets:
                try:
                    w.config(bg=color)
                except Exception:
                    pass
            self.after(duration, lambda: self._restore_flash(widgets))
        except Exception:
            pass

    def _restore_flash(self, widgets):
        try:
            if not self.winfo_exists():
                return
            self.config(bg=self._orig_bg)
            for w in widgets:
                try:
                    w.config(bg=self._orig_bg)
                except Exception:
                    pass
        except Exception:
            pass

    def update_total(self, seconds):
        try:
            if not self.winfo_exists():
                return
            m = seconds // 60
            s = seconds % 60
            self.total_label.config(text=f'TRÄNINGSTID KVAR: {m:02d}:{s:02d}')
        except Exception:
            pass

    def update_current(self, name):
        try:
            if not self.winfo_exists():
                return
            self.current_name.config(text=name)
        except Exception:
            pass

    def update_time(self, seconds):
        try:
            if not self.winfo_exists():
                return
            self.current_time.config(text=f'{seconds}s')
        except Exception:
            pass

    def update_next(self, name):
        try:
            if not self.winfo_exists():
                return
            self.next_label.config(text=f'NÄSTA TRÄNING: {name}')
        except Exception:
            pass

    def close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


class SessionController:
    def __init__(self, root, pool, period_minutes, work_sec, rest_sec, session_win=None):
        self.root = root
        self.pool = pool[:]
        self.period_seconds = int(period_minutes) * 60
        self.work_sec = int(work_sec)
        self.rest_sec = int(rest_sec)
        self.running = False
        self.paused = False
        self.skip_flag = False
        self._start_time = None
        self._elapsed = 0
        self.current_phase = None
        self.current_ex = None
        self.phase_remaining = 0.0
        self._last_whole = None
        self.session_win = session_win
        try:
            self._tcl_name = self.root.register(lambda: _safe_tick(weakref.ref(self)))
        except Exception:
            self._tcl_name = None

    def start(self):
        self.running = True
        self._start_time = time.time()
        self._elapsed = 0
        self._next_item()
        if self.session_win:
            try:
                self.session_win.play_transition('start')
                self.session_win.flash(self.session_win.work_flash, 180)
            except Exception:
                pass
        self._tick()

    def _next_item(self):
        self.current_ex = random.choice(self.pool)
        self.phase_work = clamp(self.work_sec, self.current_ex.min_time, self.current_ex.max_time)
        self.current_phase = 'work'
        self.phase_remaining = float(self.phase_work)
        self._last_whole = None
        if self.session_win:
            self.session_win.update_current(self.current_ex.name)
            self.session_win.update_time(int(self.phase_remaining))
            next_ex = random.choice(self.pool)
            self.session_win.update_next(next_ex.name)
            try:
                self.session_win.play_transition('start')
                self.session_win.flash(self.session_win.work_flash, 220)
            except Exception:
                pass
        else:
            try:
                self.root.preview_info.config(text=f'WORK: {self.current_ex.name} - {int(self.phase_remaining)}s')
            except Exception:
                pass

    def _start_rest(self):
        self.current_phase = 'rest'
        self.phase_remaining = float(self.rest_sec)
        self._last_whole = None
        if self.session_win:
            self.session_win.update_current('VILA')
            self.session_win.update_time(int(self.phase_remaining))
            try:
                self.session_win.play_transition('rest')
                self.session_win.flash(self.session_win.rest_flash, 220)
            except Exception:
                pass
        else:
            try:
                self.root.preview_info.config(text=f'REST: {int(self.phase_remaining)}s')
            except Exception:
                pass

    def toggle_pause(self):
        self.paused = not self.paused

    def skip(self):
        self.skip_flag = True

    def stop(self):
        self.running = False
        if self.session_win:
            try:
                self.session_win.close()
            except Exception:
                pass
        if getattr(self, '_tcl_name', None):
            try:
                self.root.deletecommand(self._tcl_name)
            except Exception:
                pass

    def _tick(self):
        if not self.running:
            if self.session_win:
                try:
                    self.session_win.close()
                except Exception:
                    pass
            else:
                try:
                    self.root.preview_info.config(text='Not running')
                except Exception:
                    pass
            try:
                self.root.pause_btn.config(state='disabled')
                self.root.skip_btn.config(state='disabled')
                self.root.stop_btn.config(state='disabled')
            except Exception:
                pass
            return

        if not self.paused:
            dt = 0.25
            self.phase_remaining -= dt
            self._elapsed = int(time.time() - self._start_time)

        remaining_total = max(0, self.period_seconds - self._elapsed)
        if self.session_win:
            self.session_win.update_total(remaining_total)
            if self.paused:
                self.session_win.update_time(int(self.phase_remaining))
            else:
                rem = max(0, int(self.phase_remaining) + (1 if self.phase_remaining - int(self.phase_remaining) > 0 else 0))
                self.session_win.update_time(rem)
                try:
                    whole = int(self.phase_remaining)
                    if whole != self._last_whole and whole <= 3 and whole > 0:
                        self._last_whole = whole
                        try:
                            self.session_win.play_transition('tick')
                        except Exception:
                            pass
                except Exception:
                    pass
        else:
            try:
                if self.paused:
                    self.root.preview_info.config(text=f'PAUSED {int(self.phase_remaining)}s')
                else:
                    rem = max(0, int(self.phase_remaining) + (1 if self.phase_remaining - int(self.phase_remaining) > 0 else 0))
                    self.root.preview_info.config(text=f'{rem}s - {self.current_phase}')
            except Exception:
                pass

        if self.skip_flag:
            self.skip_flag = False
            self.phase_remaining = 0

        if not self.paused and self.phase_remaining <= 0:
            if self.current_phase == 'work':
                if self._elapsed >= self.period_seconds:
                    self.running = False
                    if self.session_win:
                        try:
                            self.session_win.update_current('Passet klart!')
                        except Exception:
                            pass
                        messagebox.showinfo('Klar', 'Passet färdigt! Bra jobbat!')
                    else:
                        messagebox.showinfo('Done', 'Session complete! Great job!')
                    return
                else:
                    self._start_rest()
            elif self.current_phase == 'rest':
                if self._elapsed >= self.period_seconds:
                    self.running = False
                    if self.session_win:
                        try:
                            self.session_win.update_current('Passet klart!')
                        except Exception:
                            pass
                        messagebox.showinfo('Klar', 'Passet färdigt! Bra jobbat!')
                    else:
                        messagebox.showinfo('Done', 'Session complete! Great job!')
                    return
                else:
                    self._next_item()

        try:
            if getattr(self, '_tcl_name', None):
                self.root.after(250, self._tcl_name)
            else:
                self._after_cb = (lambda cref=weakref.ref(self): _safe_tick(cref))
                self.root.after(250, self._after_cb)
        except Exception:
            try:
                self.root.after(250, self._tick)
            except Exception:
                pass


class HIITApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('HIIT Trainer')
        self.geometry('1000x600')
        self.style = ttk.Style(self)
        default_font = tkfont.nametofont('TkDefaultFont')
        self.large_font = tkfont.Font(family=default_font.actual('family'), size=16, weight='bold')
        self.hmi_font = tkfont.Font(family=default_font.actual('family'), size=12)
        self.style.configure('HMI.TLabelframe', font=self.large_font, padding=10)
        self.style.configure('HMI.TButton', font=self.hmi_font, padding=6)
        self.exercises = load_exercises()
        if not self.exercises:
            self._ensure_sample()
        self._build_ui()
        self._session = None

    def _ensure_sample(self):
        self.exercises.extend([
            Exercise('Push-ups', 'arms', 30, 60, 'Standard push-ups'),
            Exercise('Squats', 'legs', 30, 60, 'Bodyweight squats'),
            Exercise('Plank', 'core', 20, 60, 'Forearm plank'),
            Exercise('Jumping jacks', 'cardio', 20, 45, 'Full body cardio'),
        ])
        save_exercises(self.exercises)

    def _build_ui(self):
        container = ttk.Frame(self)
        container.pack(fill='both', expand=True, padx=12, pady=12)
        container.columnconfigure(0, weight=0)
        container.columnconfigure(1, weight=1)
        frame_opts = ttk.LabelFrame(container, text='Session Options', style='HMI.TLabelframe')
        frame_opts.grid(row=0, column=0, sticky='ns', padx=(0,10), pady=4)
        period_frame = ttk.Frame(frame_opts)
        period_frame.pack(anchor='w', pady=6)
        ttk.Label(period_frame, text='Välj period:').pack(side='left')
        self.period_var = tk.IntVar(value=20)
        for val, txt in ((20, '20 min'), (40, '40 min'), (60, '60 min')):
            ttk.Radiobutton(period_frame, text=txt, value=val, variable=self.period_var).pack(side='left', padx=6)
        intensity_frame = ttk.Frame(frame_opts)
        intensity_frame.pack(anchor='w', pady=6)
        ttk.Label(intensity_frame, text='Träna (s)').pack(side='left')
        self.work_var = tk.IntVar(value=30)
        ttk.Spinbox(intensity_frame, from_=5, to=300, textvariable=self.work_var, width=6).pack(side='left', padx=6)
        ttk.Label(intensity_frame, text='Vila (s)').pack(side='left')
        self.rest_var = tk.IntVar(value=15)
        ttk.Spinbox(intensity_frame, from_=5, to=300, textvariable=self.rest_var, width=6).pack(side='left', padx=6)
        focus_frame = ttk.Frame(frame_opts)
        focus_frame.pack(anchor='w', pady=6)
        ttk.Label(focus_frame, text='Fokus:').pack(side='left')
        self.focus_var = tk.StringVar(value='Mixed')
        self._refresh_focus_menu()
        self.focus_menu = tk.OptionMenu(focus_frame, self.focus_var, 'Mixed')
        self.focus_menu.pack(side='left', padx=6)
        # Populate menu items
        menu = self.focus_menu['menu']
        menu.delete(0, 'end')
        for choice in self.focus_choices:
            menu.add_command(label=choice, command=lambda v=choice: self.focus_var.set(v))
        btn_frame = ttk.Frame(frame_opts)
        btn_frame.pack(anchor='w', pady=12)
        ttk.Button(btn_frame, text='Starta träning', command=self.on_start, style='HMI.TButton').pack(side='left', pady=6)
        ttk.Button(btn_frame, text='Lägg till träningstyp', command=self.on_add_exercise, style='HMI.TButton').pack(side='left', padx=6)
        ttk.Button(btn_frame, text='Uppdatera', command=self.refresh_exercises, style='HMI.TButton').pack(side='left', padx=6)
        right = ttk.Frame(container)
        right.grid(row=0, column=1, sticky='nswe')
        preview_frame = ttk.LabelFrame(right, text='Översikt', style='HMI.TLabelframe')
        preview_frame.pack(fill='both', expand=True, padx=6, pady=4)
        self.preview_info = tk.Label(preview_frame, text='Klar för träning', font=self.large_font, anchor='center')
        self.preview_info.pack(fill='both', expand=True, padx=12, pady=12)
        list_frame = ttk.LabelFrame(right, text='Träningstyper', style='HMI.TLabelframe')
        list_frame.pack(fill='both', expand=True, padx=6, pady=4)
        self.ex_listbox = tk.Listbox(list_frame, height=12, font=self.hmi_font)
        self.ex_listbox.pack(side='left', fill='both', expand=True, padx=(6,0), pady=6)
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.ex_listbox.yview)
        scrollbar.pack(side='left', fill='y')
        self.ex_listbox.config(yscrollcommand=scrollbar.set)
        self._populate_listbox()
        ctrl = ttk.Frame(right)
        ctrl.pack(fill='x', padx=6, pady=6)
        self.pause_btn = ttk.Button(ctrl, text='Pausa', command=self.on_pause, state='disabled', style='HMI.TButton')
        self.pause_btn.pack(side='left', padx=6)
        self.skip_btn = ttk.Button(ctrl, text='Hoppa', command=self.on_skip, state='disabled', style='HMI.TButton')
        self.skip_btn.pack(side='left', padx=6)
        self.stop_btn = ttk.Button(ctrl, text='Stoppa', command=self.on_stop, state='disabled', style='HMI.TButton')
        self.stop_btn.pack(side='left', padx=6)

    def _refresh_focus_menu(self):
        groups = sorted(set(e.group for e in self.exercises))
        self.focus_choices = ['Mixed'] + groups
        if self.focus_var.get() not in self.focus_choices:
            self.focus_var.set('Mixed')

    def _populate_listbox(self):
        self.ex_listbox.delete(0, tk.END)
        for e in self.exercises:
            self.ex_listbox.insert(tk.END, f"{e.name} [{e.group}] {e.min_time}s-{e.max_time}s")

    def refresh_exercises(self):
        self.exercises = load_exercises()
        self._refresh_focus_menu()
        menu = self.focus_menu['menu']
        menu.delete(0, 'end')
        for choice in self.focus_choices:
            menu.add_command(label=choice, command=lambda v=choice: self.focus_var.set(v))
        self._populate_listbox()
        self.preview_info.config(text=f'{len(self.exercises)} träningstyper')

    def on_add_exercise(self):
        dlg = AddExerciseDialog(self)
        self.wait_window(dlg)
        if dlg.saved:
            self.exercises.append(dlg.exercise)
            save_exercises(self.exercises)
            self.refresh_exercises()

    def on_start(self):
        if self._session and self._session.running:
            messagebox.showinfo('Körs redan', 'Ett pass körs redan')
            return
        period = self.period_var.get()
        work = self.work_var.get()
        rest = self.rest_var.get()
        focus = self.focus_var.get()
        if focus == 'Mixed':
            focus_groups = sorted(set(e.group for e in self.exercises))
        else:
            focus_groups = [focus]
        pool = [e for e in self.exercises if e.group in focus_groups]
        if not pool:
            messagebox.showwarning('Ingen träning', 'Inga träningstyper matchar vald fokus')
            return
        session_win = SessionWindow(self)
        self._session = SessionController(self, pool, period, work, rest, session_win)
        session_win.pause_btn.config(command=self._session.toggle_pause)
        session_win.skip_btn.config(command=self._session.skip)
        session_win.stop_btn.config(command=self._session.stop)
        self._session.start()
        self.pause_btn.config(state='normal')
        self.skip_btn.config(state='normal')
        self.stop_btn.config(state='normal')

    def on_pause(self):
        if not self._session:
            return
        self._session.toggle_pause()

    def on_skip(self):
        if self._session:
            self._session.skip()

    def on_stop(self):
        if self._session:
            self._session.stop()
            self._session = None
            self.preview_info.config(text='Klar för träning')
            self.pause_btn.config(state='disabled')
            self.skip_btn.config(state='disabled')
            self.stop_btn.config(state='disabled')


class AddExerciseDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title('Lägg till träningstyp')
        self.saved = False
        self.exercise = None
        self.transient(parent)
        self.grab_set()
        ttk.Label(self, text='Träningsnamn').grid(row=0, column=0, sticky='w', padx=6, pady=4)
        self.e_name = ttk.Entry(self, width=40)
        self.e_name.grid(row=0, column=1, padx=6, pady=4)
        ttk.Label(self, text='Grupp').grid(row=1, column=0, sticky='w', padx=6, pady=4)
        self.e_group = ttk.Entry(self, width=20)
        self.e_group.grid(row=1, column=1, sticky='w', padx=6, pady=4)
        ttk.Label(self, text='Min sekunder').grid(row=2, column=0, sticky='w', padx=6, pady=4)
        self.e_min = ttk.Spinbox(self, from_=5, to=600, width=8)
        self.e_min.set(30)
        self.e_min.grid(row=2, column=1, sticky='w', padx=6, pady=4)
        ttk.Label(self, text='Max sekunder').grid(row=3, column=0, sticky='w', padx=6, pady=4)
        self.e_max = ttk.Spinbox(self, from_=5, to=600, width=8)
        self.e_max.set(60)
        self.e_max.grid(row=3, column=1, sticky='w', padx=6, pady=4)
        ttk.Label(self, text='Beskrivning').grid(row=4, column=0, sticky='w', padx=6, pady=4)
        self.e_desc = ttk.Entry(self, width=40)
        self.e_desc.grid(row=4, column=1, padx=6, pady=4)
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=8)
        ttk.Button(btn_frame, text='Spara', command=self.on_save).pack(side='left', padx=6)
        ttk.Button(btn_frame, text='Avbryt', command=self.destroy).pack(side='left', padx=6)

    def on_save(self):
        name = self.e_name.get().strip()
        group = self.e_group.get().strip() or 'general'
        try:
            min_t = int(self.e_min.get())
            max_t = int(self.e_max.get())
        except Exception:
            messagebox.showerror('Invalid', 'Min/Max must be numbers')
            return
        if not name:
            messagebox.showerror('Invalid', 'Name required')
            return
        if min_t <= 0 or max_t <= 0 or min_t > max_t:
            messagebox.showerror('Invalid', 'Min/Max range invalid')
            return
        desc = self.e_desc.get().strip()
        self.exercise = Exercise(name, group, min_t, max_t, desc)
        self.saved = True
        self.destroy()


if __name__ == '__main__':
    app = HIITApp()
    app.mainloop()
"""
HIIT Trainer GUI using tkinter (HMI-style)
- Uses `exercises.json` in same folder for persistence
- Choose period, intensity, and focus group
- Add/list exercises via GUI
- Start a live HIIT session with a large HMI-style session window

Run: `python hiit_gui.py`
"""

import json
import os
import random
import time
import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont
import weakref


def _safe_tick(controller_ref):
    """Top-level safe caller for scheduled controller ticks."""
    controller = controller_ref()
    if controller is None:
        return
    try:
        controller._tick()
    except Exception:
        return

DATA_FILE = os.path.join(os.path.dirname(__file__), 'exercises.json')


class Exercise:
    def __init__(self, name, group, min_time=10, max_time=60, description=''):
        self.name = name
        self.group = group
        self.min_time = int(min_time)
        self.max_time = int(max_time)
        self.description = description

    def to_dict(self):
        return {
            'name': self.name,
            'group': self.group,
            'min_time': self.min_time,
            'max_time': self.max_time,
            'description': self.description,
        }

    @staticmethod
    def from_dict(d):
        return Exercise(d['name'], d['group'], d.get('min_time', 10), d.get('max_time', 60), d.get('description', ''))


class SessionController:
    def __init__(self, root, pool, period_minutes, work_sec, rest_sec, session_win=None):
        self.root = root
        self.pool = pool[:]
        self.period_seconds = period_minutes * 60
        self.work_sec = work_sec
        self.rest_sec = rest_sec

        self.running = False
        self.paused = False
        self.skip_flag = False
        self._start_time = None
        self._elapsed = 0

        self.current_phase = None  # 'work' or 'rest'
        self.current_ex = None
        self.phase_remaining = 0.0

        # countdown helper to avoid repeating beeps
        self._last_whole = None

        # optional HMI window
        self.session_win = session_win
        # register a persistent Tcl command wrapper to avoid Tk losing the Python callable
        try:
            self._tcl_name = self.root.register(lambda: _safe_tick(weakref.ref(self)))
        except Exception:
            self._tcl_name = None

    def start(self):
        self.running = True
        self._start_time = time.time()
        self._elapsed = 0
        self._next_item()
        # small start transition
        if self.session_win:
            try:
                self.session_win.play_transition('start')
                self.session_win.flash(self.session_win.work_flash, 180)
            except Exception:
                pass
        self._tick()

    def _next_item(self):
        # pick random exercise from pool
        self.current_ex = random.choice(self.pool)
        # clamp work to exercise range
        self.phase_work = clamp(self.work_sec, self.current_ex.min_time, self.current_ex.max_time)
        self.current_phase = 'work'
        self.phase_remaining = float(self.phase_work)
        if self.session_win:
            self.session_win.update_current(self.current_ex.name)
            self.session_win.update_time(int(self.phase_remaining))
            # next preview
            # attempt to peek next exercise name
            next_ex = random.choice(self.pool)
            self.session_win.update_next(next_ex.name)
            # flash and sound for new work interval
            try:
                self.session_win.play_transition('start')
                self.session_win.flash(self.session_win.work_flash, 200)
            except Exception:
                pass
        else:
            self.root.preview_info.config(text=f'WORK: {self.current_ex.name} - {int(self.phase_remaining)}s')

    def _start_rest(self):
        self.current_phase = 'rest'
        self.phase_remaining = float(self.rest_sec)
        if self.session_win:
            self.session_win.update_current('VILA')
            self.session_win.update_time(int(self.phase_remaining))
            try:
                self.session_win.play_transition('rest')
                self.session_win.flash(self.session_win.rest_flash, 200)
            except Exception:
                pass
        else:
            self.root.preview_info.config(text=f'REST: {int(self.phase_remaining)}s')

    def toggle_pause(self):
        self.paused = not self.paused

    def skip(self):
        # mark to end current phase
        self.skip_flag = True

    def stop(self):
        self.running = False
        if self.session_win:
            try:
                self.session_win.close()
            except Exception:
                pass
        # unregister tcl command if present
        if getattr(self, '_tcl_name', None):
            try:
                self.root.deletecommand(self._tcl_name)
            except Exception:
                pass

    def _tick(self):
        if not self.running:
            # clean up UI
            if self.session_win:
                try:
                    self.session_win.close()
                except Exception:
                    pass
            else:
                self.root.preview_info.config(text='Not running')
            # disable controls
            try:
                self.root.pause_btn.config(state='disabled')
                self.root.skip_btn.config(state='disabled')
                self.root.stop_btn.config(state='disabled')
            except Exception:
                pass
            return

        # update elapsed
        if not self.paused:
            # decrement remaining
            dt = 0.25
            self.phase_remaining -= dt
            self._elapsed = int(time.time() - self._start_time)

        # update display
        remaining_total = max(0, self.period_seconds - self._elapsed)
        if self.session_win:
            self.session_win.update_total(remaining_total)
            if self.paused:
                self.session_win.update_time(int(self.phase_remaining))
            else:
                rem = max(0, int(self.phase_remaining) + (1 if self.phase_remaining - int(self.phase_remaining) > 0 else 0))
                self.session_win.update_time(rem)
                # countdown beeps for last 3 seconds
                try:
                    whole = int(self.phase_remaining)
                    if whole != self._last_whole and whole <= 3 and whole > 0:
                        self._last_whole = whole
                        try:
                            self.session_win.play_transition('tick')
                        except Exception:
                            pass
                except Exception:
                    pass
        else:
            if self.paused:
                self.root.preview_info.config(text=f'PAUSED {int(self.phase_remaining)}s')
            else:
                rem = max(0, int(self.phase_remaining) + (1 if self.phase_remaining - int(self.phase_remaining) > 0 else 0))
                self.root.preview_info.config(text=f'{rem}s - {self.current_phase}')

        # check skip or completion
        if self.skip_flag:
            self.skip_flag = False
            self.phase_remaining = 0

        if not self.paused and self.phase_remaining <= 0:
            if self.current_phase == 'work':
                # finished work, start rest if still time left
                if self._elapsed >= self.period_seconds:
                    self.running = False
                    if self.session_win:
                        try:
                            self.session_win.update_current('Passet klart!')
                        except Exception:
                            pass
                        messagebox.showinfo('Klar', 'Passet färdigt! Bra jobbat!')
                    else:
                        messagebox.showinfo('Done', 'Session complete! Great job!')
                    return
                else:
                    self._start_rest()
            elif self.current_phase == 'rest':
                # finished rest, pick next exercise
                if self._elapsed >= self.period_seconds:
                    self.running = False
                    if self.session_win:
                        try:
                            self.session_win.update_current('Passet klart!')
                        except Exception:
                            pass
                        messagebox.showinfo('Klar', 'Passet färdigt! Bra jobbat!')
                    else:
                        messagebox.showinfo('Done', 'Session complete! Great job!')
                    return
                else:
                    self._next_item()

        # schedule next tick using a safe top-level wrapper (prevents Tcl 'invalid command' when
        # the bound method is removed from Python side)
        # schedule next tick using the registered Tcl wrapper if available
        try:
            if getattr(self, '_tcl_name', None):
                self.root.after(250, self._tcl_name)
            else:
                # keep a strong reference to the scheduled callable so Tcl doesn't lose it
                self._after_cb = (lambda cref=weakref.ref(self): _safe_tick(cref))
                self.root.after(250, self._after_cb)
        except Exception:
            # fallback to direct scheduling
            try:
                self.root.after(250, self._tick)
            except Exception:
                pass


if __name__ == '__main__':
    app = HIITApp()
    app.mainloop()
"""
HIIT Trainer GUI using tkinter
- Uses `exercises.json` in same folder for persistence
- Choose period, intensity, and focus group
- Add/list exercises via GUI
- Start a live session with visible countdown and controls

Run: `python hiit_gui.py`
"""

import json
import os
import random
import time
import tkinter as tk
from tkinter import ttk, messagebox

DATA_FILE = os.path.join(os.path.dirname(__file__), 'exercises.json')

class Exercise:
    def __init__(self, name, group, min_time=10, max_time=60, description=''):
        self.name = name
        self.group = group
        self.min_time = int(min_time)
        self.max_time = int(max_time)
        self.description = description

    def to_dict(self):
        return {
            'name': self.name,
            'group': self.group,
            'min_time': self.min_time,
            'max_time': self.max_time,
            'description': self.description,
        }

    @staticmethod
    def from_dict(d):
        return Exercise(d['name'], d['group'], d.get('min_time', 10), d.get('max_time', 60), d.get('description', ''))


def load_exercises():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [Exercise.from_dict(x) for x in data]
    except Exception:
        return []


def save_exercises(ex_list):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump([e.to_dict() for e in ex_list], f, indent=2, ensure_ascii=False)


def clamp(v, a, b):
    return max(a, min(b, v))


class HIITApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('HIIT Trainer')
        self.geometry('720x480')

        self.exercises = load_exercises()
        if not self.exercises:
            self._ensure_sample()

        self._build_ui()
        self._session = None

    def _ensure_sample(self):
        self.exercises.extend([
            Exercise('Push-ups', 'arms', 30, 60, 'Standard push-ups'),
            Exercise('Squats', 'legs', 30, 60, 'Bodyweight squats'),
            Exercise('Plank', 'core', 20, 60, 'Forearm plank'),
            Exercise('Jumping jacks', 'cardio', 20, 45, 'Full body cardio'),
        ])
        save_exercises(self.exercises)

    def _build_ui(self):
        frame_opts = ttk.LabelFrame(self, text='Session Options')
        frame_opts.pack(fill='x', padx=10, pady=8)

        # Period
        period_frame = ttk.Frame(frame_opts)
        period_frame.pack(anchor='w', pady=4)
        ttk.Label(period_frame, text='Duration: ').pack(side='left')
        self.period_var = tk.IntVar(value=20)
        for val, txt in ((20, '20 min'), (40, '40 min'), (60, '60 min')):
            ttk.Radiobutton(period_frame, text=txt, value=val, variable=self.period_var).pack(side='left', padx=6)

        # Intensity
        intensity_frame = ttk.Frame(frame_opts)
        intensity_frame.pack(anchor='w', pady=4)
        ttk.Label(intensity_frame, text='Work (s): ').pack(side='left')
        self.work_var = tk.IntVar(value=30)
        ttk.Spinbox(intensity_frame, from_=5, to=300, textvariable=self.work_var, width=6).pack(side='left', padx=6)
        ttk.Label(intensity_frame, text='Rest (s): ').pack(side='left')
        self.rest_var = tk.IntVar(value=15)
        ttk.Spinbox(intensity_frame, from_=5, to=300, textvariable=self.rest_var, width=6).pack(side='left', padx=6)

        # Focus
        focus_frame = ttk.Frame(frame_opts)
        focus_frame.pack(anchor='w', pady=4)
        ttk.Label(focus_frame, text='Focus: ').pack(side='left')
        self.focus_var = tk.StringVar(value='Mixed')
        self._refresh_focus_menu()
        self.focus_menu = ttk.OptionMenu(focus_frame, self.focus_var, self.focus_var.get(), *self.focus_choices)
        self.focus_menu.pack(side='left', padx=6)

        # Controls
        controls_frame = ttk.Frame(frame_opts)
        controls_frame.pack(anchor='w', pady=6)
        ttk.Button(controls_frame, text='Start', command=self.on_start).pack(side='left', padx=6)
        ttk.Button(controls_frame, text='Add Exercise', command=self.on_add_exercise).pack(side='left', padx=6)
        ttk.Button(controls_frame, text='Refresh', command=self.refresh_exercises).pack(side='left', padx=6)

        # Exercises list
        list_frame = ttk.LabelFrame(self, text='Exercises')
        list_frame.pack(fill='both', expand=True, padx=10, pady=8)
        self.ex_listbox = tk.Listbox(list_frame, height=8)
        self.ex_listbox.pack(side='left', fill='both', expand=True, padx=(6,0), pady=6)
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.ex_listbox.yview)
        scrollbar.pack(side='left', fill='y')
        self.ex_listbox.config(yscrollcommand=scrollbar.set)
        self._populate_listbox()

        # Session panel
        session_frame = ttk.LabelFrame(self, text='Live Session')
        session_frame.pack(fill='x', padx=10, pady=8)
        self.session_label = ttk.Label(session_frame, text='Not running', font=('TkDefaultFont', 14))
        self.session_label.pack(anchor='w', padx=6, pady=4)
        self.timer_label = ttk.Label(session_frame, text='', font=('TkDefaultFont', 20, 'bold'))
        self.timer_label.pack(anchor='w', padx=6, pady=4)

        btn_frame = ttk.Frame(session_frame)
        btn_frame.pack(anchor='w', padx=6, pady=6)
        self.pause_btn = ttk.Button(btn_frame, text='Pause', command=self.on_pause, state='disabled')
        self.pause_btn.pack(side='left', padx=6)
        self.skip_btn = ttk.Button(btn_frame, text='Skip', command=self.on_skip, state='disabled')
        self.skip_btn.pack(side='left', padx=6)
        self.stop_btn = ttk.Button(btn_frame, text='Stop', command=self.on_stop, state='disabled')
        self.stop_btn.pack(side='left', padx=6)

    def _refresh_focus_menu(self):
        groups = sorted(set(e.group for e in self.exercises))
        self.focus_choices = ['Mixed'] + groups
        if self.focus_var.get() not in self.focus_choices:
            self.focus_var.set('Mixed')

    def _populate_listbox(self):
        self.ex_listbox.delete(0, tk.END)
        for e in self.exercises:
            self.ex_listbox.insert(tk.END, f"{e.name} [{e.group}] {e.min_time}s-{e.max_time}s")

    def refresh_exercises(self):
        self.exercises = load_exercises()
        self._refresh_focus_menu()
        # Rebuild focus menu
        menu = self.focus_menu['menu']
        menu.delete(0, 'end')
        for choice in self.focus_choices:
            menu.add_command(label=choice, command=lambda v=choice: self.focus_var.set(v))
        self._populate_listbox()

    def on_add_exercise(self):
        dlg = AddExerciseDialog(self)
        self.wait_window(dlg)
        if dlg.saved:
            self.exercises.append(dlg.exercise)
            save_exercises(self.exercises)
            self.refresh_exercises()

    def on_start(self):
        if self._session and self._session.running:
            messagebox.showinfo('Already running', 'A session is already running')
            return
        period = self.period_var.get()
        work = self.work_var.get()
        rest = self.rest_var.get()
        focus = self.focus_var.get()
        if focus == 'Mixed':
            focus_groups = sorted(set(e.group for e in self.exercises))
        else:
            focus_groups = [focus]
        pool = [e for e in self.exercises if e.group in focus_groups]
        if not pool:
            messagebox.showwarning('No exercises', 'No exercises match the selected focus')
            return
        self._session = SessionController(self, pool, period, work, rest)
        self._session.start()
        # enable controls
        self.pause_btn.config(state='normal')
        self.skip_btn.config(state='normal')
        self.stop_btn.config(state='normal')

    def on_pause(self):
        if not self._session:
            return
        self._session.toggle_pause()
        if self._session.paused:
            self.pause_btn.config(text='Resume')
        else:
            self.pause_btn.config(text='Pause')

    def on_skip(self):
        if self._session:
            self._session.skip()

    def on_stop(self):
        if self._session:
            self._session.stop()
            self._session = None
            self.session_label.config(text='Not running')
            self.timer_label.config(text='')
            self.pause_btn.config(state='disabled', text='Pause')
            self.skip_btn.config(state='disabled')
            self.stop_btn.config(state='disabled')


class AddExerciseDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title('Add Exercise')
        self.saved = False
        self.exercise = None
        self.transient(parent)
        self.grab_set()

        ttk.Label(self, text='Name').grid(row=0, column=0, sticky='w', padx=6, pady=4)
        self.e_name = ttk.Entry(self, width=40)
        self.e_name.grid(row=0, column=1, padx=6, pady=4)

        ttk.Label(self, text='Group').grid(row=1, column=0, sticky='w', padx=6, pady=4)
        self.e_group = ttk.Entry(self, width=20)
        self.e_group.grid(row=1, column=1, sticky='w', padx=6, pady=4)

        ttk.Label(self, text='Min seconds').grid(row=2, column=0, sticky='w', padx=6, pady=4)
        self.e_min = ttk.Spinbox(self, from_=5, to=600, width=8)
        self.e_min.set(30)
        self.e_min.grid(row=2, column=1, sticky='w', padx=6, pady=4)

        ttk.Label(self, text='Max seconds').grid(row=3, column=0, sticky='w', padx=6, pady=4)
        self.e_max = ttk.Spinbox(self, from_=5, to=600, width=8)
        self.e_max.set(60)
        self.e_max.grid(row=3, column=1, sticky='w', padx=6, pady=4)

        ttk.Label(self, text='Description').grid(row=4, column=0, sticky='w', padx=6, pady=4)
        self.e_desc = ttk.Entry(self, width=40)
        self.e_desc.grid(row=4, column=1, padx=6, pady=4)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=8)
        ttk.Button(btn_frame, text='Save', command=self.on_save).pack(side='left', padx=6)
        ttk.Button(btn_frame, text='Cancel', command=self.destroy).pack(side='left', padx=6)

    def on_save(self):
        name = self.e_name.get().strip()
        group = self.e_group.get().strip() or 'general'
        try:
            min_t = int(self.e_min.get())
            max_t = int(self.e_max.get())
        except Exception:
            messagebox.showerror('Invalid', 'Min/Max must be numbers')
            return
        if not name:
            messagebox.showerror('Invalid', 'Name required')
            return
        if min_t <= 0 or max_t <= 0 or min_t > max_t:
            messagebox.showerror('Invalid', 'Min/Max range invalid')
            return
        desc = self.e_desc.get().strip()
        self.exercise = Exercise(name, group, min_t, max_t, desc)
        self.saved = True
        self.destroy()


class SessionController:
    def __init__(self, root, pool, period_minutes, work_sec, rest_sec):
        self.root = root
        self.pool = pool[:]
        self.period_seconds = period_minutes * 60
        self.work_sec = work_sec
        self.rest_sec = rest_sec

        self.running = False
        self.paused = False
        self.skip_flag = False
        self._start_time = None
        self._elapsed = 0

        self.current_phase = None  # 'work' or 'rest'
        self.current_ex = None
        self.phase_remaining = 0.0

    def start(self):
        self.running = True
        self._start_time = time.time()
        self._elapsed = 0
        self._next_item()
        self._tick()

    def _next_item(self):
        # pick random exercise from pool
        self.current_ex = random.choice(self.pool)
        # clamp work to exercise range
        self.phase_work = clamp(self.work_sec, self.current_ex.min_time, self.current_ex.max_time)
        self.current_phase = 'work'
        self.phase_remaining = float(self.phase_work)
        self.root.session_label.config(text=f'WORK: {self.current_ex.name} ({self.current_ex.group})')
        self.root.timer_label.config(text=f'{int(self.phase_remaining)}s')

    def _start_rest(self):
        self.current_phase = 'rest'
        self.phase_remaining = float(self.rest_sec)
        self.root.session_label.config(text='REST')
        self.root.timer_label.config(text=f'{int(self.phase_remaining)}s')

    def toggle_pause(self):
        self.paused = not self.paused

    def skip(self):
        # mark to end current phase
        self.skip_flag = True

    def stop(self):
        self.running = False

    def _tick(self):
        if not self.running:
            self.root.session_label.config(text='Not running')
            self.root.timer_label.config(text='')
            # disable controls
            self.root.pause_btn.config(state='disabled', text='Pause')
            self.root.skip_btn.config(state='disabled')
            self.root.stop_btn.config(state='disabled')
            return

        # update elapsed
        if not self.paused:
            # decrement remaining
            dt = 0.25
            self.phase_remaining -= dt
            self._elapsed = int(time.time() - self._start_time)

        # update display
        if self.paused:
            self.root.timer_label.config(text=f'PAUSED {int(self.phase_remaining)}s')
        else:
            rem = max(0, int(self.phase_remaining) + (1 if self.phase_remaining - int(self.phase_remaining) > 0 else 0))
            self.root.timer_label.config(text=f'{rem}s')

        # check skip or completion
        if self.skip_flag:
            self.skip_flag = False
            self.phase_remaining = 0

        if not self.paused and self.phase_remaining <= 0:
            if self.current_phase == 'work':
                # finished work, start rest if still time left
                if self._elapsed >= self.period_seconds:
                    self.running = False
                    self.root.session_label.config(text='Session complete!')
                    self.root.timer_label.config(text='')
                    # disable controls
                    self.root.pause_btn.config(state='disabled', text='Pause')
                    self.root.skip_btn.config(state='disabled')
                    self.root.stop_btn.config(state='disabled')
                    messagebox.showinfo('Done', 'Session complete! Great job!')
                    return
                else:
                    self._start_rest()
            elif self.current_phase == 'rest':
                # finished rest, pick next exercise
                if self._elapsed >= self.period_seconds:
                    self.running = False
                    self.root.session_label.config(text='Session complete!')
                    self.root.timer_label.config(text='')
                    self.root.pause_btn.config(state='disabled', text='Pause')
                    self.root.skip_btn.config(state='disabled')
                    self.root.stop_btn.config(state='disabled')
                    messagebox.showinfo('Done', 'Session complete! Great job!')
                    return
                else:
                    self._next_item()

        # update elapsed summary occasionally
        remaining_total = max(0, self.period_seconds - self._elapsed)
        self.root.title(f'HIIT Trainer - Remaining {remaining_total}s')

        # schedule next tick (use safe wrapper)
        try:
            # keep a strong reference to the scheduled callable so Tcl doesn't lose it
            self._after_cb = (lambda cref=weakref.ref(self): _safe_tick(cref))
            self.root.after(250, self._after_cb)
        except Exception:
            try:
                self.root.after(250, self._tick)
            except Exception:
                pass


if __name__ == '__main__':
    app = HIITApp()
    app.mainloop()
