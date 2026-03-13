"""PII / secret detection and placeholder substitution.

Ports regex patterns from the anon detector library. No external dependencies.

Placeholder format: [TypeName_8hexchars]  e.g. [UUID_a1b2c3d4]

Public API:
    transform_secrets(text) -> (transformed_text, {hash: original})
"""

from __future__ import annotations

import hashlib
import re
from datetime import date

# ---------------------------------------------------------------------------
# Compiled regexes (most-specific / longest patterns first)
# ---------------------------------------------------------------------------

# Application ID: 17 digits + 3 uppercase letters + 5+ alphanumeric chars
_APPLICATIONID_RE = re.compile(r"\b\d{17}[A-Z]{3}[0-9a-z]{5,}\b", re.IGNORECASE)

# Payment account: starts with 4, total 20 digits
_PAYMENT_ACCOUNT_RE = re.compile(r"(?P<payment_account>\b4\d{19}\b)")

# Correspondent account: starts with 301, total 20 digits
_CORRESPONDENT_ACCOUNT_RE = re.compile(r"(?P<correspondent_account>\b301\d{17}\b)")

# UUID: standard 8-4-4-4-12 hex, allows optional whitespace around dashes
_UUID_RE = re.compile(
    r"[0-9a-z]{8}\s*-\s*[0-9a-z]{4}\s*-\s*[0-9a-z]{4}\s*-\s*[0-9a-z]{4}\s*-\s*[0-9a-z]{12}",
    re.IGNORECASE,
)

# Contract: "договор" or "номер" (with optional endings), optional non-digit chars,
# then 5+ digit number. Excludes matches where extra text contains card/order/policy keywords.
_CONTRACT_RE = re.compile(
    r"\b(договор|номер)(а|у|ом|е)?\b\s*(?P<extra>\D{,10})\s*(?P<number>\d{5,})",
    re.IGNORECASE,
)
_CONTRACT_EXCLUSION_RE = re.compile(
    r"(карты|заказа|полиса|сч[её]та|заявки)", re.IGNORECASE
)

# Siebel ID: digit-dash-5to9 alphanumeric chars
_SIEBELID_RE = re.compile(r"\b\d-[A-Z0-9]{5,9}\b", re.IGNORECASE)

# Client code: 3 uppercase letters + "0" + 6+ digits
_CLIENTCODE_RE = re.compile(r"\b[A-Z]{3}0\d{6,}\b", re.IGNORECASE)

# PAN: 13-19 digits, optionally separated by spaces/dashes/dots (Luhn-validated below)
_PAN_RE = re.compile(r"((\d((\s*)|[-.])){13,19})")
_PAN_STRIP_RE = re.compile(r"[-\s.]")

# ---------------------------------------------------------------------------
# Phase 2: Passport patterns (ported from anon detectors/constants/passport.py)
# ---------------------------------------------------------------------------

# Russian passport: series (2+2 digits) + number (6 digits), with heuristic lookbehind
# Heuristics suppress matches preceded by financial/system keywords (ИНН, КПП, договор, etc.)
_RUS_PASSPORT_HEURISTICS_BEFORE = (
    r"(?<!#)(?<!^)(?<!_)(?<!/)(?<!;)(?<!,)(?<!\.)"
    r"(?<!номера )(?<!номера)(?<!тел)(?<!тел:)(?<!tel)(?<!tel:)"
    r"(?<!банка)(?<!банка:)(?<!банка:\n)(?<!банка: \n)"
    r"(?<!банка\n)(?<!банка \n)(?<!полиса )(?<!полиса)"
    r"(?<!Полис )(?<!Полис)(?<!счет)(?<!счет\n)(?<!счет )"
    r"(?<!счет:)(?<!счет: )(?<!договору)(?<!договору )"
    r"(?<!Договор: )(?<!Договор:)(?<!Договор )(?<!Договор)"
    r"(?<!артикул)(?<!артикул:)(?<!артикул: )"
    r"(?<!договору)(?<!договору )(?<!договору  )"
    r"(?<!договора)(?<!договора )(?<!договора:)"
    r"(?<!договора: )(?<!договор)(?<!договор )"
    r"(?<!диалог)(?<!диалог )(?<!№ )(?<!№)"
    r"(?<!бик)(?<!ИНН  - )(?<!ИНН –)(?<!ИНН – )"
    r"(?<!ИНН -)(?<!ИНН - )(?<!ИНН  -)(?<!ИНН  )"
    r"(?<!ИНН )(?<!ИНН: )(?<!ИНН:)(?<!ИНН)"
    r"(?<!инн)(?<!инн )(?<!инн)(?<!инн:)(?<!инн: )"
    r"(?<!инн:  )(?<!инн \n)(?<!инн –)(?<!инн – )"
    r"(?<!инн\n)(?<!кпп)(?<!кпп:)(?<!кпп: )"
    r"(?<!кпп )(?<!TMST)(?<!TMST)(?<!укажите)(?<!укажите )"
    r"(?<!на)(?<!на )"
    r"(?<!\+7-)(?<!\+7)"
)
_RUS_PASSPORT_HEURISTICS_AFTER = r"(?!:)(?!%)(?!&)(?!.html)(?!/)(?!#)"

