import os
import json
import string
import re
import io
import base64
import glob
import uuid
import datetime
from flask import Flask, render_template, request, send_file, redirect, url_for, session, flash, jsonify
from PIL import Image, ImageDraw, ImageFont, ExifTags
from werkzeug.utils import secure_filename

try:
    import google.generativeai as genai
    genai.configure(api_key="<DEIN_GEMINI_API_KEY>")  # <-- Platzhalter
    GEMINI_AVAILABLE = False  # Feature-Flag deaktiviert
except ImportError:
    GEMINI_AVAILABLE = False

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Für Session, ggf. anpassen
ADMIN_PASSWORD = 'Instagram2025'
LAYOUTS_FILE = 'layouts.json'
LOGO_FOLDER = 'static/logos/'
FONTS_FOLDER = os.path.join(os.path.dirname(__file__), 'fonts')
SHOW_CAPTION_FEATURE = True

# Layout-Konfiguration (wie im Bot)
LAYOUTS = {
    "JUNGSF4KTEN": {
        "watermark_text": "JUNGSF4KTEN",
        "text_color": (255, 114, 189),
        "logo_file": "static/logos/JUNGSF4KTEN.png",
        "watermark_color": (0, 120, 255),
    },
    "MADCHENF4KTEN": {
        "watermark_text": "MADCHENF4KTEN",
        "text_color": (255, 114, 189),
        "logo_file": "static/logos/MADCHENF4KTEN.png",
        "watermark_color": (255, 50, 50),
    },
    "LIEBESAKTFAKTEN": {
        "watermark_text": "LIEBESAKTFAKTEN",
        "text_color": (255, 114, 189),
        "logo_file": "static/logos/LIEBESAKTFAKTEN.png",
        "watermark_color": (147, 0, 211),
    },
    "BINBETRUNKEN": {
        "watermark_text": "BINBETRUNKEN",
        "text_color": (255, 114, 189),
        "logo_file": "static/logos/BINBETRUNKEN.png",
        "watermark_color": (255, 50, 50),
    },
    "GESCHLECHTS.FAKTEN": {
        "watermark_text": "GESCHLECHTS.FAKTEN",
        "text_color": (255, 114, 189),
        "logo_file": "static/logos/GESCHLECHTS.FAKTEN.png",
        "watermark_color": (0, 120, 255),
    },
    "DOKTORSPIELFAKTEN": {
        "watermark_text": "DOKTORSPIELFAKTEN",
        "text_color": (255, 114, 189),
        "logo_file": "static/logos/DOKTORSPIELFAKTEN.png",
        "watermark_color": (255, 105, 180),
    },
}

# Hilfsfunktionen für Layouts

