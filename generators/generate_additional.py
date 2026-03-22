import io, json, hashlib, logging
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
import requests
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import black, toColor, green, gold, magenta
from reportlab.lib.utils import ImageReader

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent

FILE_TITLE = "placeholder"  # Запасной заголовок, используется если в JSON нет _meta с name
FILE_TITLE_PT = 36  # Размер шрифта заголовка внизу страницы
FILE_TITLE_FONT_PATH = BASE_DIR / "fonts" / "adanascript.ttf"  # Путь к шрифту для заголовка
TITLE_TOP_OFFSET_MM = 4.0  # Отступ от верхнего края для боковых колонок
TITLE_BOTTOM_OFFSET_MM = 10.0  # Отступ снизу перед выводом заголовка

SUBTITLE_PT = 24  # Размер шрифта подзаголовка "Летописцы и сказочники"
TITLE_GAP_MM = 2.5  # Вертикальный отступ между заголовком и подзаголовком

IMAGE_SCALE = 1  # Масштаб картинок сказочников/летописцев/странников
JINX_IMAGE_SCALE = 0.75  # Масштаб картинок в строках сглазов (где две картинки подряд)
JINX_LEFT_OFFSET_MM = 15.0  # Отступ слева для строк сглазов
IMAGE_MM = 22.0  # Базовый размер картинки в миллиметрах
SIDE_IMAGE_SCALE = 0.625  # Масштаб картинок в боковых колонках (I и II+)
ROMAN_PT = 36  # Размер шрифта для римских цифр I и II+

MARGIN_MM = 1.0  # Отступ от левого и правого края страницы
BOTTOM_MARGIN_MM = 1.0  # Минимальный отступ от нижнего края перед переносом страницы
ROW_GAP_MM = 3.0  # Вертикальный отступ между строками с ролями
GROUP_GAP_MM = 0.0  # Дополнительный отступ между группами ролей
TEXT_GAP_MM = 2.0  # Горизонтальный отступ между картинкой и текстом
ROMAN_GAP = 7.5  # Отступ после римской цифры до первой картинки (множитель LINE_SPACING)
LINE_SPACING = 1.06  # Межстрочный интервал (множитель)
ROLE_PT = 14  # Размер шрифта названия роли
ABILITY_PT = 13  # Размер шрифта описания способности
GROUP_HEADER_PT = 16  # Размер шрифта заголовков групп (Сказочники, Летописцы, Странники)

JINX_IMAGE_GAP_MM = 0.0  # Отступ между двумя картинками в строке сглаза

JSON_PATH = BASE_DIR / "script.json"  # Путь к файлу с данными ролей
FONT_FILE = BASE_DIR / "fonts" / "Dumbledor3Thin.ttf"  # Путь к основному шрифту
FONT_FAMILY_DEFAULT = FONT_FILE.stem
CACHE_DIR = BASE_DIR / "cache_images"  # Папка для кэширования скачанных картинок

DUSK_IMAGE_PATH = BASE_DIR / "assets" / "dusk.png"  # Путь к картинке "Закат" для боковых колонок
MINIONINFO_IMAGE_PATH = BASE_DIR / "assets" / "minioninfo.png"  # Путь к картинке "Приспешники" для боковых колонок
DEMONINFO_IMAGE_PATH = BASE_DIR / "assets" / "demoninfo.png"  # Путь к картинке "Демон" для боковых колонок
DAWN_IMAGE_PATH = BASE_DIR / "assets" / "dawn.png"  # Путь к картинке "Рассвет" для боковых колонок
DJINN_IMAGE_PATH = BASE_DIR / "assets" / "djinn.png"  # Путь к картинке Джинна

GAP_AFTER_DJINN_MM = 0.0  # Отступ после блока Джинна перед сглазами
GAP_BETWEEN_JINX_IMAGES_MM = 0.0  # Отступ между двумя картинками в строке сглаза
GAP_BETWEEN_JINX_ENTRIES_MM = 0.0  # Вертикальный отступ между разными сглазами

PAGE_W_PT, PAGE_H_PT = A4