_RUS_PASSPORT_RE = re.compile(
    _RUS_PASSPORT_HEURISTICS_BEFORE
    + r"(?<!\d)(?P<series>(серия)[-: ]{0,3})?"
    + r"(?P<RUS_s1>[0-9 ]{2})[- ]{0,3}"
    + r"(?P<RUS_s2>[0-9 ]{2})[- \s]{0,3}"
    + r"(?P<number_kw>(номер)|(№)?)[-: ]{0,3}"
    + r"(?P<RUS_number>([0-9][ ]*){5}[0-9])\b"
    + _RUS_PASSPORT_HEURISTICS_AFTER
)

# Ukrainian passport: 8 digits (birth date YYYYMMDD) + optional separator + 5 digits
_UKR_PASSPORT_RE = re.compile(
    r"\b(?P<UKR_first>[0-9]{8})[- ]{0,3}(?P<UKR_second>[0-9]{5})\b"
)

# Belarusian passport: 7 digits + 1 letter + 3 digits + 2 letters + 1 digit
_BLR_PASSPORT_RE = re.compile(r"\b(?P<BLR>[0-9]{7}[A-Z]{1}[0-9]{3}[A-Z]{2}[0-9]{1})\b")

# Georgian passport: 2 digits + 2 letters + 5 digits
_GEO_PASSPORT_RE = re.compile(r"\b(?P<GEO>[0-9]{2}[A-Z]{2}[0-9]{5})\b")

# Kyrgyz/Uzbek passport: 2 letters + 7 digits
_KGZ_UZB_PASSPORT_RE = re.compile(r"\b(?P<KGZ_UZB>[A-Z]{2}[0-9]{7})\b")

# Kazakh/Azerbaijani/Turkmen passport: 1 letter + 7 digits
_KAZ_AZE_TKM_PASSPORT_RE = re.compile(r"\b(?P<KAZ_AZE_TKM>[A-Z][0-9]{7})\b")

# OKATO region codes for Russian passports (from anon/core/detectors/data/passport_data.py)
_RUS_REGIONS_OKATO: frozenset[str] = frozenset({
    "01", "03", "04", "05", "07", "08", "10", "11", "12", "14", "15", "17", "18", "19",
    "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "32", "33", "34",
    "35", "36", "37", "38", "40", "41", "42", "43", "44", "45", "46", "47", "49", "50",
    "52", "53", "54", "55", "56", "57", "58", "60", "61", "63", "64", "65", "66", "67",
    "68", "69", "70", "71", "73", "74", "75", "76", "77", "78", "79", "80", "81", "82",
    "83", "84", "85", "86", "87", "88", "89", "90", "91", "92", "93", "94", "95", "96",
    "97", "98", "99",
})

# Valid Russian passport issue years: 1997-1999 (last century) + 00 through current_year-1998+2
_RUS_PASSPORT_LAST_CENTURY_YEARS: frozenset[str] = frozenset({"97", "98", "99"})


