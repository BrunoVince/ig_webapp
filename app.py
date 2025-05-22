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
import unicodedata

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
ENABLE_BULK_CREATION = False  # Feature-Flag für Massenerstellung

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
    # Unicode-Normalisierung (NFKC)
    text = unicodedata.normalize('NFKC', text)
    # Erlaube alle druckbaren Zeichen plus deutsche Sonderzeichen und typografische Anführungszeichen
    allowed = set(string.printable + 'äöüÄÖÜß€–—""\'\'\…„"‚\'')
    return ''.join(c for c in text if c in allowed or c == '\n')

pattern_color = re.compile(r'<(.*?)>')
def parse_colored_segments(text, color):
    # Debug: Eingabezeile protokollieren
    print(f"Parsing input line: '{text}'")
    
    # Verbesserte Segmentierung für farbige Texte
    result = []
    last = 0
    for match in pattern_color.finditer(text):
        # Text vor der Farbmarkierung (weiß)
        if match.start() > last:
            result.append((text[last:match.start()], (255,255,255)))
        
        # Farbmarkierter Text (in Layout-Farbe)
        result.append((match.group(1), color))
        last = match.end()
    
    # Text nach der letzten Farbmarkierung (weiß)
    if last < len(text):
        result.append((text[last:], (255,255,255)))
    
    # Debug: Zeige alle extrahierten Segmente
    print(f"Parsed segments: {result}")
    
    # Detaillierte Segment-Info
    for i, (segment, seg_color) in enumerate(result):
        color_name = "FARBIG" if seg_color == color else "weiß"
        print(f"  Segment {i+1}: '{segment}' ({color_name}, Länge: {len(segment)})")
    
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
    logo_size_val = int(layout.get('logo_size', 120))
    logo_margin_top = int(layout.get('logo_margin_top', 30))
    logo_margin_left = int(layout.get('logo_margin_left', 30))
    logo_height = 0
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA").resize((logo_size_val, logo_size_val), Image.LANCZOS)
        img.paste(logo, (logo_margin_left, logo_margin_top), logo)
        logo_height = logo_size_val
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
    watermark_width = watermark_bbox[2] - watermark_bbox[0]
    watermark_height = watermark_bbox[3] - watermark_bbox[1]
    watermark_offset_y = watermark_bbox[1]
    padding_y = int(watermark_height * 0.5)
    padding_x = int(watermark_width * 0.1)
    
    # Verfügbarer Bereich für Text (mit festen Margins)
    margin_top = 240
    margin_bottom = 240
    text_area_height = height - margin_top - margin_bottom  # 600px (1080px - 2 * 240px = 600px)
    
    # Text in Absätze aufteilen
    paragraph_texts = re.split(r'\n\s*\n', text)
    print(f"Erkannte Absätze: {len(paragraph_texts)}")
    for i, p in enumerate(paragraph_texts):
        print(f"Absatz {i+1}: '{p}'")

    lines_per_paragraph = [p.split('\n') for p in paragraph_texts]
    print(f"Zeilen pro Absatz: {[len(lines) for lines in lines_per_paragraph]}")
    for i, para_lines in enumerate(lines_per_paragraph):
        print(f"Absatz {i+1} mit {len(para_lines)} Zeilen:")
        for j, line in enumerate(para_lines):
            print(f"  Zeile {j+1}: '{line}'")

    colored_paragraphs = [
        [parse_colored_segments(line, text_color) for line in paragraph_lines]
        for paragraph_lines in lines_per_paragraph
    ]
    
    # Debug: Analysiere die Textsegmente
    print("\nFarbsegment-Analyse:")
    for i, paragraph in enumerate(colored_paragraphs):
        print(f"Absatz {i+1}:")
        for j, line in enumerate(paragraph):
            print(f"  Zeile {j+1} mit {len(line)} Segmenten:")
            for k, (seg_text, seg_color) in enumerate(line):
                if seg_color == text_color:
                    color_desc = "FARBIG"
                else:
                    color_desc = "weiß"
                print(f"    Segment {k+1}: '{seg_text}' ({color_desc})")
    
    # Sammle alle Zeilen mit Farbwechseln
    print("\nZeilen mit Farbwechseln:")
    for i, paragraph in enumerate(colored_paragraphs):
        for j, line in enumerate(paragraph):
            if len(line) > 1:  # Mehr als ein Segment = Farbwechsel
                print(f"  Absatz {i+1}, Zeile {j+1} hat {len(line)} Farbsegmente")
    
    # Schriftgrößenberechnung
    font_size_min = 10
    # Flexible maximale Schriftgröße: Prozent oder Pixel
    if layout.get('max_font_size_mode', 'percent') == 'pixel':
        font_size_max = int(layout.get('max_font_size_value', 162))  # Default: 162px
    else:
        font_size_max = int(width * float(layout.get('max_font_size_value', 15.0)) / 100)
    # Optional: Absolute Obergrenze (z.B. nie größer als 15% der Breite)
    font_size_max = min(font_size_max, int(width * 0.15))
    optimal_font = None
    optimal_lines = None
    optimal_line_height = None
    optimal_paragraph_break = None
    word_spacing = layout.get('word_spacing', 0)
    
    while font_size_min <= font_size_max:
        font_size = (font_size_min + font_size_max) // 2
        try:
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            try:
                font = ImageFont.truetype("Arial.ttf", font_size)
            except IOError:
                font = ImageFont.load_default()
                
        # Berechne Textumbruch mit aktueller Schriftgröße
        lines = []
        all_segments = []
        
        # Sammle zunächst alle Segmente aus allen Absätzen in der richtigen Reihenfolge
        for p_idx, paragraph in enumerate(colored_paragraphs):
            paragraph_segments = []
            
            # Gehe durch jede Zeile im Absatz
            for line_idx, line in enumerate(paragraph):
                line_segments = []
                
                # Verarbeite jedes Segment in der Zeile
                for seg_text, seg_color in line:
                    words = seg_text.split(' ')
                    for i, word in enumerate(words):
                        is_last = (i == len(words) - 1)
                        word_with_space = word if is_last else word + ' '
                        line_segments.append((word_with_space, seg_color))
                
                # Füge alle Segmente dieser Zeile hinzu
                for segment in line_segments:
                    paragraph_segments.append(segment)
                
                # Füge eine Zeilenumbruch-Markierung nach jeder Zeile außer der letzten ein
                if line_idx < len(paragraph) - 1:
                    # Spezielle Markierung für Zeilenumbruch
                    paragraph_segments.append(("<<<LINE_BREAK>>>", None))
            
            all_segments.append(paragraph_segments)
        
        # Verarbeite alle Segmente im Absatz
        for p_idx, paragraph_segments in enumerate(all_segments):
            line = []
            current_width = 0
            
            # Debug-Info zum Absatz
            print(f"\nVerarbeite Absatz {p_idx+1} mit {len(paragraph_segments)} Segmenten:")
            
            for word_with_space, seg_color in paragraph_segments:
                # Prüfe auf spezielle Zeilenumbruch-Markierung
                if word_with_space == "<<<LINE_BREAK>>>" and seg_color is None:
                    # Zeilenumbruch: Aktuelle Zeile hinzufügen und neue Zeile beginnen
                    if line:
                        lines.append(line)
                        line = []
                        current_width = 0
                    continue
                
                # Debug-Info zum aktuellen Wort
                color_name = "FARBIG" if seg_color == text_color else "weiß"
                print(f"  Wort: '{word_with_space.strip()}' ({color_name})")
                
                word_width = font.getlength(word_with_space)
                
                # Prüfe, ob das Wort zu lang für eine Zeile ist
                if word_width > max_text_width:
                    # Füge die aktuelle Zeile hinzu, falls nicht leer
                    if line:
                        lines.append(line)
                        line = []
                        current_width = 0
                    
                    # Zeichenweiser Umbruch für zu lange Wörter
                    word = word_with_space.rstrip()  # Entferne ggf. angehängtes Leerzeichen
                    part = ''
                    part_width = 0
                    
                    for char in word:
                        char_width = font.getlength(char)
                        if part and part_width + char_width > max_text_width:
                            # Teil zu lang, füge als Zeile hinzu und starte neu
                            line.append((part, seg_color))
                            lines.append(line)
                            line = []
                            part = ''
                            part_width = 0
                        
                        part += char
                        part_width += char_width
                    
                    # Restlichen Teil hinzufügen
                    if part:
                        line.append((part, seg_color))
                        current_width = part_width
                        
                    # Füge ggf. das Leerzeichen hinzu
                    if word_with_space.endswith(' '):
                        current_width += font.getlength(' ')
                else:
                    # Normaler Fall: Prüfe, ob das Wort in die aktuelle Zeile passt
                    new_width = current_width
                    if line:  # Wortabstand nur, wenn bereits Wörter in der Zeile sind
                        new_width += word_spacing
                    new_width += word_width
                    
                    if new_width > max_text_width and line:
                        # Nicht genug Platz, starte neue Zeile
                        lines.append(line)
                        line = [(word_with_space, seg_color)]
                        current_width = word_width
                    else:
                        # Genug Platz, füge zur aktuellen Zeile hinzu
                        if line:
                            current_width += word_spacing
                        line.append((word_with_space, seg_color))
                        current_width += word_width
            
            # Letzte Zeile des Absatzes hinzufügen
            if line:
                lines.append(line)
            
            # Absatzende markieren, aber nur, wenn nicht der letzte Absatz
            if p_idx < len(all_segments) - 1:
                lines.append(None)
        
        # Debug: Analysiere die umgebrochenen Zeilen und deren Farben
        print("\nUmgebrochene Zeilen mit Farbinformationen:")
        for i, line in enumerate(lines):
            if line is None:
                print(f"  Zeile {i+1}: [Absatzumbruch]")
            else:
                line_str = ""
                has_color = False
                for word, color in line:
                    color_name = "FARBIG" if color == text_color else "weiß"
                    line_str += f"[{word.strip()}:{color_name}] "
                    if color == text_color:
                        has_color = True
                print(f"  Zeile {i+1}: {line_str}")
                print(f"    Hat farbige Segmente: {has_color}")
                
        # Letztes Absatzende entfernen, falls vorhanden
        if lines and lines[-1] is None:
            lines.pop()
        
        # Berechne die tatsächliche Höhe mit Zeilenabständen
        line_height = font.getbbox('Hg')[3] - font.getbbox('Hg')[1]
        paragraph_break = int(line_height * 1.5)
        
        # Berechne die Gesamthöhe inkl. aller Abstände
        total_height = 0
        current_paragraph_lines = 0
        for l in lines:
            if l is None:
                total_height += paragraph_break
                if current_paragraph_lines > 1:
                    total_height -= line_spacing
                current_paragraph_lines = 0
            else:
                total_height += line_height
                if current_paragraph_lines > 0:
                    total_height += line_spacing
                current_paragraph_lines += 1
        
        # Ziehe den letzten Zeilenabstand ab, falls nötig
        if current_paragraph_lines > 1:
            total_height -= line_spacing
            
        # Prüfe, ob der Text in den verfügbaren Bereich passt
        if total_height <= text_area_height:
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
    num_lines = len([l for l in optimal_lines if l is not None])
    num_paragraphs = len([l for l in optimal_lines if l is None]) + 1
    
    # Berechne die Gesamthöhe mit korrekter Berücksichtigung von:
    # - Zeilenhöhen
    # - Zeilenabständen
    # - Absatzabständen
    
    # Flache Liste aller normalen Textzeilen (keine Absatzumbrüche)
    rendering_lines = []
    for line in optimal_lines:
        if line is not None:  # Ignoriere Absatzumbrüche
            rendering_lines.append(line)
    
    # Ermittle Absatzgrenzen
    absatz_beginne = [0]  # Erste Zeile beginnt immer einen Absatz
    absatz_enden = []
    
    # Durchlaufe original Zeilen und ermittle Absatzgrenzen
    line_idx = 0
    for i, line in enumerate(optimal_lines):
        if line is None:  # Absatzende
            absatz_enden.append(line_idx - 1)  # Ende des vorherigen Absatzes
            if i+1 < len(optimal_lines) and optimal_lines[i+1] is not None:
                absatz_beginne.append(line_idx)  # Beginn des nächsten Absatzes
        else:
            line_idx += 1
    
    # Letzter Absatz endet bei der letzten Zeile
    if rendering_lines:
        absatz_enden.append(len(rendering_lines) - 1)
    
    # Debug: Zeige Absatzgrenzen
    print(f"Absatzgrenzen - Beginne: {absatz_beginne}, Enden: {absatz_enden}")
    
    # Für jede Zeile speichern, ob sie einen Absatz beginnt oder innerhalb eines Absatzes ist
    ist_absatz_beginn = [False] * len(rendering_lines)
    for beginn in absatz_beginne:
        if beginn < len(rendering_lines):
            ist_absatz_beginn[beginn] = True
    
    # Für jede Zeile speichern, ob sie einen Absatz beendet
    ist_absatz_ende = [False] * len(rendering_lines)
    for ende in absatz_enden:
        if ende < len(rendering_lines):
            ist_absatz_ende[ende] = True
    
    # Berechne die Gesamthöhe des Textes ohne Zeilenabstände
    base_height = len(rendering_lines) * optimal_line_height
    
    # Füge Zeilenabstände hinzu
    zeilenabstand_summe = 0
    absatzabstand_summe = 0
    
    for i in range(len(rendering_lines) - 1):  # Für alle Zeilen außer der letzten
        if ist_absatz_ende[i]:
            # Nach einem Absatzende folgt ein Absatzabstand
            absatzabstand_summe += optimal_paragraph_break
        else:
            # Innerhalb eines Absatzes folgt ein Zeilenabstand
            zeilenabstand_summe += line_spacing
    
    total_text_height = base_height + zeilenabstand_summe + absatzabstand_summe
    
    # Debug-Ausgaben
    print(f"Anzahl Zeilen: {len(rendering_lines)}")
    print(f"Zeilenhöhe (Basis): {optimal_line_height}px")
    print(f"Basis-Höhe (ohne Abstände): {base_height}px")
    print(f"Zeilenabstand: {line_spacing}px, Summe: {zeilenabstand_summe}px")
    print(f"Absatzabstand: {optimal_paragraph_break}px, Summe: {absatzabstand_summe}px")
    print(f"Gesamttexthöhe: {total_text_height}px")
    print(f"Verfügbare Höhe: {text_area_height}px")
    
    # Zentrierung im verfügbaren Bereich
    if total_text_height <= text_area_height:
        # Text passt in verfügbaren Bereich - zentriere ihn
        text_area_center = margin_top + (text_area_height // 2)  # = 540px
        y = text_area_center - (total_text_height // 2)
    else:
        # Text ist zu groß - starte bei margin_top
        y = margin_top
    
    # Font-Baseline-Korrektur: Ermöglicht eine manuelle Anpassung der Textposition
    y_correction = int(layout.get('y_correction', 0))  # Neue Layout-Einstellung
    y += y_correction  # Korrektur anwenden
    
    # Rendering des Texts - mit genau definierten Abständen
    current_y = y
    
    # Zusätzliche Debug-Ausgabe für Renderingprozess
    print("\nRendering-Prozess (präzise):")
    
    for i, line in enumerate(rendering_lines):
        # Debug-Ausgabe für aktuelle Zeile
        debug_line = " ".join([f"{word.strip()}" for word, _ in line])
        print(f"  Zeile {i+1}: '{debug_line}' bei Position y={current_y}px")
        print(f"    Absatzbeginn: {ist_absatz_beginn[i]}, Absatzende: {ist_absatz_ende[i]}")
        
        # Rendere die Zeile
        line_width = sum(optimal_font.getlength(word) + (len(word) - 1) * letter_spacing for word, _ in line)
        if len(line) > 1:
            line_width += (len(line) - 1) * word_spacing
            
        x = margin + (max_text_width - line_width) // 2
        
        # Rendere jedes Wort der Zeile
        for w_idx, (word, color) in enumerate(line):
            # Rendere das Wort mit Schatten
            shadow_rgba = hex_to_rgb(shadow_color) + (shadow_opacity,)
            for j, char in enumerate(word):
                draw.text((x + shadow_offset_x, current_y + shadow_offset_y), char, font=optimal_font, fill=shadow_rgba)
                draw.text((x, current_y), char, font=optimal_font, fill=color)
                x += optimal_font.getlength(char)
                if j < len(word) - 1:
                    x += letter_spacing
            if w_idx < len(line) - 1:
                x += word_spacing
        
        # Zeilenhöhe immer hinzufügen
        current_y += optimal_line_height
        print(f"    Zeilenhöhe hinzugefügt: {optimal_line_height}px -> neue y={current_y}px")
        
        # Prüfe, ob nach dieser Zeile ein Abstand hinzugefügt werden muss
        if i < len(rendering_lines) - 1:  # Nicht die letzte Zeile
            if ist_absatz_ende[i]:
                # Absatzabstand hinzufügen
                current_y += optimal_paragraph_break
                print(f"    Absatzabstand hinzugefügt: {optimal_paragraph_break}px -> neue y={current_y}px")
            else:
                # Normaler Zeilenabstand
                current_y += line_spacing
                print(f"    Zeilenabstand hinzugefügt: {line_spacing}px -> neue y={current_y}px")
    
    # Debug-Ausgaben für die Abstände
    print(f"Start-Y-Position: {y}px (inkl. y_correction: {y_correction}px)")
    print(f"End-Y-Position: {current_y}px")
    print(f"Tatsächliche Texthöhe: {current_y - y}px")
    print(f"Berechnete Texthöhe: {total_text_height}px")
    print(f"Abstand oben: {y}px")
    print(f"Abstand unten: {height - current_y}px")
    print(f"Verhältnis unten/oben: {(height - current_y) / y:.2f}")
    print(f"Ideales Verhältnis: 1.0 (gleiche Abstände)")
    
    # Empfehlung für y_correction
    if abs((height - current_y) / y - 1.0) > 0.1:  # Mehr als 10% Unterschied
        empfohlene_korrektur = int((y - (height - current_y)) / 2)
        print(f"Empfohlene y_correction: {empfohlene_korrektur}px")
    
    watermark_bbox = draw.textbbox((0, 0), watermark['text'], font=watermark_font)
    watermark_width = watermark_bbox[2] - watermark_bbox[0]
    watermark_height = watermark_bbox[3] - watermark_bbox[1]
    watermark_offset_y = watermark_bbox[1]
    
    # --- Wasserzeichen-Balken-Dimensionen ---
    # Balkenhöhe: entweder benutzerdefiniert oder automatisch berechnet
    watermark_bar_height = int(layout.get('watermark_bar_height', 0))
    if watermark_bar_height <= 0:
        # Automatische Berechnung basierend auf Texthöhe
        bar_height = int(watermark_height + 2 * padding_y)
    else:
        # Benutzerdefinierte Höhe
        bar_height = watermark_bar_height
    
    # Balkenbreite: entweder benutzerdefiniert oder automatisch berechnet
    watermark_bar_width = int(layout.get('watermark_bar_width', 0))
    if watermark_bar_width <= 0:
        # Automatische Berechnung basierend auf Textbreite
        bar_width = int(watermark_width + 2 * padding_x)
    else:
        # Benutzerdefinierte Breite
        bar_width = watermark_bar_width
    
    # --- Wasserzeichen-Balken erzeugen ---
    # Gradient-Logik
    def hex_to_rgb_tuple(hexcolor):
        hexcolor = hexcolor.lstrip('#')
        return tuple(int(hexcolor[i:i+2], 16) for i in (0, 2, 4))
        
    def create_vertical_gradient(width, height, color1, color2):
        base = Image.new('RGB', (width, height), color1)
        top = Image.new('RGB', (width, height), color2)
        mask = Image.linear_gradient('L').resize((width, height))
        return Image.composite(top, base, mask)
    
    # Balken erstellen (mit oder ohne Gradient)
    if layout.get('watermark_bar_gradient_enabled'):
        color1 = hex_to_rgb_tuple(layout.get('watermark_bar_gradient_start', '#0078ff'))
        color2 = hex_to_rgb_tuple(layout.get('watermark_bar_gradient_end', '#0078ff'))
        gradient = create_vertical_gradient(bar_width, bar_height, color1, color2)
        background_rect = gradient.convert('RGBA')
    else:
        background_rect = Image.new('RGBA', (bar_width, bar_height), watermark['color'])
    
    # Balken positionieren
    bar_x = (width - bar_width) // 2
    bar_y = height - watermark_margin_bottom - bar_height // 2
    
    background_rect_pos = (bar_x, bar_y)
    img.paste(background_rect, background_rect_pos, background_rect)
    
    # Text horizontal zentrieren im Balken
    watermark_x = (width - watermark_width) // 2
    
    # Text vertikal zentrieren im Balken
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
            return render_template('index.html', layouts=layouts, error="Bitte ein Bild hochladen.", text_value=text_value, layout_value=layout_value, is_admin=is_admin, show_caption_feature=SHOW_CAPTION_FEATURE, caption_value=caption_value, enable_bulk_creation=ENABLE_BULK_CREATION)
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
        return render_template('index.html', layouts=layouts, result_url=data_url, text_value=text_value, layout_value=layout_value, is_admin=is_admin, filename=filename, show_caption_feature=SHOW_CAPTION_FEATURE, caption_value=caption_value, enable_bulk_creation=ENABLE_BULK_CREATION)
    return render_template('index.html', layouts=layouts, text_value=text_value, layout_value=layout_value, is_admin=is_admin, show_caption_feature=SHOW_CAPTION_FEATURE, caption_value=caption_value, enable_bulk_creation=ENABLE_BULK_CREATION)

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
    return render_template('admin.html', layouts=layouts, is_admin=True, enable_bulk_creation=ENABLE_BULK_CREATION)

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
        watermark_bar_width = int(request.form.get('watermark_bar_width', 0))
        watermark_bar_height = int(request.form.get('watermark_bar_height', 0))
        max_font_size_mode = request.form.get('max_font_size_mode', 'percent')
        max_font_size_value = float(request.form.get('max_font_size_value', 15.0))
        logo_size = int(request.form.get('logo_size', 120))
        word_spacing = int(request.form.get('word_spacing', 0))
        watermark_bar_gradient_enabled = bool(request.form.get('watermark_bar_gradient_enabled'))
        watermark_bar_gradient_start = request.form.get('watermark_bar_gradient_start', '#0078ff')
        watermark_bar_gradient_end = request.form.get('watermark_bar_gradient_end', '#0078ff')
        logo_margin_top = int(request.form.get('logo_margin_top', 30))
        logo_margin_left = int(request.form.get('logo_margin_left', 30))
        y_correction = int(request.form.get('y_correction', 0))
        # Ursprüngliche Logo-Upload-Logik wiederherstellen
        logo_file = request.files.get('logo_file')
        logo_path = layout.get('logo_file', f'static/logos/{name}.png')
        if logo_file and logo_file.filename:
            filename = secure_filename(f'{name}.png')
            logo_path = os.path.join(LOGO_FOLDER, filename)
            logo_file.save(logo_path)
        # Font-Upload bleibt wie gehabt
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
            'watermark_bar_width': watermark_bar_width,
            'watermark_bar_height': watermark_bar_height,
            'max_font_size_mode': max_font_size_mode,
            'max_font_size_value': max_font_size_value,
            'logo_size': logo_size,
            'word_spacing': word_spacing,
            'watermark_bar_gradient_enabled': watermark_bar_gradient_enabled,
            'watermark_bar_gradient_start': watermark_bar_gradient_start,
            'watermark_bar_gradient_end': watermark_bar_gradient_end,
            'logo_margin_top': logo_margin_top,
            'logo_margin_left': logo_margin_left,
            'y_correction': y_correction
        }
        if layout_key != name and layout_key in layouts:
            del layouts[layout_key]
        save_layouts(layouts)
        flash('Layout gespeichert.', 'success')
        return redirect(url_for('admin'))
    return render_template('edit_layout.html', layout=layout, layout_key=layout_key, is_admin=True, fonts=fonts, enable_bulk_creation=ENABLE_BULK_CREATION)

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

@app.route('/admin/export_layouts')
def export_layouts():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    return send_file(LAYOUTS_FILE, as_attachment=True, download_name='layouts.json', mimetype='application/json')

@app.route('/admin/import_layouts', methods=['POST'])
def import_layouts():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    file = request.files.get('import_file')
    if not file:
        flash('Keine Datei ausgewählt!', 'danger')
        return redirect(url_for('admin'))
    try:
        data = json.load(file)
        # Optional: Validierung der Struktur
        if not isinstance(data, dict):
            raise ValueError('Ungültiges Layout-Format!')
        save_layouts(data)
        flash('Layouts erfolgreich importiert.', 'success')
    except Exception as e:
        flash(f'Fehler beim Import: {e}', 'danger')
    return redirect(url_for('admin'))

@app.route('/bulk-create', methods=['GET', 'POST'])
def bulk_create():
    if not ENABLE_BULK_CREATION:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        # Prüfe, ob ein Bild hochgeladen wurde
        if 'file' not in request.files:
            flash('Kein Bild ausgewählt', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('Kein Bild ausgewählt', 'danger')
            return redirect(request.url)
        
        # Prüfe, ob Text eingegeben wurde
        text = request.form.get('text', '').strip()
        if not text:
            flash('Kein Text eingegeben', 'danger')
            return redirect(request.url)
        
        # Sichere das hochgeladene Bild
        filename = secure_filename(file.filename)
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        os.makedirs('static/uploads', exist_ok=True)
        temp_path = os.path.join('static/uploads', f"{timestamp}_{filename}")
        file.save(temp_path)
        
        # Lade alle verfügbaren Layouts
        layouts = load_layouts()
        
        # Generiere für jedes Layout ein Bild
        generated_images = []
        
        for layout_key in layouts.keys():
            # Generiere ein eindeutiges Bild für jedes Layout
            result_filename = f"{layout_key}_{timestamp}.jpg"
            result_path = os.path.join('static/generated', result_filename)
            
            try:
                # Erstelle das Bild mit dem spezifischen Layout
                result_img = create_image_with_text_and_watermark(temp_path, text, layout_key)
                os.makedirs('static/generated', exist_ok=True)
                
                # BytesIO-Objekt korrekt als Datei speichern
                with open(result_path, 'wb') as f:
                    f.write(result_img.getvalue())
                
                # Speichere Informationen zum generierten Bild
                generated_images.append({
                    'layout': layout_key,
                    'image_path': result_path,
                    'image_url': url_for('static', filename=f'generated/{result_filename}')
                })
            except Exception as e:
                flash(f'Fehler bei Layout {layout_key}: {str(e)}', 'danger')
        
        # Lösche das temporäre Originalbild
        try:
            os.remove(temp_path)
        except:
            pass
        
        # Zeige die Ergebnisse an
        return render_template('bulk_results.html', generated_images=generated_images)
    
    return render_template('bulk_create.html')

@app.route('/admin/toggle_feature/<feature_name>', methods=['POST'])
def toggle_feature(feature_name):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    global ENABLE_BULK_CREATION, SHOW_CAPTION_FEATURE
    
    if feature_name == 'bulk_creation':
        ENABLE_BULK_CREATION = not ENABLE_BULK_CREATION
        status = "aktiviert" if ENABLE_BULK_CREATION else "deaktiviert"
        flash(f'Massenerstellung wurde {status}.', 'success')
    elif feature_name == 'caption':
        SHOW_CAPTION_FEATURE = not SHOW_CAPTION_FEATURE
        status = "aktiviert" if SHOW_CAPTION_FEATURE else "deaktiviert"
        flash(f'Caption-Feature wurde {status}.', 'success')
    
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True, port=5001) 