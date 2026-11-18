import re
from datetime import date

_OCR_DIGIT_MAP = str.maketrans(
    {"O": "0", "О": "0", "o": "0", "о": "0", "l": "1", "I": "1", "З": "3", "з": "3"}
)
_OCR_TOKEN = re.compile(r"[0-9OОoоlIЗз]*\d[0-9OОoоlIЗз]*")


def ocr_fix(text: str) -> str:
    return _OCR_TOKEN.sub(lambda m: m.group().translate(_OCR_DIGIT_MAP), text)


_KZ_TO_RU = str.maketrans("әғқңөұүһіӘҒҚҢӨҰҮҺІ", "агкноуухиАГКНОУУХИ")
_LOOKALIKE = str.maketrans("аеокрсухмтвн", "aeokpcyxmtbh")
LEGAL_FORMS = {"тоо", "жшс", "ип", "ао", "ак", "оао", "зао", "ооо", "llp", "llc", "ltd", "жк"}


def norm_key(s: str) -> str:
    s = s.translate(_KZ_TO_RU).casefold().replace("ё", "е").translate(_LOOKALIKE)
    return re.sub(r"[\W_]+", " ", s).strip()


def compact_key(s: str) -> str:
    return norm_key(s).replace(" ", "")


_LEGAL_FORM_KEYS = {norm_key(f) for f in LEGAL_FORMS}


def name_tokens(name: str) -> list[str]:
    return [t for t in norm_key(name).split() if t not in _LEGAL_FORM_KEYS and len(t) > 1]


def token_coverage(name: str, text: str) -> float:
    tokens = name_tokens(name)
    if not tokens:
        return 0.0
    hay = norm_key(text)
    return sum(1 for t in tokens if t in hay) / len(tokens)


_EN_THOUSANDS = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")
_SPACED_RUN = re.compile(r"\d+(?:[.,]\d+)?(?:[   ]\d+(?:[.,]\d+)?)*")
_GROUP_SEP = re.compile(r"[   ]")


def _to_float(s: str) -> float:
    return float(s.replace(",", "."))


def number_candidates(text: str) -> set[float]:
    # В таблицах пробел разделяет и тысячи, и колонки ("50 2 100 105 000"),
    # поэтому берём все допустимые склейки групп: 50, 2100, 105000, ...
    cands: set[float] = set()
    for m in _EN_THOUSANDS.finditer(text):
        cands.add(float(m.group().replace(",", "")))
    for m in _SPACED_RUN.finditer(text):
        groups = _GROUP_SEP.split(m.group())
        for i in range(len(groups)):
            cands.add(_to_float(groups[i]))
            for j in range(i + 1, len(groups)):
                head, tail = groups[i], groups[i + 1 : j + 1]
                if not head.isdigit():
                    break
                if not all(re.fullmatch(r"\d{3}", g) for g in tail[:-1]):
                    break
                if not re.fullmatch(r"\d{3}(?:[.,]\d+)?", tail[-1]):
                    break
                cands.add(_to_float(head + "".join(tail)))
    return cands


def contains_number(value: float, candidates: set[float]) -> bool:
    return any(abs(value - c) < 0.005 for c in candidates)


_WORD_UNITS: dict[str, int] = {
    "ноль": 0, "один": 1, "одна": 1, "одно": 1, "два": 2, "две": 2, "три": 3, "четыре": 4,
    "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
    "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
    "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
    "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90, "сто": 100,
    "двести": 200, "триста": 300, "четыреста": 400, "пятьсот": 500, "шестьсот": 600,
    "семьсот": 700, "восемьсот": 800, "девятьсот": 900,
    "бір": 1, "екі": 2, "үш": 3, "төрт": 4, "бес": 5, "алты": 6, "жеті": 7, "сегіз": 8,
    "тоғыз": 9, "он": 10, "жиырма": 20, "отыз": 30, "қырық": 40, "елу": 50, "алпыс": 60,
    "жетпіс": 70, "сексен": 80, "тоқсан": 90,
}  # fmt: skip
_WORD_HUNDRED_KZ = "жүз"  # множитель: "үш жүз" = 300
_WORD_SCALES: dict[str, int] = {
    "тысяча": 1_000, "тысячи": 1_000, "тысяч": 1_000, "мың": 1_000,
    "миллион": 1_000_000, "миллиона": 1_000_000, "миллионов": 1_000_000,
    "миллиард": 1_000_000_000, "миллиарда": 1_000_000_000, "миллиардов": 1_000_000_000,
}  # fmt: skip
_WORD = re.compile(r"[^\W\d_]+")


