# Confluence HTML Export Tool

Tool zum Exportieren von Confluence-Seiten als Roh-HTML zur Debugging und Analyse des Markdown Converters.

## Installation

Stelle sicher, dass die benötigten Pakete installiert sind:

```bash
pip install requests
```

## Verwendung

### Umgebungsvariable setzen (optional)

Um den API-Token nicht jedes Mal eingeben zu müssen, kannst du ihn als Umgebungsvariable setzen:

```bash
export CONFLUENCE_TOKEN="dein_api_token_hier"
```

### Grundlegende Verwendung

```bash
# Einfacher Export (Page ID ist erforderlich)
python bin/export_confluence_html.py 244744731

# Mit eigenem Ausgabedateiname
python bin/export_confluence_html.py 244744731 meine_seite.html

# Mit anderer Confluence-Instanz
python bin/export_confluence_html.py 244744731 meine_seite.html https://confluence.example.com
```

### Parameter

- **page_id** (erforderlich): Die ID der Confluence-Seite, die exportiert werden soll
- **output_file** (optional): Name der Ausgabedatei (Standard: `raw_html_{page_id}.html`)
- **confluence_url** (optional): Basis-URL der Confluence-Instanz (Standard: `https://confluence.oediv.lan`)

### Hilfe anzeigen

```bash
python bin/export_confluence_html.py --help
```

## Beispielausgabe

```
Fetching page 244744731 from https://confluence.oediv.lan...

✅ Successfully exported Confluence page!
   Page: Meine Testseite (ID: 244744731)
   Space: PROJ
   File: raw_html_244744731.html
   Size: 15432 characters
```

## Hinweise

- Das Skript verwendet Bearer-Token-Authentifizierung
- Die exportierte HTML ist die `export_view` Darstellung von Confluence
- Das HTML kann direkt für die Debugging des Markdown Converters verwendet werden
- Bei Authentifizierungsfehlern prüfe den API-Token und die Berechtigungen

## Fehlerbehandlung

- **401**: Ungültiger API-Token oder fehlende Berechtigungen
- **404**: Seite existiert nicht oder du hast keinen Zugriff
- **Timeout**: Netzwerk- oder Verbindungsprobleme zur Confluence-Instanz
