import json
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Set

# Simple display mapping for main area codes -> names
AREA_DISPLAY_MAP = {
    "1": "Maskinteknik",
    "3383": "Maskinteknik",
    "3392": "Tillämpad mekanik",
    "teme": "Tillämpad mekanik",
}

INRIKTNINGAR = [
    "Energi- och miljöteknik",
    "Flygteknik",
    "Industriell produktion",
    "Konstruktionsmaterial",
    "Konstruktionsteknik och produktutveckling",
    "Kvalitets- och verksamhetsutveckling",
    "Logistik och supply chain management",
    "Mekatronik",
    "Produktionsledning",
    "Tillämpad mekanik",
]

HUVUDOMRADEN = [
    "Datateknik",
    "Datavetenskap",
    "Elektroteknik",
    "Energi- och miljöteknik",
    "Flygteknik",
    "Fysik",
    "Industriell ekonomi",
    "Maskinteknik",
    "Matematik",
    "Medicinsk teknik",
    "Produktutveckling",
    "Programmering",
    "Teknisk fysik",
    "Tillämpad matematik",
]


@dataclass
class Course:
    code: str
    name: str
    hp: float
    level: str
    main_areas: List[str]
    status: str
    profiles: List[str]
    term: int
    period: str = ""

    @property
    def is_advanced(self) -> bool:
        return self.level.upper().startswith("A")

    @property
    def is_thesis(self) -> bool:
        return "examensarbete" in self.name.lower() or self.level.upper().startswith("A2")


def load_db(path: Path) -> Dict[str, Course]:
    data = json.loads(path.read_text(encoding="utf-8"))
    db: Dict[str, Course] = {}
    for row in data:
        raw_profiles = row.get("profiles")
        if not raw_profiles:
            single_profile = row.get("profile")
            if isinstance(single_profile, str) and single_profile:
                raw_profiles = [single_profile]
            elif isinstance(single_profile, list):
                raw_profiles = single_profile
        if isinstance(raw_profiles, str):
            raw_profiles = [raw_profiles]

        course = Course(
            code=row.get("code", "").strip(),
            name=row.get("name", ""),
            hp=float(row.get("hp", 0) or 0),
            level=row.get("level", ""),
            main_areas=list(row.get("main_areas", []) or []),
            status=row.get("status", ""),
            profiles=list(raw_profiles or []),
            term=int(row.get("term", 0) or 0),
            period=str(row.get("period", "") or ""),
        )
        if course.code:
            db[course.code.upper()] = course
    return db


def is_primary_area_course(course: Course, area_targets: Set[str], profile_targets: Set[str]) -> bool:
    if any(ma.lower() in area_targets for ma in course.main_areas):
        return True
    return any(p.lower() in profile_targets for p in course.profiles)


def format_main_areas(areas: List[str]) -> str:
    formatted: List[str] = []
    for a in areas:
        key = a.strip().lower()
        formatted.append(AREA_DISPLAY_MAP.get(key, a))
    return ", ".join(formatted)


class PlanApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("LiU Course Checker")

        self.db_path = Path("courses_db.json")
        if not self.db_path.exists():
            messagebox.showerror("Fel", "courses_db.json saknas. Kör scrapern först.")
            raise SystemExit(1)
        self.db = load_db(self.db_path)

        self.plan_slots = [
            ("T7P1", "Termin 7 - Period 1"),
            ("T8P1", "Termin 8 - Period 1"),
            ("T9P1", "Termin 9 - Period 1"),
            ("T7P2", "Termin 7 - Period 2"),
            ("T8P2", "Termin 8 - Period 2"),
            ("T9P2", "Termin 9 - Period 2"),
        ]
        self.plan: Dict[str, List[str]] = {slot: [] for slot, _ in self.plan_slots}

        # Requirement status vars
        self.req_keys = [
            "total",
            "profile",
            "project",
            "advanced",
            "delkrav_a",
            "delkrav_b",
            "delkrav_c",
            "primary18",
        ]
        self.req_vars: Dict[str, tk.StringVar] = {key: tk.StringVar(value="(ej kontrollerat)") for key in self.req_keys}
        self.req_labels: Dict[str, tk.Label] = {}

        self._build_ui()
        self._populate_search()
        self.drag_code: str | None = None

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=4)
        top.pack(fill=tk.BOTH, expand=True)

        # Config area
        config = ttk.LabelFrame(top, text="Inställningar", padding=6)
        config.pack(fill=tk.X)

        self.profile_var = tk.StringVar(value=INRIKTNINGAR[0])
        self.primary_area_var = tk.StringVar(value="Maskinteknik")
        self.base_hp_var = tk.DoubleVar(value=180.0)

        ttk.Label(config, text="Profil").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Combobox(
            config,
            textvariable=self.profile_var,
            values=INRIKTNINGAR,
            state="readonly",
            width=28,
        ).grid(row=0, column=1, sticky=tk.W, padx=4, pady=2)

        ttk.Label(config, text="Huvudområde").grid(row=0, column=2, sticky=tk.W, padx=4, pady=2)
        ttk.Combobox(
            config,
            textvariable=self.primary_area_var,
            values=HUVUDOMRADEN,
            state="readonly",
            width=28,
        ).grid(row=0, column=3, sticky=tk.W, padx=4, pady=2)

        ttk.Label(config, text="Baspoäng").grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(config, textvariable=self.base_hp_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=4, pady=2)

        # Rad med sök (vänster) och kravstatus (höger)
        paned = ttk.Panedwindow(top, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, pady=6)

        search_container = ttk.Frame(paned, padding=4)
        status_container = ttk.Frame(paned, padding=4)
        paned.add(search_container, weight=3)
        paned.add(status_container, weight=2)

        # Search area (vänster del av paned)
        search_frame = ttk.LabelFrame(search_container, text="Sök kurs", padding=6)
        search_frame.pack(fill=tk.BOTH, expand=True, pady=6)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._populate_search())
        ttk.Entry(search_frame, textvariable=self.search_var, width=50).pack(anchor=tk.W, pady=2)

        cols = ("code", "name", "hp", "level", "profiles", "main", "term", "period")
        self.tree = ttk.Treeview(search_frame, columns=cols, show="headings", height=5)
        headings = {
            "code": "Kurskod",
            "name": "Namn",
            "hp": "hp",
            "level": "Nivå",
            "profiles": "Profiler",
            "main": "Huvudområden",
            "term": "Termin",
            "period": "Period",
        }
        for col, text in headings.items():
            self.tree.heading(col, text=text)
            if col == "code":
                width = 80
            elif col in {"hp", "level", "term", "period"}:
                width = 60
            else:
                width = 170
            self.tree.column(col, width=width, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)

        # Enable drag from tree to period listboxes
        self.tree.bind("<ButtonPress-1>", self._on_tree_press)
        self.tree.bind("<ButtonRelease-1>", self._on_tree_release)

        # Kravstatus (höger del av paned)
        req_frame = ttk.LabelFrame(status_container, text="Kravstatus", padding=6)
        req_frame.pack(fill=tk.BOTH, expand=True, pady=6)
        req_frame.columnconfigure(1, weight=1)

        row = 0
        def add_req(label: str, key: str):
            nonlocal row
            ttk.Label(req_frame, text=label).grid(row=row, column=0, sticky=tk.W, padx=4, pady=2)
            lbl = tk.Label(req_frame, textvariable=self.req_vars[key], anchor="w")
            lbl.grid(row=row, column=1, sticky=tk.W, padx=4, pady=2)
            self.req_labels[key] = lbl
            row += 1

        add_req("Totalpoäng", "total")
        add_req("Profilkrav", "profile")
        add_req("Projekt T9", "project")
        add_req("Avancerad nivå", "advanced")
        add_req("Delkrav A", "delkrav_a")
        add_req("Delkrav B", "delkrav_b")
        add_req("Delkrav C", "delkrav_c")
        add_req("Huvudområde A≥18", "primary18")

        # Plan area under paned, full bredd
        plan_frame = ttk.LabelFrame(top, text="Planering T7-T9", padding=6)
        plan_frame.pack(fill=tk.BOTH, expand=True, pady=6)

        control_frame = ttk.Frame(plan_frame)
        control_frame.pack(fill=tk.X)

        ttk.Label(control_frame, text="Välj period").pack(side=tk.LEFT, padx=4)
        self.slot_var = tk.StringVar(value=self.plan_slots[0][0])
        slot_names = [label for _, label in self.plan_slots]
        self.slot_combo = ttk.Combobox(control_frame, state="readonly", values=slot_names)
        self.slot_combo.current(0)
        self.slot_combo.pack(side=tk.LEFT, padx=4)

        ttk.Button(control_frame, text="Lägg till", command=self._add_selected_course).pack(side=tk.LEFT, padx=4)
        ttk.Button(control_frame, text="Ta bort", command=self._remove_selected_course).pack(side=tk.LEFT, padx=4)
        ttk.Button(control_frame, text="Spara", command=self._save_plan).pack(side=tk.LEFT, padx=4)
        ttk.Button(control_frame, text="Ladda", command=self._load_plan).pack(side=tk.LEFT, padx=4)
        ttk.Button(control_frame, text="Kontrollera", command=self._on_check_click).pack(side=tk.LEFT, padx=4)

        self.slot_listboxes: Dict[str, tk.Listbox] = {}
        grid = ttk.Frame(plan_frame)
        grid.pack(fill=tk.BOTH, expand=True)
        for idx, (slot, label) in enumerate(self.plan_slots):
            row = idx // 3
            col = idx % 3
            lf = ttk.LabelFrame(grid, text=label, padding=4)
            lf.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            grid.columnconfigure(col, weight=1)
            grid.rowconfigure(row, weight=1)
            lb = tk.Listbox(lf, height=6)
            lb.pack(fill=tk.BOTH, expand=True)
            self.slot_listboxes[slot] = lb

    def _populate_search(self) -> None:
        query = self.search_var.get().strip().lower()
        for row in self.tree.get_children():
            self.tree.delete(row)
        for course in self.db.values():
            if query and query not in course.code.lower() and query not in course.name.lower():
                continue
            self.tree.insert(
                "",
                tk.END,
                iid=course.code,
                values=(
                    course.code,
                    course.name,
                    f"{course.hp:.1f}",
                    course.level,
                    ", ".join(course.profiles),
                    format_main_areas(course.main_areas),
                    course.term,
                    course.period,
                ),
            )

    def _selected_slot(self) -> str:
        name = self.slot_combo.get()
        for slot, label in self.plan_slots:
            if label == name:
                return slot
        return self.plan_slots[0][0]

    def _add_selected_course(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Ingen kurs", "Markera en kurs i listan först.")
            return
        code = selection[0]
        self._add_code_to_slot(code, self._selected_slot())

    def _remove_selected_course(self) -> None:
        slot = self._selected_slot()
        lb = self.slot_listboxes[slot]
        sel = lb.curselection()
        if not sel:
            return
        idx = sel[0]
        code = self.plan[slot][idx]
        self.plan[slot].remove(code)
        self._refresh_slot(slot)

    def _add_code_to_slot(self, code: str, slot: str) -> None:
        if code in self.plan[slot]:
            return
        # Tillåt samma kurs i flera perioder (t.ex. periodöverskridande kurser)
        self.plan[slot].append(code)
        self._refresh_slot(slot)

    # Drag-and-drop from tree to listboxes
    def _on_tree_press(self, event) -> None:
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.drag_code = item
        else:
            self.drag_code = None

    def _on_tree_release(self, event) -> None:
        if not self.drag_code:
            return
        target_widget = self.root.winfo_containing(event.x_root, event.y_root)
        for slot, lb in self.slot_listboxes.items():
            if target_widget is lb:
                self._add_code_to_slot(self.drag_code, slot)
                break
        self.drag_code = None

    def _on_check_click(self) -> None:
        # Wrapper to ensure button always invokes the check
        try:
            self._check_requirements()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Fel vid kontroll", str(exc))

    def _refresh_slot(self, slot: str) -> None:
        lb = self.slot_listboxes[slot]
        lb.delete(0, tk.END)
        for code in self.plan[slot]:
            course = self.db.get(code)
            if course:
                lb.insert(tk.END, f"{course.code} {course.name} ({course.hp:.1f} hp)")
            else:
                lb.insert(tk.END, code)

    def _save_plan(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile="plan.json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        payload = {
            "plan": self.plan,
            "profile": self.profile_var.get(),
            "primary_area": self.primary_area_var.get(),
            "base_hp": self.base_hp_var.get(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("Sparat", f"Plan sparad till {path}")

    def _load_plan(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.plan = {slot: data.get("plan", {}).get(slot, []) for slot, _ in self.plan_slots}
        self.profile_var.set(data.get("profile", ""))
        self.primary_area_var.set(data.get("primary_area", "Maskinteknik"))
        self.base_hp_var.set(data.get("base_hp", 180.0))
        for slot, _ in self.plan_slots:
            self._refresh_slot(slot)
        messagebox.showinfo("Laddat", f"Plan laddad från {path}")

    def _collect_courses(self) -> List[Course]:
        codes: List[str] = []
        seen: set[str] = set()
        for slot_codes in self.plan.values():
            for c in slot_codes:
                if c not in seen:
                    seen.add(c)
                    codes.append(c)
        return [self.db[c] for c in codes if c in self.db]

    def _check_requirements(self) -> None:
        try:
            courses = self._collect_courses()
            base_hp = float(self.base_hp_var.get() or 0)
            profile_name = self.profile_var.get().strip().lower()
            primary_area = (self.primary_area_var.get() or "Maskinteknik").strip()
            primary_area_lower = primary_area.lower()

            primary_area_aliases = {primary_area_lower}
            if primary_area_lower in {"maskinteknik", "maskin"}:
                primary_area_aliases.update({"maskin", "maskinteknik", "3383", "3392", "1", "teme", "tillämpad mekanik"})

            primary_profile_targets = set()
            if primary_area_lower in {"maskinteknik", "maskin"}:
                primary_profile_targets.update({"tillämpad mekanik", "applied mechanics"})

            thesis_hp = 30.0  # assumed OK
            total_hp = base_hp + sum(c.hp for c in courses) + thesis_hp

            profile_courses = [c for c in courses if any(p.lower() == profile_name for p in c.profiles)] if profile_name else []
            profile_hp = sum(c.hp for c in profile_courses)

            project_in_profile = next((c for c in profile_courses if c.term == 9 and "projekt" in c.name.lower()), None)

            advanced_courses = [c for c in courses if c.is_advanced]
            advanced_hp = sum(c.hp for c in advanced_courses) + thesis_hp  # räknar in exjobb som A

            adv_primary = [
                c for c in advanced_courses if is_primary_area_course(c, primary_area_aliases, primary_profile_targets) and not c.is_thesis
            ]
            adv_primary_hp = sum(c.hp for c in adv_primary) + thesis_hp  # räkna exjobb till huvudområde

            adv_non_thesis = [c for c in advanced_courses if not c.is_thesis]
            adv_non_thesis_hp = sum(c.hp for c in adv_non_thesis)

            primary_advanced_hp = sum(
                c.hp for c in advanced_courses if is_primary_area_course(c, primary_area_aliases, primary_profile_targets)
            ) + thesis_hp

            # Uppdatera kravstatus-rutan
            def set_status(key: str, ok: bool, detail: str) -> None:
                self.req_vars[key].set(("OK " if ok else "EJ OK ") + detail)
                lbl = self.req_labels.get(key)
                if lbl:
                    lbl.configure(foreground="green" if ok else "red")

            set_status("total", total_hp >= 300, f"{total_hp:.1f}/300 (bas {base_hp:.1f} + exjobb 30)")
            if profile_name:
                set_status("profile", profile_hp >= 60, f"{profile_hp:.1f}/60 inom {self.profile_var.get() or 'profil'}")
            else:
                set_status("profile", False, "- ange profil -")
            set_status("project", project_in_profile is not None, project_in_profile.code if project_in_profile else "saknas")
            set_status("advanced", advanced_hp >= 90, f"{advanced_hp:.1f}/90")
            set_status("delkrav_a", adv_primary_hp >= 30, f"{adv_primary_hp:.1f}/30")
            set_status("delkrav_b", adv_non_thesis_hp >= 60, f"{adv_non_thesis_hp:.1f}/60")
            set_status("delkrav_c", True, f"{thesis_hp:.1f}/30 (antaget)")
            set_status("primary18", primary_advanced_hp >= 18, f"{primary_advanced_hp:.1f}/18")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Fel vid kontroll", str(exc))

def main() -> None:
    root = tk.Tk()
    app = PlanApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
