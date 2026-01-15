import argparse
import json
import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


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
    period: str


TERMIN_RE = re.compile(r"(termin|semester)\s*(\d+)", re.IGNORECASE)
PERIOD_RE = re.compile(r"period\s*(\d+)", re.IGNORECASE)
PROFILE_RE = re.compile(r"profil\s*:\s*(.+)", re.IGNORECASE)
COURSE_CODE_RE = re.compile(r"^[A-ZÅÄÖ]{3,}\d{2,}")

MAIN_AREA_MAP = {
    "1": "Maskinteknik",
    "3383": "Maskinteknik",
    "3392": "Tillämpad mekanik",
    "teme": "Tillämpad mekanik",
    "2": "Industriell ekonomi",
    "3": "Logistik och supply chain",
    "4": "Energi- och miljöteknik",
}


def normalize(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").strip().split())


def parse_hp(raw: str) -> Optional[float]:
    cleaned = raw.replace("*", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def map_area_token(token: str) -> str:
    key = token.strip().lower()
    return MAIN_AREA_MAP.get(key, token.strip())


def parse_main_areas(raw: str) -> List[str]:
    raw = normalize(raw)
    if not raw or raw == "-":
        return []
    parts = re.split(r"[,/;]\s*", raw)
    return [map_area_token(part) for part in parts if part.strip()]


def map_status(raw: str, vof_attr: Optional[str] = None) -> str:
    # Prefer data-vof attribute when available (c/e/v)
    if vof_attr:
        raw = vof_attr.upper()
    else:
        raw = normalize(raw).upper()
    mapping = {
        "O": "Obligatorisk",
        "OBLIGATORISK": "Obligatorisk",
        "C": "Obligatorisk",
        "V": "Valbar",
        "VALBAR": "Valbar",
        "E": "Valbar",
        "F": "Frivillig",
        "FRIVILLIG": "Frivillig",
        "O/V": "Obligatorisk/Valbar",
        "O/V / VALBAR": "Obligatorisk/Valbar",
    }
    return mapping.get(raw, raw or "Okand")


def extract_headers(table):
    headers = [normalize(th.get_text()) for th in table.find_all("th")]
    header_to_idx = {h.lower(): idx for idx, h in enumerate(headers)}
    return headers, header_to_idx


def column_index(headers: List[str], needle_patterns: List[str], fallback: int = 0) -> int:
    needle_patterns = [p.lower() for p in needle_patterns]
    for idx, h in enumerate(headers):
        h_low = h.lower()
        if any(p in h_low for p in needle_patterns):
            return idx
    return fallback


def parse_table(table, current_profile: str, current_term: int) -> List[Course]:
    headers, _ = extract_headers(table)
    if not headers:
        # Some tables may lack <th>; infer by position
        headers = []
    idx_code = column_index(headers, ["kod", "kurskod", "course code"], 0)
    idx_name = column_index(headers, ["namn", "kursnamn", "course name"], 1)
    idx_hp = column_index(headers, ["hp", "poang", "poäng", "credits"], 2)
    idx_level = column_index(headers, ["niva", "nivå", "level"], 3)
    idx_main = column_index(headers, ["huvudomr", "huvudområde", "field"], 4)
    idx_status = column_index(headers, ["v/o", "status", "obligatorisk", "ecv"], 5)

    courses: List[Course] = []
    current_period: str = ""
    for row in table.find_all("tr"):
        header_cell = row.find("th", attrs={"colspan": True})
        if header_cell:
            header_text = normalize(header_cell.get_text())
            period_match = PERIOD_RE.search(header_text)
            if period_match:
                current_period = period_match.group(1)
            continue
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        cell_text = [normalize(c.get_text()) for c in cells]
        code = cell_text[idx_code] if idx_code < len(cell_text) else ""
        if not COURSE_CODE_RE.match(code):
            continue
        name = cell_text[idx_name] if idx_name < len(cell_text) else ""
        hp_raw = cell_text[idx_hp] if idx_hp < len(cell_text) else ""
        hp = parse_hp(hp_raw) or 0.0
        level = cell_text[idx_level] if idx_level < len(cell_text) else ""
        main_raw = cell_text[idx_main] if idx_main < len(cell_text) else ""
        main_areas = parse_main_areas(main_raw)

        # Fallback: use data-field-of-study numbers if main area empty
        if not main_areas:
            data_field = row.get("data-field-of-study")
            if data_field:
                main_areas = [map_area_token(part) for part in data_field.split("|") if part]

        status_raw = cell_text[idx_status] if idx_status < len(cell_text) else ""
        status = map_status(status_raw, row.get("data-vof"))

        courses.append(
            Course(
                code=code,
                name=name,
                hp=hp,
                level=level,
                main_areas=main_areas,
                status=status,
                profiles=[current_profile],
                term=current_term,
                period=current_period,
            )
        )
    return courses


def merge_courses(courses: List[Course]) -> List[Course]:
    by_code: dict[str, Course] = {}
    for c in courses:
        key = c.code.upper()
        if key not in by_code:
            by_code[key] = c
            continue
        existing = by_code[key]
        merged_profiles = sorted({*existing.profiles, *c.profiles})
        merged_main = sorted({*existing.main_areas, *c.main_areas})
        existing.profiles = merged_profiles
        existing.main_areas = merged_main
    return list(by_code.values())


def scrape(url: str) -> List[Course]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Map specialization code -> readable name from the filter select; include empty as Gemensam.
    spec_map: Dict[str, str] = {
        "": "Gemensam",
        "FLYG": "Flygteknik",
        "ESMT": "Energi- och miljöteknik",
        "KTPU": "Konstruktionsteknik och produktutveckling",
        "KMAT": "Konstruktionsmaterial",
        "TEME": "Tillämpad mekanik",
        "LOGS": "Logistik och supply chain management",
        "MEKA": "Mekatronik",
        "PRDL": "Operations Management",
        "INPR": "Produktionsteknik",
        "KVAL": "Kvalitetsutveckling",
    }
    for opt in soup.select(".specializations-filter option"):
        code = (opt.get("value") or "").strip()
        name = normalize(opt.get_text()) or code or "Gemensam"
        if code:
            spec_map.setdefault(code, name)

    courses: List[Course] = []
    current_term: Optional[int] = None

    # Walk headings + specialization blocks in order
    for tag in soup.find_all(["h2", "h3", "h4", "h5", "h6", "div"]):
        if tag.name in {"h2", "h3", "h4", "h5", "h6"}:
            text = normalize(tag.get_text())
            term_match = TERMIN_RE.search(text)
            if term_match:
                current_term = int(term_match.group(2))
            continue

        if tag.name == "div" and tag.has_attr("data-specialization") and current_term is not None and current_term >= 7:
            code = tag.get("data-specialization") or ""
            profile_name = spec_map.get(code, code or "Gemensam")
            table = tag.find("table")
            if table:
                courses.extend(parse_table(table, profile_name, current_term))

    return merge_courses(courses)


def write_courses_json(courses: List[Course], path: str = "courses_db.json") -> None:
    payload = [asdict(c) for c in courses]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape course data from LiU Studieinfo.")
    parser.add_argument("--program", default="6CMMM", help="Programkod, t.ex. 6CMMM")
    parser.add_argument("--instance", help="Antagningsomgång/instance-id, t.ex. 5172 för 2022")
    parser.add_argument("--year", type=int, help="Antagningsår (ex 2022, 2023, 2024, 2025). Lämna tomt för interaktiv fråga.")
    parser.add_argument("--url", help="Överskriv full URL om du vill ange manuellt")
    parser.add_argument("--out", default="courses_db.json", help="Sökväg för output JSON")
    args = parser.parse_args()

    year_to_instance = {
        2022: "5172",
        2023: "5457",
        2024: "5740",
        2025: "6028",
    }

    instance = args.instance
    year = args.year

    if not instance and not year and not args.url:
        # Interactive prompt if neither year nor instance nor full URL supplied
        try:
            entered = input("Ange antagningsår (2022-2025) eller instance-id: ").strip()
        except EOFError:
            entered = ""
        if entered.isdigit():
            if len(entered) == 4:
                year = int(entered)
            else:
                instance = entered

    if not instance and year:
        instance = year_to_instance.get(year)
        if not instance:
            raise SystemExit(f"No instance mapping for year {year}")

    if args.url:
        url = args.url
    else:
        base = f"https://studieinfo.liu.se/program/{args.program}"
        if instance:
            base += f"/{instance}"
        url = base + "#curriculum"

    courses = scrape(url)
    write_courses_json(courses, path=args.out)
    print(f"Scraped {len(courses)} courses from {url} -> {args.out}")


if __name__ == "__main__":
    main()
