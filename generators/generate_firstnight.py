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
from reportlab.lib.colors import black, toColor
from reportlab.lib.utils import ImageReader

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent

FILE_TITLE = "placeholder"  # Запасной заголовок, используется если в JSON нет _meta с name
FILE_TITLE_PT = 12.25  # Размер шрифта заголовка
SUBTITLE_TEXT = "Первая ночь"  # Текст подзаголовка
SUBTITLE_PT = 14.25  # Размер шрифта подзаголовка
TITLE_TOP_OFFSET_MM = 4.0  # Отступ заголовка от верхнего края страницы

URL_IMAGE_SCALE = 0.625  # Масштаб картинок из интернета
ASSET_IMAGE_SCALE = 0.625  # Масштаб картинок из папки assets (Закат, Приспешники, Демон, Рассвет)
JSON_PATH = BASE_DIR / "script.json"  # Путь к файлу с данными ролей
FONT_FILE = BASE_DIR / "fonts" / "Dumbledor3Thin.ttf"  # Путь к основному шрифту
FONT_FAMILY_DEFAULT = FONT_FILE.stem
CACHE_DIR = BASE_DIR / "cache_images"  # Папка для кэширования скачанных картинок

DUSK_IMAGE_PATH = BASE_DIR / "assets" / "dusk.png"  # Путь к картинке "Закат"
MINIONINFO_IMAGE_PATH = BASE_DIR / "assets" / "minioninfo.png"  # Путь к картинке "Приспешники"
DEMONINFO_IMAGE_PATH = BASE_DIR / "assets" / "demoninfo.png"  # Путь к картинке "Демон"
DAWN_IMAGE_PATH = BASE_DIR / "assets" / "dawn.png"  # Путь к картинке "Рассвет"

PAGE_W_PT, PAGE_H_PT = A4
MARGIN_MM = 1.0  # Отступ от левого и правого края страницы
BOTTOM_MARGIN_MM = 1.0  # Минимальный отступ от нижнего края перед переносом страницы
ROW_GAP_MM = 3.0  # Вертикальный отступ между строками с ролями
TEXT_GAP_MM = 2.0  # Горизонтальный отступ между картинкой и текстом
IMAGE_MM = 22.0  # Базовый размер картинки роли в миллиметрах
ROLE_PT = 13.25  # Размер шрифта названия роли
ABILITY_PT = 12.25  # Размер шрифта описания способности
LINE_SPACING = 1.06  # Межстрочный интервал (множитель)
TITLE_GAP_MM = 2.5  # Вертикальный отступ между заголовком и подзаголовком

if FONT_FILE.exists():
    try:
        pdfmetrics.registerFont(TTFont(FONT_FAMILY_DEFAULT, str(FONT_FILE)))
        FONT_FAMILY = FONT_FAMILY_DEFAULT
    except:
        FONT_FAMILY = "Helvetica"
else:
    FONT_FAMILY = "Helvetica"

CACHE_DIR.mkdir(exist_ok=True)

def md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def cache_filename(url: str) -> Path:
    return CACHE_DIR / (md5_hex(url) + ".png")

def crop_transparent(img: Image.Image, pad: int = 2) -> Image.Image:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    if bbox:
        x0, y0, x1, y1 = bbox
        x0 = max(0, x0 - pad)
        y0 = max(0, y0 - pad)
        x1 = min(img.width, x1 + pad)
        y1 = min(img.height, y1 + pad)
        return img.crop((x0, y0, x1, y1))
    return img

def fetch_image(source: Any) -> Any:
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

def load_roles() -> List[Dict[str, Any]]:
    with open(JSON_PATH, encoding="utf-8") as f:
        roles = json.load(f)

    enriched = []
    for i, r in enumerate(roles):
        fn = r.get("firstNight")
        if not fn or float(fn) == 0.0:
            continue
        enriched.append({
            "name": r.get("name", ""),
            "team": r.get("team"),
            "firstNight": float(fn),
            "firstNightReminder": r.get("firstNightReminder", ""),
            "image": r.get("image"),
            "order": i,
        })

    special_rows = [
        {"name": "Закат", "team": None, "firstNight": 0.0, "firstNightReminder": "Город засыпает.",
         "image": DUSK_IMAGE_PATH, "order": -3},
        {"name": "Приспешники", "team": "minion", "firstNight": 6.0,
         "firstNightReminder": [{"text": "Пробудите всех "}, {"text": "Приспешников", "color": "red"},
                                {"text": ". Дайте им установить зрительный контакт, затем укажите им на "},
                                {"text": "Демона", "color": "red"}, {"text": ". Усыпите "},
                                {"text": "Приспешников", "color": "red"}, {"text": "."}],
         "image": MINIONINFO_IMAGE_PATH, "order": -2},
        {"name": "Демон", "team": "demon", "firstNight": 9.0,
         "firstNightReminder": [{"text": "Пробудите "}, {"text": "Демона", "color": "red"},
                                {"text": ", по очереди укажите на всех "}, {"text": "Приспешников", "color": "red"},
                                {"text": ", после чего покажите ему жетоны трёх "}, {"text": "добрых", "color": "blue"},
                                {"text": " ролей, не участвующих в игре. Усыпите "}, {"text": "Демона", "color": "red"},
                                {"text": "."}],
         "image": DEMONINFO_IMAGE_PATH, "order": -1},
        {"name": "Рассвет", "team": None, "firstNight": 53.0, "firstNightReminder": "Город просыпается.",
         "image": DAWN_IMAGE_PATH, "order": 10 ** 9},
    ]
    enriched.extend(special_rows)
    enriched.sort(key=lambda r: (r["firstNight"], r["order"]))
    return enriched