def _rus_passport_valid_issue_years() -> frozenset[str]:
    """Build the set of valid 2-digit issue year strings for Russian passports."""
    current_year = date.today().year
    last_possible = current_year - 2000 + 2  # cur_century_begin_year=2000
    years = set(_RUS_PASSPORT_LAST_CENTURY_YEARS)
    for y in range(last_possible + 1):
        years.add(f"{y:02d}")
    return frozenset(years)


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


# ---------------------------------------------------------------------------
# Phase 2: SNILS (ported from anon detectors/local/snils.py)
# ---------------------------------------------------------------------------

_SNILS_WORD_RE = re.compile(
    r"\b[сcs][нn][иi][лl][сcs](?:а|у|ом|е|ов|ам|ами|ы)?\b", re.IGNORECASE
)
_SNILS_RE = re.compile(
    r"""
    \b
    (?P<exact>
        \d{3}[-]+
        \d{3}[-]+
        \d{3}[-\s]+
        \d{2}
    )
    |
    (?P<similar>
       (?<!\+)              # don't start with + (not phone)
       (?:\d[\s-]*){10}     # 10 digits with spaces
       \d
    )
    \b""",
    re.VERBOSE,
)
_SNILS_WORD_MARGIN = 50


def _snils_checksum_valid(snils: str) -> bool:
    """Validate SNILS by checksum (algorithm from anon SNILSDetector._validate_snils)."""
    digits = "".join(re.findall(r"\d+", snils))
    if len(digits) != 11:
        return False
    snils_digits = digits[:9]
    control_number = int(digits[9:11])
    coefficients = [9, 8, 7, 6, 5, 4, 3, 2, 1]
    total = sum(int(d) * c for d, c in zip(snils_digits, coefficients))
    if total < 100:
        calculated = total
    elif total == 100:
        calculated = 0
    else:
        remainder = total % 101
        calculated = 0 if remainder == 100 else remainder
    return control_number == calculated


# ---------------------------------------------------------------------------
# Phase 2: Email (ported from anon detectors/constants/constants_email.py)
# ---------------------------------------------------------------------------

_EMAIL_DOT = r"\s*(?:\.|точка|тчк|точ|тч|точк|dot)\s*"
_EMAIL_DOT_TALK = r"\s*(?:точка|тчк|точ|тч|точк|дот|dot)\s*"
_EMAIL_DOMAIN_END = (
    r"(рф|ру|ком|бай|орг|нет|нэт|cу|ru|by|com|org|net|"
    r"su|de|cn|uk|nl|br|au|fr|eu|it|[a-zа-я]{2,3})"
)

_EMAIL_POPULAR_STRICT_DOMAINS = (
    "gmail|mail|yandex|yahoo|tbank|hotmail|vk|protonmail|rambler|icloud|outlook|bk|inbox"
)
_EMAIL_DOMAIN_ENDINGS = "ru|com|net|org|by|ua|kz|ру|ком|нэт|орг|уа|юа|кз|рф"

_EMAIL_POPULAR_TALK_DOMAINS = (
    r"тбанк|tbank|т-банк|t-bank|ти банк|ti bank|ти-банк|ti-bank|тинк|tink|тиньк|тинькофф|tinkoff"
    r"|тинькофф-банк|tinkoff-bank|тинькоффбанк|tinkoffbank"
    r"|яндекс|yandex|яндкс|yandx|yndx"
    r"|джимейл|gmeil|джимайл|gmail|джи-мейл|g-meil|джи-майл|g-mail|жмейл|jmail|гмайл|гмейл"
    r"|яху|yahoo|еху|yehoo|йеху|jahoo|jehoo"
    r"|мэйл|mail|мейл|meil|майл"
    r"|рамблер|rambler|рэмблер|rembler|румблер|rumbler"
    r"|вк|vk|вэка|vka"
    r"|протон|proton|протон-мейл|proton-meil|протон-майл|proton-mail|протонмейл|protonmeil"
    r"|протонмайл|protonmail"
    r"|аутлук|outlook|аут лук|out look|оутлук|оут лук"
    r"|хотмейл|hotmeil|хотмайл|hotmail"
    r"|бк|bk|бэка|bka|бка|б-ка|b-ka"
    r"|иклауд|icloud|и-клауд|i-cloud|айклауд|клауд|cloud|иклоуд|иклод|iclod|и-клод|i-clod"
    r"|айклод|клод|clod"
    r"|инбокс|inbox|ин-бокс|in-box|ин бокс|in boxинбок|inbok|ин-бок|in-bok"
)

