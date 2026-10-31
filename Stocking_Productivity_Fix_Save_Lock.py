import os, sqlite3, calendar, hashlib, hmac, secrets
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, date

APP_DATA = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "StockingProductivity")
os.makedirs(APP_DATA, exist_ok=True)
DB = os.path.join(APP_DATA, "stocking_productivity.db")

ADMIN_ID = "I3J108"
ADMIN_NAME = "Shubham Chatur"
ADMIN_PASSWORD = "Shubham@0510"

BG = "#EAF8E8"  # Light green background applied across all application pages
SIDEBAR = "#102A43"
SIDEBAR2 = "#173B5F"
ACCENT = "#0877E8"
ACCENT2 = "#19A7FF"
TEXT = "#172033"
MUTED = "#6B778C"
WHITE = "#FFFFFF"
BORDER = "#D7E2EE"
GREEN = "#16834A"
RED = "#C62828"

EMPLOYEE_SEED = [('1', 'AJAY Y', 'STOCKING', 'RAJOO', 'Active'), ('2', 'MAHESAH J', 'STOCKING', 'RAJOO', 'Active'), ('3', 'RISHIKESH Y', 'STOCKING', 'RAJOO', 'Active'), ('4', 'ASHUTOSH Y', 'STOCKING', 'RAJOO', 'Active'), ('5', 'YOGENDRA M', 'STOCKING', 'RAJOO', 'Active'), ('6', 'JISHAN A', 'STOCKING', 'RAJOO', 'Active'), ('7', 'SAMIR Y', 'STOCKING', 'RAJOO', 'Active'), ('8', 'AKASH S', 'STOCKING', 'RAJOO', 'Active'), ('9', 'VISHAL S', 'STOCKING', 'RAJOO', 'Active'), ('10', 'SACHIN K', 'STOCKING', 'RAJOO', 'Active'), ('11', 'RAHUL P', 'STOCKING', 'RAJOO', 'Active'), ('12', 'GANESH M', 'STOCKING', 'RAJOO', 'Active'), ('13', 'PRASHANT J', 'STOCKING', 'RAJOO', 'Active'), ('14', 'NILESH P', 'STOCKING', 'RAJOO', 'Active'), ('15', 'AMOL S', 'STOCKING', 'RAJOO', 'Active'), ('16', 'SANDIP Y', 'STOCKING', 'RAJOO', 'Active'), ('17', 'ROHIT K', 'STOCKING', 'RAJOO', 'Active'), ('18', 'VIKAS R', 'STOCKING', 'RAJOO', 'Active'), ('19', 'KIRAN S', 'STOCKING', 'RAJOO', 'Active'), ('20', 'RAJESH M', 'STOCKING', 'RAJOO', 'Active'), ('21', 'MANOJ P', 'STOCKING', 'RAJOO', 'Active'), ('22', 'SANTOSH K', 'STOCKING', 'RAJOO', 'Active'), ('23', 'DHARAMRAJ K', 'STOCKING', 'RAJOO', 'Active'), ('24', 'SURAJ M', 'STOCKING', 'RAJOO', 'Active'), ('25', 'DEEPAK K', 'STOCKING', 'RAJOO', 'Active')]

def db():
    # Wait for other short-lived readers/writers instead of failing immediately.
    c = sqlite3.connect(DB, timeout=30.0)
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("PRAGMA synchronous=NORMAL")
    c.row_factory = sqlite3.Row
    return c

def hash_password(password):
    """Return a salted PBKDF2 password hash for storage."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt, 310_000)
    return "pbkdf2_sha256$310000$%s$%s" % (salt.hex(), digest.hex())


def verify_password(password, stored):
    """Verify modern hashes and support one-time migration from legacy plaintext."""
    stored = str(stored or "")
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, rounds, salt_hex, digest_hex = stored.split("$", 3)
            digest = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
            return hmac.compare_digest(digest.hex(), digest_hex)
        except (ValueError, TypeError):
            return False
    return hmac.compare_digest(str(password), stored)


def is_iso_month(value):
    try:
        datetime.strptime(value, "%Y-%m")
        return True
    except (TypeError, ValueError):
        return False


def normalized_date_sql(column):
    """SQL expression normalizing ISO YYYY-MM-DD and legacy DD-MM-YYYY dates."""
    return (f"CASE WHEN substr({column},5,1)='-' THEN substr({column},1,10) "
            f"WHEN length({column})=10 AND substr({column},3,1)='-' "
            f"THEN substr({column},7,4)||'-'||substr({column},4,2)||'-'||substr({column},1,2) "
            f"ELSE '' END")


def accuracy(labels, mistakes):
    labels = int(labels or 0); mistakes = int(mistakes or 0)
    return round((labels - mistakes) * 100 / labels, 2) if labels else 0.0

def init_db():
    c = db()
    # WAL allows the dashboard to read while daily productivity is being saved.
    # Keep the same database file; this does not erase any existing records.
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        login_id TEXT PRIMARY KEY, display_name TEXT NOT NULL,
        password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'User',
        active INTEGER NOT NULL DEFAULT 1)""")

    # Migration-safe Employee Master:
    # Older versions may already have an employees table without department.
    if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='employees'").fetchone():
        cols = {r["name"] for r in c.execute("PRAGMA table_info(employees)").fetchall()}
        migrations = [
            ("department", "TEXT DEFAULT 'STOCKING'"),
            ("supervisor", "TEXT DEFAULT ''"),
            ("status", "TEXT NOT NULL DEFAULT 'Active'"),
            ("left_date", "TEXT DEFAULT ''")
        ]
        for col, definition in migrations:
            if col not in cols:
                c.execute(f"ALTER TABLE employees ADD COLUMN {col} {definition}")
        c.execute("UPDATE employees SET department='STOCKING' WHERE department IS NULL OR department=''")
        c.execute("UPDATE employees SET supervisor='' WHERE supervisor IS NULL")
        c.execute("UPDATE employees SET status='Active' WHERE status IS NULL OR status=''")
    else:
        c.execute("""CREATE TABLE employees(
            employee_id TEXT PRIMARY KEY, employee_name TEXT NOT NULL,
            department TEXT DEFAULT 'STOCKING', supervisor TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Active', left_date TEXT DEFAULT '')""")

    c.execute("""CREATE TABLE IF NOT EXISTS supervisors(
        name TEXT PRIMARY KEY, active INTEGER NOT NULL DEFAULT 1)""")
    c.execute("INSERT OR IGNORE INTO supervisors(name,active) VALUES(?,1)",("RAJOO",))

    c.execute("""CREATE TABLE IF NOT EXISTS daily(
        work_date TEXT NOT NULL, employee_id TEXT NOT NULL,
        labels INTEGER NOT NULL DEFAULT 0, mistakes INTEGER NOT NULL DEFAULT 0,
        supervisor TEXT DEFAULT '', remark TEXT DEFAULT '',
        accuracy REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'Present', shift TEXT NOT NULL DEFAULT 'G',
        PRIMARY KEY(work_date, employee_id))""")
    # Migration for older database layouts. Add every column required by the
    # current app without deleting/recreating the existing daily table.
    dcols = {r["name"] for r in c.execute("PRAGMA table_info(daily)").fetchall()}
    required_daily_columns = [
        # Some older database versions require employee_name on every daily row.
        # Keep this column compatible and populate it for new writes.
        ("employee_name", "TEXT NOT NULL DEFAULT ''"),
        ("labels", "INTEGER NOT NULL DEFAULT 0"),
        ("mistakes", "INTEGER NOT NULL DEFAULT 0"),
        ("supervisor", "TEXT DEFAULT ''"),
        ("remark", "TEXT DEFAULT ''"),
        ("accuracy", "REAL NOT NULL DEFAULT 0"),
        ("status", "TEXT NOT NULL DEFAULT 'Present'"),
        ("shift", "TEXT NOT NULL DEFAULT 'G'"),
        ("updated_by_id", "TEXT NOT NULL DEFAULT ''"),
        ("updated_by_name", "TEXT NOT NULL DEFAULT ''"),
    ]
    added_daily_columns = set()
    for col, definition in required_daily_columns:
        if col not in dcols:
            c.execute(f"ALTER TABLE daily ADD COLUMN {col} {definition}")
            dcols.add(col)
            added_daily_columns.add(col)

    # Preserve values stored by earlier versions that used different names.
    # Backfill only when a legacy column exists; never overwrite current values.
    legacy_sources = {
        "labels": ("labels_scanned", "total_labels", "scanned_labels"),
        "mistakes": ("total_mistakes", "error_count", "errors"),
        "supervisor": ("supervisor_name",),
        "remark": ("remarks", "comments"),
    }
    for target, candidates in legacy_sources.items():
        if target not in added_daily_columns:
            continue
        source = next((name for name in candidates if name in dcols), None)
        if source and source != target:
            c.execute(f"UPDATE daily SET {target} = COALESCE({source}, {target})")
    # Backfill legacy employee_name values without overwriting existing names.
    current_cols = {r["name"] for r in c.execute("PRAGMA table_info(daily)").fetchall()}
    if "employee_name" in current_cols and c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='employees'").fetchone():
        c.execute("""UPDATE daily SET employee_name=COALESCE(
            (SELECT employee_name FROM employees WHERE employees.employee_id=daily.employee_id), '')
            WHERE employee_name IS NULL OR employee_name=''""")
    # Recompute only missing/zero accuracy values from migrated label counts.
    c.execute("UPDATE daily SET accuracy = CASE WHEN COALESCE(labels,0)>0 THEN ROUND((labels-COALESCE(mistakes,0))*100.0/labels,2) ELSE 0 END WHERE accuracy IS NULL OR accuracy=0")

    c.execute("INSERT OR IGNORE INTO users VALUES(?,?,?,?,?)",
              (ADMIN_ID, ADMIN_NAME, hash_password(ADMIN_PASSWORD), "Admin", 1))
    # Ensure Shubham's login stays Admin even if an older database had it as User.
    # Preserve the existing password hash.
    c.execute("UPDATE users SET display_name=?, role='Admin', active=1 WHERE login_id=?",
              (ADMIN_NAME, ADMIN_ID))

    for e in EMPLOYEE_SEED:
        # Works with both migrated and newly-created employee tables.
        c.execute("""INSERT OR IGNORE INTO employees
            (employee_id,employee_name,department,supervisor,status)
            VALUES(?,?,?,?,?)""", e)

    c.commit()
    c.close()

class CalendarPopup(tk.Toplevel):
    def __init__(self, parent, variable, title="Select Date", date_format="%Y-%m-%d", on_select=None):
        super().__init__(parent)
        self.var=variable; self.date_format=date_format; self.on_select=on_select; self.title(title); self.resizable(False,False)
        self.configure(bg=WHITE); self.transient(parent); self.grab_set()
        try:
            d=datetime.strptime(variable.get(),self.date_format)
        except:
            d=datetime.now()
        self.year,self.month=d.year,d.month
        self.build()

    def build(self):
        for w in self.winfo_children(): w.destroy()
        head=tk.Frame(self,bg=WHITE); head.pack(fill="x",padx=10,pady=10)
        tk.Button(head,text="‹",command=self.prev,relief="flat",bg=WHITE,
                  font=("Segoe UI",14)).pack(side="left")
        tk.Label(head,text=f"{calendar.month_name[self.month]} {self.year}",
                 bg=WHITE,fg=TEXT,font=("Segoe UI",11,"bold")).pack(side="left",expand=True)
        tk.Button(head,text="›",command=self.next,relief="flat",bg=WHITE,
                  font=("Segoe UI",14)).pack(side="right")
        grid=tk.Frame(self,bg=WHITE); grid.pack(padx=10,pady=(0,7))
        for i,n in enumerate(["Mo","Tu","We","Th","Fr","Sa","Su"]):
            tk.Label(grid,text=n,width=4,bg=WHITE,fg=MUTED,font=("Segoe UI",9,"bold")).grid(row=0,column=i)
        today_dt = date.today()
        try:
            selected_dt = datetime.strptime(self.var.get(), self.date_format).date()
        except Exception:
            selected_dt = None
        for r,wk in enumerate(calendar.monthcalendar(self.year,self.month),1):
            for col,d in enumerate(wk):
                if d:
                    is_today = (self.year == today_dt.year and self.month == today_dt.month and d == today_dt.day)
                    is_selected = (selected_dt is not None and self.year == selected_dt.year and self.month == selected_dt.month and d == selected_dt.day)
                    bg = "#DCEEFF" if is_today else WHITE
                    fg = "#0B5CAB" if is_today else TEXT
                    relief = "solid" if (is_today or is_selected) else "flat"
                    bd = 1 if (is_today or is_selected) else 0
                    tk.Button(grid,text=str(d),width=4,relief=relief,bd=bd,bg=bg,fg=fg,
                              font=("Segoe UI",9,"bold" if is_today else "normal"),
                              command=lambda d=d:self.pick(d)).grid(row=r,column=col,padx=1,pady=1)
    def prev(self):
        self.month-=1
        if self.month==0:self.month=12;self.year-=1
        self.build()
    def next(self):
        self.month+=1
        if self.month==13:self.month=1;self.year+=1
        self.build()
    def pick(self,d):
        self.var.set(datetime(self.year,self.month,d).strftime(self.date_format))
        if self.on_select:
            self.on_select()
        self.destroy()