def make_image_square(img: Image.Image, base_px: int) -> Optional[io.BytesIO]:
    if img is None:
        return None
    try:
        pil = crop_transparent(img.copy())
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

def team_color(team: Any) -> str:
    if team in ("townsfolk", "outsider"): return "blue"
    if team in ("minion", "demon"): return "red"
    return "black"

def start_page(c, title_text):
    margin = MARGIN_MM * mm
    title_y = PAGE_H_PT - margin - TITLE_TOP_OFFSET_MM * mm
    c.setFillColor(black)
    c.setFont(FONT_FAMILY, FILE_TITLE_PT)
    c.drawCentredString(PAGE_W_PT / 2, title_y, title_text)
    c.setFont(FONT_FAMILY, SUBTITLE_PT)
    c.drawCentredString(PAGE_W_PT / 2, title_y - FILE_TITLE_PT - TITLE_GAP_MM * mm, SUBTITLE_TEXT)
    return title_y - FILE_TITLE_PT - TITLE_GAP_MM * mm - SUBTITLE_PT - 4 * mm

with open(JSON_PATH, encoding="utf-8") as f:
    all_roles_data = json.load(f)

meta = next((r for r in all_roles_data if r.get("id") == "_meta"), None)
if meta:
    meta_name = meta.get("name")
    meta_author = meta.get("author")
    if meta_name and meta_author:
        FILE_TITLE = f"{meta_name} by {meta_author}"
    elif meta_name:
        FILE_TITLE = meta_name
    elif meta_author:
        FILE_TITLE = f"{FILE_TITLE} by {meta_author}"

safe_title = "".join(c for c in FILE_TITLE if c not in r'\/:*?"<>|')
OUTPUT_PDF = BASE_DIR / f"{safe_title}_firstnight.pdf"

roles = load_roles()
for r in roles:
    r["image_obj"] = fetch_image(r.get("image"))

c = canvas.Canvas(str(OUTPUT_PDF), pagesize=A4)
margin = MARGIN_MM * mm
bottom_margin = BOTTOM_MARGIN_MM * mm
y_cursor = start_page(c, FILE_TITLE)
content_width = PAGE_W_PT - 2 * margin
text_width = content_width - IMAGE_MM * mm - TEXT_GAP_MM * mm

BASE_PX = 591
url_image_pt = IMAGE_MM * mm * URL_IMAGE_SCALE
asset_image_pt = IMAGE_MM * mm * ASSET_IMAGE_SCALE

for role in roles:
    name_lines = wrap_text_simple(role.get("name", ""), FONT_FAMILY, ROLE_PT, text_width)
    reminder_segments = segments_from_text(role.get("firstNightReminder", ""))
    reminder_tokens = tokens_from_segments(reminder_segments)
    reminder_lines = wrap_tokens_to_lines(reminder_tokens, FONT_FAMILY, ABILITY_PT, text_width)

    if role.get("image") in [str(DUSK_IMAGE_PATH), str(MINIONINFO_IMAGE_PATH), str(DEMONINFO_IMAGE_PATH),
                             str(DAWN_IMAGE_PATH)]:
        current_image_pt = asset_image_pt
    else:
        current_image_pt = url_image_pt

    text_block_height = len(name_lines) * ROLE_PT * LINE_SPACING + len(reminder_lines) * ABILITY_PT * LINE_SPACING + 2
    block_height = max(current_image_pt, text_block_height)

    if y_cursor - block_height < bottom_margin:
        c.showPage()
        y_cursor = start_page(c, FILE_TITLE)

    x = margin
    y_top = y_cursor
    img = role.get("image_obj")
    if img:
        bio = make_image_square(img, BASE_PX)
        if bio:
            image_y = y_top - (block_height + current_image_pt) / 2
            c.drawImage(ImageReader(bio), x, image_y, width=current_image_pt, height=current_image_pt, mask='auto')

    text_x = x + current_image_pt + TEXT_GAP_MM * mm
    text_block_top = y_top - (block_height - text_block_height) / 2
    text_y = text_block_top - 2

    name_color = team_color(role.get("team"))
    try:
        c.setFillColor(toColor(name_color))
    except:
        c.setFillColor(black)
    c.setFont(FONT_FAMILY, ROLE_PT)
    for nl in name_lines:
        c.drawString(text_x, text_y, nl)
        text_y -= ROLE_PT * LINE_SPACING

    c.setFillColor(black)
    c.setFont(FONT_FAMILY, ABILITY_PT)
    for line in reminder_lines:
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
    y_cursor = y_top - block_height - ROW_GAP_MM * mm

c.showPage()
c.save()
logging.info("Saved PDF to %s", OUTPUT_PDF)