if FONT_FILE.exists():
    try:
        pdfmetrics.registerFont(TTFont(FONT_FAMILY_DEFAULT, str(FONT_FILE)))
        FONT_FAMILY = FONT_FAMILY_DEFAULT
    except:
        FONT_FAMILY = "Helvetica"
else:
    FONT_FAMILY = "Helvetica"

if FILE_TITLE_FONT_PATH.exists():
    try:
        pdfmetrics.registerFont(TTFont("TitleFont", str(FILE_TITLE_FONT_PATH)))
        FILE_TITLE_FONT = "TitleFont"
    except:
        FILE_TITLE_FONT = FONT_FAMILY
else:
    FILE_TITLE_FONT = FONT_FAMILY

CACHE_DIR.mkdir(exist_ok=True)

def md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def cache_filename(url: str) -> Path:
    return CACHE_DIR / (md5_hex(url) + ".png")

def fetch_image(source: Any) -> Optional[Image.Image]:
    if not source:
        return None
    if isinstance(source, Path):
        try:
            return Image.open(source)
        except:
            return None
    if isinstance(source, str) and source.startswith(("http://", "https://")):
        fname = cache_filename(source)
        if fname.exists():
            try:
                return Image.open(fname)
            except:
                fname.unlink()
        try:
            resp = requests.get(source, timeout=10)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            img.save(fname, format="PNG")
            return img
        except:
            return None
    path = Path(source)
    if path.exists():
        try:
            return Image.open(path)
        except:
            return None
    return None

def string_width(text: str, fontname: str, fontsize: float) -> float:
    try:
        return pdfmetrics.stringWidth(text, fontname, fontsize)
    except:
        return pdfmetrics.stringWidth(text, "Helvetica", fontsize)

def wrap_text_simple(text: str, fontname: str, fontsize: float, max_width: float) -> List[str]:
    words = text.split(" ")
    lines = []
    cur = ""
    for w in words:
        t = (cur + " " + w).strip() if cur else w
        if string_width(t, fontname, fontsize) > max_width:
            if cur:
                lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines

def segments_from_text(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, str):
        return [{"text": value, "bold": False, "italic": False, "color": None}]
    if isinstance(value, list):
        segs = []
        for item in value:
            if isinstance(item, dict):
                segs.append({
                    "text": item.get("text", ""),
                    "bold": bool(item.get("bold", False)),
                    "italic": bool(item.get("italic", False)),
                    "color": item.get("color")
                })
            else:
                segs.append({"text": str(item), "bold": False, "italic": False, "color": None})
        return segs
    if isinstance(value, dict):
        txt = value.get("text", "")
        fmt = value.get("format", []) or []
        if not fmt:
            return [{"text": txt, "bold": False, "italic": False, "color": None}]
        segs = []
        idx = 0
        for f in sorted(fmt, key=lambda x: x.get("start", 0)):
            s = int(f.get("start", 0))
            e = int(f.get("end", 0))
            if s > idx:
                segs.append({"text": txt[idx:s], "bold": False, "italic": False, "color": None})
            segs.append({
                "text": txt[s:e],
                "bold": bool(f.get("bold", False)),
                "italic": bool(f.get("italic", False)),
                "color": f.get("color")
            })
            idx = e
        if idx < len(txt):
            segs.append({"text": txt[idx:], "bold": False, "italic": False, "color": None})
        return segs
    return [{"text": str(value), "bold": False, "italic": False, "color": None}]

def tokens_from_segments(segments: List[Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any]]]:
    tokens = []
    for seg in segments:
        parts = seg.get("text", "").split(" ")
        for i, p in enumerate(parts):
            if p != "":
                tokens.append((p, seg))
            if i != len(parts) - 1:
                tokens.append((" ", seg))
    return tokens

def wrap_tokens_to_lines(tokens, fontname, fontsize, max_width):
    lines = []
    cur_line = []
    cur_w = 0.0
    for token, seg in tokens:
        w = string_width(token, fontname, fontsize)
        if token == " ":
            if cur_line and cur_w + w <= max_width:
                cur_line.append((token, seg))
                cur_w += w
            continue
        if cur_line and cur_w + w > max_width:
            lines.append(cur_line)
            cur_line = [(token, seg)]
            cur_w = w
        else:
            cur_line.append((token, seg))
            cur_w += w
    if cur_line:
        lines.append(cur_line)
    return lines

