"""
Smart Study Planner  -  CSM 216 Python Project   (ALL-IN-ONE FILE)
Run this single file in PyCharm:  right-click > Run 'smart_planner'
Needs:  pip install pandas

Sections in this file (same as the 5-module project, merged):
  1. Settings (config.py)        4. Calendar export (calendar_export.py)
  2. Validation (validation.py)  5. View + Controller (ui.py)
  3. Model (data_model.py)       6. Entry point (main.py)
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, date, timedelta
import os
import hashlib
import pandas as pd



# ======================================================================
# 1. SETTINGS
# ======================================================================
# ---------- theme ----------
BG, SIDE, CARD, FIELD = "#0f172a", "#1e1b4b", "#1e293b", "#334155"
TXT, MUTED = "#e2e8f0", "#94a3b8"
PURPLE, PINK, CYAN, AMBER = "#8b5cf6", "#ec4899", "#22d3ee", "#f59e0b"
GREEN, RED, BLUE = "#10b981", "#ef4444", "#3b82f6"
PALETTE = [PURPLE, PINK, CYAN, AMBER, GREEN, BLUE, RED, "#a3e635"]
FONT = "Segoe UI"
COLUMNS = ["Subject", "Deadline", "Duration", "Difficulty", "Priority_Score", "Status"]
WEIGHT = {"High": 3, "Medium": 2, "Low": 1}
SUBJECTS = ["Data Structures", "Machine Learning", "Database Management",
            "Python Programming", "Digital Electronics", "Mathematics"]


def lighten(c, f=0.18):
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(v + (255 - v) * f) for v in (r, g, b))


# ======================================================================
# 2. VALIDATION
# ======================================================================
def validate_session(subject, deadline, duration):
    subject, deadline, duration = subject.strip(), deadline.strip(), duration.strip()
    if not subject or not deadline or not duration:
        return False, "Please fill in all the fields.", None, None
    try:
        due = datetime.strptime(deadline, "%Y-%m-%d").date()
    except ValueError:
        return False, "Use the date format YYYY-MM-DD (e.g. 2026-11-20).", None, None
    if due < date.today():
        return False, "Deadline cannot be in the past.", None, None
    try:
        hours = float(duration)
    except ValueError:
        return False, "Duration must be a number.", None, None
    if not 0 < hours <= 12:
        return False, "Duration must be between 0 and 12 hours.", None, None
    return True, "", deadline, hours


def validate_daily_hours(text):
    try:
        hours = float(text)
    except ValueError:
        return False, "Enter a valid number of daily study hours.", None
    if hours <= 0:
        return False, "Daily study hours must be more than 0.", None
    return True, "", hours


# ======================================================================
# 3. MODEL (Pandas)
# ======================================================================
class StudyModel:
    def __init__(self):
        self.df = pd.DataFrame(columns=COLUMNS)
        self.plan_df = pd.DataFrame(columns=["Date", "Subject", "Hours"])

    # ---------- data operations ----------
    def add_session(self, subject, deadline, hours, difficulty):
        self.df.loc[len(self.df)] = [subject, deadline, hours, difficulty, 0.0, "Pending"]

    def delete_sessions(self, indexes):
        self.df = self.df.drop(indexes).reset_index(drop=True)

    def mark_done(self, indexes):
        """Mark sessions as completed. Returns the names that were newly marked."""
        names = []
        for i in indexes:
            if self.df.at[i, "Status"] != "Done":
                self.df.at[i, "Status"] = "Done"
                names.append(self.df.at[i, "Subject"])
        return names

    def clear(self):
        self.df = pd.DataFrame(columns=COLUMNS)

    def add_sample(self):
        samples = [("Data Structures", 5, 3, "High"), ("Machine Learning", 9, 4, "High"),
                   ("Database Management", 12, 2, "Medium"), ("Python Programming", 7, 2, "Low"),
                   ("Mathematics", 15, 3, "Medium")]
        for subject, days, hours, diff in samples:
            deadline = (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")
            self.add_session(subject, deadline, float(hours), diff)

    # ---------- core allocation engine ----------
    def compute_priority(self):
        """Priority = difficulty weight x urgency (closer deadline -> higher score)."""
        if self.df.empty:
            return
        days = (pd.to_datetime(self.df["Deadline"]) - pd.Timestamp(date.today())).dt.days
        self.df["Days_Left"] = days.clip(lower=1)
        self.df["Priority_Score"] = (self.df["Difficulty"].map(WEIGHT) * 10 / self.df["Days_Left"]).round(1)
        self.df = self.df.sort_values(["Priority_Score", "Deadline"],
                                      ascending=[False, True]).reset_index(drop=True)

    def generate_plan(self, daily_hours):
        """Fill each day with the most urgent sessions first.
        Returns (plan DataFrame, hours that could not fit before the deadlines)."""
        work = self.df[self.df["Status"] != "Done"]          # finished sessions are not planned again
        if work.empty:
            self.plan_df = pd.DataFrame(columns=["Date", "Subject", "Hours"])
            return self.plan_df, 0
        remaining = {i: r["Duration"] for i, r in work.iterrows()}
        rows, day = [], date.today()
        last_day = pd.to_datetime(work["Deadline"]).max().date()
        while day <= last_day:
            free = daily_hours
            for i, r in work.iterrows():             # already sorted by priority
                if free <= 0:
                    break
                due = datetime.strptime(r["Deadline"], "%Y-%m-%d").date()
                if remaining[i] > 0 and day <= due:
                    take = min(remaining[i], free)
                    rows.append((day.strftime("%a, %d %b %Y"), r["Subject"], round(take, 1)))
                    remaining[i] -= take
                    free -= take
            day += timedelta(days=1)
        self.plan_df = pd.DataFrame(rows, columns=["Date", "Subject", "Hours"])
        leftover = sum(v for v in remaining.values() if v > 0)
        return self.plan_df, leftover

    # ---------- time slot assigner ----------
    def assign_time_slots(self, start_text, available_hours, break_min=10, max_block=2.0):
        """Give each session a clock time slot, one after another, in priority order.
        Returns (slots, not_covered).
        slots = [(subject, "18:00", "20:00", hours), ...]; not_covered = subjects with no time left."""
        t = datetime.strptime(start_text, "%H:%M")
        day_end = t + timedelta(hours=available_hours)
        slots, skipped = [], []
        for _, r in self.df.iterrows():              # df is already sorted by priority
            if r["Status"] == "Done":                # finished sessions get no slot
                continue
            if t >= day_end:
                skipped.append(r["Subject"])
                continue
            hours = min(r["Duration"], max_block, (day_end - t).total_seconds() / 3600)
            end = t + timedelta(hours=hours)
            slots.append((r["Subject"], t.strftime("%H:%M"), end.strftime("%H:%M"), round(hours, 2)))
            t = end + timedelta(minutes=break_min)   # short break before the next subject
        return slots, skipped

    # ---------- files ----------
    def save_csv(self, path):
        self.df[COLUMNS].to_csv(path, index=False)

    def save_plan(self, path):
        self.plan_df.to_csv(path, index=False)

    def load_csv(self, path):
        data = pd.read_csv(path)
        if not {"Subject", "Deadline", "Duration", "Difficulty"}.issubset(data.columns):
            raise ValueError("File is missing required columns")
        data["Priority_Score"] = 0.0
        if "Status" not in data.columns:
            data["Status"] = "Pending"
        data["Status"] = data["Status"].fillna("Pending")
        self.df = data[COLUMNS].copy()
        return len(self.df)


# ======================================================================
# 4. CALENDAR EXPORT (.ics)
# ======================================================================
def slots_to_ics(slots, day=None, reminder_min=10):
    """slots = [(subject, "18:00", "20:00", hours), ...] from StudyModel.assign_time_slots"""
    day = day or date.today()
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Smart Study Planner//EN", "CALSCALE:GREGORIAN"]
    offset, prev = 0, None
    for n, (subject, start, end, hours) in enumerate(slots):
        s_t = datetime.strptime(start, "%H:%M").time()
        e_t = datetime.strptime(end, "%H:%M").time()
        if prev is not None and s_t < prev:          # the schedule passed midnight
            offset += 1
        prev = s_t
        s = datetime.combine(day + timedelta(days=offset), s_t)
        e = datetime.combine(day + timedelta(days=offset), e_t)
        if e <= s:
            e += timedelta(days=1)
        lines += ["BEGIN:VEVENT", f"UID:{stamp}-{n}@smartstudyplanner", f"DTSTAMP:{stamp}",
                  f"DTSTART:{s:%Y%m%dT%H%M%S}", f"DTEND:{e:%Y%m%dT%H%M%S}",
                  f"SUMMARY:Study: {subject}",
                  "BEGIN:VALARM", f"TRIGGER:-PT{reminder_min}M", "ACTION:DISPLAY",
                  f"DESCRIPTION:{subject} starts in {reminder_min} minutes", "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ======================================================================
# 4b. GOOGLE CALENDAR SYNC (direct connection through the Google API)
# ======================================================================
# One-time setup: credentials.json (downloaded from Google Cloud) must be in the same folder as this file.
# Needs:  pip install google-api-python-client google-auth-oauthlib
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TIMEZONE = "Asia/Kolkata"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")


def get_google_service():
    """Log in to Google (browser opens only the first time) and return the Calendar service."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, GOOGLE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def slot_datetimes(slots, day=None):
    """Turn [(subject, "18:00", "20:00", h), ...] into [(subject, start_datetime, end_datetime), ...]."""
    day, offset, prev, out = day or date.today(), 0, None, []
    for subject, start, end, _ in slots:
        s_t = datetime.strptime(start, "%H:%M").time()
        e_t = datetime.strptime(end, "%H:%M").time()
        if prev is not None and s_t < prev:            # the schedule passed midnight
            offset += 1
        prev = s_t
        s = datetime.combine(day + timedelta(days=offset), s_t)
        e = datetime.combine(day + timedelta(days=offset), e_t)
        if e <= s:
            e += timedelta(days=1)
        out.append((subject, s, e))
    return out


