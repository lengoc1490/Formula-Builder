"""
number_to_words.py
==================
Đọc số thành chữ tiếng Việt — phiên bản tổng quát.

Tính năng:
  - Số nguyên, số thập phân (tuỳ độ chính xác)
  - Số âm
  - Tiền tệ (VND, USD, EUR, GBP, JPY, ...)
  - Hai kiểu đọc phần thập phân:
      * "digit"   — đọc từng chữ số : 1.045 → "...phẩy không bốn năm"
      * "integer" — đọc như số nguyên: 1.045 → "...phẩy không trăm bốn mươi lăm"
  - Chuỗi định dạng Việt Nam "1.234,56" và Quốc tế "1,234.56"
  - Không phụ thuộc thư viện ngoài (chỉ dùng stdlib)

Sử dụng:
    from number_to_words import number_to_words

    number_to_words(1_000_001)
    # → "Một triệu không trăm linh một"

    number_to_words(122351.01)
    # → "Một trăm hai mươi hai nghìn ba trăm năm mươi mốt phẩy không một"

    number_to_words(100.05, currency="USD")
    # → "Một trăm đô la Mỹ năm cent"

    number_to_words(100.7, currency="VND")
    # → "Một trăm linh một đồng"   (VND không xu → làm tròn)

    number_to_words(1.2345, decimal_mode="digit", decimal_digits=4)
    # → "Một phẩy hai ba bốn năm"

    number_to_words(1.2345, decimal_mode="integer", decimal_digits=4)
    # → "Một phẩy hai nghìn ba trăm bốn mươi lăm"

    number_to_words("9.50")
    # → "Chín phẩy năm mươi"

    number_to_words(-9.5)
    # → "Âm chín phẩy năm"

    number_to_words("1.234,56")
    # → "Một nghìn hai trăm ba mươi tư phẩy năm mươi sáu"
"""

import re
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from typing import Literal, Optional, Union

# ---------------------------------------------------------------------------
# Kiểu tham số
# ---------------------------------------------------------------------------

DecimalMode = Literal["digit", "integer"]

# ---------------------------------------------------------------------------
# Bảng từ cơ bản
# ---------------------------------------------------------------------------

_ONES = ["", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]

_TEENS = [
    "mười",     "mười một", "mười hai", "mười ba",  "mười bốn",
    "mười lăm", "mười sáu", "mười bảy", "mười tám", "mười chín",
]

_TENS = [
    "", "mười", "hai mươi", "ba mươi", "bốn mươi", "năm mươi",
    "sáu mươi", "bảy mươi", "tám mươi", "chín mươi",
]

# ---------------------------------------------------------------------------
# Bảng tiền tệ mặc định
# ---------------------------------------------------------------------------

_CURRENCY_MAP: dict[str, dict] = {
    # "fraction" = "" → không có đơn vị nhỏ → làm tròn về số nguyên
    "VND": {"main": "đồng",             "fraction": ""},
    "USD": {"main": "đô la Mỹ",         "fraction": "cent",    "fraction_digits": 2},
    "EUR": {"main": "ơ rô",             "fraction": "cent",    "fraction_digits": 2},
    "GBP": {"main": "bảng Anh",         "fraction": "pence",   "fraction_digits": 2},
    "JPY": {"main": "yên Nhật",         "fraction": ""},
    "CNY": {"main": "nhân dân tệ",      "fraction": "hào",     "fraction_digits": 2},
    "KRW": {"main": "won",              "fraction": ""},
    "SGD": {"main": "đô la Singapore",  "fraction": "cent",    "fraction_digits": 2},
    "AUD": {"main": "đô la Úc",         "fraction": "cent",    "fraction_digits": 2},
    "CAD": {"main": "đô la Canada",     "fraction": "cent",    "fraction_digits": 2},
    "CHF": {"main": "franc Thụy Sĩ",    "fraction": "rappen",  "fraction_digits": 2},
    "HKD": {"main": "đô la Hồng Kông",  "fraction": "cent",    "fraction_digits": 2},
    "THB": {"main": "baht",             "fraction": "satang",  "fraction_digits": 2},
}