def make_image_square(img: Image.Image, base_px: int) -> Optional[io.BytesIO]:
    if img is None:
        return None
    try:
        pil = img.copy().convert("RGBA")
        w, h = pil.size
        size = base_px
        max_dim = max(w, h)
        scale = size / max_dim
        new_size = (int(round(w * scale)), int(round(h * scale)))
        resized = pil.resize(new_size, resample=Image.LANCZOS)
        bg = Image.new("RGB", (size, size), (255, 255, 255))
        paste_x = (size - new_size[0]) // 2
        paste_y = (size - new_size[1]) // 2
        if resized.mode in ("RGBA", "LA"):
            alpha = resized.split()[-1]
            bg.paste(resized.convert("RGBA"), (paste_x, paste_y), mask=alpha)
        else:
            bg.paste(resized.convert("RGB"), (paste_x, paste_y))
        bio = io.BytesIO()
        bg.save(bio, format="PNG")
        bio.seek(0)
        return bio
    except:
        return None

def load_all_roles() -> List[Dict[str, Any]]:
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)

with open(JSON_PATH, encoding="utf-8") as f:
    all_roles_data = json.load(f)

meta = next((r for r in all_roles_data if r.get("id") == "_meta"), None)
if meta:
    meta_name = meta.get("name")
    if meta_name:
        FILE_TITLE = meta_name

safe_title = "".join(c for c in FILE_TITLE if c not in r'\/:*?"<>|')
OUTPUT_PDF = BASE_DIR / f"{safe_title}_additional.pdf"

all_roles = load_all_roles()
role_by_name = {r["name"]: r for r in all_roles}

for r in all_roles:
    r["image_obj"] = fetch_image(r.get("image"))

fabled_roles = [r for r in all_roles if r.get("team") == "fabled"]
loric_roles = [r for r in all_roles if r.get("team") == "loric"]
traveller_roles = [r for r in all_roles if r.get("team") == "traveller"]

has_jinxes = any(r.get("jinxes") for r in all_roles)

jinx_entries = []
for role in all_roles:
    jinxes = role.get("jinxes")
    if not jinxes or not isinstance(jinxes, dict):
        continue
    for target_name, jinx_text in jinxes.items():
        if target_name in role_by_name:
            target_role = role_by_name[target_name]
            jinx_entries.append((role, target_role, jinx_text))

def build_left_column_roles() -> List[Dict[str, Any]]:
    enriched = []
    for i, r in enumerate(all_roles):
        fn = r.get("firstNight")
        if fn and float(fn) != 0.0:
            enriched.append({
                "name": r["name"],
                "team": r.get("team"),
                "firstNight": float(fn),
                "image_obj": r["image_obj"],
                "order": i,
            })
    special_rows = [
        {"name": "Закат", "team": None, "firstNight": 0.0, "image_obj": fetch_image(DUSK_IMAGE_PATH), "order": -3},
        {"name": "Приспешники", "team": "minion", "firstNight": 6.0, "image_obj": fetch_image(MINIONINFO_IMAGE_PATH),
         "order": -2},
        {"name": "Демон", "team": "demon", "firstNight": 9.0, "image_obj": fetch_image(DEMONINFO_IMAGE_PATH),
         "order": -1},
        {"name": "Рассвет", "team": None, "firstNight": 53.0, "image_obj": fetch_image(DAWN_IMAGE_PATH),
         "order": 10 ** 9},
    ]
    enriched.extend(special_rows)
    enriched.sort(key=lambda r: (r["firstNight"], r["order"]))
    return enriched

