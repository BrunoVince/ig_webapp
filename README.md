# Telegram WebApp – Text auf Bild

Dieses Projekt ist eine eigenständige Web-App (Flask), mit der du wie im Telegram-Bot Bilder mit Text, Layout und Wasserzeichen erstellen kannst.

## Features
- Bild-Upload, Texteingabe, Layout-Auswahl
- Wasserzeichen-Logo oben links, Textschatten, farbige Textpassagen
- Ergebnisbild direkt im Browser anzeigen und herunterladen

## Projektstruktur
```
telegram_webapp/
├── app.py                # Flask-Hauptdatei
├── requirements.txt      # Abhängigkeiten
├── static/
│   └── logos/            # Logos für die Layouts
├── templates/
│   └── index.html        # Haupt-HTML-Template
└── README.md             # Diese Anleitung
```

## Starten
1. Lege deine Layout-Logos in `static/logos/` ab (Dateiname = Layoutname, z.B. DOKTORSPIELFAKTEN.png)
2. Installiere die Abhängigkeiten:
   ```
   pip install -r requirements.txt
   ```
3. Starte die App:
   ```
   python app.py
   ```
4. Öffne die Web-App im Browser: [http://localhost:5000](http://localhost:5000)

---

Du kannst den Telegram-Bot und die Web-App unabhängig voneinander weiterentwickeln. 