_EMAIL_SEP = r"(?:[\s<.,:';/?&%$#!^*>]*)"
_EMAIL_WORD_START = r"(?:(?<=\s)|(?<=^)|(?<=[!\"#$%&'()*+,-./:;<=>?@[\]^_`{|}~]))"
_EMAIL_WORD_END = r"(?:(?=\s)|(?=$)|(?=[!\"#$%&'()*+,-./:;<=>?@[\]^_`{|}~]))"

_EMAIL_STRICT = rf"""
    (?<!\*)                             # no asterisk before
    (?=[a-zA-Z0-9_.+-]*[a-zA-Z])        # username has at least one letter
    [a-zA-Zа-яА-Я0-9_.+-]{{4,}}        # username >= 4 chars
    \s*@\s*
    (?=[a-zA-Z0-9_-]*[a-zA-Z])          # domain has letters
    (?![-]{{1,}}$)[a-zA-Z0-9_-]{{3,}}  # domain > 2 chars, not all dashes
    (?:\.\s*[a-zA-Z]{{2,40}})?
"""

_EMAIL_STRICT_KNOWN = rf"""
    (?<!\*)
    [a-zA-Zа-яА-Я0-9_.+-]{{4,}}
    \s*@\s*
    (?:{_EMAIL_POPULAR_STRICT_DOMAINS})
    {_EMAIL_DOT}
    {_EMAIL_DOMAIN_END}
"""

_EMAIL_STRICT_KNOWN_NO_SUFFIX = rf"""
    (?<!\*)
    [a-zA-Zа-яА-Я0-9_.+-]{{4,}}
    \s*@\s*
    (?:(?:{_EMAIL_POPULAR_STRICT_DOMAINS})(?:{_EMAIL_DOMAIN_ENDINGS}))
"""

_EMAIL_TALK_KNOWN = rf"""
    (?=[a-zA-Zа-яА-Я0-9_.+\u2013\u2014\-|]*[a-zA-Zа-яА-Я])
    [a-zA-Zа-яА-Я0-9_.+\u2013\u2014\-|]{{4,}}
    {_EMAIL_SEP}
    (?:\bсобака\b|\bсобачка\b|\bсобакен\b|\bсобачк\b|\bсобак\b|\bsobaka\b)
    {_EMAIL_SEP}
    (?:{_EMAIL_POPULAR_TALK_DOMAINS})
"""

_EMAIL_TALK_UNKNOWN = rf"""
    (?=[a-zA-Zа-яА-Я0-9_.+\u2013\u2014\-|]*[a-zA-Zа-яА-Я])
    [a-zA-Zа-яА-Я0-9_.+\u2013\u2014\-|]{{4,}}
    {_EMAIL_SEP}
    (?:\bсобака\b|\bсобачка\b|\bсобакен\b|\bсобачк\b|\bсобак\b|\bsobaka\b)
    {_EMAIL_SEP}
    (?=[a-zA-Zа-яА-Я0-9\s\-_]*[a-zA-Zа-яА-Я])
    [a-zA-Zа-яА-Я0-9\s\-_]{{2,}}
    {_EMAIL_DOT_TALK}
    {_EMAIL_DOMAIN_END}
"""

_EMAIL_NO_AT = (
    r"(?<!\w)"
    r"(?:[a-zA-Zа-яА-Я0-9_.+-]{4,20})"
    r"(?:(?:" + _EMAIL_POPULAR_STRICT_DOMAINS + r")(?:" + _EMAIL_DOMAIN_ENDINGS + r"))"
    r"(?!\w)"
)