def build_right_column_roles() -> List[Dict[str, Any]]:
    enriched = []
    for i, r in enumerate(all_roles):
        on = r.get("otherNight")
        if on and float(on) != 0.0:
            enriched.append({
                "name": r["name"],
                "team": r.get("team"),
                "otherNight": float(on),
                "image_obj": r["image_obj"],
                "order": i,
            })
    special_rows = [
        {"name": "Закат", "team": None, "otherNight": 0.0, "image_obj": fetch_image(DUSK_IMAGE_PATH), "order": -1},
        {"name": "Рассвет", "team": None, "otherNight": 72.0, "image_obj": fetch_image(DAWN_IMAGE_PATH),
         "order": 10 ** 9},
    ]
    enriched.extend(special_rows)
    enriched.sort(key=lambda r: (r["otherNight"], r["order"]))
    return enriched

left_roles = build_left_column_roles()
right_roles = build_right_column_roles()

def draw_role(c, x, y_top, role, image_pt, text_width, name_color=None):
    name_lines = wrap_text_simple(role.get("name", ""), FONT_FAMILY, ROLE_PT, text_width)
    ability_segments = segments_from_text(role.get("ability", ""))
    ability_tokens = tokens_from_segments(ability_segments)
    ability_lines = wrap_tokens_to_lines(ability_tokens, FONT_FAMILY, ABILITY_PT, text_width)

    text_block_height = len(name_lines) * ROLE_PT * LINE_SPACING + len(ability_lines) * ABILITY_PT * LINE_SPACING + 2
    block_height = max(image_pt, text_block_height)

    img = role.get("image_obj")
    if img:
        bio = make_image_square(img, int(round(image_pt * 3)))
        if bio:
            image_y = y_top - (block_height + image_pt) / 2
            c.drawImage(ImageReader(bio), x, image_y, width=image_pt, height=image_pt, mask='auto')

    text_x = x + image_pt + TEXT_GAP_MM * mm
    text_block_top = y_top - (block_height - text_block_height) / 2
    text_y = text_block_top - 2

    if name_color:
        try:
            c.setFillColor(toColor(name_color))
        except:
            c.setFillColor(black)
    else:
        c.setFillColor(black)
    c.setFont(FONT_FAMILY, ROLE_PT)
    for nl in name_lines:
        c.drawString(text_x, text_y, nl)
        text_y -= ROLE_PT * LINE_SPACING

    c.setFillColor(black)
    c.setFont(FONT_FAMILY, ABILITY_PT)
    for line in ability_lines:
        x_cursor = text_x
        for token, seg in line:
            color = seg.get("color")
            c.setFillColor(toColor(color) if color else black)
            if seg.get("bold", False):
                c.drawString(x_cursor, text_y, token)
                c.drawString(x_cursor + 0.25, text_y, token)
            else:
                c.drawString(x_cursor, text_y, token)
            x_cursor += string_width(token, FONT_FAMILY, ABILITY_PT)
        text_y -= ABILITY_PT * LINE_SPACING
    c.setFillColor(black)

    return y_top - block_height - ROW_GAP_MM * mm

def draw_group_header(c, x, y, text, color):
    c.setFillColor(toColor(color))
    c.setFont(FONT_FAMILY, GROUP_HEADER_PT)
    c.drawString(x, y, text)
    c.setFillColor(black)
    return y - GROUP_HEADER_PT * LINE_SPACING - 2

def draw_side_column(c, x, y_start, title, roles_list, image_pt):
    y = y_start - 8 * mm
    c.setFont(FONT_FAMILY, ROMAN_PT)
    c.drawCentredString(x + image_pt / 2, y, title)
    y -= ROMAN_GAP * LINE_SPACING

    for role in roles_list:
        img = role.get("image_obj")
        if img:
            bio = make_image_square(img, int(round(image_pt * 3)))
            if bio:
                image_y = y - image_pt
                c.drawImage(ImageReader(bio), x, image_y, width=image_pt, height=image_pt, mask='auto')
        y -= image_pt + ROW_GAP_MM * mm
    return y

c = canvas.Canvas(str(OUTPUT_PDF), pagesize=A4)

margin = MARGIN_MM * mm
bottom_margin = BOTTOM_MARGIN_MM * mm

