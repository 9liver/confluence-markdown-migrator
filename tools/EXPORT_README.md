# Confluence HTML Export Tool

Tool zum Exportieren von Confluence-Seiten als Roh-HTML zur Debugging und Analyse des Markdown Converters.

## Installation

Stelle sicher, dass die benötigten Pakete installiert sind:

```bash
pip install requests
```

Für Umgebungen mit interner CA (z. B. Firmennetzwerk):
```bash
pip install truststore
```

## Verwendung

### Umgebungsvariablen setzen (optional)

**API-Token** (um nicht jedes Mal eingeben zu müssen):
```bash
export CONFLUENCE_TOKEN="dein_api_token_hier"
```

**System-Zertifikate verwenden** (für interne CAs):
```bash
# Option 1: truststore verwenden (Python 3.10+, empfohlen)
export USE_SYSTEM_CA=1

# Option 2: Eigenes CA-Bundle angeben
export REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt
```

### Grundlegende Verwendung

```bash
# Einfacher Export (Page ID ist erforderlich)
python export_confluence_html.py 244744731

# Mit eigenem Ausgabedateiname
python export_confluence_html.py 244744731 meine_seite.html

# Mit anderer Confluence-Instanz
python export_confluence_html.py 244744731 meine_seite.html https://confluence.example.com

# Mit system Zertifikaten (für interne CAs)
USE_SYSTEM_CA=1 python export_confluence_html.py 244744731

# Ohne SSL-Verifizierung (NICHT EMPFOHLEN, aber funktioniert)
python export_confluence_html.py --insecure 244744731
# Oder:
CONFLUENCE_INSECURE=1 python export_confluence_html.py 244744731
```

### Parameter

- **page_id** (erforderlich): Die ID der Confluence-Seite, die exportiert werden soll
- **output_file** (optional): Name der Ausgabedatei (Standard: `raw_html_{page_id}.html`)
- **confluence_url** (optional): Basis-URL der Confluence-Instanz (Standard: `https://confluence.oediv.lan`)

### Hilfe anzeigen

```bash
python export_confluence_html.py --help
```

## Beispielausgabe

```
Using system CA certificate store
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

## System-Zertifikate (Interne CA)

Für Firmennetzwerke mit eigener Certificate Authority:

1. **truststore installieren** (empfohlen):
   ```bash
   pip install truststore
   ```

2. **Umgebungsvariable setzen**:
   ```bash
   export USE_SYSTEM_CA=1
   ```

3. **Oder alternativ CA-Bundle angeben**:
   ```bash
   # Finde das System-CA-Bundle
   # Ubuntu/Debian: /etc/ssl/certs/ca-certificates.crt
   # RHEL/CentOS: /etc/pki/tls/certs/ca-bundle.crt
   export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
   ```

   Die `truststore` Methode ist besser, weil:
   - Sie nutzt das native Betriebssystem-Zertifikatspeicher
   - Funktioniert automatisch mit System-Updates
   - Unterstützt macOS, Windows und Linux
   - Kein manuelles CA-Bundle Management nötig

## Fehlerbehandlung

- **401**: Ungültiger API-Token oder fehlende Berechtigungen
- **404**: Seite existiert nicht oder du hast keinen Zugriff
- **SSL Errors**: Prüfe System-CA-Konfiguration oder setze `verify_ssl=False` (unsicher!)
- **Timeout**: Netzwerk- oder Verbindungsprobleme zur Confluence-Instanz