class Login(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Stocking Productivity System")
        sw,sh=self.winfo_screenwidth(),self.winfo_screenheight()
        w,h=900,560
        if sw<1000 or sh<650:
            w=max(800,sw-40); h=max(520,sh-90)
        self.geometry(f"{w}x{h}+{max(0,(sw-w)//2)}+{max(0,(sh-h)//2)}")
        self.resizable(False,False); self.configure(bg="#071A33")
        self.show_pw=tk.BooleanVar(value=False); self.id=tk.StringVar(); self.pw=tk.StringVar()
        self.build(); self.after(120,self.id_entry.focus_set); self.disable_maximize()

    def disable_maximize(self):
        try:
            import ctypes
            hwnd=self.winfo_id(); GWL_STYLE=-16; WS_MAXIMIZEBOX=0x00010000
            style=ctypes.windll.user32.GetWindowLongW(hwnd,GWL_STYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd,GWL_STYLE,style & ~WS_MAXIMIZEBOX)
        except: pass

    def build(self):
        # ---------- LEFT BRAND PANEL ----------
        left=tk.Frame(self,bg="#082B52")
        left.pack(side="left",fill="both",expand=True)

        cv=tk.Canvas(left,bg="#082B52",highlightthickness=0)
        cv.place(relwidth=1,relheight=1)

        def draw_bg(e):
            cv.delete("all")
            w,h=e.width,e.height
            for x in range(-h,w,85):
                cv.create_line(x,h,x+h,0,fill="#0D3A67",width=2)
            for x in (int(w*.72),int(w*.88)):
                cv.create_line(x,int(h*.15),x,h,fill="#123F6B",width=6)
                for y in (int(h*.34),int(h*.52),int(h*.70)):
                    cv.create_line(x-75,y,x+20,y,fill="#123F6B",width=5)
            cv.create_rectangle(0,int(h*.87),w,h,fill="#062340",outline="")
        cv.bind("<Configure>",draw_bg)

        brand=tk.Frame(left,bg="#082B52")
        brand.place(relx=.085,rely=.13,relwidth=.83,relheight=.76)

        tk.Label(brand,text="▰",bg="#082B52",fg="#2EAFFF",
                 font=("Segoe UI",24,"bold")).pack(anchor="w")

        tk.Label(brand,text="STOCKING",bg="#082B52",fg=WHITE,
                 font=("Segoe UI",27,"bold")).pack(anchor="w",pady=(5,0))
        tk.Label(brand,text="PRODUCTIVITY",bg="#082B52",fg="#2EAFFF",
                 font=("Segoe UI",27,"bold")).pack(anchor="w")
        tk.Label(brand,text="SYSTEM",bg="#082B52",fg=WHITE,
                 font=("Segoe UI",27,"bold")).pack(anchor="w")

        tk.Frame(brand,bg="#28A8FF",height=3).pack(fill="x",pady=(14,10))
        tk.Label(brand,text="Track   |   Manage   |   Analyze   |   Improve",
                 bg="#082B52",fg="#DCEBFA",font=("Segoe UI",9)).pack(anchor="w")

        tip=tk.Frame(brand,bg="#0A3761",highlightbackground="#1C6594",
                     highlightthickness=1)
        tip.pack(fill="x",pady=24)
        tk.Label(tip,text="Better Tracking\nHigher Productivity\nStronger Team",
                 bg="#0A3761",fg=WHITE,justify="left",
                 font=("Segoe UI",11)).pack(anchor="w",padx=20,pady=14)

        # ---------- RIGHT LOGIN PANEL ----------
        right=tk.Frame(self,bg=BG,width=300)
        right.pack(side="right",fill="y")
        right.pack_propagate(False)

        card_canvas=tk.Canvas(right,bg=BG,highlightthickness=0,bd=0)
        card_canvas.place(relx=.5,rely=.5,anchor="center",relwidth=.97,relheight=.72)

        def draw_login_card(event=None):
            card_canvas.delete("rounded_card")
            cw=max(20,card_canvas.winfo_width())
            ch=max(20,card_canvas.winfo_height())
            r=12
            # Rounded white card body with a blue accent strip along the top.
            card_canvas.create_arc(0,0,2*r,2*r,start=90,extent=90,fill=WHITE,outline=WHITE,tags="rounded_card")
            card_canvas.create_arc(cw-2*r,0,cw,2*r,start=0,extent=90,fill=WHITE,outline=WHITE,tags="rounded_card")
            card_canvas.create_arc(0,ch-2*r,2*r,ch,start=180,extent=90,fill=WHITE,outline=WHITE,tags="rounded_card")
            card_canvas.create_arc(cw-2*r,ch-2*r,cw,ch,start=270,extent=90,fill=WHITE,outline=WHITE,tags="rounded_card")
            card_canvas.create_rectangle(r,0,cw-r,ch,fill=WHITE,outline=WHITE,tags="rounded_card")
            card_canvas.create_rectangle(0,r,cw,ch-r,fill=WHITE,outline=WHITE,tags="rounded_card")
            card_canvas.create_rectangle(0,0,cw,7,fill=ACCENT,outline=ACCENT,tags="rounded_card")

        card_canvas.bind("<Configure>",draw_login_card)
        card=tk.Frame(card_canvas,bg=WHITE,bd=0,highlightthickness=0)
        card_canvas.create_window(1,7,anchor="nw",window=card,width=1,height=1,tags="card_content")

        def size_login_content(event=None):
            card_canvas.itemconfigure("card_content",width=max(1,card_canvas.winfo_width()-2),height=max(1,card_canvas.winfo_height()-8))
        card_canvas.bind("<Configure>",lambda e:(draw_login_card(e),size_login_content(e)))

        tk.Frame(card,bg=ACCENT,height=0).pack(fill="x")

        tk.Label(card,text="Welcome to i3PL",bg=WHITE,fg="#102B4D",
                 font=("Segoe UI",19,"bold")).pack(pady=(13,4))
        tk.Label(card,text="Login to access Stocking Productivity System",
                 bg=WHITE,fg=MUTED,font=("Segoe UI",8)).pack(pady=(0,10))

        def make_field(icon,var,show=""):
            outer=tk.Frame(card,bg="#F8FBFE",highlightbackground="#BFD3E5",
                           highlightthickness=1)
            outer.pack(fill="x",padx=20,pady=5)

            tk.Label(outer,text=icon,bg="#F8FBFE",fg="#4B6983",
                     font=("Segoe UI",10)).pack(side="left",padx=(8,5))

            ent=tk.Entry(outer,textvariable=var,show=show,bd=0,
                         relief="flat",bg="#F8FBFE",fg=TEXT,
                         insertbackground=TEXT,font=("Segoe UI",12))
            ent.pack(side="left",fill="x",expand=True,ipady=6)
            return ent

        self.id_entry=make_field("♟",self.id)
        self.id_entry.insert(0,"")
        self.pe=make_field("🔒",self.pw,"•")

        show_row=tk.Frame(card,bg=WHITE)
        show_row.pack(fill="x",padx=32,pady=(1,5))

        tk.Checkbutton(show_row,text="Show Password",
                       variable=self.show_pw,command=self.toggle,
                       bg=WHITE,activebackground=WHITE,
                       selectcolor=WHITE,fg="#60768C",
                       font=("Segoe UI",8),bd=0,
                       highlightthickness=0).pack(side="left")

        login_btn=tk.Button(card,text="LOGIN   →",command=self.login,
                            bg=ACCENT,fg=WHITE,activebackground="#075DBA",
                            activeforeground=WHITE,relief="flat",bd=0,
                            font=("Segoe UI",11,"bold"),cursor="hand2")
        login_btn.pack(fill="x",padx=20,ipady=8,pady=(0,10))

        note=tk.Frame(card,bg="#E5F4E1")
        note.pack(fill="x",padx=18)

        tk.Label(note,text="✓",bg="#E5F4E1",fg=ACCENT,
                 font=("Segoe UI",14,"bold")).pack(side="left",
                                                  padx=(8,5),pady=7)
        tk.Label(note,text="Authorized users only\nPlease use your valid Login ID and Password", wraplength=205,
                 bg="#E5F4E1",fg="#25415D",justify="left",
                 font=("Segoe UI",8)).pack(side="left",pady=7)

        tk.Label(card,text="Stocking Productivity System  •  v1.0",
                 bg=WHITE,fg="#718096",font=("Segoe UI",9,"bold")).pack(
                     side="bottom",pady=(0,3))
        tk.Label(card,text="Developed by Shubham Chatur",
                 bg=WHITE,fg="#718096",font=("Segoe UI",9)).pack(
                     side="bottom",pady=(0,10))

        self.bind("<Return>",lambda e:self.login())

    def toggle(self): self.pe.config(show="" if self.show_pw.get() else "•")
    def login(self):
        c=db()
        try:
            row=c.execute("SELECT login_id,display_name,role,password FROM users WHERE login_id=? AND active=1",
                          (self.id.get().strip(),)).fetchone()
            if not row or not verify_password(self.pw.get(), row["password"]):
                messagebox.showerror("Login Failed","Invalid Login ID or Password.")
                return
            # Migrate old plaintext passwords after a successful login.
            if not str(row["password"]).startswith("pbkdf2_sha256$"):
                c.execute("UPDATE users SET password=? WHERE login_id=?", (hash_password(self.pw.get()), row["login_id"]))
                c.commit()
            login_data=(row["login_id"],row["display_name"],row["role"])
        finally:
            c.close()
        self.destroy(); App(*login_data).mainloop()

class App(tk.Tk):
    def __init__(self,login_id,display_name,role):
        super().__init__()
        self.login_id,self.display_name,self.role=login_id,display_name,role
        self.title("Stocking Productivity Software")
        self.geometry("1200x760"); self.minsize(1050,680); self.configure(bg=BG)
        try:
            self.state("zoomed")
        except Exception:
            pass
        self.style(); self.build_shell(); self.show_dashboard()

    def is_admin(self):
        return str(getattr(self, "role", "")).strip().lower() == "admin"

    def style(self):
        s=ttk.Style(self); s.theme_use("clam")
        s.configure("Treeview",background=WHITE,foreground=TEXT,rowheight=32,fieldbackground=WHITE,font=("Segoe UI",9),borderwidth=1,relief="solid")
        s.configure("Treeview.Heading",background="#E4F2E1",foreground=TEXT,font=("Segoe UI",9,"bold"))
        s.map("Treeview",background=[("selected","#D8EFD3")] ,foreground=[("selected",TEXT)])

    def build_shell(self):
        side=tk.Frame(self,bg=SIDEBAR,width=220); side.pack(side="left",fill="y"); side.pack_propagate(False)
        tk.Label(side,text="STOCKING",bg=SIDEBAR,fg=WHITE,font=("Segoe UI",20,"bold")).pack(anchor="w",padx=20,pady=(25,0))
        tk.Label(side,text="PRODUCTIVITY SYSTEM",bg=SIDEBAR,fg="#7CC7FF",font=("Segoe UI",8,"bold")).pack(anchor="w",padx=20,pady=(0,25))
        self.nav_buttons=[]
        for text,cmd in [("⌂  Dashboard",self.show_dashboard),("▣  Daily Productivity",self.show_daily),
                         ("▤  Monthly Summary",self.show_monthly),("👥  Employee Master",self.show_employees)]:
            b=tk.Button(side,text=text,command=cmd,anchor="w",bg=SIDEBAR,fg="#DCEBFA",activebackground=SIDEBAR2,
                        activeforeground=WHITE,bd=0,relief="flat",font=("Segoe UI",10,"bold"),padx=20,pady=12)
            b.pack(fill="x"); self.nav_buttons.append(b)
        if self.is_admin():
            b=tk.Button(side,text="⚙  User / ID Management",command=self.show_users,anchor="w",bg=SIDEBAR,fg="#DCEBFA",
                        activebackground=SIDEBAR2,activeforeground=WHITE,bd=0,relief="flat",font=("Segoe UI",10,"bold"),padx=20,pady=12)
            b.pack(fill="x"); self.nav_buttons.append(b)
            b=tk.Button(side,text="◉  Supervisor Master",command=self.show_supervisors,anchor="w",bg=SIDEBAR,fg="#DCEBFA",
                        activebackground=SIDEBAR2,activeforeground=WHITE,bd=0,relief="flat",font=("Segoe UI",10,"bold"),padx=20,pady=12)
            b.pack(fill="x"); self.nav_buttons.append(b)
        tk.Frame(side,bg=SIDEBAR).pack(fill="both",expand=True)
        user=tk.Frame(side,bg=SIDEBAR2)
        user.pack(fill="x",pady=(0,0))

        tk.Label(user,text="LOGGED IN",bg=SIDEBAR2,fg="#9FC2DD",
                 font=("Segoe UI",9,"bold")).pack(anchor="w",padx=20,pady=(16,2))
        tk.Label(user,text=self.display_name,bg=SIDEBAR2,fg=WHITE,
                 font=("Segoe UI",13,"bold")).pack(anchor="w",padx=20,pady=(0,3))
        tk.Label(user,text=f"{self.login_id}  •  {self.role}",bg=SIDEBAR2,
                 fg="#B8D0E4",font=("Segoe UI",9)).pack(anchor="w",padx=20,pady=(0,8))
        tk.Button(user,text="Logout",command=self.logout,bg=SIDEBAR2,
                  fg="#FFB8B8",activebackground=SIDEBAR2,
                  activeforeground="#FFFFFF",bd=0,relief="flat",
                  font=("Segoe UI",10,"bold"),cursor="hand2").pack(anchor="w",padx=16,pady=(0,14))

        credit=tk.Frame(side,bg=SIDEBAR)
        credit.pack(fill="x",side="bottom")
        tk.Frame(credit,bg="#2EAFFF",height=2).pack(fill="x",padx=18,pady=(0,10))
        tk.Label(credit,text="Designed & Developed by",bg=SIDEBAR,fg="#7FA5C5",
                 font=("Segoe UI",8)).pack()
        tk.Label(credit,text="Shubham Chatur",bg=SIDEBAR,fg=WHITE,
                 font=("Segoe UI",11,"bold")).pack(pady=(1,2))
        tk.Label(credit,text="Stocking Productivity System  •  v1.0",
                 bg=SIDEBAR,fg="#7FA5C5",font=("Segoe UI",7)).pack(pady=(0,12))
        self.main=tk.Frame(self,bg=BG); self.main.pack(side="right",fill="both",expand=True)

    def clear(self):
        # Commit any active spreadsheet-style editor and keep unsaved rows in memory
        # when the user switches tabs, so typing is never silently discarded.
        if hasattr(self, "daily_tv"):
            try:
                self._close_daily_editor(commit=True)
                self._cache_daily_rows()
            except Exception:
                pass
        for w in self.main.winfo_children(): w.destroy()

    def header(self,title,sub=""):
        h=tk.Frame(self.main,bg=BG); h.pack(fill="x",padx=28,pady=(22,14))
        tk.Label(h,text=title,bg=BG,fg=TEXT,font=("Segoe UI",20,"bold")).pack(anchor="w")
        if sub: tk.Label(h,text=sub,bg=BG,fg=MUTED,font=("Segoe UI",9)).pack(anchor="w",pady=(2,0))
        return h

    def card(self,parent,title,value,icon):
        f=tk.Frame(parent,bg=WHITE,highlightbackground=BORDER,highlightthickness=1)
        tk.Label(f,text=icon,bg=WHITE,fg=ACCENT,font=("Segoe UI",20,"bold")).pack(anchor="w",padx=16,pady=(14,2))
        tk.Label(f,text=title,bg=WHITE,fg=MUTED,font=("Segoe UI",8,"bold")).pack(anchor="w",padx=16)
        tk.Label(f,text=str(value),bg=WHITE,fg=TEXT,font=("Segoe UI",19,"bold")).pack(anchor="w",padx=16,pady=(1,14))
        return f

    def open_dashboard_month_picker(self):
        """Open a month/year chooser for the Dashboard selector."""
        current = self.dashboard_month_var.get().strip()
        try:
            parsed = datetime.strptime(current, "%B %Y")
            initial_year, initial_month = parsed.year, parsed.month
        except ValueError:
            today = date.today()
            initial_year, initial_month = today.year, today.month

        popup = tk.Toplevel(self)
        popup.title("Choose Dashboard Month")
        popup.configure(bg=BG)
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()

        year_var = tk.StringVar(value=str(initial_year))
        month_names = list(calendar.month_name)[1:]
        month_buttons = []

        header = tk.Frame(popup, bg=BG)
        header.pack(fill="x", padx=12, pady=(12, 8))
        tk.Button(header, text="◀", width=3, command=lambda: change_year(-1),
                  bg=WHITE, fg=TEXT, bd=1).pack(side="left")
        year_box = tk.Spinbox(header, from_=2000, to=2100, width=7,
                              textvariable=year_var, justify="center",
                              font=("Segoe UI", 11, "bold"),
                              command=lambda: refresh_month_buttons())
        year_box.pack(side="left", padx=8)
        tk.Button(header, text="▶", width=3, command=lambda: change_year(1),
                  bg=WHITE, fg=TEXT, bd=1).pack(side="left")

        month_frame = tk.Frame(popup, bg=BG)
        month_frame.pack(padx=12, pady=(0, 12))

        def choose_month(month_number):
            try:
                year = int(year_var.get())
                if not 2000 <= year <= 2100:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Invalid Year", "Please select a year from 2000 to 2100.", parent=popup)
                return
            chosen = date(year, month_number, 1).strftime("%B %Y")
            popup.grab_release()
            popup.destroy()
            self.show_dashboard(chosen)

        def refresh_month_buttons():
            try:
                year = int(year_var.get())
            except ValueError:
                year = initial_year
            for month_number, button in enumerate(month_buttons, start=1):
                is_selected = (year == initial_year and month_number == initial_month)
                button.configure(bg=(ACCENT if is_selected else WHITE),
                                 fg=(WHITE if is_selected else TEXT))

        def change_year(delta):
            try:
                year = int(year_var.get()) + delta
                if not 2000 <= year <= 2100:
                    return
                year_var.set(str(year))
                refresh_month_buttons()
            except ValueError:
                year_var.set(str(initial_year))
                refresh_month_buttons()

        for index, month_name in enumerate(month_names):
            button = tk.Button(month_frame, text=month_name[:3], width=8,
                               bg=(ACCENT if index + 1 == initial_month else WHITE),
                               fg=(WHITE if index + 1 == initial_month else TEXT),
                               bd=1, relief="solid",
                               command=lambda month_number=index + 1: choose_month(month_number))
            button.grid(row=index // 4, column=index % 4, padx=3, pady=3)
            month_buttons.append(button)

        year_var.trace_add("write", lambda *_: refresh_month_buttons())
        refresh_month_buttons()
        popup.bind("<Escape>", lambda _event: (popup.grab_release(), popup.destroy()))
        popup.protocol("WM_DELETE_WINDOW", lambda: (popup.grab_release(), popup.destroy()))

        # Ensure Tk has calculated the full calendar size before positioning it.
        # Center over the application when possible, and clamp inside the screen bounds.
        popup.update_idletasks()
        width = max(300, popup.winfo_reqwidth())
        height = max(190, popup.winfo_reqheight())
        parent_x = self.winfo_rootx()
        parent_y = self.winfo_rooty()
        parent_w = max(self.winfo_width(), 1)
        parent_h = max(self.winfo_height(), 1)
        x = parent_x + (parent_w - width) // 2
        y = parent_y + (parent_h - height) // 2
        screen_w = popup.winfo_screenwidth()
        screen_h = popup.winfo_screenheight()
        x = max(0, min(x, screen_w - width))
        y = max(0, min(y, screen_h - height))
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.lift()
        popup.focus_force()

    def show_dashboard(self, selected_month=None):
        # Month-wise dashboard. Keep the selected month when refreshing the page.
        if selected_month is None:
            try:
                selected_month = self.dashboard_month_var.get()
            except Exception:
                selected_month = date.today().strftime("%B %Y")
        self.clear()
        header = self.header("Dashboard", "Stocking department • month-wise productivity overview")

        # Month selector: October 2026 onwards only (no older months).
        month_options = []
        start_month = date(2026, 10, 1)
        now = date.today().replace(day=1)
        if now < start_month:
            now = start_month
        for offset in range(36):
            month_index = (start_month.year * 12 + (start_month.month - 1)) + offset
            y, m0 = divmod(month_index, 12)
            month_options.append(date(y, m0 + 1, 1).strftime("%B %Y"))
        if selected_month not in month_options:
            selected_month = now.strftime("%B %Y")
        selector = tk.Frame(self.main, bg=BG)
        selector.pack(fill="x", padx=28, pady=(0, 12))
        tk.Label(selector, text="Select Month", bg=BG, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 10))
        self.dashboard_month_var = tk.StringVar(value=selected_month)
        month_display = tk.Entry(selector, textvariable=self.dashboard_month_var,
                                 width=18, font=("Segoe UI", 10), state="readonly",
                                 readonlybackground=WHITE, fg=TEXT, relief="solid", bd=1)
        month_display.pack(side="left")
        tk.Button(selector, text="▦ Choose Month", command=self.open_dashboard_month_picker,
                  bg="#DDF2D8", fg=TEXT, bd=0, padx=10, pady=5,
                  font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 0))
        month_key = datetime.strptime(selected_month, "%B %Y").strftime("%Y-%m")

        active = scans = mistakes = month_scans = 0
        recent_rows = []
        top_rows = []
        c = None
        try:
            c = db()
            tables = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "employees" in tables:
                ec = {r["name"] for r in c.execute("PRAGMA table_info(employees)").fetchall()}
                if "status" in ec:
                    active = c.execute("SELECT COUNT(*) FROM employees WHERE status='Active'").fetchone()[0]
                else:
                    active = c.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
            if "daily" in tables:
                dc = {r["name"] for r in c.execute("PRAGMA table_info(daily)").fetchall()}
                date_col = next((x for x in ("work_date", "date", "entry_date") if x in dc), None)
                labels_col = next((x for x in ("labels", "labels_scanned") if x in dc), None)
                mistakes_col = next((x for x in ("mistakes", "error_count") if x in dc), None)
                empid_col = next((x for x in ("employee_id", "emp_id") if x in dc), None)
                if date_col and labels_col:
                    # Support both ISO dates (YYYY-MM-DD) and older DD-MM-YYYY records.
                    month_filter = f"(substr({date_col},1,7)=? OR (substr({date_col},7,4)||'-'||substr({date_col},4,2))=?)"
                    scans = c.execute(f"SELECT COALESCE(SUM({labels_col}),0) FROM daily WHERE {month_filter}", (month_key, month_key)).fetchone()[0] or 0
                    if mistakes_col:
                        mistakes = c.execute(f"SELECT COALESCE(SUM({mistakes_col}),0) FROM daily WHERE {month_filter}", (month_key, month_key)).fetchone()[0] or 0
                    # Show how many employees were marked Absent for each date.
                    absent_conditions = []
                    if "shift" in dc:
                        absent_conditions.append("shift='Absent'")
                    if "status" in dc:
                        absent_conditions.append("status='Absent'")
                    absent_expr = "SUM(CASE WHEN " + " OR ".join(absent_conditions) + " THEN 1 ELSE 0 END)" if absent_conditions else "0"
                    mistakes_expr = f"SUM({mistakes_col})" if mistakes_col else "0"
                    query = f"SELECT {date_col} AS d, SUM({labels_col}) AS l, {mistakes_expr} AS m, {absent_expr} AS absent_count FROM daily WHERE {month_filter} GROUP BY {date_col} ORDER BY CASE WHEN substr({date_col},5,1)='-' THEN {date_col} ELSE substr({date_col},7,4)||'-'||substr({date_col},4,2)||'-'||substr({date_col},1,2) END DESC"
                    recent_rows = c.execute(query, (month_key, month_key)).fetchall()
                if "employees" in tables and labels_col and empid_col:
                    ec = {r["name"] for r in c.execute("PRAGMA table_info(employees)").fetchall()}
                    name_col = next((x for x in ("employee_name", "name") if x in ec), None)
                    emp_key = next((x for x in ("employee_id", "emp_id") if x in ec), None)
                    if name_col and emp_key:
                        active_filter = " WHERE e.status='Active'" if "status" in ec else ""
                        if date_col:
                            top_month_filter = f"(substr(d.{date_col},1,7)=? OR (substr(d.{date_col},7,4)||'-'||substr(d.{date_col},4,2))=?)"
                            mistakes_expr = f"COALESCE(SUM(d.{mistakes_col}),0)" if mistakes_col else "0"
                            top_query = f"SELECT e.{name_col} AS nm, COALESCE(SUM(d.{labels_col}),0) AS l, {mistakes_expr} AS m FROM employees e LEFT JOIN daily d ON e.{emp_key}=d.{empid_col} AND {top_month_filter} {active_filter} GROUP BY e.{emp_key}"
                            top_rows = c.execute(top_query, (month_key, month_key)).fetchall()
                        else:
                            top_rows = c.execute(f"SELECT e.{name_col} AS nm, 0 AS l, 0 AS m FROM employees e{active_filter}").fetchall()
                        # Balanced score: 70% relative label volume + 30% accuracy.
                        max_labels = max((int(r["l"] or 0) for r in top_rows), default=0)
                        scored_rows = []
                        for r in top_rows:
                            label_count = int(r["l"] or 0)
                            acc = accuracy(label_count, r["m"])
                            work_score = (label_count * 100 / max_labels) if max_labels else 0
                            final_score = work_score * 0.70 + acc * 0.30
                            scored_rows.append({"nm": r["nm"], "l": label_count, "m": int(r["m"] or 0),
                                                "acc": acc, "score": final_score})
                        top_rows = sorted(scored_rows, key=lambda r: (-r["score"], -r["l"], str(r["nm"] or "").casefold()))
        except Exception as exc:
            # Keep the dashboard usable and make database/query issues visible for troubleshooting.
            messagebox.showwarning("Dashboard Data", f"Dashboard data could not be loaded.\n\n{exc}", parent=self)
        finally:
            if c:
                c.close()

        body = tk.Frame(self.main, bg=BG)
        body.pack(fill="both", expand=True, padx=28, pady=(0,18))
        body.grid_columnconfigure(0, weight=2); body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(2, weight=1)
        month_bar = tk.Frame(body, bg="#E5F4E1", highlightbackground="#B9DDB5", highlightthickness=1)
        month_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0,10))
        tk.Label(month_bar, text=f"{selected_month.upper()} PRODUCTIVITY", bg="#E5F4E1", fg="#244B36", font=("Segoe UI",9,"bold")).pack(side="left", padx=16, pady=11)

        # New analytics chart row: placed ABOVE the existing Daily Activity and
        # Top Scan Employee sections. Uses Tk Canvas only (no extra package).
        charts = tk.Canvas(body, height=196, bg=BG, bd=0, highlightthickness=0)
        charts.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0,10))

        def draw_dashboard_charts(_event=None):
            charts.delete("all")
            width = max(charts.winfo_width(), 900)
            gap = 10
            card_w = (width - gap * 2) / 3
            card_h = 188
            dark = "#E5F4E1"
            muted = "#55745D"
            foreground = "#244B36"
            accent_colors = ["#4E9D65", "#6DAEDB", "#D88B56", "#8B79C9", "#D1B84B"]

            def card(index, title, subtitle=""):
                x0 = index * (card_w + gap)
                charts.create_rectangle(x0, 2, x0 + card_w, card_h, fill=dark, outline="#B9DDB5")
                charts.create_text(x0 + 14, 17, text=title, fill=foreground,
                                   anchor="w", font=("Segoe UI", 9, "bold"))
                if subtitle:
                    charts.create_text(x0 + 14, 33, text=subtitle, fill=muted,
                                       anchor="w", font=("Segoe UI", 7))
                return x0

            # Scan Quality: successful labels vs recorded mistakes.
            x0 = card(0, "Scan Quality", "Successful labels vs recorded mistakes")
            good = max(0, int(scans or 0) - int(mistakes or 0))
            bad = max(0, int(mistakes or 0))
            quality_total = good + bad
            cx, cy, radius = x0 + card_w * 0.36, 108, 53
            if quality_total:
                charts.create_arc(cx-radius, cy-radius, cx+radius, cy+radius,
                                  start=90, extent=-360*good/quality_total, style="pieslice",
                                  fill="#00D5C8", outline=dark, width=2)
                charts.create_arc(cx-radius, cy-radius, cx+radius, cy+radius,
                                  start=90-360*good/quality_total, extent=-360*bad/quality_total,
                                  style="pieslice", fill="#D82BEA", outline=dark, width=2)
                charts.create_oval(cx-29, cy-29, cx+29, cy+29, fill=dark, outline=dark)
                charts.create_text(cx, cy-3, text=f"{accuracy(scans, mistakes):.1f}%", fill=foreground,
                                   font=("Segoe UI", 10, "bold"))
                charts.create_text(cx, cy+12, text="accuracy", fill=muted, font=("Segoe UI", 7))
            else:
                charts.create_oval(cx-radius, cy-radius, cx+radius, cy+radius,
                                   outline="#B9DDB5", width=12)
                charts.create_text(cx, cy, text="No data", fill=muted, font=("Segoe UI", 8))
            lx = x0 + card_w * 0.65
            for yy, color, label, value in [(82, "#00D5C8", "Scan Labels", good),
                                            (112, "#D82BEA", "Mistakes", bad)]:
                charts.create_rectangle(lx, yy, lx+9, yy+9, fill=color, outline="")
                charts.create_text(lx+14, yy+4, text=label, fill=foreground, anchor="w",
                                   font=("Segoe UI", 8))
                charts.create_text(x0+card_w-12, yy+4, text=f"{value:,}", fill=muted,
                                   anchor="e", font=("Segoe UI", 8))

            # Daily Labels Trend.
            x1 = card(1, "Daily Labels Trend", f"Daily totals • {selected_month}")
            daily = [(str(r["d"]), max(0, int(r["l"] or 0))) for r in reversed(recent_rows)]
            daily = daily[-10:]
            plot_left, plot_right = x1 + 22, x1 + card_w - 14
            plot_top, plot_bottom = 55, 153
            charts.create_line(plot_left, plot_bottom, plot_right, plot_bottom, fill="#46516D", width=1)
            max_daily = max((v for _, v in daily), default=0)
            if daily and max_daily:
                usable_w = plot_right - plot_left
                slot = usable_w / len(daily)
                bar_w = max(5, min(20, slot * 0.58))
                for i, (day, value) in enumerate(daily):
                    bx = plot_left + i*slot + (slot-bar_w)/2
                    bh = (plot_bottom-plot_top) * value / max_daily
                    charts.create_rectangle(bx, plot_bottom-bh, bx+bar_w, plot_bottom,
                                            fill=accent_colors[i % len(accent_colors)], outline="")
                    charts.create_text(bx+bar_w/2, plot_bottom+12, text=day[-2:], fill=muted,
                                       font=("Segoe UI", 7))
                charts.create_text(plot_left, plot_top-3, text=f"Peak: {max_daily:,}",
                                   fill=muted, anchor="w", font=("Segoe UI", 7))
            else:
                charts.create_text((plot_left+plot_right)/2, 102, text="No daily label data",
                                   fill=muted, font=("Segoe UI", 8))

            # Live Employees: current count of employees whose status is Active.
            x2 = card(2, "Live Employees", "Currently active employees")
            charts.create_text(x2 + card_w/2, 98, text=f"{int(active or 0):,}",
                               fill="#4E9D65", font=("Segoe UI", 34, "bold"))
            charts.create_text(x2 + card_w/2, 130, text="Active Employees", fill=foreground,
                               font=("Segoe UI", 9, "bold"))

        charts.bind("<Configure>", draw_dashboard_charts)

        recent = tk.Frame(body, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        recent.grid(row=2, column=0, sticky="nsew", padx=(0,8))
        top = tk.Frame(recent, bg=WHITE); top.pack(fill="x", padx=15, pady=13)
        tk.Label(top, text="Daily Activity", bg=WHITE, fg=TEXT, font=("Segoe UI",11,"bold")).pack(side="left")
        tk.Label(top, text=f"Latest dates in {selected_month}", bg=WHITE, fg=MUTED, font=("Segoe UI",8)).pack(side="right")
        table_frame = tk.Frame(recent, bg=WHITE)
        table_frame.pack(fill="both", expand=True, padx=12, pady=(0,12))
        tv = ttk.Treeview(table_frame, columns=("date","labels","mistakes","accuracy","absent"), show="headings", height=10)
        for col,txt,w in [("date","Date",105),("labels","Labels",85),("mistakes","Mistakes",85),("accuracy","Accuracy",90),("absent","Absent",75)]:
            tv.heading(col,text=txt); tv.column(col,width=w,anchor="center",stretch=True)
        daily_vscroll = ttk.Scrollbar(table_frame, orient="vertical", command=tv.yview)
        daily_hscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=daily_vscroll.set, xscrollcommand=daily_hscroll.set)
        tv.grid(row=0, column=0, sticky="nsew")
        daily_vscroll.grid(row=0, column=1, sticky="ns")
        daily_hscroll.grid(row=1, column=0, sticky="ew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        # Keep every row's normal alternating background. Treeview tags apply to
        # the whole row, so do not give absent rows a special background.
        # Absent counts remain clickable through the column-specific click handler below.
        tv.tag_configure("absent_clickable", foreground="#075DBA", background=WHITE, font=("Segoe UI", 9, "bold"))
        tv.tag_configure("normal_row", foreground=TEXT, background=WHITE)
        for r in recent_rows:
            absent_count = int(r["absent_count"] or 0)
            row_tag = "absent_clickable" if absent_count > 0 else "normal_row"
            tv.insert("", "end", values=(r["d"], r["l"] or 0, r["m"] or 0, f"{accuracy(r['l'],r['m']):.2f}%", absent_count), tags=(row_tag,))
        if not recent_rows: tv.insert("", "end", values=("No data for this month", "0", "0", "0.00%", "0"))

        # Clicking Absent opens a dedicated, styled window instead of a plain message box.
        def show_absent_names(event):
            if tv.identify_region(event.x, event.y) != "cell" or tv.identify_column(event.x) != "#5":
                return
            item = tv.identify_row(event.y)
            if not item:
                return
            values = tv.item(item, "values")
            if not values or not str(values[0]).startswith("20"):
                return
            work_date = str(values[0]).strip()
            conn = None
            try:
                conn = db()
                dcols = {x["name"] for x in conn.execute("PRAGMA table_info(daily)").fetchall()}
                ecols = {x["name"] for x in conn.execute("PRAGMA table_info(employees)").fetchall()}
                date_col = next((x for x in ("work_date", "date", "entry_date") if x in dcols), None)
                conditions = []
                if "shift" in dcols:
                    conditions.append("d.shift='Absent'")
                if "status" in dcols:
                    conditions.append("d.status='Absent'")
                if not date_col or not conditions:
                    names = []
                else:
                    if "employee_name" in dcols and "employee_name" in ecols:
                        name_expr = "COALESCE(NULLIF(d.employee_name,''), e.employee_name)"
                    elif "employee_name" in dcols:
                        name_expr = "d.employee_name"
                    elif "employee_name" in ecols:
                        name_expr = "e.employee_name"
                    else:
                        name_expr = "'Unknown employee'"
                    join = " LEFT JOIN employees e ON e.employee_id=d.employee_id" if "employee_id" in dcols and "employee_id" in ecols else ""
                    sql = f"SELECT {name_expr} AS employee_name FROM daily d{join} WHERE d.{date_col}=? AND (" + " OR ".join(conditions) + ") ORDER BY employee_name"
                    names = [str(x["employee_name"] or "Unknown employee") for x in conn.execute(sql, (work_date,)).fetchall()]
            except Exception as exc:
                messagebox.showerror("Absent Employees", f"Could not load absent employee names.\\n\\n{exc}", parent=self)
                return
            finally:
                if conn:
                    conn.close()

            win = tk.Toplevel(self)
            win.title("Absent Employees")
            win.configure(bg=BG)
            win.resizable(False, False)
            win.transient(self)
            width, height = 520, 440
            x = self.winfo_rootx() + max(20, (self.winfo_width() - width) // 2)
            y = self.winfo_rooty() + max(20, (self.winfo_height() - height) // 2)
            win.geometry(f"{width}x{height}+{x}+{y}")

            header_frame = tk.Frame(win, bg=SIDEBAR, height=92)
            header_frame.pack(fill="x")
            header_frame.pack_propagate(False)
            tk.Label(header_frame, text="ABSENT EMPLOYEES", bg=SIDEBAR, fg=WHITE,
                     font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=22, pady=(15, 2))
            tk.Label(header_frame, text=f"Attendance details  •  {work_date}", bg=SIDEBAR,
                     fg="#B9D8F2", font=("Segoe UI", 9)).pack(anchor="w", padx=23)

            # Keep the dialog clean: summary card removed as requested.
            list_frame = tk.Frame(win, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
            list_frame.pack(fill="both", expand=True, padx=18, pady=16)
            tk.Label(list_frame, text="EMPLOYEE LIST", bg=WHITE, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(10, 6))
            absent_tv = ttk.Treeview(list_frame, columns=("sr", "name", "attendance"),
                                     show="headings", height=8)
            absent_tv.heading("sr", text="Sr. No.")
            absent_tv.heading("name", text="Employee Name")
            absent_tv.heading("attendance", text="Attendance")
            absent_tv.column("sr", width=65, anchor="center")
            absent_tv.column("name", width=270, anchor="w")
            absent_tv.column("attendance", width=125, anchor="center")
            absent_tv.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            absent_tv.tag_configure("odd", background="#FFFFFF")
            absent_tv.tag_configure("even", background="#F1F6FC")
            for i, name in enumerate(names, 1):
                absent_tv.insert("", "end", values=(i, name, "ABSENT"),
                                 tags=("odd" if i % 2 else "even",))

            footer = tk.Frame(win, bg=BG)
            footer.pack(fill="x", padx=18, pady=(0, 14))
            tk.Button(footer, text="Close", command=win.destroy, bg=ACCENT, fg=WHITE,
                      activebackground="#075DBA", activeforeground=WHITE,
                      relief="flat", bd=0, padx=24, pady=8,
                      font=("Segoe UI", 9, "bold"), cursor="hand2").pack(side="right")
            win.grab_set()
            win.focus_set()
        tv.bind("<ButtonRelease-1>", show_absent_names)
        tv.bind("<Motion>", lambda e: tv.configure(cursor="hand2" if tv.identify_region(e.x,e.y)=="cell" and tv.identify_column(e.x)=="#5" else ""))

        side = tk.Frame(body, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        side.grid(row=2, column=1, sticky="nsew")
        tk.Label(side, text="Top Scan Employee Name", bg=WHITE, fg=TEXT, font=("Segoe UI",11,"bold")).pack(anchor="w", padx=15, pady=(13,3))
        tk.Label(side, text=f"Balanced ranking: 70% Labels + 30% Accuracy • {selected_month}", bg=WHITE, fg=MUTED, font=("Segoe UI",8)).pack(anchor="w", padx=15, pady=(0,8))
        list_wrap = tk.Frame(side, bg=WHITE)
        list_wrap.pack(fill="both", expand=True, padx=8, pady=(0,8))
        list_canvas = tk.Canvas(list_wrap, bg=WHITE, highlightthickness=0, bd=0)
        list_scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=list_canvas.yview)
        list_canvas.configure(yscrollcommand=list_scroll.set)
        list_scroll.pack(side="right", fill="y")
        list_canvas.pack(side="left", fill="both", expand=True)
        list_inner = tk.Frame(list_canvas, bg=WHITE)
        list_window = list_canvas.create_window((0,0), window=list_inner, anchor="nw")
        list_inner.bind("<Configure>", lambda _e: list_canvas.configure(scrollregion=list_canvas.bbox("all")))
        list_canvas.bind("<Configure>", lambda e: list_canvas.itemconfigure(list_window, width=e.width))
        # Fixed column headings appear once; each employee stays on one compact row.
        heading = tk.Frame(list_inner, bg="#E5F4E1")
        heading.pack(fill="x", padx=4, pady=(0,3))
        for col, label, width, anchor in [
            (0, "Top Scan Employee Name", 0, "w"),
            (1, "Labels Scan", 78, "center"),
            (2, "Mistakes", 68, "center"),
            (3, "Accuracy", 68, "center"),
            (4, "Score", 54, "center")]:
            tk.Label(heading, text=label, bg="#E5F4E1", fg="#244B36",
                     font=("Segoe UI",7,"bold"), anchor=anchor,
                     width=(width // 8 if width else 1)).grid(row=0,column=col,sticky="ew",padx=4,pady=7)
        heading.grid_columnconfigure(0, weight=1)
        for i,r in enumerate(top_rows,1):
            row_bg = "#F7FAFD" if i % 2 else "#FFFFFF"
            f = tk.Frame(list_inner, bg=row_bg)
            f.pack(fill="x", padx=4, pady=1)
            labels_value = int(r["l"] or 0)
            mistakes_value = int(r["m"] or 0)
            tk.Label(f, text=f"{i}. {r['nm']}", bg=row_bg, fg=TEXT,
                     font=("Segoe UI",8,"bold"), anchor="w").grid(row=0,column=0,sticky="ew",padx=6,pady=7)
            tk.Label(f, text=f"{labels_value:,}", bg=row_bg, fg=ACCENT,
                     font=("Segoe UI",8,"bold"), width=9, anchor="center").grid(row=0,column=1,padx=2)
            tk.Label(f, text=f"{mistakes_value:,}", bg=row_bg, fg=RED,
                     font=("Segoe UI",8), width=7, anchor="center").grid(row=0,column=2,padx=2)
            acc_value = float(r.get("acc", accuracy(labels_value, mistakes_value)))
            tk.Label(f, text=f"{acc_value:.1f}%", bg=row_bg,
                     fg=GREEN if acc_value >= 98 else TEXT,
                     font=("Segoe UI",8,"bold"), width=7, anchor="center").grid(row=0,column=3,padx=2)
            tk.Label(f, text=f"{float(r.get('score', 0)):.1f}", bg=row_bg, fg="#1769A0",
                     font=("Segoe UI",8,"bold"), width=5, anchor="center").grid(row=0,column=4,padx=2)
            f.grid_columnconfigure(0,weight=1)
        if not top_rows: tk.Label(list_inner, text="No active employees available.", bg=WHITE, fg=MUTED, font=("Segoe UI",9)).pack(pady=30)

    def get_supervisor_names(self):
        c=db(); rows=c.execute("SELECT name FROM supervisors WHERE active=1 ORDER BY name").fetchall(); c.close()
        return [r["name"] for r in rows]

    def show_daily(self):
        self.clear(); self.header("Daily Productivity","Select a shift for present employees, or choose Absent / Weekly Off / Holiday.")
        top=tk.Frame(self.main,bg=BG); top.pack(fill="x",padx=28,pady=(0,4))
        self.daily_date=tk.StringVar(value=date.today().isoformat())
        date_card=tk.Frame(top,bg=WHITE,highlightbackground=BORDER,highlightthickness=1)
        date_card.pack(side="left")
        tk.Label(date_card,text="Selected Date",bg=WHITE,fg=MUTED,font=("Segoe UI",8,"bold")).pack(side="left",padx=(12,5),pady=9)
        tk.Label(date_card,textvariable=self.daily_date,bg=WHITE,fg=TEXT,font=("Segoe UI",10,"bold"),width=12,anchor="center").pack(side="left",padx=(0,10),pady=8)
        def choose_daily_date():
            self._close_daily_editor(commit=True)
            self._cache_daily_rows()
            CalendarPopup(self,self.daily_date,on_select=self._daily_date_selected)
        tk.Button(top,text="Select Date",command=choose_daily_date,bg=ACCENT,fg=WHITE,activebackground=ACCENT,activeforeground=WHITE,bd=0,padx=16,pady=7,font=("Segoe UI",9,"bold")).pack(side="left",padx=10)
        tk.Button(top,text="Save",command=self.save_daily,bg=GREEN,fg=WHITE,activebackground=GREEN,activeforeground=WHITE,bd=0,padx=16,pady=7,font=("Segoe UI",9,"bold")).pack(side="left")

        box=tk.Frame(self.main,bg=WHITE,highlightbackground=BORDER,highlightthickness=1); box.pack(fill="both",expand=True,padx=28,pady=16)
        cols=("sr","name","shift","labels","mistakes","accuracy","supervisor","user_id","user_name")
        self.daily_tv=ttk.Treeview(box,columns=cols,show="headings",selectmode="browse")
        heads={"sr":"Sr No","name":"Employee Name","shift":"Shift / Attendance","labels":"Labels","mistakes":"Mistakes","accuracy":"Accuracy %","supervisor":"Supervisor","user_id":"User ID","user_name":""}
        widths={"sr":65,"name":220,"shift":155,"labels":100,"mistakes":100,"accuracy":115,"supervisor":180,"user_id":180,"user_name":0}
        for col in cols:
            self.daily_tv.heading(col,text=heads[col])
            self.daily_tv.column(col,width=widths[col],minwidth=0 if col == "user_name" else 20,stretch=False if col == "user_name" else True,anchor="center")
        self.daily_tv.pack(fill="both",expand=True,padx=10,pady=10)
        self.daily_tv.bind("<KeyPress>", self._daily_key_hint)
        self.daily_tv.bind("<Button-1>",self.edit_daily_click)
        self._daily_editor = None
        self._daily_editor_commit = None
        if not hasattr(self, "daily_drafts"):
            self.daily_drafts = {}
        if not hasattr(self, "daily_selected_date"):
            self.daily_selected_date = date.today().isoformat()
        self.daily_date.set(self.daily_selected_date)
        self.daily_data={}
        self.populate_daily()

    def set_all_daily_status(self,status):
        return

    def populate_daily(self):
        for i in self.daily_tv.get_children(): self.daily_tv.delete(i)
        c=db(); emps=c.execute("SELECT * FROM employees WHERE status='Active' ORDER BY CAST(employee_id AS INTEGER),employee_name").fetchall()
        rows=c.execute("SELECT * FROM daily WHERE work_date=?",(self.daily_date.get(),)).fetchall(); c.close()
        saved={str(r["employee_id"]):r for r in rows}; self.daily_data={}
        selected_date = self.daily_date.get()
        self.daily_selected_date = selected_date
        for sr,e in enumerate(emps,1):
            eid=str(e["employee_id"])
            r=saved.get(eid)
            draft=self.daily_drafts.get((selected_date,eid))
            if draft is not None:
                vals=list(draft)
                while len(vals) < 9: vals.append(self.display_name if len(vals)==8 else (self.login_id if len(vals)==7 else ""))
                vals[0]=sr; vals[1]=e["employee_name"]
            else:
                shift=(r["shift"] if r else "")
                # Older saved records: map attendance status into the single Shift / Attendance column.
                if r and r["status"] in ("Absent", "Weekly Off", "Holiday"):
                    shift=r["status"]
                labels=(str(r["labels"]) if r and int(r["labels"] or 0) != 0 else "")
                mistakes=(str(r["mistakes"]) if r and int(r["mistakes"] or 0) != 0 else "")
                vals=(sr,e["employee_name"],shift,labels,mistakes,
                      f"{accuracy(int(labels or 0),int(mistakes or 0)):.2f}%",r["supervisor"] if r else "", (r["updated_by_id"] if r and str(r["updated_by_id"] or "").strip() else ""), "")
            iid=self.daily_tv.insert("", "end", iid=eid, values=vals)
            self.daily_data[iid]=list(vals)
            tags=["row_even" if sr % 2 == 0 else "row_odd"]
            if vals[2] == "Absent": tags.append("absent")
            elif vals[2] == "Holiday": tags.append("holiday")
            elif vals[2] == "Weekly Off": tags.append("off")
            self.daily_tv.item(iid,tags=tuple(tags))
        self.daily_tv.tag_configure("row_odd",background="#FFFFFF")
        self.daily_tv.tag_configure("row_even",background="#F7FAFD")
        self.daily_tv.tag_configure("absent",background="#FFF1F1")
        self.daily_tv.tag_configure("holiday",background="#FFF7E6")
        self.daily_tv.tag_configure("off",background="#EEF3F7")

    def _daily_row_edit_allowed(self, iid):
        # Admin can edit saved records. A normal user may edit only until Save;
        # after a record exists in SQLite it is locked for non-admin users.
        if self.is_admin():
            return True
        c = db()
        try:
            exists = c.execute(
                "SELECT 1 FROM daily WHERE work_date=? AND employee_id=?",
                (self.daily_date.get(), str(iid))
            ).fetchone()
        finally:
            c.close()
        return not bool(exists)

    def _close_daily_editor(self, commit=True):
        ed = getattr(self, "_daily_editor", None)
        callback = getattr(self, "_daily_editor_commit", None)
        if commit and ed is not None and callback is not None:
            try:
                callback()
            except Exception:
                pass
        ed = getattr(self, "_daily_editor", None)
        try:
            if ed is not None and ed.winfo_exists():
                ed.destroy()
        except Exception:
            pass
        self._daily_editor = None
        self._daily_editor_commit = None

    def _cache_daily_rows(self):
        tv = getattr(self, "daily_tv", None)
        if tv is None or not tv.winfo_exists():
            return
        d = self.daily_date.get()
        for iid in tv.get_children():
            self.daily_drafts[(d, str(iid))] = list(tv.item(iid, "values"))

    def _daily_date_selected(self):
        self.daily_selected_date = self.daily_date.get()
        self.populate_daily()

    def edit_daily_click(self,event):
        self._close_daily_editor()
        iid=self.daily_tv.identify_row(event.y); col=self.daily_tv.identify_column(event.x)
        if not iid or col == "#1":
            return
        if not self._daily_row_edit_allowed(iid):
            messagebox.showinfo(
                "Entry Locked",
                "This employee's entry has already been saved. Only Admin can edit saved productivity data."
            )
            return
        idx=int(col[1:])-1
        if idx == 1 or idx == 5:
            return
        x,y,w,h=self.daily_tv.bbox(iid,col)
        if not h:
            return
        vals=list(self.daily_tv.item(iid,"values"))
        old=str(vals[idx])

        # Excel-like inline dropdowns
        if idx == 2:
            cb=ttk.Combobox(self.daily_tv, values=("", "First", "Second", "Night", "Absent", "Weekly Off", "Holiday"), state="readonly", font=("Segoe UI",9))
            cb.place(in_=self.daily_tv, x=x,y=y,width=w,height=h)
            self._daily_editor = cb
            cb.set(old)
            cb.focus_set()
            def finish_attendance(event=None):
                if not cb.winfo_exists(): return
                selected=cb.get()
                vals=list(self.daily_tv.item(iid,"values")); vals[2]=selected
                if selected in ("Absent", "Weekly Off", "Holiday"):
                    vals[3]=""; vals[4]=""; vals[5]="0.00%"
                self.daily_tv.item(iid,values=vals)
                cb.destroy()
                self._daily_editor = None
                self._daily_editor_commit = None
                self.daily_drafts[(self.daily_date.get(), str(iid))] = list(vals)
            self._daily_editor_commit = finish_attendance
            cb.bind("<<ComboboxSelected>>",finish_attendance)
            return "break"

        if idx in (3,4):
            ent=tk.Entry(self.daily_tv, font=("Segoe UI",9), relief="flat", bd=1, highlightthickness=1, highlightbackground=ACCENT)
            ent.place(in_=self.daily_tv, x=x,y=y,width=w,height=h)
            self._daily_editor = ent
            ent.insert(0, old)
            ent.select_range(0,"end")
            ent.focus_set()
            # Keep keyboard focus on the inline editor; Treeview can otherwise reclaim focus.
            self.after(50, lambda: ent.focus_force() if ent.winfo_exists() else None)
            def finish_num(event=None):
                if not ent.winfo_exists(): return
                nv=ent.get().strip()
                vals=list(self.daily_tv.item(iid,"values"))
                if vals[2] in ("Absent", "Weekly Off", "Holiday"):
                    nv=""
                try:
                    if nv == "":
                        num = 0
                    elif nv.isdigit():
                        num = max(0, int(nv))
                    else:
                        raise ValueError
                except Exception:
                    messagebox.showwarning("Invalid Value", "Please enter numbers only.")
                    ent.focus_force()
                    return
                vals[idx]=str(num)
                labels=int(vals[3] or 0)
                mistakes=int(vals[4] or 0)
                if mistakes > labels:
                    messagebox.showwarning("Invalid Value", "Mistakes cannot be greater than Labels.")
                    ent.focus_force()
                    return
                vals[5]=f"{accuracy(labels,mistakes):.2f}%"
                self.daily_tv.item(iid,values=vals)
                ent.destroy()
                self._daily_editor = None
                self._daily_editor_commit = None
                self.daily_drafts[(self.daily_date.get(), str(iid))] = list(vals)
            self._daily_editor_commit = finish_num
            ent.bind("<Return>",finish_num)
            ent.bind("<FocusOut>",finish_num)

            # Spreadsheet-like arrow navigation: save the current value first,
            # then move to the adjacent editable cell/row without losing input.
            def move_after_save(direction):
                try:
                    current_rows=list(self.daily_tv.get_children())
                    row_index=current_rows.index(str(iid))
                    target_col=idx
                    target_row=row_index
                    if direction == "Up": target_row=max(0,row_index-1)
                    elif direction == "Down": target_row=min(len(current_rows)-1,row_index+1)
                    elif direction == "Left": target_col=max(3,idx-1)
                    elif direction == "Right": target_col=min(4,idx+1)
                    target_iid=current_rows[target_row]
                    self.daily_tv.selection_set(target_iid)
                    self.daily_tv.focus(target_iid)
                    self.daily_tv.see(target_iid)
                    self.after(10, lambda: self._start_daily_numeric_editor(target_iid,target_col) if target_col in (3,4) else None)
                except Exception:
                    pass

            def arrow_move(event, direction):
                # Commit the active number, then open the adjacent numeric cell.
                current_rows = list(self.daily_tv.get_children())
                try:
                    row_index = current_rows.index(str(iid))
                except ValueError:
                    return "break"
                target_col = idx
                target_row = row_index
                if direction == "Up": target_row = max(0, row_index - 1)
                elif direction == "Down": target_row = min(len(current_rows) - 1, row_index + 1)
                elif direction == "Left": target_col = max(3, idx - 1)
                elif direction == "Right": target_col = min(4, idx + 1)
                # Save while the editor still exists; after it closes, move focus.
                finish_num()
                target_iid = current_rows[target_row]
                self.after_idle(lambda iid2=target_iid, col2=target_col: self._start_daily_numeric_editor(iid2, col2))
                return "break"

            for key in ("Up", "Down", "Left", "Right"):
                ent.bind(f"<KeyPress-{key}>", lambda ev, k=key: arrow_move(ev, k))
            return "break"

        if idx == 6:
            names=[""]+self.get_supervisor_names()
            cb=ttk.Combobox(self.daily_tv, values=names, state="readonly", font=("Segoe UI",9))
            cb.place(in_=self.daily_tv, x=x,y=y,width=w,height=h)
            self._daily_editor = cb
            cb.set(old if old in names else "")
            cb.focus_set()
            def finish_sup(event=None):
                if not cb.winfo_exists(): return
                vals=list(self.daily_tv.item(iid,"values")); vals[6]=cb.get().strip()
                self.daily_tv.item(iid,values=vals)
                cb.destroy()
                self._daily_editor = None
                self._daily_editor_commit = None
                self.daily_drafts[(self.daily_date.get(), str(iid))] = list(vals)
            self._daily_editor_commit = finish_sup
            cb.bind("<<ComboboxSelected>>",finish_sup)
            return "break"

    def _start_daily_numeric_editor(self, iid, idx):
        """Open a numeric inline editor for Labels/Mistakes using the latest row values."""
        if not self.daily_tv.exists(iid) or not self._daily_row_edit_allowed(iid):
            return
        col=f"#{idx+1}"
        bbox=self.daily_tv.bbox(iid,col)
        if not bbox:
            return
        x,y,w,h=bbox
        vals=list(self.daily_tv.item(iid,"values"))
        ent=tk.Entry(self.daily_tv, font=("Segoe UI",9), relief="flat", bd=1,
                     highlightthickness=1, highlightbackground=ACCENT)
        ent.place(in_=self.daily_tv,x=x,y=y,width=w,height=h)
        self._daily_editor=ent
        ent.insert(0,str(vals[idx] or ""))
        ent.select_range(0,"end")
        ent.focus_force()
        def finish(event=None):
            if not ent.winfo_exists(): return
            nv=ent.get().strip()
            row=list(self.daily_tv.item(iid,"values"))
            try:
                num=0 if nv=="" else int(nv)
                if num < 0: raise ValueError
            except Exception:
                messagebox.showwarning("Invalid Value","Please enter a whole number (0 or greater).")
                ent.focus_force(); return
            row[idx]=str(num)
            labels=int(row[3] or 0); mistakes=int(row[4] or 0)
            if mistakes>labels:
                messagebox.showwarning("Invalid Value","Mistakes cannot be greater than Labels.")
                ent.focus_force(); return
            row[5]=f"{accuracy(labels,mistakes):.2f}%"
            self.daily_tv.item(iid,values=row)
            self.daily_drafts[(self.daily_date.get(),str(iid))]=list(row)
            ent.destroy(); self._daily_editor=None; self._daily_editor_commit=None
        self._daily_editor_commit=finish
        ent.bind("<Return>",finish)
        ent.bind("<FocusOut>",finish)

        def arrow_move(event, direction):
            rows = list(self.daily_tv.get_children())
            try:
                row_index = rows.index(str(iid))
            except ValueError:
                return "break"
            target_col = idx
            target_row = row_index
            if direction == "Up": target_row = max(0, row_index - 1)
            elif direction == "Down": target_row = min(len(rows) - 1, row_index + 1)
            elif direction == "Left": target_col = max(3, idx - 1)
            elif direction == "Right": target_col = min(4, idx + 1)
            finish()
            target_iid = rows[target_row]
            self.after_idle(lambda iid2=target_iid, col2=target_col: self._start_daily_numeric_editor(iid2, col2))
            return "break"

        for key in ("Up", "Down", "Left", "Right"):
            ent.bind(f"<KeyPress-{key}>", lambda ev, k=key: arrow_move(ev, k))

    # Kept for backward compatibility with older saved layouts.
    def edit_daily_cell(self,event):
        return self.edit_daily_click(event)

    def _daily_key_hint(self,event):
        # Keep normal Treeview navigation; cell editing is intentionally click-to-edit like a spreadsheet.
        return

    def save_daily(self):
        self._close_daily_editor(commit=True)
        self._cache_daily_rows()
        c=db()
        try:
            existing={str(r["employee_id"]) for r in c.execute("SELECT employee_id FROM daily WHERE work_date=?",(self.daily_date.get(),)).fetchall()}
            is_admin = self.is_admin()
            skipped=0
            saved_count=0
            updated_count=0
            for iid in self.daily_tv.get_children():
                v=self.daily_tv.item(iid,"values"); eid=str(iid)
                attendance=str(v[2] or "").strip()
                labels_text=str(v[3] or "").strip()
                mistakes_text=str(v[4] or "").strip()
                supervisor_text=str(v[6] or "").strip()

                # Do not create database records for untouched employee rows.
                # Previously, Save inserted a default zero/Present row for every
                # employee, which made all of them appear locked to non-admins.
                if not attendance and not labels_text and not mistakes_text and not supervisor_text:
                    continue

                if not is_admin and eid in existing:
                    skipped += 1
                    continue

                # Shift / Attendance is optional. Blank attendance is treated as Present
                # for rows where labels/mistakes/supervisor were actually entered.
                if attendance in ("Absent", "Weekly Off", "Holiday"):
                    status=attendance; shift=""; labels=0; mistakes=0
                else:
                    status="Present"; shift=attendance or ""
                    try:
                        labels=max(0,int(v[3] or 0)); mistakes=max(0,int(v[4] or 0))
                    except Exception:
                        messagebox.showerror("Invalid Data","Labels and Mistakes must be numbers."); c.close(); return
                    if mistakes > labels:
                        messagebox.showwarning("Invalid Data","Mistakes cannot be greater than Labels."); c.close(); return
                acc=accuracy(labels,mistakes)
                employee_name = str(v[1] or "").strip()
                if eid in existing:
                    updated_count += 1
                c.execute("""INSERT INTO daily(work_date,employee_id,employee_name,labels,mistakes,supervisor,remark,accuracy,status,shift,updated_by_id,updated_by_name)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                             ON CONFLICT(work_date,employee_id) DO UPDATE SET employee_name=excluded.employee_name,
                             labels=excluded.labels,mistakes=excluded.mistakes,supervisor=excluded.supervisor,remark=excluded.remark,
                             accuracy=excluded.accuracy,status=excluded.status,shift=excluded.shift,updated_by_id=excluded.updated_by_id,updated_by_name=excluded.updated_by_name""",
                          (self.daily_date.get(),eid,employee_name,labels,mistakes,v[6].strip(),"",acc,status,shift,self.login_id,self.display_name))
                saved_count += 1
            c.commit()
        except sqlite3.OperationalError as exc:
            try:
                c.rollback()
            except Exception:
                pass
            try:
                c.close()
            except Exception:
                pass
            messagebox.showerror(
                "Database Busy",
                "The database is currently being used by another software window.\n\n"
                "Please close any other Stocking Productivity window and click Save again.\n\n"
                f"Details: {exc}", parent=self)
            return
        finally:
            try:
                c.close()
            except Exception:
                pass
        for key in list(self.daily_drafts):
            if key[0] == self.daily_date.get():
                self.daily_drafts.pop(key, None)
        new_count = max(0, saved_count - updated_count)
        messagebox.showinfo(
            "Save Result",
            f"Daily Productivity Save Result\n\nNew Entries Saved: {new_count}\nExisting Entries Updated: {updated_count}\nExisting Entries Skipped: {skipped}\n\nDate: {self.daily_date.get()}\nUpdated By: {self.display_name} ({self.login_id})",
            parent=self
        )
        self.populate_daily()

    def show_monthly(self):
        self.clear(); self.header("Monthly Summary", "Employee-wise totals from the productivity database.")
        top=tk.Frame(self.main,bg=BG); top.pack(fill="x",padx=28)
        self.month_var=tk.StringVar(value=date.today().strftime("%Y-%m"))
        self.month_search_var=tk.StringVar(value="")
        self.month_status_var=tk.StringVar(value="All")
        tk.Label(top,text="Month",bg=BG,fg=TEXT,font=("Segoe UI",9,"bold")).pack(side="left")
        month_display=tk.Entry(top,textvariable=self.month_var,width=10,font=("Segoe UI",9),state="readonly",readonlybackground=WHITE)
        month_display.pack(side="left",padx=(8,4))
        tk.Button(top,text="▦ Choose Month",command=self.open_month_picker,bg="#DDF2D8",fg=TEXT,bd=0,padx=10,pady=5).pack(side="left",padx=(0,6))
        tk.Button(top,text="Refresh",command=self.populate_monthly,bg=ACCENT,fg=WHITE,bd=0,padx=12,pady=5).pack(side="left",padx=(0,12))
        tk.Label(top,text="Search",bg=BG,fg=TEXT,font=("Segoe UI",9,"bold")).pack(side="left")
        search_entry=tk.Entry(top,textvariable=self.month_search_var,width=20,font=("Segoe UI",9))
        search_entry.pack(side="left",padx=7)
        tk.Label(top,text="Attendance",bg=BG,fg=TEXT,font=("Segoe UI",9,"bold")).pack(side="left",padx=(8,4))
        status_box=ttk.Combobox(top,textvariable=self.month_status_var,values=("All","Present","Absent"),state="readonly",width=10)
        status_box.pack(side="left",padx=(0,10))
        tk.Button(top,text="Export Excel",command=self.export_monthly_excel,bg="#16834A",fg=WHITE,bd=0,padx=12,pady=5).pack(side="left",padx=(0,6))
        tk.Button(top,text="Export PDF",command=self.export_monthly_pdf,bg="#B34838",fg=WHITE,bd=0,padx=12,pady=5).pack(side="left")
        box=tk.Frame(self.main,bg=WHITE,highlightbackground=BORDER,highlightthickness=1); box.pack(fill="both",expand=True,padx=28,pady=16)
        cols=("id","name","labels","mistakes","accuracy","present","absent")
        self.month_tv=ttk.Treeview(box,columns=cols,show="headings")
        headers=[("id","Employee ID",90),("name","Employee Name",220),("labels","Total Labels",115),("mistakes","Total Mistakes",115),("accuracy","Overall Accuracy %",140),("present","Total Present Days",125),("absent","Total Absent Days",125)]
        for col,title,width in headers:
            self.month_tv.heading(col,text=title)
            self.month_tv.column(col,width=width,anchor="center")
        self.month_tv.column("name",anchor="w")
        yscroll=ttk.Scrollbar(box,orient="vertical",command=self.month_tv.yview)
        xscroll=ttk.Scrollbar(box,orient="horizontal",command=self.month_tv.xview)
        self.month_tv.configure(yscrollcommand=yscroll.set,xscrollcommand=xscroll.set)
        self.month_tv.pack(side="top",fill="both",expand=True,padx=(10,0),pady=(10,0))
        yscroll.pack(side="right",fill="y",pady=(10,0))
        xscroll.pack(side="bottom",fill="x",padx=10,pady=(0,10))
        self.month_tv.bind("<ButtonRelease-1>",self.monthly_name_click)
        self.month_search_var.trace_add("write",lambda *_:self.populate_monthly())
        status_box.bind("<<ComboboxSelected>>",lambda *_:self.populate_monthly())
        self.populate_monthly()

    def open_month_picker(self):
        """Open a small month/year chooser; selection writes YYYY-MM to month_var."""
        current = self.month_var.get().strip()
        try:
            parsed = datetime.strptime(current, "%Y-%m")
            initial_year, initial_month = parsed.year, parsed.month
        except ValueError:
            today = date.today()
            initial_year, initial_month = today.year, today.month

        popup = tk.Toplevel(self)
        popup.title("Choose Month")
        popup.configure(bg=BG)
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()

        year_var = tk.StringVar(value=str(initial_year))
        month_names = list(calendar.month_name)[1:]
        selected_month = {"value": initial_month}

        header = tk.Frame(popup, bg=BG)
        header.pack(fill="x", padx=12, pady=(12, 8))
        tk.Button(header, text="◀", width=3, command=lambda: change_year(-1),
                  bg=WHITE, fg=TEXT, bd=1).pack(side="left")
        year_box = tk.Spinbox(header, from_=2000, to=2100, width=7, textvariable=year_var,
                              justify="center", font=("Segoe UI", 11, "bold"),
                              command=lambda: refresh_month_buttons())
        year_box.pack(side="left", padx=8)
        tk.Button(header, text="▶", width=3, command=lambda: change_year(1),
                  bg=WHITE, fg=TEXT, bd=1).pack(side="left")

        month_frame = tk.Frame(popup, bg=BG)
        month_frame.pack(padx=12, pady=(0, 12))
        month_buttons = []

        def choose_month(month_number):
            try:
                year = int(year_var.get())
                if not 2000 <= year <= 2100:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Invalid Year", "Please select a year from 2000 to 2100.", parent=popup)
                return
            self.month_var.set(f"{year:04d}-{month_number:02d}")
            popup.grab_release()
            popup.destroy()
            self.populate_monthly()

        def refresh_month_buttons():
            try:
                year = int(year_var.get())
            except ValueError:
                year = initial_year
            for month_number, button in enumerate(month_buttons, start=1):
                is_selected = (year == initial_year and month_number == initial_month)
                button.configure(bg=(ACCENT if is_selected else WHITE),
                                 fg=(WHITE if is_selected else TEXT))

        def change_year(delta):
            try:
                year = int(year_var.get()) + delta
            except ValueError:
                year = initial_year
            year_var.set(str(max(2000, min(2100, year))))
            refresh_month_buttons()

        for index, month_name in enumerate(month_names):
            button = tk.Button(month_frame, text=month_name[:3], width=9,
                               command=lambda month_number=index + 1: choose_month(month_number),
                               bg=WHITE, fg=TEXT, activebackground="#CDECC7", bd=1,
                               font=("Segoe UI", 9))
            button.grid(row=index // 4, column=index % 4, padx=3, pady=3, sticky="ew")
            month_buttons.append(button)

        year_var.trace_add("write", lambda *_: refresh_month_buttons())
        refresh_month_buttons()
        popup.bind("<Escape>", lambda _event: popup.destroy())
        popup.update_idletasks()
        x = self.winfo_rootx() + 230
        y = self.winfo_rooty() + 105
        popup.geometry(f"+{x}+{y}")

    def _monthly_rows(self, validate_month=True):
        m=self.month_var.get().strip()
        if validate_month and not is_iso_month(m):
            messagebox.showwarning("Invalid Month", "Please enter month in YYYY-MM format (for example, 2026-10).", parent=self)
            return []
        c=db()
        try:
            date_expr=normalized_date_sql("d.work_date")
            rows=c.execute(f"""SELECT e.employee_id,e.employee_name,
                         COALESCE(SUM(d.labels),0) labels,COALESCE(SUM(d.mistakes),0) mistakes,
                         SUM(CASE WHEN COALESCE(d.status,'Present')='Present' THEN 1 ELSE 0 END) present_days,
                         SUM(CASE WHEN COALESCE(d.status,'Present')='Absent' THEN 1 ELSE 0 END) absent_days,
                         COUNT(d.work_date) days
                         FROM employees e LEFT JOIN daily d ON d.employee_id=e.employee_id AND substr({date_expr},1,7)=?
                         GROUP BY e.employee_id,e.employee_name ORDER BY CAST(e.employee_id AS INTEGER), e.employee_name""",(m,)).fetchall()
        finally:
            c.close()
        q=self.month_search_var.get().strip().casefold() if hasattr(self,"month_search_var") else ""
        selected_status=self.month_status_var.get() if hasattr(self,"month_status_var") else "All"
        filtered=[]
        for r in rows:
            if q and q not in str(r["employee_name"]).casefold() and q not in str(r["employee_id"]).casefold():
                continue
            if selected_status=="Present" and int(r["present_days"] or 0)<=0:
                continue
            if selected_status=="Absent" and int(r["absent_days"] or 0)<=0:
                continue
            filtered.append(r)
        return filtered

    def populate_monthly(self):
        if not hasattr(self,"month_tv"):
            return
        for i in self.month_tv.get_children(): self.month_tv.delete(i)
        rows=self._monthly_rows()
        for r in rows:
            self.month_tv.insert("", "end", iid=str(r["employee_id"]), values=(
                r["employee_id"],r["employee_name"],r["labels"],r["mistakes"],
                f"{accuracy(r['labels'],r['mistakes']):.2f}%",r["present_days"] or 0,r["absent_days"] or 0))

    def monthly_name_click(self,event):
        if self.month_tv.identify_column(event.x)=="#2":
            iid=self.month_tv.identify_row(event.y)
            if iid:
                self.after(100,lambda eid=iid:self.show_monthly_employee_details(eid))

    def monthly_name_double_click(self,event):
        if self.month_tv.identify_column(event.x)=="#2":
            iid=self.month_tv.identify_row(event.y)
            if iid:
                self.show_monthly_employee_details(iid)

    def show_monthly_employee_details(self,employee_id):
        # Allow only one Monthly Summary Daily Details window at a time.
        # If one is already open, focus it and do not open another employee's window.
        existing=getattr(self,"_monthly_detail_window",None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    existing.focus_force()
                    return
            except tk.TclError:
                pass
            self._monthly_detail_window=None

        if not is_iso_month(self.month_var.get().strip()):
            messagebox.showwarning("Invalid Month", "Please enter month in YYYY-MM format.",parent=self); return
        selected=self.month_tv.item(employee_id,"values")
        employee_name=selected[1] if selected else str(employee_id)
        win=tk.Toplevel(self); self._monthly_detail_window=win
        win.title(f"Daily Details - {employee_name}"); win.geometry("900x520"); win.configure(bg=BG); win.transient(self)

        def close_monthly_details():
            try:
                win.grab_release()
            except tk.TclError:
                pass
            if getattr(self,"_monthly_detail_window",None) is win:
                self._monthly_detail_window=None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW",close_monthly_details)
        # Modal behavior prevents opening another detail window until this one closes.
        win.grab_set()
        win.focus_force()
        tk.Label(win,text=f"{employee_name}  |  {self.month_var.get().strip()}",bg=BG,fg=TEXT,font=("Segoe UI",13,"bold")).pack(anchor="w",padx=16,pady=12)
        frame=tk.Frame(win,bg=WHITE); frame.pack(fill="both",expand=True,padx=14,pady=(0,14))
        cols=("date","status","shift","labels","mistakes","accuracy","supervisor","updated_by")
        tv=ttk.Treeview(frame,columns=cols,show="headings")
        for col,title,width in [("date","Work Date",100),("status","Attendance",100),("shift","Shift",70),("labels","Labels",80),("mistakes","Mistakes",90),("accuracy","Accuracy %",100),("supervisor","Supervisor",130),("updated_by","Updated By",180)]:
            tv.heading(col,text=title); tv.column(col,width=width,anchor="center")
        scroll=ttk.Scrollbar(frame,orient="vertical",command=tv.yview); tv.configure(yscrollcommand=scroll.set)
        tv.pack(side="left",fill="both",expand=True); scroll.pack(side="right",fill="y")
        c=db()
        try:
            date_expr=normalized_date_sql("work_date")
            records=c.execute(f"""SELECT work_date,status,shift,labels,mistakes,accuracy,supervisor,updated_by_name,updated_by_id
                FROM daily WHERE employee_id=? AND substr({date_expr},1,7)=?
                ORDER BY {date_expr}""",(str(employee_id),self.month_var.get().strip())).fetchall()
        finally: c.close()
        for r in records:
            updated=(str(r["updated_by_name"] or "") + (f" ({r['updated_by_id']})" if r["updated_by_id"] else "")).strip()
            tv.insert("","end",values=(r["work_date"],r["status"],r["shift"],r["labels"],r["mistakes"],f"{float(r['accuracy'] or 0):.2f}%",r["supervisor"],updated))
        if not records:
            tk.Label(win,text="No daily entries found for this employee in the selected month.",bg=BG,fg=MUTED).pack(pady=(0,12))

    def export_monthly_excel(self):
        rows=self._monthly_rows()
        if not rows: return
        path=filedialog.asksaveasfilename(parent=self,title="Export Monthly Summary to Excel",defaultextension=".xlsx",filetypes=[("Excel Workbook","*.xlsx")],initialfile=f"Stocking_Monthly_Summary_{self.month_var.get().strip()}.xlsx")
        if not path: return
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment
            wb=Workbook(); ws=wb.active; ws.title="Monthly Summary"
            ws.append(["Month",self.month_var.get().strip()]); ws.append([])
            headers=["Employee ID","Employee Name","Total Labels","Total Mistakes","Overall Accuracy %","Total Present Days","Total Absent Days"]
            ws.append(headers)
            for r in rows:
                ws.append([r["employee_id"],r["employee_name"],r["labels"],r["mistakes"],accuracy(r["labels"],r["mistakes"]),r["present_days"] or 0,r["absent_days"] or 0])
            for cell in ws[3]:
                cell.font=Font(bold=True,color="FFFFFF"); cell.fill=PatternFill("solid",fgColor="0877E8"); cell.alignment=Alignment(horizontal="center")
            for col,width in enumerate([16,28,16,17,20,20,20],1): ws.column_dimensions[chr(64+col)].width=width
            ws.freeze_panes="A4"; ws.auto_filter.ref=f"A3:G{ws.max_row}"
            wb.save(path)
            messagebox.showinfo("Export Complete",f"Excel file saved successfully:\n{path}",parent=self)
        except Exception as exc:
            messagebox.showerror("Excel Export Failed",f"Could not export Excel file.\n{exc}",parent=self)

    def export_monthly_pdf(self):
        rows=self._monthly_rows()
        if not rows: return
        path=filedialog.asksaveasfilename(parent=self,title="Export Monthly Summary to PDF",defaultextension=".pdf",filetypes=[("PDF Document","*.pdf")],initialfile=f"Stocking_Monthly_Summary_{self.month_var.get().strip()}.pdf")
        if not path: return
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.units import mm
            doc=SimpleDocTemplate(path,pagesize=landscape(A4),rightMargin=10*mm,leftMargin=10*mm,topMargin=10*mm,bottomMargin=10*mm)
            styles=getSampleStyleSheet(); story=[Paragraph(f"Stocking Productivity - Monthly Summary ({self.month_var.get().strip()})",styles["Title"]),Spacer(1,5*mm)]
            data=[["Employee ID","Employee Name","Total Labels","Total Mistakes","Accuracy %","Total Present Days","Total Absent Days"]]
            for r in rows:
                data.append([str(r["employee_id"]),str(r["employee_name"]),str(r["labels"]),str(r["mistakes"]),f"{accuracy(r['labels'],r['mistakes']):.2f}%",str(r["present_days"] or 0),str(r["absent_days"] or 0)])
            table=Table(data,repeatRows=1,colWidths=[23*mm,43*mm,24*mm,25*mm,25*mm,30*mm,30*mm])
            table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0877E8")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("ALIGN",(0,0),(-1,-1),"CENTER"),("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#D7E2EE")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#EAF8E8")]),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
            story.append(table); doc.build(story)
            messagebox.showinfo("Export Complete",f"PDF file saved successfully:\n{path}",parent=self)
        except Exception as exc:
            messagebox.showerror("PDF Export Failed",f"Could not export PDF file.\n{exc}",parent=self)

    def show_employees(self):
        self.clear(); self.header("Employee Master","Manage Stocking employees and Active / Left status.")
        bar=tk.Frame(self.main,bg=BG); bar.pack(fill="x",padx=28)
        if self.is_admin():
            tk.Button(bar,text="Add Employee",command=self.add_employee,bg=ACCENT,fg=WHITE,bd=0,padx=14,pady=7).pack(side="left",padx=(0,7))
            tk.Button(bar,text="Edit Employee",command=self.edit_employee,bg="#1769A0",fg=WHITE,bd=0,padx=14,pady=7).pack(side="left",padx=(0,7))
            tk.Button(bar,text="Mark Left / Reactivate",command=self.change_status,bg="#B76A00",fg=WHITE,bd=0,padx=14,pady=7).pack(side="left",padx=(0,7))
            tk.Button(bar,text="Delete Employee",command=self.delete_employee,bg="#C62828",fg=WHITE,bd=0,padx=14,pady=7).pack(side="left",padx=(0,7))
        else:
            tk.Label(bar,text="Read-only employee list",bg=BG,fg=MUTED,font=("Segoe UI",9)).pack(side="left")
        box=tk.Frame(self.main,bg=WHITE,highlightbackground=BORDER,highlightthickness=1); box.pack(fill="both",expand=True,padx=28,pady=16)
        cols=("sr","name","status","left_date")
        self.emp_tv=ttk.Treeview(box,columns=cols,show="headings")
        for c,t,w in [("sr","Sr No",80),("name","Employee Name",360),("status","Status",130),("left_date","Left Date",150)]:
            self.emp_tv.heading(c,text=t); self.emp_tv.column(c,width=w,anchor="center")
        self.emp_tv.pack(fill="both",expand=True,padx=10,pady=10)
        self.emp_tv.tag_configure("left",foreground="#C62828",background="#FFF0F0")
        self.emp_tv.tag_configure("active",foreground=TEXT,background=WHITE)
        self.populate_employees()

    def populate_employees(self):
        for i in self.emp_tv.get_children(): self.emp_tv.delete(i)
        c=db(); rows=c.execute("SELECT employee_id,employee_name,status,COALESCE(left_date,'') left_date FROM employees ORDER BY CAST(employee_id AS INTEGER), employee_name").fetchall(); c.close()
        for sr,r in enumerate(rows,1):
            tag="left" if r["status"]=="Left" else "active"
            self.emp_tv.insert("", "end", iid=str(r["employee_id"]), values=(sr,r["employee_name"],r["status"],r["left_date"] or "-"), tags=(tag,))

    def edit_employee(self):
        if not self.is_admin():
            messagebox.showerror("Access Denied", "Only Admin can edit Employee Master.", parent=self)
            return
        # Keep only one Edit Employee dialog open at a time.
        existing = getattr(self, "_edit_employee_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return
        sel=self.emp_tv.selection()
        if not sel:
            messagebox.showwarning("Select Employee","Please select an employee to edit.")
            return
        employee_id=sel[0]; current=self.emp_tv.item(sel[0],"values")
        win=tk.Toplevel(self); self._edit_employee_window = win
        win.title("Edit Employee"); win.resizable(False,False); win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        name=tk.StringVar(value=current[1]); status=tk.StringVar(value=current[2]); left_date=tk.StringVar(value="" if current[3]=="-" else current[3])
        tk.Label(win,text="Employee Name",bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).grid(row=0,column=0,sticky="w",padx=18,pady=10)
        # Employee Master editing is Admin-only; employee ID remains immutable.
        name_entry = tk.Entry(win,textvariable=name,width=30,font=("Segoe UI",9),state="normal")
        name_entry.grid(row=0,column=1,padx=18,pady=10)
        tk.Label(win,text="Status",bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).grid(row=1,column=0,sticky="w",padx=18,pady=10)
        ttk.Combobox(win,textvariable=status,values=("Active","Left"),state="readonly",width=27).grid(row=1,column=1,padx=18,pady=10)
        tk.Label(win,text="Left Date",bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).grid(row=2,column=0,sticky="w",padx=18,pady=10)
        left_entry=tk.Entry(win,textvariable=left_date,width=22,font=("Segoe UI",9),state="readonly"); left_entry.grid(row=2,column=1,padx=(18,4),pady=10,sticky="w")
        date_button=tk.Button(win,text="📅",command=lambda:CalendarPopup(win,left_date,"Select Left Date","%d-%m-%Y"),bg=WHITE,fg=TEXT,bd=1,relief="solid",font=("Segoe UI",9))
        date_button.grid(row=2,column=2,padx=(0,18),pady=10)
        tk.Label(win,text="Format: DD-MM-YYYY",bg=WHITE,fg=MUTED,font=("Segoe UI",7)).grid(row=3,column=1,columnspan=2,sticky="w",padx=18)
        def toggle_left_date(*_):
            enabled = status.get() == "Left"
            date_button.configure(state=("normal" if enabled else "disabled"))
            if not enabled:
                left_date.set("")
        status.trace_add("write", toggle_left_date)
        toggle_left_date()
        def save():
            if not name.get().strip():
                messagebox.showerror("Required","Employee Name is required.",parent=win)
                return
            ld=left_date.get().strip()
            if status.get()=="Left":
                if not ld: messagebox.showerror("Left Date Required","Please enter the date when the employee left.",parent=win); return
                try: datetime.strptime(ld,"%d-%m-%Y")
                except ValueError: messagebox.showerror("Invalid Date","Use DD-MM-YYYY format.",parent=win); return
            else: ld=""
            c=db()
            c.execute("UPDATE employees SET employee_name=?,status=?,left_date=? WHERE employee_id=?",
                      (name.get().strip(),status.get(),ld,employee_id))
            c.commit(); c.close()
            self._edit_employee_window = None
            win.grab_release(); win.destroy(); self.populate_employees()
        tk.Button(win,text="Save Changes",command=save,bg=ACCENT,fg=WHITE,bd=0,padx=15,pady=7,font=("Segoe UI",9,"bold")).grid(row=4,column=0,columnspan=2,pady=14)
        # Center the dialog over the main application window after its widgets determine the size.
        win.update_idletasks()
        dialog_w, dialog_h = win.winfo_reqwidth(), win.winfo_reqheight()
        parent_x, parent_y = self.winfo_rootx(), self.winfo_rooty()
        parent_w, parent_h = self.winfo_width(), self.winfo_height()
        dialog_x = max(0, parent_x + (parent_w - dialog_w) // 2)
        dialog_y = max(0, parent_y + (parent_h - dialog_h) // 2)
        win.geometry(f"{dialog_w}x{dialog_h}+{dialog_x}+{dialog_y}")
        name_entry.focus_set()

    def delete_employee(self):
        if not self.is_admin():
            messagebox.showerror("Access Denied","Only Admin can delete employees."); return
        sel=self.emp_tv.selection()
        if not sel: messagebox.showwarning("Select Employee","Please select an employee to delete."); return
        employee_id=sel[0]; name=self.emp_tv.item(sel[0],"values")[1]
        if not messagebox.askyesno("Confirm Delete",f"Delete employee '{name}'?\n\nHistorical productivity records will be retained."): return
        c=db(); c.execute("DELETE FROM employees WHERE employee_id=?",(employee_id,)); c.commit(); c.close(); self.populate_employees()

    def add_employee(self):
        if not self.is_admin():
            messagebox.showerror("Access Denied", "Only Admin can add employees.", parent=self)
            return
        win=tk.Toplevel(self); win.title("Add Employee"); win.resizable(False,False); win.configure(bg=BG)
        eid=tk.StringVar(); name=tk.StringVar()
        for i,(lab,var) in enumerate([("Employee ID",eid),("Employee Name",name)]):
            tk.Label(win,text=lab,bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).grid(row=i,column=0,sticky="w",padx=18,pady=10)
            tk.Entry(win,textvariable=var,width=30,font=("Segoe UI",9)).grid(row=i,column=1,padx=18,pady=10)
        def save():
            if not eid.get().strip() or not name.get().strip(): messagebox.showerror("Required","Employee ID and Employee Name are required.",parent=win); return
            c=db()
            try:
                c.execute("INSERT INTO employees (employee_id,employee_name,department,supervisor,status,left_date) VALUES(?,?,?,?,?,?)",(eid.get().strip(),name.get().strip(),"STOCKING","","Active","")); c.commit()
            except sqlite3.IntegrityError:
                messagebox.showerror("Duplicate","Employee ID already exists.",parent=win); c.close(); return
            c.close(); win.destroy(); self.populate_employees()
        tk.Button(win,text="Save",command=save,bg=ACCENT,fg=WHITE,bd=0,padx=15,pady=7,font=("Segoe UI",9,"bold")).grid(row=2,column=0,columnspan=2,pady=14)

    def change_status(self):
        if not self.is_admin():
            messagebox.showerror("Access Denied", "Only Admin can change employee status.", parent=self)
            return
        sel=self.emp_tv.selection()
        if not sel: messagebox.showwarning("Select Employee","Please select an employee."); return
        employee_id=sel[0]; vals=self.emp_tv.item(sel[0],"values"); current=vals[2]; name=vals[1]
        if current=="Active":
            win=tk.Toplevel(self); win.title("Mark Employee Left"); win.resizable(False,False); win.configure(bg=BG)
            tk.Label(win,text=f"Employee: {name}",bg=WHITE,fg=TEXT,font=("Segoe UI",10,"bold")).pack(anchor="w",padx=20,pady=(18,8))
            tk.Label(win,text="Left Date (DD-MM-YYYY)",bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).pack(anchor="w",padx=20)
            d=tk.StringVar(value=datetime.now().strftime("%d-%m-%Y"))
            row=tk.Frame(win,bg=WHITE); row.pack(padx=20,pady=8,anchor="w")
            tk.Entry(row,textvariable=d,width=21,font=("Segoe UI",9)).pack(side="left")
            tk.Button(row,text="📅",command=lambda:CalendarPopup(win,d,"Select Left Date","%d-%m-%Y"),bg=WHITE,fg=TEXT,bd=1,relief="solid",font=("Segoe UI",9)).pack(side="left",padx=5)
            def save_left():
                try: datetime.strptime(d.get().strip(),"%d-%m-%Y")
                except ValueError: messagebox.showerror("Invalid Date","Use DD-MM-YYYY format.",parent=win); return
                c=db(); c.execute("UPDATE employees SET status='Left',left_date=? WHERE employee_id=?",(d.get().strip(),employee_id)); c.commit(); c.close(); win.destroy(); self.populate_employees()
            tk.Button(win,text="Confirm Left",command=save_left,bg="#C62828",fg=WHITE,bd=0,padx=15,pady=7,font=("Segoe UI",9,"bold")).pack(pady=(2,18))
        else:
            if not messagebox.askyesno("Reactivate Employee",f"Set '{name}' back to Active?\n\nThe Left Date will be cleared."): return
            c=db(); c.execute("UPDATE employees SET status='Active',left_date='' WHERE employee_id=?",(employee_id,)); c.commit(); c.close(); self.populate_employees()

    def show_supervisors(self):
        if not self.is_admin():
            messagebox.showerror("Access Denied","Only Admin can manage supervisors.")
            return
        self.clear()
        self.header("Supervisor Master","Admin can add or remove supervisor names used in Daily Productivity.")
        bar=tk.Frame(self.main,bg=BG); bar.pack(fill="x",padx=28)
        tk.Button(bar,text="Add Supervisor",command=self.add_supervisor,bg=ACCENT,fg=WHITE,bd=0,padx=14,pady=7,font=("Segoe UI",9,"bold")).pack(side="left")
        tk.Button(bar,text="Delete Supervisor",command=self.delete_supervisor,bg="#C62828",fg=WHITE,bd=0,padx=14,pady=7,font=("Segoe UI",9,"bold")).pack(side="left",padx=7)
        box=tk.Frame(self.main,bg=WHITE,highlightbackground=BORDER,highlightthickness=1); box.pack(fill="both",expand=True,padx=28,pady=16)
        self.sup_tv=ttk.Treeview(box,columns=("sr","name"),show="headings")
        self.sup_tv.heading("sr",text="Sr No"); self.sup_tv.heading("name",text="Supervisor Name")
        self.sup_tv.column("sr",width=90,anchor="center"); self.sup_tv.column("name",width=320,anchor="center")
        self.sup_tv.pack(fill="both",expand=True,padx=10,pady=10)
        self.populate_supervisors()

    def populate_supervisors(self):
        for i in self.sup_tv.get_children(): self.sup_tv.delete(i)
        c=db(); rows=c.execute("SELECT name FROM supervisors WHERE active=1 ORDER BY name").fetchall(); c.close()
        for i,r in enumerate(rows,1): self.sup_tv.insert("", "end", values=(i,r["name"]))

    def add_supervisor(self):
        if not self.is_admin(): return
        win=tk.Toplevel(self); win.title("Add Supervisor"); win.resizable(False,False); win.configure(bg=BG)
        name=tk.StringVar()
        tk.Label(win,text="Supervisor Name",bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).pack(anchor="w",padx=18,pady=(18,6))
        tk.Entry(win,textvariable=name,width=32,font=("Segoe UI",9)).pack(padx=18,pady=6)
        def save():
            n=name.get().strip()
            if not n: messagebox.showerror("Required","Supervisor Name is required.",parent=win); return
            c=db()
            try: c.execute("INSERT INTO supervisors(name,active) VALUES(?,1)",(n,)); c.commit()
            except sqlite3.IntegrityError: messagebox.showerror("Duplicate","Supervisor already exists.",parent=win); c.close(); return
            c.close(); win.destroy(); self.populate_supervisors()
        tk.Button(win,text="Save",command=save,bg=ACCENT,fg=WHITE,bd=0,padx=16,pady=7,font=("Segoe UI",9,"bold")).pack(pady=16)

    def delete_supervisor(self):
        if not self.is_admin(): return
        sel=self.sup_tv.selection()
        if not sel: messagebox.showwarning("Select Supervisor","Please select a supervisor."); return
        name=self.sup_tv.item(sel[0],"values")[1]
        if not messagebox.askyesno("Confirm Delete",f"Delete supervisor '{name}' from the dropdown?\n\nExisting saved records will remain unchanged."): return
        c=db(); c.execute("UPDATE supervisors SET active=0 WHERE name=?",(name,)); c.commit(); c.close(); self.populate_supervisors()

    def show_users(self):
        if not self.is_admin():
            messagebox.showerror("Access Denied","Only Admin can manage users.")
            return
        self.clear()
        self.header("User / ID Management","Admin-only area for creating and deleting login IDs.")
        bar=tk.Frame(self.main,bg=BG); bar.pack(fill="x",padx=28)
        tk.Button(bar,text="Create Login ID",command=self.add_user,bg=ACCENT,fg=WHITE,bd=0,padx=14,pady=7).pack(side="left")
        tk.Button(bar,text="Delete User",command=self.delete_user,bg="#C62828",fg=WHITE,bd=0,padx=14,pady=7).pack(side="left",padx=7)
        box=tk.Frame(self.main,bg=WHITE,highlightbackground=BORDER,highlightthickness=1); box.pack(fill="both",expand=True,padx=28,pady=16)
        cols=("id","name","role","status")
        self.user_tv=ttk.Treeview(box,columns=cols,show="headings")
        for c,t,w in [("id","Login ID",150),("name","Name",250),("role","Role",120),("status","Status",100)]:
            self.user_tv.heading(c,text=t); self.user_tv.column(c,width=w,anchor="center")
        self.user_tv.pack(fill="both",expand=True,padx=10,pady=10)
        self.populate_users()

    def populate_users(self):
        for i in self.user_tv.get_children(): self.user_tv.delete(i)
        c=db(); rows=c.execute("SELECT login_id,display_name,role,active FROM users ORDER BY display_name").fetchall(); c.close()
        for r in rows:
            self.user_tv.insert("", "end", values=(r["login_id"],r["display_name"],r["role"],"Active" if r["active"] else "Disabled"))

    def delete_user(self):
        if not self.is_admin():
            messagebox.showerror("Access Denied","Only Admin can manage users."); return
        sel=self.user_tv.selection()
        if not sel:
            messagebox.showwarning("Select User","Please select a user to delete."); return
        login_id=self.user_tv.item(sel[0],"values")[0]
        if login_id == ADMIN_ID:
            messagebox.showwarning("Not Allowed","The owner/Admin Login ID cannot be deleted."); return
        if not messagebox.askyesno("Confirm Delete",f"Delete user '{login_id}'?\n\nThis user will no longer be able to login."):
            return
        c=db(); c.execute("DELETE FROM users WHERE login_id=?",(login_id,)); c.commit(); c.close(); self.populate_users()

    def add_user(self):
        if not self.is_admin():
            messagebox.showerror("Access Denied","Only Admin can create login IDs."); return
        win=tk.Toplevel(self); win.title("Create Login ID"); win.resizable(False,False); win.configure(bg=BG)
        vals=[tk.StringVar() for _ in range(3)]
        for i,lab in enumerate(["Login ID","Name","Password"]):
            tk.Label(win,text=lab,bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).grid(row=i,column=0,sticky="w",padx=18,pady=8)
            tk.Entry(win,textvariable=vals[i],width=28,show="•" if i==2 else "").grid(row=i,column=1,padx=18,pady=8)
        tk.Label(win,text="Role",bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).grid(row=3,column=0,sticky="w",padx=18,pady=8)
        role_var = tk.StringVar(value="User")
        role_box = ttk.Combobox(win,textvariable=role_var,values=("User","Admin"),state="readonly",width=25)
        role_box.grid(row=3,column=1,padx=18,pady=8)
        def save():
            if not all(v.get().strip() for v in vals):
                messagebox.showerror("Required","All fields are required.",parent=win); return
            if len(vals[2].get()) < 8:
                messagebox.showerror("Weak Password", "Password must be at least 8 characters long.", parent=win); return
            c=db()
            try:
                selected_role = role_var.get().strip()
                c.execute("INSERT INTO users VALUES(?,?,?,?,1)",(vals[0].get().strip(),vals[1].get().strip(),hash_password(vals[2].get()),selected_role)); c.commit()
            except sqlite3.IntegrityError:
                messagebox.showerror("Duplicate","Login ID already exists.",parent=win); c.close(); return
            c.close(); win.destroy(); self.populate_users()
        tk.Button(win,text="Create User",command=save,bg=ACCENT,fg=WHITE,bd=0,padx=15,pady=7,font=("Segoe UI",9,"bold")).grid(row=4,column=0,columnspan=2,pady=14)

    def logout(self):
        if not messagebox.askyesno(
            "Confirm Logout",
            f"Are you sure you want to logout, {self.display_name}?"
        ):
            return
        self.destroy()
        Login().mainloop()

init_db()
Login().mainloop()