side_image_pt = IMAGE_MM * mm * SIDE_IMAGE_SCALE
left_col_width = side_image_pt + 2 * mm
right_col_width = side_image_pt + 2 * mm
center_col_width = PAGE_W_PT - 2 * margin - left_col_width - right_col_width

left_col_x = margin
center_col_x = margin + left_col_width
right_col_x = margin + left_col_width + center_col_width

top_y = PAGE_H_PT - margin - TITLE_TOP_OFFSET_MM * mm

draw_side_column(c, left_col_x, top_y, "I", left_roles, side_image_pt)
draw_side_column(c, right_col_x, top_y, "II+", right_roles, side_image_pt)

y_cursor = top_y - FILE_TITLE_PT - TITLE_GAP_MM * mm

if fabled_roles or has_jinxes:
    y_cursor = draw_group_header(c, center_col_x, y_cursor, "Сказочники", "gold")

center_image_pt = IMAGE_MM * mm * IMAGE_SCALE
jinx_image_pt = IMAGE_MM * mm * JINX_IMAGE_SCALE
text_width = center_col_width - center_image_pt - TEXT_GAP_MM * mm

if has_jinxes:
    djinn_img = fetch_image(DJINN_IMAGE_PATH)

    djinn_desc_segments = [
        {"text": "В игре присутствует особое правило "},
        {"text": "Джинна", "color": "gold"},
        {"text": ". Оно известно всем игрокам."}
    ]
    djinn_desc_tokens = tokens_from_segments(djinn_desc_segments)

    djinn_name = "Джинн"
    djinn_name_width = string_width(djinn_name, FONT_FAMILY, ROLE_PT)
    djinn_desc_lines = wrap_tokens_to_lines(djinn_desc_tokens, FONT_FAMILY, ABILITY_PT, text_width)

    text_block_height = ROLE_PT * LINE_SPACING + len(djinn_desc_lines) * ABILITY_PT * LINE_SPACING + 2
    block_height = max(center_image_pt, text_block_height)

    image_y = y_cursor - (block_height + center_image_pt) / 2
    if djinn_img:
        bio = make_image_square(djinn_img, int(round(center_image_pt * 3)))
        if bio:
            c.drawImage(ImageReader(bio), center_col_x, image_y, width=center_image_pt, height=center_image_pt,
                        mask='auto')

    text_x = center_col_x + center_image_pt + TEXT_GAP_MM * mm
    text_block_top = y_cursor - (block_height - text_block_height) / 2
    text_y = text_block_top - 2

    c.setFillColor(gold)
    c.setFont(FONT_FAMILY, ROLE_PT)
    c.drawString(text_x, text_y, djinn_name)
    text_y -= ROLE_PT * LINE_SPACING

    c.setFillColor(black)
    c.setFont(FONT_FAMILY, ABILITY_PT)
    for line in djinn_desc_lines:
        x_cursor = text_x
        for token, seg in line:
            color = seg.get("color")
            c.setFillColor(toColor(color) if color else black)
            if seg.get("bold", False):
                c.drawString(x_cursor, text_y, token)
                c.drawString(x_cursor + 0.25, text_y, token)
            else:
                c.drawString(x_cursor, text_y, token)
            x_cursor += string_width(token, FONT_FAMILY, ABILITY_PT)
        text_y -= ABILITY_PT * LINE_SPACING
    c.setFillColor(black)

    y_cursor -= block_height + GAP_AFTER_DJINN_MM * mm

    jinx_offset_x = center_col_x + JINX_LEFT_OFFSET_MM * mm
    jinx_text_width = center_col_width - (jinx_offset_x - center_col_x) - 2 * jinx_image_pt - 2 * TEXT_GAP_MM * mm

    for role, target, jinx_text in jinx_entries:
        img1 = role.get("image_obj")
        img2 = target.get("image_obj")
        if not img1 or not img2:
            continue

        segments = segments_from_text(jinx_text)
        tokens = tokens_from_segments(segments)
        lines = wrap_tokens_to_lines(tokens, FONT_FAMILY, ABILITY_PT, jinx_text_width)

        text_block_height = len(lines) * ABILITY_PT * LINE_SPACING + 2
        block_height = max(jinx_image_pt, text_block_height)

        image_y = y_cursor - (block_height + jinx_image_pt) / 2

        bio1 = make_image_square(img1, int(round(jinx_image_pt * 3)))
        if bio1:
            c.drawImage(ImageReader(bio1), jinx_offset_x, image_y, width=jinx_image_pt, height=jinx_image_pt,
                        mask='auto')

        bio2 = make_image_square(img2, int(round(jinx_image_pt * 3)))
        if bio2:
            c.drawImage(ImageReader(bio2), jinx_offset_x + jinx_image_pt + GAP_BETWEEN_JINX_IMAGES_MM * mm, image_y,
                        width=jinx_image_pt, height=jinx_image_pt, mask='auto')

        text_x = jinx_offset_x + 2 * jinx_image_pt + 2 * TEXT_GAP_MM * mm
        text_block_top = y_cursor - (block_height - text_block_height) / 2
        text_y = text_block_top - 2

        c.setFont(FONT_FAMILY, ABILITY_PT)
        for line in lines:
            x_cursor = text_x
            for token, seg in line:
                color = seg.get("color")
                c.setFillColor(toColor(color) if color else black)
                if seg.get("bold", False):
                    c.drawString(x_cursor, text_y, token)
                    c.drawString(x_cursor + 0.25, text_y, token)
                else:
                    c.drawString(x_cursor, text_y, token)
                x_cursor += string_width(token, FONT_FAMILY, ABILITY_PT)
            text_y -= ABILITY_PT * LINE_SPACING
        c.setFillColor(black)

        y_cursor -= block_height + GAP_BETWEEN_JINX_ENTRIES_MM * mm