# ---------------------------------------------------------------------------
# Parse đầu vào → Decimal
# ---------------------------------------------------------------------------

def _parse_number(amount: Union[int, float, str, Decimal, None]) -> Optional[Decimal]:
    """
    Chuyển đổi nhiều kiểu đầu vào thành Decimal.

    Hỗ trợ:
      - int, float, Decimal
      - Chuỗi quốc tế  : "1,234.56"
      - Chuỗi Việt Nam : "1.234,56"
      - Dấu âm/dương   : "-1.5", "+2"
      - Phần thập phân bất kỳ số chữ số

    Trả về None nếu không parse được.
    """
    if amount is None:
        return None
    if isinstance(amount, Decimal):
        return amount
    if isinstance(amount, (int, float)):
        return Decimal(str(amount))

    s = str(amount).strip()
    if not s:
        return None

    negative = False
    if s.startswith('-'):
        negative, s = True, s[1:].lstrip()
    elif s.startswith('+'):
        s = s[1:].lstrip()

    s = re.sub(r'\s+', '', s)
    if not s:
        return None

    last_dot   = s.rfind('.')
    last_comma = s.rfind(',')
    last_sep   = max(last_dot, last_comma)

    integer_part = s
    decimal_part = ""

    if last_sep != -1:
        after = s[last_sep + 1:]
        if after.isdigit() and len(after) >= 1:
            integer_part = s[:last_sep].replace('.', '').replace(',', '')
            decimal_part = after
        else:
            integer_part = s.replace('.', '').replace(',', '')
    else:
        integer_part = s

    if not integer_part:
        integer_part = "0"
    if not re.fullmatch(r'\d+', integer_part):
        return None

    decimal_str = f"{integer_part}.{decimal_part}" if decimal_part else integer_part

    try:
        val = Decimal(decimal_str)
        return -val if negative else val
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Đọc phần nguyên
# ---------------------------------------------------------------------------

def _group_name(pos: int) -> str:
    """
    Tên nhóm theo vị trí (0 = đơn vị).

    pos=1 → nghìn          (10^3)
    pos=2 → triệu          (10^6)
    pos=3 → tỷ             (10^9)
    pos=4 → nghìn tỷ       (10^12)
    pos=5 → triệu tỷ       (10^15)
    pos=6 → tỷ tỷ          (10^18)
    pos=7 → nghìn tỷ tỷ    (10^21)
    ...
    """
    if pos == 0:
        return ""
    base_names = ["nghìn", "triệu", "tỷ"]
    base  = (pos - 1) % 3       # 0=nghìn, 1=triệu, 2=tỷ
    cycle = (pos - 1) // 3      # 0 → lần đầu, 1 → thêm "tỷ", 2 → "tỷ tỷ", ...
    name  = base_names[base]
    if cycle > 0:
        name = name + " " + " ".join(["tỷ"] * cycle)
    return name


@lru_cache(maxsize=1000)
def _read_group(n: int) -> str:
    """
    Đọc một nhóm 3 chữ số (1–999).

    Quy tắc "linh":
      - Có hàng trăm VÀ phần lẻ là 1–9 → thêm "linh"
      - Không có hàng trăm → đọc thẳng (không thêm "không trăm")
    """
    if not (1 <= n <= 999):
        raise ValueError(f"_read_group: ngoài khoảng 1–999, nhận {n}")

    hundreds, remainder = divmod(n, 100)
    parts: list[str] = []

    if hundreds:
        parts.append(f"{_ONES[hundreds]} trăm")

    if remainder == 0:
        pass
    elif remainder < 10:
        if hundreds:
            parts.append("linh")
        parts.append(_ONES[remainder])
    elif remainder < 20:
        parts.append(_TEENS[remainder - 10])
    else:
        tens, ones = divmod(remainder, 10)
        parts.append(_TENS[tens])
        if ones:
            suffix = {1: "mốt", 4: "tư", 5: "lăm"}.get(ones, _ONES[ones])
            parts.append(suffix)

    return " ".join(parts)


