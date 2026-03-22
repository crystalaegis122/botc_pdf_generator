import io, json, hashlib, logging
from pathlib import Path
from typing import List, Tuple, Dict, Any
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
TITLE_TOP_OFFSET_MM = 4.0  # Отступ заголовка от верхнего края страницы

JSON_PATH = BASE_DIR / "script.json"  # Путь к файлу с данными ролей
FONT_FILE = BASE_DIR / "fonts" / "Dumbledor3Thin.ttf"  # Путь к основному шрифту
FONT_FAMILY_DEFAULT = FONT_FILE.stem
CACHE_DIR = BASE_DIR / "cache_images"  # Папка для кэширования скачанных картинок

PAGE_W_PT, PAGE_H_PT = A4
MARGIN_MM = 1.0  # Отступ от краёв страницы в миллиметрах
GUTTER_MM = 0.0  # Расстояние между колонками
COLS = 2  # Количество колонок
IMAGE_MM = 22.0  # Базовый размер картинки роли в миллиметрах
IMAGE_SCALE = 0.640625  # Масштаб картинки роли (итоговый размер = IMAGE_MM * IMAGE_SCALE)
JINX_IMAGE_SCALE_SMALL = 0.375  # Масштаб мини-картинок сглазов (рядом с названием роли)
ROLE_PT = 13.25  # Размер шрифта названия роли
ABILITY_PT = 12.25  # Размер шрифта описания способности
LINE_SPACING = 1.06  # Межстрочный интервал (множитель)
GROUP_SPACING = 0 * mm  # Дополнительный отступ между группами ролей

GROUP_ORDER = ["townsfolk", "outsider", "minion", "demon"]  # Порядок вывода групп ролей
GROUP_LABELS = {  # Названия групп на русском
    "townsfolk": "Горожане",
    "outsider": "Изгои",
    "minion": "Приспешники",
    "demon": "Демоны",
}
GROUP_HEADER_COLOR = {  # Цвета заголовков групп
    "townsfolk": "blue",
    "outsider": "blue",
    "minion": "red",
    "demon": "red",
}

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


def fetch_image(url: str) -> Any:
    if not url:
        return None
    fname = cache_filename(url)
    if fname.exists():
        try:
            return Image.open(fname)
        except:
            fname.unlink()
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        img.save(fname, format="PNG")
        return img
    except:
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

def segments_from_ability(ability: Any) -> List[Dict[str, Any]]:
    if isinstance(ability, str):
        return [{"text": ability, "bold": False, "italic": False, "color": None}]
    if isinstance(ability, list):
        segs = []
        for s in ability:
            if isinstance(s, dict):
                segs.append({
                    "text": s.get("text", ""),
                    "bold": bool(s.get("bold", False)),
                    "italic": bool(s.get("italic", False)),
                    "color": s.get("color")
                })
            else:
                segs.append({"text": str(s), "bold": False, "italic": False, "color": None})
        return segs
    if isinstance(ability, dict):
        txt = ability.get("text", "")
        fmt = ability.get("format", []) or []
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
    return [{"text": str(ability), "bold": False, "italic": False, "color": None}]

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

with open(JSON_PATH, encoding="utf-8") as f:
    roles = json.load(f)

meta = next((r for r in roles if r.get("id") == "_meta"), None)
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
OUTPUT_PDF = BASE_DIR / f"{safe_title}_roles.pdf"

for r in roles:
    r["image_obj"] = fetch_image(r.get("image"))

role_by_name = {r["name"]: r for r in roles}
for r in roles:
    r["jinx_images"] = []
    jinxes = r.get("jinxes", {})
    for target_name in jinxes.keys():
        if target_name in role_by_name:
            target_role = role_by_name[target_name]
            target_img = target_role.get("image_obj")
            if target_img:
                r["jinx_images"].append(target_img)

c = canvas.Canvas(str(OUTPUT_PDF), pagesize=A4)

margin = MARGIN_MM * mm
gutter = GUTTER_MM * mm
col_width = (PAGE_W_PT - 2 * margin - gutter) / 2
image_pt = IMAGE_MM * mm * IMAGE_SCALE
jinx_image_pt_small = IMAGE_MM * mm * JINX_IMAGE_SCALE_SMALL

title_y = PAGE_H_PT - margin - TITLE_TOP_OFFSET_MM * mm
c.setFont(FONT_FAMILY, FILE_TITLE_PT)
c.drawCentredString(PAGE_W_PT / 2, title_y, FILE_TITLE)
c.setFillColor(black)

y_cursor = title_y - FILE_TITLE_PT - 4 * mm