def load_layouts():
    with open(LAYOUTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_layouts(layouts):
    with open(LAYOUTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(layouts, f, indent=2, ensure_ascii=False)

def hex_to_rgb(hexcolor):
    hexcolor = hexcolor.lstrip('#')
    return tuple(int(hexcolor[i:i+2], 16) for i in (0, 2, 4))

def clean_text(text):
    text = text.replace('\r', '')
    allowed = set(string.printable + 'äöüÄÖÜß€–—""\'\'…')
    return ''.join(c for c in text if c in allowed or c == '\n')

pattern_color = re.compile(r'<(.*?)>')
def parse_colored_segments(text, color):
    result = []
    last = 0
    for match in pattern_color.finditer(text):
        if match.start() > last:
            result.append((text[last:match.start()], (255,255,255)))
        result.append((match.group(1), color))
        last = match.end()
    if last < len(text):
        result.append((text[last:], (255,255,255)))
    return result

def get_available_fonts():
    fonts = []
    for ext in ('*.ttf', '*.otf'):
        fonts.extend([os.path.basename(f) for f in glob.glob(os.path.join(FONTS_FOLDER, ext))])
    return sorted(fonts)

def fix_image_orientation(img):
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                break
        exif = img._getexif()
        if exif is not None:
            orientation = exif.get(orientation, None)
            if orientation == 3:
                img = img.rotate(180, expand=True)
            elif orientation == 6:
                img = img.rotate(270, expand=True)
            elif orientation == 8:
                img = img.rotate(90, expand=True)
    except Exception:
        pass
    return img

def crop_center_square(img):
    side = min(img.width, img.height)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    right = left + side
    bottom = top + side
    return img.crop((left, top, right, bottom))

def create_image_with_text_and_watermark(background_path, text, layout_key):
    layouts = load_layouts()
    layout = layouts[layout_key]
    font_path = os.path.join(FONTS_FOLDER, layout.get('font', 'GeezaPro-Bold.ttf'))
    letter_spacing = int(layout.get('letter_spacing', -2))
    line_spacing = int(layout.get('line_spacing', -11))
    watermark = {
        "text": layout["watermark_text"],
        "color": hex_to_rgb(layout["watermark_color"])
    }
    text_color = hex_to_rgb(layout["text_color"])
    opacity = float(layout.get("opacity", 0.6))
    opacity = max(0.0, min(opacity, 1.0))
    shadow_color = layout.get('shadow_color', '#000000')
    shadow_opacity = int(layout.get('shadow_opacity', 180))
    shadow_offset_x = int(layout.get('shadow_offset_x', 3))
    shadow_offset_y = int(layout.get('shadow_offset_y', 3))
    watermark_margin_bottom = int(layout.get('watermark_margin_bottom', 40))
    img = Image.open(background_path)
    img = fix_image_orientation(img)
    img = crop_center_square(img)
    img = img.resize((1080, 1080), Image.LANCZOS)
    img = img.convert("RGB")
    width, height = img.size
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, int(255 * opacity)))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)
    margin = int(min(width, height) * 0.1)
    max_text_width = width - 2 * margin
    logo_path = layout["logo_file"]
    logo_height = 0
    if os.path.exists(logo_path):
        logo_size = (120, 120)
        logo = Image.open(logo_path).convert("RGBA").resize(logo_size, Image.LANCZOS)
        img.paste(logo, (30, 30), logo)
        logo_height = logo_size[1]
    watermark_font_path = os.path.join(FONTS_FOLDER, layout.get('watermark_font', 'GeezaPro-Bold.ttf'))
    watermark_font_size = int(width * float(layout.get('watermark_font_size_percent', 4.5)) / 100)
    try:
        watermark_font = ImageFont.truetype(watermark_font_path, watermark_font_size)
    except IOError:
        try:
            watermark_font = ImageFont.truetype("Arial.ttf", watermark_font_size)
        except IOError:
            watermark_font = ImageFont.load_default()
    watermark_font_color = hex_to_rgb(layout.get('watermark_font_color', '#ffffff'))
    watermark_bbox = draw.textbbox((0, 0), watermark['text'], font=watermark_font)
    watermark_height = watermark_bbox[3] - watermark_bbox[1]
    padding_y = int(watermark_height * 0.5)
    bar_height = int(watermark_height + 2 * padding_y)
    reserved_bottom = bar_height + margin // 2
    reserved_top = max(logo_height + 30, 150)
    max_text_height = height - reserved_top - reserved_bottom - margin
    paragraph_texts = re.split(r'\n\s*\n', text)
    lines_per_paragraph = [p.split('\n') for p in paragraph_texts]
    colored_paragraphs = [
        [parse_colored_segments(line, text_color) for line in paragraph_lines]
        for paragraph_lines in lines_per_paragraph
    ]
    font_size_min = 10
    # Flexible maximale Schriftgröße: Prozent oder Pixel
    if layout.get('max_font_size_mode', 'percent') == 'pixel':
        font_size_max = int(layout.get('max_font_size_value', 162))  # Default: 162px
    else:
        font_size_max = int(width * float(layout.get('max_font_size_value', 15.0)) / 100)
    # Optional: Absolute Obergrenze (z.B. nie größer als 15% der Breite)
    # font_size_max = min(font_size_max, int(width * 0.15))
    font_size_max = min(font_size_max, int(width * 0.15))
    optimal_font = None
    optimal_lines = None
    optimal_line_height = None
    optimal_paragraph_break = None
    while font_size_min <= font_size_max:
        font_size = (font_size_min + font_size_max) // 2
        try:
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            try:
                font = ImageFont.truetype("Arial.ttf", font_size)
            except IOError:
                font = ImageFont.load_default()
        lines = []
        for paragraph in colored_paragraphs:
            for segs in paragraph:
                line = []
                current_width = 0
                for seg_text, seg_color in segs:
                    words = seg_text.split(' ')
                    for i, word in enumerate(words):
                        is_last = (i == len(words) - 1)
                        word_with_space = word if is_last else word + ' '
                        word_width = font.getlength(word_with_space)
                        if word_width > max_text_width:
                            # Wort ist zu lang, Zeichenweise umbrechen (ohne Leerzeichen)
                            part = ''
                            part_width = 0
                            for char in word:
                                char_width = font.getlength(char)
                                if part and part_width + char_width > max_text_width:
                                    line.append((part, seg_color))
                                    lines.append(line)
                                    line = []
                                    part = ''
                                    part_width = 0
                                part += char
                                part_width += char_width
                            if part:
                                line.append((part, seg_color))
                                current_width = part_width
                        else:
                            if current_width + word_width > max_text_width and line:
                                lines.append(line)
                                line = []
                                current_width = 0
                            line.append((word_with_space, seg_color))
                            current_width += word_width
                if line:
                    lines.append(line)
            lines.append(None)
        if lines and lines[-1] is None:
            lines.pop()
        line_height = font.getbbox('Hg')[3] - font.getbbox('Hg')[1]
        paragraph_break = int(line_height * 1.5)
        total_text_height = 0
        for l in lines:
            if l is None:
                total_text_height += paragraph_break
            else:
                total_text_height += line_height
        if total_text_height <= max_text_height:
            optimal_font = font
            optimal_lines = lines
            optimal_line_height = line_height
            optimal_paragraph_break = paragraph_break
            font_size_min = font_size + 1
        else:
            font_size_max = font_size - 1
    if optimal_font is None:
        try:
            optimal_font = ImageFont.truetype("Arial Bold.ttf", 12)
        except IOError:
            try:
                optimal_font = ImageFont.truetype("Arial.ttf", 12)
            except IOError:
                optimal_font = ImageFont.load_default()
        optimal_lines = []
        for paragraph in colored_paragraphs:
            for segs in paragraph:
                line = []
                for seg_text, seg_color in segs:
                    line.append((seg_text, seg_color))
                optimal_lines.append(line)
            optimal_lines.append(None)
        if optimal_lines and optimal_lines[-1] is None:
            optimal_lines.pop()
        optimal_line_height = optimal_font.getbbox('Hg')[3] - optimal_font.getbbox('Hg')[1]
        optimal_paragraph_break = int(optimal_line_height * 1.5)
    total_text_height = 0
    for l in optimal_lines:
        if l is None:
            total_text_height += optimal_paragraph_break
        else:
            total_text_height += optimal_line_height
    y = reserved_top + (max_text_height - total_text_height) // 2
    for line in optimal_lines:
        if line is None:
            y += optimal_paragraph_break
            continue
        line_width = 0
        for word, _ in line:
            line_width += sum(optimal_font.getlength(c) + letter_spacing for c in word) - (letter_spacing if word else 0)
        x = margin + (max_text_width - line_width) // 2
        shadow_rgba = hex_to_rgb(shadow_color) + (shadow_opacity,)
        for word, color in line:
            for i, char in enumerate(word):
                draw.text((x + shadow_offset_x, y + shadow_offset_y), char, font=optimal_font, fill=shadow_rgba)
                draw.text((x, y), char, font=optimal_font, fill=color)
                x += optimal_font.getlength(char)
                if i < len(word) - 1:
                    x += letter_spacing
        y += optimal_line_height + line_spacing
    watermark_bbox = draw.textbbox((0, 0), watermark['text'], font=watermark_font)
    watermark_width = watermark_bbox[2] - watermark_bbox[0]
    watermark_height = watermark_bbox[3] - watermark_bbox[1]
    watermark_offset_y = watermark_bbox[1]
    padding_y = int(watermark_height * 0.5)
    padding_x = int(watermark_width * 0.1)
    bar_height = int(watermark_height + 2 * padding_y)
    background_rect = Image.new('RGBA', (
        int(watermark_width + 2 * padding_x),
        bar_height
    ), watermark['color'])
    watermark_x = (width - watermark_width) // 2
    bar_y = height - watermark_margin_bottom - bar_height // 2
    background_rect_pos = (
        int(watermark_x - padding_x),
        bar_y
    )
    img.paste(background_rect, background_rect_pos, background_rect)
    text_y = bar_y + (bar_height - watermark_height) // 2 - watermark_offset_y
    draw.text((watermark_x, text_y), 
              watermark['text'], 
              font=watermark_font, 
              fill=watermark_font_color + (255,))
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=100, subsampling=0)
    output.seek(0)
    return output