_EMAIL_PATTERN = rf"""
    {_EMAIL_WORD_START}
    (?:
        {_EMAIL_STRICT}
        |
        {_EMAIL_STRICT_KNOWN}
        |
        {_EMAIL_STRICT_KNOWN_NO_SUFFIX}
        |
        {_EMAIL_TALK_UNKNOWN}
        |
        {_EMAIL_TALK_KNOWN}
        |
        {_EMAIL_NO_AT}
    )
    {_EMAIL_WORD_END}
"""

_EMAIL_RE = re.compile(_EMAIL_PATTERN, re.IGNORECASE | re.VERBOSE)

# ---------------------------------------------------------------------------
# Phase 2: INN (ported from anon detectors/utils/account_validators.py)
# ---------------------------------------------------------------------------

# INN regex: 10 or 12 digits (must be disambiguated — run 12 first)
_INN12_RE = re.compile(r"(?P<inn>\b\d{12}\b)")
_INN10_RE = re.compile(r"(?P<inn>\b\d{10}\b)")


def _inn12_valid(inn: str) -> bool:
    """Validate 12-digit personal INN checksum (ported from anon validate_inn)."""
    if len(inn) != 12 or not inn.isdigit():
        return False

    def _ctrl(coefs: tuple) -> int:
        return sum(c * int(inn[i]) for i, c in enumerate(coefs)) % 11 % 10

    n11 = _ctrl((7, 2, 4, 10, 3, 5, 9, 4, 6, 8))
    n12 = _ctrl((3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8))
    return n11 == int(inn[10]) and n12 == int(inn[11])


def _inn10_valid(inn: str) -> bool:
    """Validate 10-digit company INN checksum."""
    if len(inn) != 10 or not inn.isdigit():
        return False
    coefs = (2, 4, 10, 3, 5, 9, 4, 6, 8)
    ctrl = sum(c * int(inn[i]) for i, c in enumerate(coefs)) % 11 % 10
    return ctrl == int(inn[9])


# ---------------------------------------------------------------------------
# Phase 2: BIC (ported from anon detectors/local/account.py)
# ---------------------------------------------------------------------------

# Russian BIC: 9 digits starting with "04"
_BIC_RE = re.compile(r"(?P<bic>\b04\d{7}\b)")

# ---------------------------------------------------------------------------
# Phase 2: KPP (ported from anon detectors/local/account.py + petrovna logic)
# ---------------------------------------------------------------------------

# KPP: preceded by "КПП" keyword, then 4 digits + 2 alphanumeric + 3 digits
_KPP_RE = re.compile(
    r"КПП[:/\\\"']?:?\s*(?P<kpp>\b[0-9]{4}[0-9A-Z]{2}[0-9]{3}\b)",
    re.IGNORECASE,
)


def _kpp_valid(kpp: str) -> bool:
    """KPP is valid if it's not all zeros and matches the structural pattern."""
    return bool(re.fullmatch(r"[0-9]{4}[0-9A-Z]{2}[0-9]{3}", kpp, re.IGNORECASE)) and kpp != "000000000"


# ---------------------------------------------------------------------------
# Phase 2: Payment amounts with currency (ported from anon detectors/local/payment.py)
# ---------------------------------------------------------------------------

_PAYMENT_INFO_RE = re.compile(
    r"\b("
    r"\d+(?:\s\d{3})*(?:[.,]\d{1,3})?\s*"
    r"(?:тыс(?:яч(?:и)?|.)?|млн\.?|миллион|миллиона|т\.?|k|к|K|К|о)?\s*"
    r"([рР](?:уб(?:лей|ль|ля|л)?)?|rub|дол(?:ларов|ара|лара)?"
    r"|евро|usd|eur|€|\$|коп(?:ейки|еек|ейку)?|юан(?:ь|ей))"
    r")\b"
)


# ---------------------------------------------------------------------------
# Luhn checksum validation (ported from stdlib — no external deps)
# ---------------------------------------------------------------------------