def sync_slots_to_google(service, slots, day=None, reminder_min=10):
    """Create one calendar event per slot. Each event gets a fixed ID made from its date, time and
    subject, so syncing the same slot again UPDATES it instead of creating a duplicate.
    Returns (created, updated)."""
    created = updated = 0
    for subject, s, e in slot_datetimes(slots, day):
        key = f"{s:%Y%m%d%H%M}|{subject}"
        event_id = hashlib.sha1(key.encode("utf-8")).hexdigest()      # only 0-9 a-f, valid for Google
        body = {"id": event_id, "summary": f"Study: {subject}",
                "start": {"dateTime": s.isoformat(), "timeZone": TIMEZONE},
                "end": {"dateTime": e.isoformat(), "timeZone": TIMEZONE},
                "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": reminder_min}]}}
        try:
            service.events().insert(calendarId="primary", body=body).execute()
            created += 1
        except Exception as err:
            if getattr(getattr(err, "resp", None), "status", None) != 409:   # 409 = this event already exists
                raise
            service.events().update(calendarId="primary", eventId=event_id, body=body).execute()
            updated += 1
    return created, updated


# ======================================================================
# 5. VIEW + CONTROLLER (Tkinter)
# ======================================================================
class SmartStudyPlanner:
    def __init__(self, root):
        self.root = root
        root.title("Smart Study Planner")
        root.geometry("1280x760")
        root.minsize(1100, 660)
        root.configure(bg=BG)

        # ----- MODEL (data_model.py) -----
        self.model = StudyModel()
        self.current = None
        self.pages, self.nav = {}, {}
        # timer state
        self.running, self.job, self.pomos = False, None, 0
        self.t_total = self.t_left = 25 * 60
        # time slots + reminders
        self.last_slots, self.notified = [], set()
        # auto-run schedule (timer follows the time slots)
        self.auto_active, self.auto_queue, self.auto_idx = False, [], 0
        self.phase, self.break_secs = "focus", 600

        self.setup_styles()
        self.build_sidebar()
        self.build_content()
        self.show_page("Dashboard")
        self.set_status("Welcome! Click 'Sample Data' in the sidebar to see the app in action.")
        self.check_reminders()

    # ================= STYLES =================
    def setup_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Treeview", background=CARD, foreground=TXT, fieldbackground=CARD,
                    rowheight=34, font=(FONT, 11), borderwidth=0)
        s.configure("Treeview.Heading", background=PURPLE, foreground="white",
                    font=(FONT, 11, "bold"), relief="flat", padding=6)
        s.map("Treeview", background=[("selected", PINK)], foreground=[("selected", "white")])
        s.map("Treeview.Heading", background=[("active", lighten(PURPLE))])
        s.configure("Vertical.TScrollbar", background=FIELD, troughcolor=CARD, arrowcolor="white", borderwidth=0)
        s.configure("Dark.TCombobox", fieldbackground=FIELD, background=PURPLE, foreground="white",
                    arrowcolor="white", padding=6)
        s.map("Dark.TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", "white")])
        s.configure("Dark.TSpinbox", fieldbackground=FIELD, foreground="white", arrowcolor="white", padding=6)
        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", "white")
        self.root.option_add("*TCombobox*Listbox.selectBackground", PINK)

    # ================= HELPERS =================
    def button(self, parent, text, color, cmd):
        b = tk.Button(parent, text=text, command=cmd, bg=color, fg="white", relief="flat", bd=0,
                      activebackground=lighten(color), activeforeground="white",
                      font=(FONT, 11, "bold"), padx=16, pady=8, cursor="hand2")
        b.bind("<Enter>", lambda e: b.config(bg=lighten(color)))
        b.bind("<Leave>", lambda e: b.config(bg=color))
        return b

    def entry(self, parent, var, width=18):
        return tk.Entry(parent, textvariable=var, width=width, bg=FIELD, fg="white", insertbackground="white",
                        relief="flat", font=(FONT, 12), highlightthickness=2,
                        highlightbackground=FIELD, highlightcolor=CYAN)

    def label(self, parent, text, size=11, color=MUTED, bold=False, bg=CARD):
        return tk.Label(parent, text=text, bg=bg, fg=color, font=(FONT, size, "bold" if bold else "normal"))

    def make_tree(self, parent, cols, widths, rows=10):
        wrap = tk.Frame(parent, bg=CARD)
        wrap.pack(fill="both", expand=True, padx=10, pady=10)
        tree = ttk.Treeview(wrap, columns=cols, show="headings", height=rows)
        for c, w in zip(cols, widths):
            tree.heading(c, text=c)
            tree.column(c, width=w, anchor="center")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tree.tag_configure("high", background="#3b1d2a", foreground="#fca5a5")
        tree.tag_configure("med", background="#3a2f14", foreground="#fcd34d")
        tree.tag_configure("low", background="#12332b", foreground="#6ee7b7")
        tree.tag_configure("done", background="#1f2937", foreground="#6b7280")
        return tree

    # ================= SIDEBAR + NAVIGATION =================
    def build_sidebar(self):
        side = tk.Frame(self.root, bg=SIDE, width=235)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="🎓 Smart Study\n     Planner", font=(FONT, 19, "bold"), fg="white",
                 bg=SIDE, justify="left").pack(anchor="w", padx=18, pady=(26, 28))

        items = [("Dashboard", "📊", PURPLE), ("Sessions", "📝", PINK),
                 ("Daily Plan", "📅", CYAN), ("Focus Timer", "⏱", AMBER)]
        for name, icon, col in items:
            b = tk.Label(side, text=f"  {icon}   {name}", font=(FONT, 13, "bold"), fg=MUTED, bg=SIDE,
                         anchor="w", padx=14, pady=12, cursor="hand2")
            b.pack(fill="x", padx=12, pady=3)
            b.bind("<Button-1>", lambda e, n=name: self.show_page(n))
            b.bind("<Enter>", lambda e, b=b, n=name: b.config(bg="#312e81") if n != self.current else None)
            b.bind("<Leave>", lambda e, b=b, n=name: b.config(bg=SIDE) if n != self.current else None)
            self.nav[name] = (b, col)

        # quick actions at the bottom
        bottom = tk.Frame(side, bg=SIDE)
        bottom.pack(side="bottom", fill="x", padx=16, pady=18)
        for text, col, cmd in [("✨ Sample Data", BLUE, self.load_sample), ("📂 Load CSV", "#475569", self.load_csv),
                               ("💾 Export CSV", GREEN, self.export_csv)]:
            self.button(bottom, text, col, cmd).pack(fill="x", pady=4)

    def show_page(self, name):
        self.current = name
        self.pages[name].tkraise()
        for n, (b, col) in self.nav.items():
            if n == name:
                b.config(bg=col, fg="white")
            else:
                b.config(bg=SIDE, fg=MUTED)
        self.title_lbl.config(text=name)

    # ================= CONTENT AREA =================
    def build_content(self):
        content = tk.Frame(self.root, bg=BG)
        content.pack(side="left", fill="both", expand=True)

        head = tk.Frame(content, bg=BG)
        head.pack(fill="x", padx=28, pady=(20, 6))
        hour = datetime.now().hour
        greet = "Good Morning" if hour < 12 else "Good Afternoon" if hour < 17 else "Good Evening"
        left = tk.Frame(head, bg=BG)
        left.pack(side="left")
        self.title_lbl = tk.Label(left, text="", font=(FONT, 26, "bold"), fg="white", bg=BG)
        self.title_lbl.pack(anchor="w")
        tk.Label(left, text=f"{greet}! Let's make today productive.", font=(FONT, 11), fg=CYAN, bg=BG).pack(anchor="w")
        tk.Label(head, text=datetime.now().strftime("📆  %A, %d %B %Y"), font=(FONT, 12, "bold"),
                 fg=AMBER, bg=BG).pack(side="right")

        self.status = tk.Label(content, text="", anchor="w", bg="#020617", fg=CYAN, font=(FONT, 10), padx=14, pady=5)
        self.status.pack(side="bottom", fill="x")

        container = tk.Frame(content, bg=BG)
        container.pack(fill="both", expand=True, padx=28, pady=(8, 14))
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        for name, builder in [("Dashboard", self.build_dashboard), ("Sessions", self.build_sessions),
                              ("Daily Plan", self.build_plan), ("Focus Timer", self.build_timer)]:
            f = tk.Frame(container, bg=BG)
            f.grid(row=0, column=0, sticky="nsew")
            self.pages[name] = f
            builder(f)

    # ---------- Page 1: Dashboard ----------
    def build_dashboard(self, page):
        row = tk.Frame(page, bg=BG)
        row.pack(fill="x")
        self.stat = {}
        for i, (key, title, icon, col) in enumerate([("hours", "TOTAL HOURS", "⏳", PURPLE), ("count", "SESSIONS", "📚", PINK),
                                                     ("urgent", "MOST URGENT", "🔥", AMBER), ("next", "NEXT DEADLINE", "🎯", CYAN)]):
            row.columnconfigure(i, weight=1, uniform="s")
            card = tk.Frame(row, bg=CARD)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            tk.Frame(card, bg=col, height=5).pack(fill="x")
            self.label(card, f"{icon}  {title}", 10, MUTED, True).pack(anchor="w", padx=16, pady=(12, 0))
            v = self.label(card, "-", 22, col, True)
            v.pack(anchor="w", padx=16, pady=(2, 16))
            self.stat[key] = v

        prog = tk.Frame(page, bg=CARD)
        prog.pack(fill="x", pady=(12, 0))
        self.prog_lbl = self.label(prog, "✅  Progress: 0 / 0 sessions completed", 11, "white", True)
        self.prog_lbl.pack(anchor="w", padx=16, pady=(10, 4))
        self.prog_cv = tk.Canvas(prog, height=18, bg=CARD, highlightthickness=0)
        self.prog_cv.pack(fill="x", padx=16, pady=(0, 12))
        self.prog_cv.bind("<Configure>", lambda e: self.draw_progress())

        charts = tk.Frame(page, bg=BG)
        charts.pack(fill="both", expand=True, pady=(14, 0))
        charts.columnconfigure(0, weight=3, uniform="c")
        charts.columnconfigure(1, weight=2, uniform="c")
        charts.rowconfigure(0, weight=1)
        for col, title, attr in [(0, "📊  Hours per Subject", "bar_cv"), (1, "🥧  Study Time Share", "pie_cv")]:
            card = tk.Frame(charts, bg=CARD)
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 0))
            self.label(card, title, 13, "white", True).pack(anchor="w", padx=16, pady=(12, 0))
            cv = tk.Canvas(card, bg=CARD, highlightthickness=0)
            cv.pack(fill="both", expand=True, padx=8, pady=8)
            cv.bind("<Configure>", lambda e: self.draw_charts())
            setattr(self, attr, cv)

    # ---------- Page 2: Sessions ----------
    def build_sessions(self, page):
        form = tk.Frame(page, bg=CARD)
        form.pack(fill="x")
        self.label(form, "➕  New Study Session", 13, "white", True).grid(row=0, column=0, columnspan=5, sticky="w", padx=16, pady=(12, 4))
        self.subject_var, self.deadline_var = tk.StringVar(), tk.StringVar()
        self.duration_var, self.diff_var = tk.StringVar(), tk.StringVar(value="Medium")
        self.deadline_var.set((date.today() + timedelta(days=7)).strftime("%Y-%m-%d"))

        self.subject_cb = ttk.Combobox(form, textvariable=self.subject_var, values=SUBJECTS, width=22,
                                       style="Dark.TCombobox", font=(FONT, 11))
        diff_cb = ttk.Combobox(form, textvariable=self.diff_var, values=list(WEIGHT), width=12, state="readonly",
                               style="Dark.TCombobox", font=(FONT, 11))
        widgets = [("Subject", self.subject_cb), ("Deadline (YYYY-MM-DD)", self.entry(form, self.deadline_var, 16)),
                   ("Duration (hours)", self.entry(form, self.duration_var, 12)), ("Difficulty", diff_cb)]
        for i, (text, w) in enumerate(widgets):
            self.label(form, text, 10, CYAN, True).grid(row=1, column=i, sticky="w", padx=(16, 4))
            w.grid(row=2, column=i, sticky="w", padx=(16, 4), pady=(2, 14), ipady=3)
        self.button(form, "+ Add Session", PURPLE, self.add_session).grid(row=2, column=4, padx=16, pady=(2, 14))

        bar = tk.Frame(page, bg=BG)
        bar.pack(fill="x", pady=10)
        self.button(bar, "✅ Mark Done", GREEN, self.mark_done).pack(side="left", padx=(0, 8))
        self.button(bar, "🗑 Delete Selected", RED, self.delete_session).pack(side="left")
        self.button(bar, "🧹 Clear All", "#475569", self.clear_all).pack(side="left", padx=8)
        tk.Label(bar, text="🔴 High   🟡 Medium   🟢 Low priority", bg=BG, fg=MUTED, font=(FONT, 10)).pack(side="right")

        card = tk.Frame(page, bg=CARD)
        card.pack(fill="both", expand=True)
        self.tree = self.make_tree(card, ("Subject", "Deadline", "Hours", "Difficulty", "Priority", "Days Left", "Status"),
                                   (210, 110, 70, 100, 80, 80, 100))

    # ---------- Page 3: Daily Plan ----------
    def build_plan(self, page):
        top = tk.Frame(page, bg=CARD)
        top.pack(fill="x")
        self.label(top, "⏰  Free study hours per day:", 12, "white", True).pack(side="left", padx=16, pady=14)
        self.daily_var = tk.StringVar(value="4")
        ttk.Spinbox(top, from_=1, to=12, width=5, textvariable=self.daily_var, style="Dark.TSpinbox",
                    font=(FONT, 12)).pack(side="left")
        self.button(top, "⚡ Generate Plan", GREEN, self.generate_plan).pack(side="left", padx=14)
        self.button(top, "💾 Export Plan", "#475569", self.export_plan).pack(side="left")
        self.plan_info = self.label(top, "", 11, AMBER, True)
        self.plan_info.pack(side="right", padx=16)

        card = tk.Frame(page, bg=CARD)
        card.pack(fill="both", expand=True, pady=(12, 0))
        self.plan_tree = self.make_tree(card, ("Date", "Subject", "Hours"), (200, 320, 120), rows=5)

        # ----- time slot assigner -----
        slot_bar = tk.Frame(page, bg=CARD)
        slot_bar.pack(fill="x", pady=(12, 0))
        self.label(slot_bar, "🕐  Start time (HH:MM):", 12, "white", True).pack(side="left", padx=16, pady=12)
        self.start_var = tk.StringVar(value="18:00")
        self.entry(slot_bar, self.start_var, 8).pack(side="left")
        self.button(slot_bar, "🕐 Assign Time Slots", PURPLE, self.assign_slots).pack(side="left", padx=14)
        self.button(slot_bar, "📆 Export to Calendar", GREEN, self.export_calendar).pack(side="left")
        self.button(slot_bar, "☁ Sync to Google", BLUE, self.sync_google).pack(side="left", padx=(8, 0))
        self.slot_info = self.label(slot_bar, "", 11, AMBER, True)
        self.slot_info.pack(side="right", padx=16)

        slot_card = tk.Frame(page, bg=CARD)
        slot_card.pack(fill="both", expand=True, pady=(8, 0))
        self.slot_tree = self.make_tree(slot_card, ("Subject", "From", "To", "Hours"), (300, 110, 110, 90), rows=4)

    # ---------- Page 4: Focus Timer ----------
    def build_timer(self, page):
        card = tk.Frame(page, bg=CARD)
        card.pack(fill="both", expand=True)
        self.label(card, "Pomodoro Focus Timer", 16, "white", True).pack(pady=(18, 0))
        self.focus_hint = self.label(card, "Pick a subject and start focusing!", 11, CYAN, False)
        self.focus_hint.pack(pady=(2, 6))
        self.ring = tk.Canvas(card, width=280, height=280, bg=CARD, highlightthickness=0)
        self.ring.pack()
        ctl = tk.Frame(card, bg=CARD)
        ctl.pack(pady=10)
        self.button(ctl, "▶ Start", GREEN, self.timer_start).pack(side="left", padx=6)
        self.button(ctl, "⏸ Pause", AMBER, self.timer_pause).pack(side="left", padx=6)
        self.button(ctl, "↺ Reset", RED, self.timer_reset).pack(side="left", padx=6)
        self.auto_lbl = self.label(card, "", 12, AMBER, True)
        self.auto_lbl.pack()
        ctl2 = tk.Frame(card, bg=CARD)
        ctl2.pack(pady=(0, 8))
        self.button(ctl2, "▶ Auto-Run Schedule", PURPLE, self.auto_start).pack(side="left", padx=6)
        self.button(ctl2, "⏭ Skip", BLUE, self.auto_skip).pack(side="left", padx=6)
        self.demo_var = tk.BooleanVar(value=False)
        tk.Checkbutton(ctl2, text="Demo mode (10-sec blocks)", variable=self.demo_var, bg=CARD, fg=TXT,
                       selectcolor=FIELD, activebackground=CARD, activeforeground=TXT,
                       font=(FONT, 10)).pack(side="left", padx=10)
        opt = tk.Frame(card, bg=CARD)
        opt.pack()
        self.label(opt, "Minutes:", 11, MUTED).pack(side="left")
        self.min_var = tk.StringVar(value="25")
        ttk.Spinbox(opt, from_=1, to=90, width=4, textvariable=self.min_var, style="Dark.TSpinbox",
                    command=self.timer_reset).pack(side="left", padx=(4, 18))
        self.pomo_lbl = self.label(opt, "🍅 Focus sessions done: 0", 12, PINK, True)
        self.pomo_lbl.pack(side="left")
        self.draw_ring()

    # ================= CONTROLLER =================
    def set_status(self, msg):
        self.status.config(text="  ● " + msg)

    def add_session(self):
        ok, msg, deadline, hours = validate_session(
            self.subject_var.get(), self.deadline_var.get(), self.duration_var.get())
        if not ok:
            return messagebox.showerror("Invalid input", msg)
        subject = self.subject_var.get().strip()
        self.model.add_session(subject, deadline, hours, self.diff_var.get())
        self.refresh()
        self.subject_var.set("")
        self.duration_var.set("")
        self.set_status(f"Added {hours:g}h of {subject}. Sorted by priority.")

    def delete_session(self):
        sel = self.tree.selection()
        if not sel:
            return messagebox.showwarning("Select a row", "Click a session in the table first.")
        self.model.delete_sessions([int(i) for i in sel])
        self.refresh()
        self.set_status("Selected session deleted.")

    def clear_all(self):
        if not self.model.df.empty and messagebox.askyesno("Clear all", "Delete ALL sessions?"):
            self.model.clear()
            self.refresh()
            self.set_status("All sessions cleared.")

    def load_sample(self):
        self.model.add_sample()
        self.refresh()
        self.set_status("Sample data loaded. Check the Dashboard and Daily Plan pages!")

    def refresh(self):
        self.model.compute_priority()
        df = self.model.df
        self.tree.delete(*self.tree.get_children())
        for i, r in df.iterrows():
            tag = "done" if r["Status"] == "Done" else \
                "high" if r["Priority_Score"] >= 10 else "med" if r["Priority_Score"] >= 4 else "low"
            self.tree.insert("", "end", iid=str(i), tags=(tag,), values=(
                r["Subject"], r["Deadline"], f"{r['Duration']:g}", r["Difficulty"], r["Priority_Score"],
                int(r["Days_Left"]), "✅ Done" if r["Status"] == "Done" else "Pending"))
        if df.empty:
            for k, v in zip(("hours", "count", "urgent", "next"), ("0", "0", "-", "-")):
                self.stat[k].config(text=v)
            self.focus_hint.config(text="Pick a subject and start focusing!")
        else:
            pend = df[df["Status"] != "Done"]               # urgent / next only look at unfinished work
            self.stat["hours"].config(text=f"{df['Duration'].sum():g} h")
            self.stat["count"].config(text=str(len(df)))
            if pend.empty:
                self.stat["urgent"].config(text="All done!")
                self.stat["next"].config(text="-")
                self.focus_hint.config(text="🎉 All sessions completed!")
            else:
                top, nxt = pend.iloc[0], pend.sort_values("Days_Left").iloc[0]
                self.stat["urgent"].config(text=top["Subject"][:18])
                self.stat["next"].config(text=f"{int(nxt['Days_Left'])} days")
                self.focus_hint.config(text=f"💡 Suggested focus: {top['Subject']} (most urgent)")
        self.draw_progress()
        self.draw_charts()

    # ----- Charts drawn on Canvas -----
    def draw_charts(self):
        bc, pc = self.bar_cv, self.pie_cv
        bc.delete("all")
        pc.delete("all")
        if self.model.df.empty:
            for cv in (bc, pc):
                cv.create_text(cv.winfo_width() / 2, cv.winfo_height() / 2, fill=MUTED, font=(FONT, 12),
                               text="No data yet.\nAdd sessions or load sample data.", justify="center")
            return
        per = self.model.df.groupby("Subject")["Duration"].sum().sort_values(ascending=False)
        mx, total = per.max(), per.sum()
        w = max(bc.winfo_width(), 300)
        for i, (sub, h) in enumerate(per.items()):
            y, col = 12 + i * 44, PALETTE[i % len(PALETTE)]
            bc.create_text(6, y + 14, text=sub[:17], anchor="w", fill=TXT, font=(FONT, 10, "bold"))
            bar_w = max(8, (w - 240) * h / mx)
            bc.create_rectangle(160, y, 160 + bar_w, y + 28, fill=col, outline="")
            bc.create_text(168 + bar_w, y + 14, text=f"{h:g}h", anchor="w", fill=col, font=(FONT, 11, "bold"))
        # pie / donut
        ph = max(pc.winfo_height(), 250)
        r, cx, cy = min(ph / 2 - 15, 95), 110, ph / 2
        start = 90
        for i, (sub, h) in enumerate(per.items()):
            col, ext = PALETTE[i % len(PALETTE)], -360 * h / total
            if len(per) == 1:
                pc.create_oval(cx - r, cy - r, cx + r, cy + r, fill=col, outline="")
            else:
                pc.create_arc(cx - r, cy - r, cx + r, cy + r, start=start, extent=ext, fill=col, outline=CARD, width=2)
            start += ext
            ly = 30 + i * 26
            pc.create_rectangle(cx + r + 25, ly, cx + r + 39, ly + 14, fill=col, outline="")
            pc.create_text(cx + r + 46, ly + 7, anchor="w", fill=TXT, font=(FONT, 10),
                           text=f"{sub[:15]}  {h / total * 100:.0f}%")
        pc.create_oval(cx - r * .55, cy - r * .55, cx + r * .55, cy + r * .55, fill=CARD, outline="")
        pc.create_text(cx, cy, text=f"{total:g}h", fill="white", font=(FONT, 16, "bold"))

    # ----- Daily plan -----
    def generate_plan(self):
        df = self.model.df
        if df.empty:
            return messagebox.showinfo("No data", "Add some study sessions first.")
        if (df["Status"] == "Done").all():
            return messagebox.showinfo("All done", "All sessions are already marked as done. 🎉")
        ok, msg, daily = validate_daily_hours(self.daily_var.get())
        if not ok:
            return messagebox.showerror("Invalid", msg)
        plan, leftover = self.model.generate_plan(daily)
        self.plan_tree.delete(*self.plan_tree.get_children())
        subjects = list(df["Subject"].unique())
        for _, r in plan.iterrows():
            tag = ("high", "med", "low")[subjects.index(r["Subject"]) % 3]
            self.plan_tree.insert("", "end", values=(r["Date"], r["Subject"], r["Hours"]), tags=(tag,))
        n_days = plan["Date"].nunique() if not plan.empty else 0
        self.plan_info.config(text=f"{plan['Hours'].sum():g} hours over {n_days} days")
        if leftover > 0:
            messagebox.showwarning("Not enough time", f"{leftover:.1f} hours do not fit before the deadlines.\n"
                                                      "Increase daily hours or reduce sessions.")
        self.set_status("Plan ready. Not happy? Change the hours and generate again.")

    # ----- Time slot assigner + calendar + reminders -----
    def assign_slots(self):
        if self.model.df.empty:
            return messagebox.showinfo("No data", "Add some study sessions first.")
        start = self.start_var.get().strip()
        try:
            datetime.strptime(start, "%H:%M")
        except ValueError:
            return messagebox.showerror("Invalid time", "Start time must look like 18:00 (HH:MM, 24-hour).")
        ok, msg, hours = validate_daily_hours(self.daily_var.get())
        if not ok:
            return messagebox.showerror("Invalid", msg)
        slots, skipped = self.model.assign_time_slots(start, hours)
        if not slots:
            return messagebox.showinfo("Nothing to schedule", "All sessions are already marked as done. 🎉")
        self.last_slots, self.notified = slots, set()
        self.slot_tree.delete(*self.slot_tree.get_children())
        for i, (sub, a, b, h) in enumerate(slots):
            tag = "high" if i == 0 else "med" if i < 3 else "low"
            self.slot_tree.insert("", "end", values=(sub, a, b, f"{h:g}"), tags=(tag,))
        self.slot_info.config(text=f"{len(slots)} subjects scheduled")
        if skipped:
            messagebox.showwarning("Not enough time", "No time left today for:\n" + ", ".join(skipped) +
                                   "\nIncrease the free hours or start earlier.")
        self.set_status("Time slots assigned in priority order. Reminders are ON while the app is open.")

    def export_calendar(self):
        if not self.last_slots:
            return messagebox.showinfo("Export", "Click 'Assign Time Slots' first.")
        path = filedialog.asksaveasfilename(defaultextension=".ics", initialfile="study_schedule.ics",
                                            filetypes=[("Calendar file", "*.ics")])
        if path:
            with open(path, "w", newline="", encoding="utf-8") as f:
                f.write(slots_to_ics(self.last_slots))
            self.set_status(f"Calendar file saved. Import it in Google Calendar: {path}")

    def sync_google(self):
        if not self.last_slots:
            return messagebox.showinfo("Sync", "Click 'Assign Time Slots' first.")
        self.set_status("Connecting to Google Calendar... (a browser window may open for login)")
        self.root.update_idletasks()
        try:
            service = get_google_service()
            created, updated = sync_slots_to_google(service, self.last_slots)
        except ImportError:
            return messagebox.showerror("Missing library", "Run this in the PyCharm terminal:\n"
                                        "pip install google-api-python-client google-auth-oauthlib")
        except FileNotFoundError:
            return messagebox.showerror("credentials.json missing",
                                        "Put credentials.json in the same folder as this file.")
        except Exception as e:
            self.set_status("Google sync failed.")
            return messagebox.showerror("Sync failed", f"{type(e).__name__}: {e}\n\n"
                                        "If it says invalid_grant, delete token.json and try again.")
        messagebox.showinfo("Synced", f"Google Calendar updated.\nNew events: {created}\nUpdated events: {updated}")
        self.set_status(f"Synced to Google Calendar ({created} new, {updated} updated).")

    def mark_done(self):
        sel = self.tree.selection()
        if not sel:
            return messagebox.showwarning("Select a row", "Click a session in the table first.")
        names = self.model.mark_done([int(i) for i in sel])
        if not names:
            return messagebox.showinfo("Already done", "The selected session(s) are already marked as done.")
        self.refresh()
        messagebox.showinfo("Task completed! ✅", "Great work! Completed:\n" + "\n".join(names))
        self.set_status("Marked done: " + ", ".join(names))

    def draw_progress(self):
        df, cv = self.model.df, self.prog_cv
        total = len(df)
        done = int((df["Status"] == "Done").sum()) if total else 0
        self.prog_lbl.config(text=f"✅  Progress: {done} / {total} sessions completed")
        cv.delete("all")
        w = max(cv.winfo_width(), 100)
        cv.create_rectangle(0, 3, w, 15, fill=FIELD, outline="")
        if total and done:
            cv.create_rectangle(0, 3, w * done / total, 15, fill=GREEN, outline="")

    def check_reminders(self):
        """Runs every 30 seconds while the app is open and pops up a reminder at each slot's start time."""
        now = datetime.now().strftime("%H:%M")
        for sub, start, end, h in self.last_slots:
            if start == now and (sub, start) not in self.notified:
                self.notified.add((sub, start))
                self.root.bell()
                messagebox.showinfo("Study time!", f"Time to study: {sub}\n{start} to {end}")
        self.root.after(30000, self.check_reminders)

    # ----- Export / Import -----
    def export_csv(self):
        if self.model.df.empty:
            return messagebox.showinfo("Export", "No data to export.")
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="study_sessions.csv",
                                            filetypes=[("CSV file", "*.csv")])
        if path:
            self.model.save_csv(path)
            self.set_status(f"Saved to {path}")

    def export_plan(self):
        if self.model.plan_df.empty:
            return messagebox.showinfo("Export", "Generate a plan first.")
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="daily_plan.csv",
                                            filetypes=[("CSV file", "*.csv")])
        if path:
            self.model.save_plan(path)
            self.set_status(f"Plan saved to {path}")

    def load_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV file", "*.csv")])
        if not path:
            return
        try:
            count = self.model.load_csv(path)
            self.refresh()
            self.set_status(f"Loaded {count} sessions from file.")
        except Exception as e:
            messagebox.showerror("Load failed", f"Could not read this file.\n{e}")

    # ================= FOCUS TIMER =================
    def draw_ring(self):
        c = self.ring
        c.delete("all")
        c.create_oval(20, 20, 260, 260, outline=FIELD, width=16)
        frac = self.t_left / self.t_total if self.t_total else 0
        in_break = self.auto_active and self.phase == "break"
        if frac > 0:
            col = CYAN if in_break else GREEN if self.running else PURPLE
            c.create_arc(20, 20, 260, 260, start=90, extent=-359.9 * frac, style="arc", outline=col, width=16)
        h, rem = divmod(self.t_left, 3600)
        m, s = divmod(rem, 60)
        c.create_text(140, 125, text=f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}", fill="white",
                      font=(FONT, 36 if h else 44, "bold"))
        if self.auto_active and self.auto_idx < len(self.auto_queue):
            if not self.running:
                state = "PAUSED"
            elif in_break:
                state = "BREAK TIME"
            else:
                state = f"STUDYING: {self.auto_queue[self.auto_idx][0]}"[:26]
        else:
            state = "FOCUSING..." if self.running else "READY"
        c.create_text(140, 180, text=state, fill=MUTED, font=(FONT, 11, "bold"))

    def timer_start(self):
        if not self.running and self.t_left > 0:
            self.running = True
            self.set_status("Focus mode ON. Stay away from your phone!")
            self.tick()

    def tick(self):
        if not self.running:
            return
        self.t_left -= 1
        self.draw_ring()
        if self.t_left <= 0:
            self.running = False
            if self.auto_active:
                return self.auto_phase_done()
            self.pomos += 1
            self.pomo_lbl.config(text=f"🍅 Focus sessions done: {self.pomos}")
            self.root.bell()
            self.timer_reset()
            messagebox.showinfo("Great job!", "Focus session complete. Take a short break!")
            return
        self.job = self.root.after(1000, self.tick)

    # ----- Auto-run schedule: the timer follows the time slots, subject by subject -----
    def update_auto_label(self):
        if not self.auto_active or self.auto_idx >= len(self.auto_queue):
            return self.auto_lbl.config(text="")
        sub, secs, hours = self.auto_queue[self.auto_idx]
        nxt = self.auto_queue[self.auto_idx + 1][0] if self.auto_idx + 1 < len(self.auto_queue) else None
        if self.phase == "break":
            self.auto_lbl.config(text=f"☕ Break time   |   Up next: {nxt}")
        else:
            self.auto_lbl.config(text=f"Now studying: {sub} ({hours:g}h)   |   Next: {nxt or 'none - last one!'}")

    def auto_start(self):
        if not self.last_slots:
            return messagebox.showinfo("Auto-Run", "Go to the Daily Plan page and click 'Assign Time Slots' first.")
        if self.job:
            self.root.after_cancel(self.job)
        demo = self.demo_var.get()
        self.auto_queue = [(sub, 10 if demo else max(1, int(h * 3600)), h) for sub, a, b, h in self.last_slots]
        self.break_secs = 5 if demo else 600
        self.auto_active, self.auto_idx, self.running = True, 0, False
        self.auto_begin_block()

    def auto_begin_block(self):
        sub, secs, hours = self.auto_queue[self.auto_idx]
        self.phase, self.t_total, self.t_left = "study", secs, secs
        self.running = True
        self.update_auto_label()
        self.draw_ring()
        self.set_status(f"Auto-run: studying {sub}. Stay focused!")
        self.job = self.root.after(1000, self.tick)

    def auto_phase_done(self):
        """Called by tick() when a study block or a break reaches zero."""
        if self.phase == "break":                         # break over -> next subject
            self.auto_idx += 1
            return self.auto_begin_block()
        sub = self.auto_queue[self.auto_idx][0]           # study block over
        self.pomos += 1
        self.pomo_lbl.config(text=f"🍅 Focus sessions done: {self.pomos}")
        self.root.bell()
        if self.auto_idx >= len(self.auto_queue) - 1:     # that was the last subject
            return self.auto_finish()
        nxt = self.auto_queue[self.auto_idx + 1][0]
        messagebox.showinfo("Block finished", f"{sub} finished.\nTake a short break! Next up: {nxt}")
        self.phase, self.t_total, self.t_left = "break", self.break_secs, self.break_secs
        self.running = True
        self.update_auto_label()
        self.draw_ring()
        self.set_status("Break time. The next subject starts automatically.")
        self.job = self.root.after(1000, self.tick)

    def auto_skip(self):
        if not self.auto_active:
            return messagebox.showinfo("Skip", "Start 'Auto-Run Schedule' first.")
        if self.job:
            self.root.after_cancel(self.job)
        self.running = False
        self.auto_idx += 1
        if self.auto_idx >= len(self.auto_queue):
            return self.auto_finish()
        self.auto_begin_block()

    def auto_finish(self):
        self.timer_reset()
        messagebox.showinfo("Schedule complete", "All subjects completed! 🎉 Great work today.")
        self.set_status("Schedule complete. Tip: mark finished sessions as done on the Sessions page.")

    def timer_pause(self):
        self.running = False
        if self.job:
            self.root.after_cancel(self.job)
        self.draw_ring()
        self.set_status("Timer paused.")

    def timer_reset(self):
        self.running = False
        if self.job:
            self.root.after_cancel(self.job)
        self.auto_active, self.phase = False, "focus"
        self.update_auto_label()
        try:
            mins = max(1, min(90, int(self.min_var.get())))
        except ValueError:
            mins = 25
        self.t_total = self.t_left = mins * 60
        self.draw_ring()


# ======================================================================
# 6. ENTRY POINT
# ======================================================================
def main():
    root = tk.Tk()
    SmartStudyPlanner(root)
    root.mainloop()


if __name__ == "__main__":
    main()