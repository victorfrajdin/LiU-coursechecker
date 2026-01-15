# LiU Course Checker
GUI tool to plan LiU Mechanical Engineering (Maskinteknik) T7–T10 studies and verify degree requirements.

## Prereqs
- Python 3.10+ (tkinter included on Windows).
- `requests`, `beautifulsoup4` (for scraping). Install with `pip install requests beautifulsoup4`.

## Workflow
1) **Scrape course data** (writes `courses_db.json`):
```bash
python scraper.py
```
2) **Start the planner GUI**:
```bash
python gui_checker.py
```
3) **Plan**: Drag courses from the search list into period boxes (T7P1–T9P2). Save/load plans via the buttons (JSON format).
4) **Check requirements**: Set `Profil` and `Huvudområde` via the drop-downs, optionally adjust `Baspoäng`, then click **Kontrollera** to see colored status.

## Drop-down values
- **Inriktningar (Profil)**: Energi- och miljöteknik, Flygteknik, Industriell produktion, Konstruktionsmaterial, Konstruktionsteknik och produktutveckling, Kvalitets- och verksamhetsutveckling, Logistik och supply chain management, Mekatronik, Produktionsledning, Tillämpad mekanik.
- **Huvudområden**: Datateknik, Datavetenskap, Elektroteknik, Energi- och miljöteknik, Flygteknik, Fysik, Industriell ekonomi, Maskinteknik, Matematik, Medicinsk teknik, Produktutveckling, Programmering, Teknisk fysik, Tillämpad matematik.

## Files
- `scraper.py` – fetches curriculum data and produces `courses_db.json`.
- `gui_checker.py` – tkinter planner/checker.
- `plan.json` – example saved plan (optional; not required to run).
- `.gitignore` ignores `.venv/`, `__pycache__/`, and Python bytecode.
