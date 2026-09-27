"""
Simple CLI HIIT training app
- Add/list exercises (persisted to exercises.json)
- Start a live HIIT session with options: duration (20/40/60), intensity (work/rest seconds), focus group
- Per-player (session) durations clamp to each exercise min/max
- Controls during live session (Windows & Unix): p = pause/resume, s = skip, q = quit

Run: `python hiit.py`
"""

import json
import os
import time
import random
import sys
import threading

DATA_FILE = os.path.join(os.path.dirname(__file__), 'exercises.json')

# Cross-platform simple key handling
try:
    import msvcrt
    def get_key_nonblocking():
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            try:
                return ch.decode('utf-8').lower()
            except Exception:
                return None
        return None
except Exception:
    # Unix fallback
    import select, tty, termios
    def get_key_nonblocking():
        dr, dw, de = select.select([sys.stdin], [], [], 0)
        if dr:
            return sys.stdin.read(1).lower()
        return None


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


def add_exercise_interactive(ex_list):
    print('\nAdd a new exercise')
    name = input('Name: ').strip()
    if not name:
        print('Name required')
        return
    group = input('Group (e.g. arms, legs, core): ').strip() or 'general'
    try:
        min_t = int(input('Min seconds (default 30): ') or '30')
        max_t = int(input('Max seconds (default 60): ') or '60')
    except ValueError:
        print('Invalid times')
        return
    description = input('Optional description: ').strip()

    ex = Exercise(name, group, min_t, max_t, description)
    ex_list.append(ex)
    save_exercises(ex_list)
    print(f'Added exercise: {name} ({group})')


def list_exercises(ex_list):
    if not ex_list:
        print('\nNo exercises yet. Add some first.')
        return
    print('\nExercises:')
    groups = {}
    for i, e in enumerate(ex_list, 1):
        print(f"{i}. {e.name} [{e.group}] {e.min_time}s-{e.max_time}s {'- '+e.description if e.description else ''}")
        groups.setdefault(e.group, 0)
        groups[e.group] += 1
    print('\nGroups:')
    for g, c in groups.items():
        print(f' - {g}: {c} exercise(s)')


def choose_focus(ex_list):
    groups = list(sorted(set(e.group for e in ex_list)))
    if not groups:
        print('No groups available. Please add exercises first.')
        return None
    print('\nAvailable focuses:')
    for i, g in enumerate(groups, 1):
        print(f'{i}. {g}')
    print(f'{len(groups)+1}. Mixed (all groups)')
    choice = input('Choose focus number: ').strip()
    try:
        c = int(choice)
        if c == len(groups) + 1:
            return groups  # all groups
        if 1 <= c <= len(groups):
            return [groups[c-1]]
    except Exception:
        pass
    print('Invalid choice')
    return None


def clamp(v, a, b):
    return max(a, min(b, v))


def run_countdown(seconds, label, controls):
    # seconds can be float; show integer countdown
    start = time.time()
    end = start + seconds
    while True:
        remaining = end - time.time()
        if remaining <= 0:
            break
        # check keys
        key = get_key_nonblocking()
        if key:
            if key == 'p':
                controls['paused'] = not controls['paused']
            elif key == 's':
                controls['skip'] = True
                break
            elif key == 'q':
                controls['quit'] = True
                break
        if controls['quit'] or controls['skip']:
            break
        if controls['paused']:
            print(f"{label} - PAUSED. Press 'p' to resume.", end='\r')
            time.sleep(0.2)
            start += 0.2  # shift end time forward so we don't lose time while paused
            end += 0.2
            continue
        secs = int(remaining) + (1 if remaining - int(remaining) > 0 else 0)
        print(f"{label} - {secs:3d}s remaining. Controls: p pause/resume, s skip, q quit", end='\r')
        time.sleep(0.2)
    print(' ' * 80, end='\r')


def start_session(ex_list, period_minutes, work_sec, rest_sec, focus_groups):
    # Build pool of exercises matching focus
    pool = [e for e in ex_list if e.group in focus_groups]
    if not pool:
        print('No exercises for selected focus groups. Aborting.')
        return

    total_seconds = period_minutes * 60
    elapsed = 0
    controls = {'paused': False, 'skip': False, 'quit': False}

    print('\nStarting HIIT session')
    print(f'Duration: {period_minutes} min, Work: {work_sec}s, Rest: {rest_sec}s, Focus: {focus_groups}')
    time.sleep(1)

    while elapsed < total_seconds and not controls['quit']:
        # choose next exercise
        ex = random.choice(pool)
        actual_work = clamp(work_sec, ex.min_time, ex.max_time)

        # WORK phase
        controls['skip'] = False
        print(f"WORK: {ex.name} ({ex.group}) - target {actual_work}s")
        phase_start = time.time()
        run_countdown(actual_work, f"WORK: {ex.name}", controls)
        if controls['quit']:
            break
        if controls['skip']:
            # skip rest and continue to next exercise
            elapsed += int(time.time() - phase_start)
            continue
        elapsed += int(time.time() - phase_start)
        if elapsed >= total_seconds:
            break

        # REST phase
        print(f"REST: {rest_sec}s")
        phase_start = time.time()
        run_countdown(rest_sec, 'REST', controls)
        if controls['quit']:
            break
        if controls['skip']:
            elapsed += int(time.time() - phase_start)
            continue
        elapsed += int(time.time() - phase_start)

        # show progress
        remaining = max(0, total_seconds - elapsed)
        print(f"Elapsed: {elapsed}s / {total_seconds}s - Remaining: {remaining}s")

    if controls['quit']:
        print('\nSession aborted by user.')
    else:
        print('\nSession complete! Great job!')


def ensure_sample(ex_list):
    if not ex_list:
        # add some example exercises
        ex_list.extend([
            Exercise('Push-ups', 'arms', 30, 60, 'Standard push-ups'),
            Exercise('Squats', 'legs', 30, 60, 'Bodyweight squats'),
            Exercise('Plank', 'core', 20, 60, 'Forearm plank'),
            Exercise('Jumping jacks', 'cardio', 20, 45, 'Full body cardio'),
        ])
        save_exercises(ex_list)


def main():
    ex_list = load_exercises()
    ensure_sample(ex_list)

    while True:
        print('\nHIIT Trainer - Main Menu')
        print('1) Start training')
        print('2) Add exercise')
        print('3) List exercises')
        print('4) Quit')
        choice = input('Choose: ').strip()
        if choice == '1':
            # duration
            print('\nChoose period:')
            print('1) 20 min')
            print('2) 40 min')
            print('3) 60 min')
            p = input('Choose: ').strip()
            period = 20
            if p == '2': period = 40
            elif p == '3': period = 60

            # intensity
            try:
                work = int(input('Work seconds (e.g. 30): ').strip() or '30')
                rest = int(input('Rest seconds (e.g. 15): ').strip() or '15')
            except ValueError:
                print('Invalid numbers')
                continue

            # focus
            focus = choose_focus(ex_list)
            if focus is None:
                continue

            start_session(ex_list, period, work, rest, focus)

        elif choice == '2':
            add_exercise_interactive(ex_list)
        elif choice == '3':
            list_exercises(ex_list)
        elif choice == '4':
            print('Goodbye!')
            break
        else:
            print('Invalid choice')


if __name__ == '__main__':
    main()