# --- Web-Frontend ---

@app.route('/', methods=['GET', 'POST'])
def index():
    result_url = None
    text_value = ''
    layout_value = None
    filename = None
    caption_value = ''
    layouts = load_layouts()
    is_admin = session.get('is_admin', False)
    if request.method == 'POST':
        text = request.form['text']
        text = clean_text(text)
        layout = request.form['layout']
        caption_value = request.form.get('caption', '')
        file = request.files['image']
        text_value = text
        layout_value = layout
        if not file:
            return render_template('index.html', layouts=layouts, error="Bitte ein Bild hochladen.", text_value=text_value, layout_value=layout_value, is_admin=is_admin, show_caption_feature=SHOW_CAPTION_FEATURE, caption_value=caption_value)
        img_path = os.path.join('static', 'tmp_upload.jpg')
        file.save(img_path)
        result_img = create_image_with_text_and_watermark(img_path, text, layout)
        os.remove(img_path)
        img_bytes = result_img.getvalue()
        img_b64 = base64.b64encode(img_bytes).decode('utf-8')
        data_url = f"data:image/jpeg;base64,{img_b64}"
        # Dateiname mit Layout und Zeitstempel
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = f"{layout}_{timestamp}.jpg"
        return render_template('index.html', layouts=layouts, result_url=data_url, text_value=text_value, layout_value=layout_value, is_admin=is_admin, filename=filename, show_caption_feature=SHOW_CAPTION_FEATURE, caption_value=caption_value)
    return render_template('index.html', layouts=layouts, text_value=text_value, layout_value=layout_value, is_admin=is_admin, show_caption_feature=SHOW_CAPTION_FEATURE, caption_value=caption_value)