for role in fabled_roles:
    if role.get("name") == "Джинн":
        continue
    y_cursor = draw_role(c, center_col_x, y_cursor, role, center_image_pt, text_width, "gold")
    if y_cursor < bottom_margin:
        c.showPage()
        y_cursor = top_y - FILE_TITLE_PT - TITLE_GAP_MM * mm
        y_cursor = draw_group_header(c, center_col_x, y_cursor, "Сказочники", "gold")

if loric_roles:
    y_cursor -= GROUP_GAP_MM * mm
    y_cursor = draw_group_header(c, center_col_x, y_cursor, "Летописцы", "green")
    for role in loric_roles:
        y_cursor = draw_role(c, center_col_x, y_cursor, role, center_image_pt, text_width, "green")
        if y_cursor < bottom_margin:
            c.showPage()
            y_cursor = top_y - FILE_TITLE_PT - TITLE_GAP_MM * mm
            y_cursor = draw_group_header(c, center_col_x, y_cursor, "Летописцы", "green")

if traveller_roles:
    y_cursor -= GROUP_GAP_MM * mm
    y_cursor = draw_group_header(c, center_col_x, y_cursor, "Рекомендуемые странники", "magenta")
    for role in traveller_roles:
        y_cursor = draw_role(c, center_col_x, y_cursor, role, center_image_pt, text_width, "magenta")
        if y_cursor < bottom_margin:
            c.showPage()
            y_cursor = top_y - FILE_TITLE_PT - TITLE_GAP_MM * mm
            y_cursor = draw_group_header(c, center_col_x, y_cursor, "Рекомендуемые странники", "magenta")

title_lines = FILE_TITLE.split(" ")
title_height = len(title_lines) * FILE_TITLE_PT * LINE_SPACING
y_cursor -= title_height + TITLE_BOTTOM_OFFSET_MM * mm

c.setFont(FILE_TITLE_FONT, FILE_TITLE_PT)
c.setFillColor(black)
for i, line in enumerate(title_lines):
    line_width = string_width(line, FILE_TITLE_FONT, FILE_TITLE_PT)
    x_center = center_col_x + (center_col_width - line_width) / 2
    y_pos = y_cursor + (len(title_lines) - 1 - i) * FILE_TITLE_PT * LINE_SPACING
    c.drawString(x_center, y_pos, line)

c.showPage()
c.save()
logging.info("Saved PDF to %s", OUTPUT_PDF)