def _luhn_valid(number: str) -> bool:
    """Return True if the digit string passes the Luhn checksum."""
    digits = [int(c) for c in number]
    # Double every second digit from the right (starting at index -2)
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_placeholder(type_name: str, original: str) -> tuple[str, str]:
    """Return (placeholder, hash8) for the given original string."""
    h = hashlib.sha256(original.encode()).hexdigest()[:8]
    return f"[{type_name}_{h}]", h


def _replace_matches(
    text: str,
    matches: list[tuple[int, int, str]],  # (start, end, original)
    type_name: str,
) -> tuple[str, dict[str, str]]:
    """Replace all (start, end) spans in text with placeholders.

    Processes in reverse order so indices stay valid.
    Returns (transformed_text, new_mappings).
    """
    new_mappings: dict[str, str] = {}
    for start, end, original in reversed(matches):
        placeholder, h = _make_placeholder(type_name, original)
        new_mappings[h] = original
        text = text[:start] + placeholder + text[end:]
    return text, new_mappings


# ---------------------------------------------------------------------------
# Per-type detection functions
# ---------------------------------------------------------------------------

def _find_application_ids(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in _APPLICATIONID_RE.finditer(text)]


def _find_payment_accounts(text: str) -> list[tuple[int, int, str]]:
    return [
        (m.start("payment_account"), m.end("payment_account"), m.group("payment_account"))
        for m in _PAYMENT_ACCOUNT_RE.finditer(text)
    ]


def _find_correspondent_accounts(text: str) -> list[tuple[int, int, str]]:
    return [
        (
            m.start("correspondent_account"),
            m.end("correspondent_account"),
            m.group("correspondent_account"),
        )
        for m in _CORRESPONDENT_ACCOUNT_RE.finditer(text)
    ]


def _find_uuids(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in _UUID_RE.finditer(text)]


def _find_contracts(text: str) -> list[tuple[int, int, str]]:
    results = []
    for m in _CONTRACT_RE.finditer(text):
        extra = m.group("extra")
        if _CONTRACT_EXCLUSION_RE.search(extra):
            continue
        start, end = m.span("number")
        results.append((start, end, m.group("number")))
    return results


def _find_siebel_ids(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in _SIEBELID_RE.finditer(text)]


def _find_client_codes(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in _CLIENTCODE_RE.finditer(text)]


def _find_pans(text: str) -> list[tuple[int, int, str]]:
    results = []
    for m in _PAN_RE.finditer(text):
        candidate = _PAN_STRIP_RE.sub("", m.group(1))
        if _luhn_valid(candidate):
            results.append((m.start(), m.end(), m.group(1)))
    return results


# ---------------------------------------------------------------------------
# Phase 2 detection functions
# ---------------------------------------------------------------------------

def _find_passports(text: str) -> list[tuple[int, int, str]]:
    """Detect passports for all supported countries (RUS, UKR, BLR, GEO, KGZ_UZB, KAZ_AZE_TKM)."""
    results: list[tuple[int, int, str]] = []
    valid_issue_years = _rus_passport_valid_issue_years()

    # Russian: validate OKATO region code and issue year
    for m in _RUS_PASSPORT_RE.finditer(text):
        s1 = m.group("RUS_s1").replace(" ", "")
        s2 = m.group("RUS_s2").replace(" ", "")
        if s1 in _RUS_REGIONS_OKATO and s2 in valid_issue_years:
            results.append((m.start(), m.end(), m.group()))

    # Ukrainian: validate birth date encoded in first 8 digits
    current_year = date.today().year
    days_in_month = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    for m in _UKR_PASSPORT_RE.finditer(text):
        first8 = m.group("UKR_first")
        py, pm, pd = int(first8[:4]), int(first8[4:6]), int(first8[6:8])
        dim = days_in_month[:]
        if _is_leap_year(py):
            dim[2] = 29
        if py <= 1900 or py > current_year:
            continue
        if pm < 1 or pm > 12:
            continue
        if 1 <= pd <= dim[pm]:
            results.append((m.start(), m.end(), m.group()))

    # Other countries: structural match only (no additional validation)
    for pat in (_BLR_PASSPORT_RE, _GEO_PASSPORT_RE, _KGZ_UZB_PASSPORT_RE, _KAZ_AZE_TKM_PASSPORT_RE):
        for m in pat.finditer(text):
            results.append((m.start(), m.end(), m.group()))

    # Sort by position so _replace_matches can process in reverse
    results.sort(key=lambda x: x[0])
    return results