# Dummy-Route für Caption-Generierung (hier später Gemini/OpenAI einbauen)
@app.route('/generate_caption', methods=['POST'])
def generate_caption():
    if not SHOW_CAPTION_FEATURE:
        return jsonify({'caption': 'Feature deaktiviert.'}), 403
    
    data = request.get_json()
    text = data.get('text', '')
    
    if not GEMINI_AVAILABLE:
        return jsonify({'caption': 'Feature deaktiviert.'})
        
    try:
        model = genai.GenerativeModel('gemini-pro')
        prompt = f"Schreibe eine kreative, kurze Instagram-Caption auf Deutsch für folgenden Bildtext:\n\n{text}\n\nCaption:"
        response = model.generate_content(prompt)
        caption = response.text.strip()
        return jsonify({'caption': caption})
    except Exception as e:
        return jsonify({'caption': f"Fehler bei der Caption-Generierung: {str(e)}"})

# --- Admin-Login ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form['password']
        if password == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin'))
        else:
            flash('Falsches Passwort!', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    flash('Abgemeldet.', 'info')
    return redirect(url_for('index'))

# --- Admin-Übersicht ---
@app.route('/admin')
def admin():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    layouts = load_layouts()
    return render_template('admin.html', layouts=layouts, is_admin=True)

# --- Layout bearbeiten/hinzufügen ---
@app.route('/admin/edit/<layout_key>', methods=['GET', 'POST'])
def edit_layout(layout_key):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    layouts = load_layouts()
    layout = layouts.get(layout_key, {})
    fonts = get_available_fonts()
    if request.method == 'POST':
        name = request.form['name']
        watermark_text = request.form['watermark_text']
        text_color = request.form['text_color']
        watermark_color = request.form['watermark_color']
        opacity = float(request.form.get('opacity', 60)) / 100
        font = request.form.get('font', 'GeezaPro-Bold.ttf')
        letter_spacing = int(request.form.get('letter_spacing', -2))
        line_spacing = int(request.form.get('line_spacing', -11))
        shadow_color = request.form.get('shadow_color', '#000000')
        shadow_opacity = int(request.form.get('shadow_opacity', 180))
        shadow_offset_x = int(request.form.get('shadow_offset_x', 3))
        shadow_offset_y = int(request.form.get('shadow_offset_y', 3))
        watermark_margin_bottom = int(request.form.get('watermark_margin_bottom', 40))
        watermark_font_color = request.form.get('watermark_font_color', '#ffffff')
        watermark_font = request.form.get('watermark_font', 'GeezaPro-Bold.ttf')
        watermark_font_size_percent = float(request.form.get('watermark_font_size_percent', 4.5))
        max_font_size_mode = request.form.get('max_font_size_mode', 'percent')
        max_font_size_value = float(request.form.get('max_font_size_value', 15.0))
        # Logo-Upload
        logo_file = request.files.get('logo_file')
        logo_path = layout.get('logo_file', f'static/logos/{name}.png')
        if logo_file and logo_file.filename:
            filename = secure_filename(f'{name}.png')
            logo_path = os.path.join(LOGO_FOLDER, filename)
            logo_file.save(logo_path)
        # Font-Upload
        font_file = request.files.get('font_file')
        if font_file and font_file.filename:
            font_filename = secure_filename(font_file.filename)
            font_path = os.path.join(FONTS_FOLDER, font_filename)
            font_file.save(font_path)
        layouts[name] = {
            'watermark_text': watermark_text,
            'text_color': text_color,
            'logo_file': logo_path,
            'watermark_color': watermark_color,
            'opacity': opacity,
            'font': font,
            'letter_spacing': letter_spacing,
            'line_spacing': line_spacing,
            'shadow_color': shadow_color,
            'shadow_opacity': shadow_opacity,
            'shadow_offset_x': shadow_offset_x,
            'shadow_offset_y': shadow_offset_y,
            'watermark_margin_bottom': watermark_margin_bottom,
            'watermark_font_color': watermark_font_color,
            'watermark_font': watermark_font,
            'watermark_font_size_percent': watermark_font_size_percent,
            'max_font_size_mode': max_font_size_mode,
            'max_font_size_value': max_font_size_value,
        }
        if layout_key != name and layout_key in layouts:
            del layouts[layout_key]
        save_layouts(layouts)
        flash('Layout gespeichert.', 'success')
        return redirect(url_for('admin'))
    return render_template('edit_layout.html', layout=layout, layout_key=layout_key, is_admin=True, fonts=fonts)

# --- Layout löschen ---
@app.route('/admin/delete/<layout_key>', methods=['POST'])
def delete_layout(layout_key):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    layouts = load_layouts()
    if layout_key in layouts:
        del layouts[layout_key]
        save_layouts(layouts)
        flash('Layout gelöscht.', 'info')
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True) 