def _read_integer(n: int) -> str:
    """
    Đọc số nguyên không âm thành chữ tiếng Việt.

    Xử lý "không trăm [linh]" khi:
      A) Có nhóm 0 liền trước nhóm đơn vị
      B) Nhóm liền trước < 100 (thiếu hàng trăm) VÀ nhóm đơn vị < 100
    """
    if n == 0:
        return "không"

    groups: list[int] = []
    tmp = n
    while tmp:
        groups.insert(0, tmp % 1000)
        tmp //= 1000

    total = len(groups)
    parts: list[str] = []

    for i, val in enumerate(groups):
        pos = total - 1 - i

        if val == 0:
            continue

        group_words = _read_group(val)
        name        = _group_name(pos)

        need_bridge = False
        if i > 0 and pos == 0:
            prev_val = groups[i - 1]
            if prev_val == 0:
                need_bridge = True
            elif prev_val < 100 and val < 100:
                need_bridge = True

        if need_bridge:
            parts.append("không trăm linh" if val < 10 else "không trăm")

        parts.append(f"{group_words} {name}".strip())

    return " ".join(parts).strip()


# ---------------------------------------------------------------------------
# Đọc phần thập phân
# ---------------------------------------------------------------------------

def _read_decimal_as_digits(dec_str: str) -> str:
    """
    Đọc từng chữ số thập phân.

    "045" → "không bốn năm"
    "5"   → "năm"
    "50"  → "năm không"
    """
    return " ".join("không" if ch == '0' else _ONES[int(ch)] for ch in dec_str)


def _read_decimal_as_integer(dec_str: str) -> str:
    """
    Đọc phần thập phân như số nguyên có đủ len(dec_str) chữ số.

    Ý nghĩa: dec_str biểu diễn con số với đúng số chữ số đó (kể cả leading zero).
    Leading zeros trong dec_str mang nghĩa (ví dụ "045" ≠ "45" trong ngữ cảnh thập phân).

    Thuật toán:
      1. Pad trái thành bội số 3 (để chia nhóm — pad KHÔNG có nghĩa).
      2. Chia thành nhóm 3 chữ số.
      3. Nhóm đầu tiên (cao nhất): kiểm tra chữ số đầu của nhóm trong chuỗi gốc
         (trước khi pad) — nếu là '0' → chèn "không trăm [linh]" trước khi đọc phần còn lại.
      4. Nhóm 0 ở giữa → "không [tên nhóm]".
      5. Nhóm đơn vị → áp dụng bridge như _read_integer.

    Ví dụ:
      "01"   → "không một"             (2 chữ số: tens=0, ones=1)
      "045"  → "không trăm bốn mươi lăm"
      "1045" → "một nghìn không trăm bốn mươi lăm"
      "0045" → "không nghìn không trăm bốn mươi lăm"
      "2345" → "hai nghìn ba trăm bốn mươi lăm"
    """
    if not dec_str:
        return "không"

    n = int(dec_str)
    total_digits = len(dec_str)

    # ── 1–2 chữ số: xử lý trực tiếp ─────────────────────────────────────
    if total_digits <= 2:
        if total_digits == 1:
            return "không" if n == 0 else _ONES[n]
        # 2 chữ số: đọc như số 2 chữ số (tens digit có thể là 0)
        tens, ones = n // 10, n % 10
        if tens == 0:
            # "05" → "không năm"
            return f"không {_ONES[ones]}" if ones else "không không"
        if n < 20:
            return _TEENS[n - 10]
        result = _TENS[tens]
        if ones:
            suffix = {1: "mốt", 4: "tư", 5: "lăm"}.get(ones, _ONES[ones])
            result += f" {suffix}"
        return result

    # ── >= 3 chữ số ───────────────────────────────────────────────────────
    # Pad trái thành bội số 3 (pad thuần căn chỉnh, không có nghĩa về leading zero)
    pad = (3 - total_digits % 3) % 3
    padded = '0' * pad + dec_str
    num_groups = len(padded) // 3
    group_strs = [padded[i*3:(i+1)*3] for i in range(num_groups)]
    group_vals = [int(g) for g in group_strs]

    parts: list[str] = []

    for i, val in enumerate(group_vals):
        pos = num_groups - 1 - i   # vị trí: 0=đơn vị, 1=nghìn, ...

        if val == 0:
            name = _group_name(pos)
            if name:
                parts.append(f"không {name}")
            elif not parts:
                parts.append("không")
            continue

        group_words = _read_group(val)
        name        = _group_name(pos)

        need_bridge = False

        if i == 0:
            # Nhóm đầu tiên (cao nhất):
            # Nếu chữ số đầu của nhóm này trong chuỗi gốc là '0' → bridge.
            # Chú ý: pad không phải leading zero có nghĩa; chỉ xét chữ số đầu
            # của nhóm tính theo chuỗi gốc (dec_str).
            # Vị trí đầu của nhóm đầu trong dec_str = group_strs[0][pad:] nếu pad>0
            # Hoặc đơn giản hơn: chữ số đầu có nghĩa là group_strs[0][pad] khi i=0
            first_meaningful = group_strs[0][pad] if pad > 0 else group_strs[0][0]
            if first_meaningful == '0':
                need_bridge = True
        elif pos == 0:
            # Nhóm đơn vị (không phải đầu): bridge như _read_integer
            prev_val = group_vals[i - 1]
            if prev_val == 0:
                need_bridge = True
            elif prev_val < 100 and val < 100:
                need_bridge = True

        if need_bridge:
            parts.append("không trăm linh" if val < 10 else "không trăm")

        parts.append(f"{group_words} {name}".strip())

    return " ".join(parts).strip()