def _is_number_word(w: str) -> bool:
    return w in _WORD_UNITS or w in _WORD_SCALES or w == _WORD_HUNDRED_KZ


def _parse_word_run(words: list[str]) -> int:
    total, current = 0, 0
    for w in words:
        if w in _WORD_UNITS:
            current += _WORD_UNITS[w]
        elif w == _WORD_HUNDRED_KZ:
            current = (current or 1) * 100
        else:
            total += (current or 1) * _WORD_SCALES[w]
            current = 0
    return total + current


def words_number_candidates(text: str) -> set[float]:
    words = [w.casefold().replace("ё", "е") for w in _WORD.findall(text)]
    result: set[float] = set()
    run: list[str] = []
    for w in [*words, ""]:
        if w and _is_number_word(w):
            run.append(w)
            continue
        if run:
            value = _parse_word_run(run)
            if value > 0:
                result.add(float(value))
            run = []
    return result


_KZ_MONTHS = {
    "қаңтар": 1, "ақпан": 2, "наурыз": 3, "сәуір": 4, "мамыр": 5, "маусым": 6,
    "шілде": 7, "тамыз": 8, "қыркүйек": 9, "қазан": 10, "қараша": 11, "желтоқсан": 12,
}  # fmt: skip
_RU_MONTH_PREFIX = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7,
    "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}  # fmt: skip
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})\b")
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_WORD_DATE = re.compile(r"\b(\d{1,2})\s+([^\W\d_]+)\s+(\d{4})")


def _month_from_word(word: str) -> int | None:
    w = word.casefold()
    for name, num in _KZ_MONTHS.items():
        if w.startswith(name):
            return num
    return _RU_MONTH_PREFIX.get(w[:3])


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def find_dates(text: str) -> set[date]:
    found: set[date | None] = set()
    for d, m, y in _NUMERIC_DATE.findall(text):
        year = int(y) + 2000 if len(y) == 2 else int(y)
        found.add(_safe_date(year, int(m), int(d)))
    for y, m, d in _ISO_DATE.findall(text):
        found.add(_safe_date(int(y), int(m), int(d)))
    for d, word, y in _WORD_DATE.findall(text):
        month = _month_from_word(word)
        if month:
            found.add(_safe_date(int(y), month, int(d)))
    return {d for d in found if d is not None}


_BIN = re.compile(r"(?<!\d)\d{12}(?!\d)")


def find_bins(text: str) -> set[str]:
    return set(_BIN.findall(text))


def bin_checksum_ok(value: str) -> bool:
    """Контрольная цифра БИН/ИИН РК (веса 1..11, при остатке 10 — веса 3..11,1,2)."""
    if not re.fullmatch(r"\d{12}", value):
        return False
    digits = [int(c) for c in value]
    s = sum(d * w for d, w in zip(digits[:11], range(1, 12), strict=True)) % 11
    if s == 10:
        weights = [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2]
        s = sum(d * w for d, w in zip(digits[:11], weights, strict=True)) % 11
        if s == 10:
            return False
    return s == digits[11]


CURRENCY_MARKERS: dict[str, re.Pattern[str]] = {
    "KZT": re.compile(r"тенге|теңге|\bтг\b|₸|\bkzt\b", re.IGNORECASE),
    "USD": re.compile(r"\busd\b|\$|доллар", re.IGNORECASE),
    "EUR": re.compile(r"\beur\b|€|евро", re.IGNORECASE),
}


def find_currencies(text: str) -> set[str]:
    return {code for code, pattern in CURRENCY_MARKERS.items() if pattern.search(text)}