for gkey in GROUP_ORDER:
    group_roles = [r for r in roles if r.get("team") == gkey]
    if not group_roles:
        continue

    header_text = GROUP_LABELS[gkey]
    try:
        c.setFillColor(toColor(GROUP_HEADER_COLOR[gkey]))
    except:
        c.setFillColor(black)
    c.setFont(FONT_FAMILY, ROLE_PT + 2)
    c.drawString(margin, y_cursor, header_text)
    c.setFillColor(black)
    y_cursor -= (ROLE_PT + 2) * LINE_SPACING + 2

    x_cols = [margin, margin + col_width + gutter]
    y_tops = [y_cursor] * 2

    for idx, role in enumerate(group_roles):
        col = idx % 2
        x = x_cols[col]
        y_top_role = y_tops[col]

        name_lines = wrap_text_simple(role.get("name", ""), FONT_FAMILY, ROLE_PT, col_width - image_pt - 2 * mm)
        segments = segments_from_ability(role.get("ability", ""))
        tokens = tokens_from_segments(segments)
        ability_lines = wrap_tokens_to_lines(tokens, FONT_FAMILY, ABILITY_PT, col_width - image_pt - 2 * mm)
        text_block_height = len(name_lines) * ROLE_PT * LINE_SPACING + len(
            ability_lines) * ABILITY_PT * LINE_SPACING + 2
        block_height = max(image_pt, text_block_height)

        img = role.get("image_obj")
        if img:
            try:
                pil = img.copy().convert("RGBA")
                w, h = pil.size
                sup_factor = 3
                target_px = (int(round(image_pt * sup_factor)), int(round(image_pt * sup_factor)))
                scale = min(target_px[0] / w, target_px[1] / h)
                new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
                resized = pil.resize(new_size, resample=Image.LANCZOS)
                bg = Image.new("RGB", target_px, (255, 255, 255))
                paste_x = (target_px[0] - new_size[0]) // 2
                paste_y = (target_px[1] - new_size[1]) // 2
                if resized.mode in ("RGBA", "LA"):
                    alpha = resized.split()[-1]
                    bg.paste(resized.convert("RGBA"), (paste_x, paste_y), mask=alpha)
                else:
                    bg.paste(resized.convert("RGB"), (paste_x, paste_y))
                bio = io.BytesIO()
                bg.save(bio, format="PNG")
                bio.seek(0)
                image_y = y_top_role - (block_height + image_pt) / 2
                c.drawImage(ImageReader(bio), x, image_y, width=image_pt, height=image_pt, mask='auto')
            except:
                pass

        text_x = x + image_pt + 2 * mm
        text_block_top = y_top_role - (block_height - text_block_height) / 2
        text_y = text_block_top - 2

        try:
            c.setFillColor(toColor(GROUP_HEADER_COLOR[gkey]))
        except:
            c.setFillColor(black)
        c.setFont(FONT_FAMILY, ROLE_PT)

        for nl in name_lines:
            c.drawString(text_x, text_y, nl)

            if nl == name_lines[-1] and role.get("jinx_images"):
                x_cursor = text_x + string_width(nl, FONT_FAMILY, ROLE_PT)
                for jinx_img in role["jinx_images"]:
                    try:
                        pil = jinx_img.copy().convert("RGBA")
                        w, h = pil.size
                        target_px = (int(round(jinx_image_pt_small * 3)), int(round(jinx_image_pt_small * 3)))
                        scale = min(target_px[0] / w, target_px[1] / h)
                        new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
                        resized = pil.resize(new_size, resample=Image.LANCZOS)
                        bg = Image.new("RGB", target_px, (255, 255, 255))
                        paste_x = (target_px[0] - new_size[0]) // 2
                        paste_y = (target_px[1] - new_size[1]) // 2
                        if resized.mode in ("RGBA", "LA"):
                            alpha = resized.split()[-1]
                            bg.paste(resized.convert("RGBA"), (paste_x, paste_y), mask=alpha)
                        else:
                            bg.paste(resized.convert("RGB"), (paste_x, paste_y))
                        bio = io.BytesIO()
                        bg.save(bio, format="PNG")
                        bio.seek(0)
                        image_y = text_y + (ROLE_PT - jinx_image_pt_small) / 2
                        c.drawImage(ImageReader(bio), x_cursor, image_y, width=jinx_image_pt_small,
                                    height=jinx_image_pt_small, mask='auto')
                        x_cursor += jinx_image_pt_small
                    except:
                        pass

            text_y -= ROLE_PT * LINE_SPACING

        c.setFillColor(black)
        c.setFont(FONT_FAMILY, ABILITY_PT)
        for line in ability_lines:
            x_cursor = text_x
            for token, seg in line:
                color = seg.get("color")
                if color:
                    try:
                        c.setFillColor(toColor(color))
                    except:
                        c.setFillColor(black)
                else:
                    c.setFillColor(black)
                is_bold = bool(seg.get("bold", False))
                if is_bold:
                    c.drawString(x_cursor, text_y, token)
                    c.drawString(x_cursor + 0.25, text_y, token)
                else:
                    c.drawString(x_cursor, text_y, token)
                x_cursor += string_width(token, FONT_FAMILY, ABILITY_PT)
            text_y -= ABILITY_PT * LINE_SPACING
        c.setFillColor(black)

        y_tops[col] = y_top_role - block_height - 3 * mm

    y_cursor = min(y_tops) - GROUP_SPACING

c.setFont(FONT_FAMILY, ABILITY_PT)
c.drawCentredString(PAGE_W_PT / 2, y_cursor, "*Не в первую ночь")

c.showPage()
c.save()
logging.info("Saved PDF to %s", OUTPUT_PDF)