def _find_snils(text: str) -> list[tuple[int, int, str]]:
    results = []
    for m in _SNILS_RE.finditer(text):
        start, end = m.span()
        raw = m.group()
        # "similar" form (no dashes) requires "снилс" keyword nearby
        if m.group("similar"):
            context_start = max(0, start - _SNILS_WORD_MARGIN)
            context_end = min(len(text), end + _SNILS_WORD_MARGIN)
            context = text[context_start:context_end]
            if not _SNILS_WORD_RE.search(context):
                continue
        if _snils_checksum_valid(raw):
            results.append((start, end, raw))
    return results


def _find_emails(text: str) -> list[tuple[int, int, str]]:
    results = []
    for m in _EMAIL_RE.finditer(text):
        email = m.group()
        # Exclude: "@" present but "нет" also present (context tag, not email)
        if "@" in email and "нет" in email:
            continue
        results.append((m.start(), m.end(), email))
    return results


def _find_inn(text: str) -> list[tuple[int, int, str]]:
    results = []
    # 12-digit first (more specific)
    for m in _INN12_RE.finditer(text):
        inn = m.group("inn")
        if _inn12_valid(inn):
            results.append((m.start("inn"), m.end("inn"), inn))
    # 10-digit (company INN)
    for m in _INN10_RE.finditer(text):
        inn = m.group("inn")
        if _inn10_valid(inn):
            results.append((m.start("inn"), m.end("inn"), inn))
    results.sort(key=lambda x: x[0])
    return results


def _find_bic(text: str) -> list[tuple[int, int, str]]:
    return [
        (m.start("bic"), m.end("bic"), m.group("bic"))
        for m in _BIC_RE.finditer(text)
    ]


def _find_kpp(text: str) -> list[tuple[int, int, str]]:
    results = []
    for m in _KPP_RE.finditer(text):
        kpp = m.group("kpp")
        if _kpp_valid(kpp):
            results.append((m.start("kpp"), m.end("kpp"), kpp))
    return results


def _find_payment_info(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in _PAYMENT_INFO_RE.finditer(text.lower())]


# ---------------------------------------------------------------------------
# Detector pipeline
# Order: longest/most-specific patterns first to avoid partial matches.
# Application IDs (25+ chars) before payment accounts (20 digits) before
# UUIDs (32 hex + dashes) before shorter patterns.
# Phase 2 detectors added after Phase 1.
# ---------------------------------------------------------------------------

_DETECTORS: list[tuple[str, object]] = [
    ("ApplicationID", _find_application_ids),
    ("PaymentAccount", _find_payment_accounts),
    ("CorrespondentAccount", _find_correspondent_accounts),
    ("UUID", _find_uuids),
    ("Contract", _find_contracts),
    ("SiebelID", _find_siebel_ids),
    ("ClientCode", _find_client_codes),
    ("PAN", _find_pans),
    # Phase 2
    ("Passport", _find_passports),
    ("SNILS", _find_snils),
    ("Email", _find_emails),
    ("INN", _find_inn),
    ("BIC", _find_bic),
    ("KPP", _find_kpp),
    ("PaymentInfo", _find_payment_info),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transform_secrets(text: str) -> tuple[str, dict[str, str]]:
    """Find and replace PII/secrets with deterministic placeholders.

    Runs each detector in order. Already-replaced spans (placeholders)
    are not re-processed because patterns don't match placeholder syntax.

    Returns (transformed_text, {hash8: original}) for all replacements made.
    """
    all_mappings: dict[str, str] = {}

    for type_name, find_fn in _DETECTORS:
        matches = find_fn(text)  # type: ignore[operator]
        if matches:
            text, new_mappings = _replace_matches(text, matches, type_name)
            all_mappings.update(new_mappings)

    return text, all_mappings
