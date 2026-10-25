"""
ocr/parsers.py — Pure-function text parsing module for OCR documents.

Extracts normalized dates, amounts, merchants, and keyword groups from
raw OCR text output. All functions in this module are pure with no
database access or file I/O.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

ARABIC_INDIC_MAP: dict[str, str] = {
    "\u0660": "0",
    "\u0661": "1",
    "\u0662": "2",
    "\u0663": "3",
    "\u0664": "4",
    "\u0665": "5",
    "\u0666": "6",
    "\u0667": "7",
    "\u0668": "8",
    "\u0669": "9",
    # Eastern Arabic-Indic / Persian digits
    "\u06f0": "0",
    "\u06f1": "1",
    "\u06f2": "2",
    "\u06f3": "3",
    "\u06f4": "4",
    "\u06f5": "5",
    "\u06f6": "6",
    "\u06f7": "7",
    "\u06f8": "8",
    "\u06f9": "9",
}

FRENCH_MONTHS: dict[str, int] = {
    # Janvier
    "janvier": 1,
    "janv": 1,
    "jan": 1,
    # Février
    "février": 2,
    "fevrier": 2,
    "févr": 2,
    "fevr": 2,
    "fev": 2,
    # Mars
    "mars": 3,
    "mar": 3,
    # Avril
    "avril": 4,
    "avr": 4,
    # Mai
    "mai": 5,
    # Juin
    "juin": 6,
    "jun": 6,
    # Juillet
    "juillet": 7,
    "juil": 7,
    "jul": 7,
    # Août
    "août": 8,
    "aout": 8,
    "aou": 8,
    # Septembre
    "septembre": 9,
    "sept": 9,
    "sep": 9,
    # Octobre
    "octobre": 10,
    "oct": 10,
    # Novembre
    "novembre": 11,
    "nov": 11,
    # Décembre
    "décembre": 12,
    "decembre": 12,
    "déc": 12,
    "dec": 12,
}

KNOWN_MERCHANTS: list[str] = [
    "STEG",
    "SONEDE",
    "TRANSTU",
    "SNCFT",
    "TGM",
    "Carrefour",
    "Monoprix",
    "Géant",
    "Géant Casino",
    "Magasin Général",
    "Aziza",
]

KEYWORD_NEAR_TOTAL: list[str] = [
    "total",
    "net a payer",
    "net à payer",
    "montant",
    "a payer",
    "à payer",
    "ttc",
    "total ttc",
    "montant total",
]

DATE_NEAR_KEYWORDS: list[str] = [
    "date",
    "emis le",
    "émis le",
    "le",
    "periode",
    "période",
    "date facture",
    "date d'emission",
]


# ─────────────────────────────────────────────────────────────────────────────
# Functions
# ─────────────────────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """
    Normalize text for OCR analysis.

    Converts to lowercase, removes diacritical marks (accents),
    converts Arabic-Indic digits to ASCII standard digits,
    and collapses consecutive whitespace characters.

    Parameters
    ----------
    text : str
        Input string.

    Returns
    -------
    str
        Cleaned, normalized string.
    """
    if not text:
        return ""

    # Convert Arabic-Indic digits
    chars = [ARABIC_INDIC_MAP.get(ch, ch) for ch in text]
    text = "".join(chars).lower()

    # Decompose unicode to strip combining diacritical marks
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")

    # Collapse whitespace
    return re.sub(r"\s+", " ", stripped).strip()


def _fix_ocr_digits(val: str) -> str:
    """
    Fix common OCR letter-to-digit substitutions in numeric date/amount tokens.
    """
    return val.translate(str.maketrans({
        "O": "0", "o": "0",
        "l": "1", "I": "1", "i": "1",
    }))


def extract_dates(text: str) -> list[date]:
    """
    Extract all valid dates from text.

    Supports:
    - dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy
    - dd/mm/yy, dd-mm-yy, dd.mm.yy (year+2000 if yy < 50 else 1900+yy)
    - dd monthname yyyy (French month names)
    - dd monthname abbreviated yyyy

    Applies OCR character corrections ('O'->'0', 'l'->'1', 'I'->'1')
    to numeric components only. Rejects impossible calendar dates and
    dates with year < 1990 or year > current_year + 1.

    Parameters
    ----------
    text : str
        Input document text.

    Returns
    -------
    list[date]
        Deduplicated list of extracted dates in order of appearance.
    """
    if not text:
        return []

    norm = normalize_text(text)
    current_year = date.today().year
    extracted: list[date] = []

    # 1. Numeric date patterns: dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy, dd/mm/yy, etc.
    # Pattern allows [0-9oilOIL] in day, month, and year parts
    numeric_pattern = re.compile(
        r"(?<![\d\w])([0-9oil]{1,2})\s*([\/\-\.])\s*([0-9oil]{1,2})\s*[\/\-\.]\s*([0-9oil]{2,4})(?![\d\w])"
    )

    for match in numeric_pattern.finditer(norm):
        raw_day, _, raw_month, raw_year = match.groups()
        day_str = _fix_ocr_digits(raw_day)
        month_str = _fix_ocr_digits(raw_month)
        year_str = _fix_ocr_digits(raw_year)

        if not (day_str.isdigit() and month_str.isdigit() and year_str.isdigit()):
            continue

        day_val = int(day_str)
        month_val = int(month_str)
        year_val = int(year_str)

        if len(year_str) == 2:
            year_val = (year_val + 2000) if year_val < 50 else (1900 + year_val)

        if not (1990 <= year_val <= current_year + 1 and 1 <= month_val <= 12 and 1 <= day_val <= 31):
            continue

        try:
            parsed = date(year_val, month_val, day_val)
            if parsed not in extracted:
                extracted.append(parsed)
        except ValueError:
            continue

    # 2. Textual month dates: dd monthname yyyy, dd monthname abbreviated yyyy
    # e.g., "15 janvier 2024", "15 janv 2024", "15 janv. 2024"
    textual_pattern = re.compile(
        r"(?<![\d\w])([0-9oil]{1,2})\s+([a-z\.]+)\s+([0-9oil]{2,4})(?![\d\w])"
    )

    for match in textual_pattern.finditer(norm):
        raw_day, raw_month_word, raw_year = match.groups()
        month_key = raw_month_word.rstrip(".")
        if month_key not in FRENCH_MONTHS:
            continue

        month_val = FRENCH_MONTHS[month_key]
        day_str = _fix_ocr_digits(raw_day)
        year_str = _fix_ocr_digits(raw_year)

        if not (day_str.isdigit() and year_str.isdigit()):
            continue

        day_val = int(day_str)
        year_val = int(year_str)

        if len(year_str) == 2:
            year_val = (year_val + 2000) if year_val < 50 else (1900 + year_val)

        if not (1990 <= year_val <= current_year + 1 and 1 <= day_val <= 31):
            continue

        try:
            parsed = date(year_val, month_val, day_val)
            if parsed not in extracted:
                extracted.append(parsed)
        except ValueError:
            continue

    return extracted


def pick_best_date(dates: list[date], text: str) -> Optional[date]:
    """
    Select the most plausible document date from candidates.

    Filters out any dates in the future. Prefers candidate dates appearing
    near DATE_NEAR_KEYWORDS in the raw/normalized text. Otherwise returns
    the most recent valid date. Never returns a future date.

    Parameters
    ----------
    dates : list[date]
        List of candidate dates.
    text : str
        Document text for proximity search.

    Returns
    -------
    Optional[date]
        The chosen date, or None if no valid non-future date exists.
    """
    if not dates:
        return None

    today = date.today()
    valid_candidates = [d for d in dates if d <= today]
    if not valid_candidates:
        return None

    if len(valid_candidates) == 1:
        return valid_candidates[0]

    norm = normalize_text(text)
    norm_keywords = [normalize_text(kw) for kw in DATE_NEAR_KEYWORDS]

    # Find keyword locations
    keyword_locs: list[int] = []
    for kw in norm_keywords:
        start = 0
        while True:
            pos = norm.find(kw, start)
            if pos == -1:
                break
            keyword_locs.append(pos)
            start = pos + len(kw)

    best_candidate: Optional[date] = None
    min_dist = float("inf")

    if keyword_locs:
        for cand in valid_candidates:
            day_s = f"{cand.day:02d}"
            month_s = f"{cand.month:02d}"
            year_s = str(cand.year)

            representations = [
                f"{day_s}/{month_s}/{year_s}",
                f"{day_s}-{month_s}-{year_s}",
                f"{day_s}.{month_s}.{year_s}",
                f"{cand.day}/{cand.month}/{year_s}",
                f"{day_s}/{month_s}/{year_s[-2:]}",
                year_s,
            ]

            cand_locs: list[int] = []
            for rep in representations:
                start = 0
                while True:
                    pos = norm.find(rep, start)
                    if pos == -1:
                        break
                    cand_locs.append(pos)
                    start = pos + len(rep)

            for c_pos in cand_locs:
                for k_pos in keyword_locs:
                    dist = abs(c_pos - k_pos)
                    if dist < min_dist:
                        min_dist = dist
                        best_candidate = cand

    if best_candidate is not None and min_dist <= 150:
        return best_candidate

    return max(valid_candidates)


def _parse_amount_candidate(s: str) -> Optional[Decimal]:
    """Helper to sanitize and parse an amount candidate string into Decimal."""
    cleaned = re.sub(r"(?i)\s*(?:dt|tnd|dinars?)$", "", s).strip()
    if not cleaned:
        return None

    # Handle comma and dot combinations
    if "," in cleaned and "." in cleaned:
        first_dot = cleaned.find(".")
        first_comma = cleaned.find(",")
        if first_dot < first_comma:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(" ", "").replace(",", ".")
    elif "." in cleaned:
        cleaned = cleaned.replace(" ", "")
    else:
        cleaned = cleaned.replace(" ", "")

    try:
        val = Decimal(cleaned)
        if Decimal(0) < val < Decimal(1_000_000):
            return val
    except (InvalidOperation, ValueError):
        return None

    return None


def extract_amounts(text: str) -> list[Decimal]:
    """
    Extract monetary amounts from text.

    Supports:
    - Digits with optional thousand separator (space or dot) then comma + 2-3 decimals
    - Digits with optional space thousand separator then dot + 2-3 decimals
    - Currency suffixes: DT, TND, dinars (case-insensitive, optional)

    Filters for amounts strictly greater than 0 and less than 1,000,000.

    Parameters
    ----------
    text : str
        Input document text.

    Returns
    -------
    list[Decimal]
        Deduplicated list of valid Decimal amounts in order of appearance.
    """
    if not text:
        return []

    norm = normalize_text(text)
    amounts: list[Decimal] = []

    # Exclude 3-part date sequences (e.g., 15.02.2024)
    # Pattern 1: comma as decimal separator (e.g. 1 234,500 or 12,500 or 12,50)
    # Pattern 2: dot as decimal separator (e.g. 1 234.500 or 12.500 or 12.50)
    # Pattern 3: integer or decimal followed by currency suffix (e.g. 150 DT, 50 TND)
    patterns = [
        # Numbers with comma decimal separator (2 or 3 decimals)
        r"(?<![\d\.\/\-])(\d{1,3}(?:[ .]\d{3})*,\d{2,3})(?:\s*(?:dt|tnd|dinars?)\b)?(?![\d\.\/\-])",
        # Numbers with dot decimal separator (2 or 3 decimals, not part of a date)
        r"(?<![\d\.\/\-])(\d{1,3}(?: \d{3})*\.\d{2,3})(?:\s*(?:dt|tnd|dinars?)\b)?(?![\d\.\/\-])",
        # Numbers with explicit currency suffix (integer or decimal)
        r"(?<![\d\.\/\-])(\d{1,3}(?:[ .]\d{3})*(?:[.,]\d{1,3})?)\s*(?:dt|tnd|dinars?)\b",
    ]

    for pat in patterns:
        for match in re.finditer(pat, norm):
            raw_match = match.group(1)
            parsed = _parse_amount_candidate(raw_match)
            if parsed is not None and parsed not in amounts:
                amounts.append(parsed)

    return amounts


def pick_best_amount(amounts: list[Decimal], text: str) -> Optional[Decimal]:
    """
    Select the most plausible total amount from extracted candidates.

    Prefers amounts appearing after KEYWORD_NEAR_TOTAL keywords in the raw text.
    Otherwise returns the largest plausible amount.

    Parameters
    ----------
    amounts : list[Decimal]
        Candidate Decimal amounts.
    text : str
        Raw document text for keyword context.

    Returns
    -------
    Optional[Decimal]
        The most likely total amount, or None if amounts is empty.
    """
    if not amounts:
        return None

    if len(amounts) == 1:
        return amounts[0]

    norm = normalize_text(text)
    norm_keywords = sorted(
        [normalize_text(kw) for kw in KEYWORD_NEAR_TOTAL],
        key=len,
        reverse=True,
    )

    # Search for amounts located after KEYWORD_NEAR_TOTAL keywords
    keyword_amounts: list[Decimal] = []
    for kw in norm_keywords:
        start = 0
        while True:
            pos = norm.find(kw, start)
            if pos == -1:
                break
            # Look at a window of 80 characters after the keyword
            window = norm[pos + len(kw): pos + len(kw) + 80]
            window_amounts = extract_amounts(window)
            for amt in window_amounts:
                if amt in amounts and amt not in keyword_amounts:
                    keyword_amounts.append(amt)
            start = pos + len(kw)

    if keyword_amounts:
        # Prefer the largest amount found near a total keyword
        return max(keyword_amounts)

    return max(amounts)


def extract_merchant(text: str) -> str:
    """
    Extract the merchant name from document text.

    Checks first against KNOWN_MERCHANTS (case-insensitive, partial match allowed).
    If no match, returns the first meaningful line (having 2+ letters, not purely
    numeric, not a date). Returns an empty string if nothing is found.

    Parameters
    ----------
    text : str
        Input document text.

    Returns
    -------
    str
        Extracted merchant name or empty string.
    """
    if not text:
        return ""

    norm = normalize_text(text)

    # 1. Match against KNOWN_MERCHANTS (longest names first)
    sorted_known = sorted(KNOWN_MERCHANTS, key=len, reverse=True)
    for merchant in sorted_known:
        norm_merchant = normalize_text(merchant)
        if norm_merchant in norm:
            return merchant

    # 2. Fallback: First meaningful line
    lines = text.splitlines()
    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue

        # Check has 2+ letters
        letters = re.findall(r"[a-zA-Z\u0600-\u06FF]", cleaned)
        if len(letters) < 2:
            continue

        # Check if line is not purely a date
        dates_in_line = extract_dates(cleaned)
        if dates_in_line:
            # Strip date occurrences to see if substantial text remains
            remainder = re.sub(r"\b\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}\b", "", cleaned)
            remainder = re.sub(r"(?i)\bdate\b", "", remainder)
            if len(re.findall(r"[a-zA-Z\u0600-\u06FF]", remainder)) < 2:
                continue

        # Check that it's not a noise line (e.g. delimiters '=====' or '------')
        stripped_line = re.sub(r"^[^\w\u0600-\u06FF]+|[^\w\u0600-\u06FF]+$", "", cleaned)
        if len(re.findall(r"[a-zA-Z\u0600-\u06FF]", stripped_line)) >= 2:
            return stripped_line

    return ""


def match_keyword_groups(text: str, keyword_groups: list[dict]) -> tuple[int, list[int]]:
    """
    Match keyword groups against document text with exact and fuzzy tolerance.

    Parameters
    ----------
    text : str
        Document text.
    keyword_groups : list[dict]
        List of groups formatted as [{"terms": [...], "required": bool}, ...].

    Returns
    -------
    tuple[int, list[int]]
        (matched_count, list_of_matched_group_indices)
    """
    if not text or not keyword_groups:
        return (0, [])

    norm = normalize_text(text)
    tokens = re.findall(r"\b\w+\b", norm)
    matched_indices: list[int] = []

    for idx, group in enumerate(keyword_groups):
        terms = group.get("terms", [])
        group_matched = False

        for term in terms:
            norm_term = normalize_text(str(term))
            if not norm_term:
                continue

            # Exact substring match
            if norm_term in norm:
                group_matched = True
                break

            # Fuzzy match using difflib
            term_words = norm_term.split()
            if len(term_words) == 1:
                close = difflib.get_close_matches(norm_term, tokens, n=1, cutoff=0.85)
                if close:
                    group_matched = True
                    break
            else:
                n = len(term_words)
                if len(tokens) >= n:
                    ngrams = [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]
                    close = difflib.get_close_matches(norm_term, ngrams, n=1, cutoff=0.85)
                    if close:
                        group_matched = True
                        break

        if group_matched:
            matched_indices.append(idx)

    return (len(matched_indices), matched_indices)


def check_keyword_requirements(
    keyword_groups: list[dict],
    matched_indices: list[int],
    min_groups: int,
) -> bool:
    """
    Determine if keyword matches meet the required minimum count and required groups.

    Parameters
    ----------
    keyword_groups : list[dict]
        List of keyword group definitions.
    matched_indices : list[int]
        Indices of groups that matched.
    min_groups : int
        Minimum number of groups that must match.

    Returns
    -------
    bool
        True if matched count >= min_groups and all required groups are satisfied.
    """
    matched_set = set(matched_indices)
    if len(matched_set) < min_groups:
        return False

    for idx, group in enumerate(keyword_groups):
        if group.get("required", False):
            if idx not in matched_set:
                return False

    return True