# ---------------------------------------------------------------------------
# Viết hoa chữ đầu
# ---------------------------------------------------------------------------

def _cap_first(s: str) -> str:
    return (s[0].upper() + s[1:]) if s else s


# ---------------------------------------------------------------------------
# Hàm công khai chính
# ---------------------------------------------------------------------------

def number_to_words(
    amount: Union[int, float, str, Decimal, None],
    *,
    currency: Optional[str] = None,
    currency_map: Optional[dict] = None,
    decimal_mode: DecimalMode = "integer",
    decimal_digits: Optional[int] = None,
    decimal_separator: str = "phẩy",
) -> str:
    """
    Đọc số thành chữ tiếng Việt — phiên bản tổng quát.

    Tham số:
        amount:
            Số cần đọc. Chấp nhận int, float, str, Decimal.

        currency:
            Mã tiền tệ ISO 4217 (VND, USD, EUR, ...).
            Nếu None → đọc thuần số.

        currency_map:
            Bảng tiền tệ tuỳ chỉnh, ghi đè bảng mặc định.
            Cấu trúc:
                {
                    "XYZ": {
                        "main": "tên đơn vị chính",
                        "fraction": "tên đơn vị lẻ",   # "" = không có xu → làm tròn
                        "fraction_digits": 2,           # số chữ số phần lẻ, mặc định 2
                    }
                }

        decimal_mode:
            Kiểu đọc phần thập phân (chỉ dùng khi KHÔNG có currency):
              "integer" (mặc định):
                  1.045 → "...phẩy không trăm bốn mươi lăm"
                  9.5   → "...phẩy năm"
                  "9.50"→ "...phẩy năm mươi"
              "digit":
                  1.045 → "...phẩy không bốn năm"
                  9.5   → "...phẩy năm"
                  "9.50"→ "...phẩy năm không"

        decimal_digits:
            Số chữ số thập phân cần giữ (làm tròn nếu dài hơn).
            - Khi có currency: mặc định lấy từ bảng (thường 2);
              fraction="" → tự động 0 (làm tròn về nguyên).
            - Khi không có currency: mặc định None = giữ nguyên tất cả
              chữ số thập phân của đầu vào (kể cả trailing zeros từ chuỗi).
            - Truyền tường minh để ghi đè.

        decimal_separator:
            Từ nối phần nguyên và thập phân (mặc định "phẩy").

    Trả về:
        Chuỗi chữ, viết hoa chữ đầu.
        "Số không hợp lệ" nếu đầu vào không parse được.
    """
    num = _parse_number(amount)
    if num is None:
        return "Số không hợp lệ"

    negative = num < 0
    num = abs(num)

    # ── Xác định số chữ số thập phân ──────────────────────────────────────
    _map = {**_CURRENCY_MAP, **(currency_map or {})}

    if currency:
        cur_upper     = currency.upper()
        info          = _map.get(cur_upper, {"main": cur_upper, "fraction": "xu", "fraction_digits": 2})
        main_unit     = info.get("main", cur_upper)
        fraction_unit = info.get("fraction", "xu")
        if decimal_digits is not None:
            frac_digits = decimal_digits
        elif not fraction_unit:
            frac_digits = 0          # không có xu → làm tròn về nguyên
        else:
            frac_digits = info.get("fraction_digits", 2)
    else:
        main_unit = fraction_unit = ""
        frac_digits = decimal_digits   # None = tự động từ đầu vào

    # ── Làm tròn ──────────────────────────────────────────────────────────
    if frac_digits is not None:
        quant   = Decimal(10) ** -frac_digits
        rounded = num.quantize(quant, rounding=ROUND_HALF_UP)
    else:
        rounded = num   # giữ nguyên độ chính xác của Decimal đã parse

    int_part = int(rounded)
    frac_val = rounded - int_part

    # ── Chuỗi chữ số thập phân ────────────────────────────────────────────
    # Lấy đúng số chữ số thập phân từ Decimal (bảo toàn trailing zeros nếu có)
    dec_str = ""
    if frac_val > 0:
        if frac_digits is not None:
            # Biết chính xác cần bao nhiêu chữ số → lấy từ rounded
            raw     = str(frac_val)
            raw_dec = raw.split('.')[1] if '.' in raw else ""
            dec_str = raw_dec.ljust(frac_digits, '0')[:frac_digits]
        else:
            # Tự động: lấy từ chuỗi Decimal, GIỮ trailing zeros
            raw     = str(frac_val)
            dec_str = raw.split('.')[1] if '.' in raw else ""
            # Không rstrip — trailing zeros có ý nghĩa (ví dụ "9.50" → "năm mươi")

    # Bỏ dec_str nếu toàn 0 (có thể xảy ra sau khi làm tròn)
    if dec_str and int(dec_str) == 0:
        dec_str = ""

    # ── Đọc phần nguyên ───────────────────────────────────────────────────
    int_words = _read_integer(int_part)

    # ── Đọc phần thập phân ───────────────────────────────────────────────
    dec_words = ""
    if dec_str:
        if currency:
            # Tiền tệ: đọc phần lẻ như số nguyên (không có leading zero)
            # Ví dụ: "05" → 5 → "năm cent" (không phải "không năm cent")
            dec_words = _read_integer(int(dec_str))
        elif decimal_mode == "digit":
            dec_words = _read_decimal_as_digits(dec_str)
        else:
            dec_words = _read_decimal_as_integer(dec_str)

    # ── Ghép kết quả ─────────────────────────────────────────────────────
    if currency:
        tokens = [int_words, main_unit]
        if dec_words and fraction_unit:
            tokens += [dec_words, fraction_unit]
        result = " ".join(t for t in tokens if t)
    else:
        result = f"{int_words} {decimal_separator} {dec_words}" if dec_words else int_words

    if negative:
        result = "âm " + result

    return _cap_first(result)