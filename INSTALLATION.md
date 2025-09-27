# Eltako Integration - Installation Guide

## 🚀 Installation Methoden

### 1. 📦 HACS Installation (Empfohlen)

#### Voraussetzungen
- [HACS](https://hacs.xyz/) muss in Home Assistant installiert sein

#### Installation über HACS
1. Gehe zu HACS in Home Assistant
2. Klicke auf "Integrations"
3. Klicke auf das "+" Symbol (Add Repository)
4. Füge diese URL hinzu: `https://github.com/nonsenseMB/home-assistant-eltako`
5. Wähle "Integration" als Kategorie
6. Klicke "Add"
7. Suche nach "Eltako" und installiere es
8. Starte Home Assistant neu

### 2. 🐳 Git Clone für Docker/Container

```bash
# In deinem Home Assistant config Verzeichnis
cd /config

# Integration klonen
git clone https://github.com/nonsenseMB/home-assistant-eltako.git temp-eltako

# Integration kopieren
mkdir -p custom_components
cp -r temp-eltako/custom_components/eltako custom_components/

# Temporäres Verzeichnis löschen
rm -rf temp-eltako

# Home Assistant neustarten
```

### 3. 🖥️ Manuelle Git Installation

```bash
# Terminal öffnen und zum Home Assistant config Verzeichnis gehen
cd /path/to/homeassistant/config

# Repository klonen
git clone https://github.com/grimmpp/home-assistant-eltako.git

# Symlink erstellen (für einfache Updates)
mkdir -p custom_components
ln -sf $(pwd)/home-assistant-eltako/custom_components/eltako custom_components/eltako

# Oder direkt kopieren
cp -r home-assistant-eltako/custom_components/eltako custom_components/
```

### 4. 📱 Home Assistant OS (Supervisor)

#### Über File Editor Add-on
1. Installiere das "File Editor" Add-on
2. Gehe zu "File Editor" > "config"
3. Erstelle `custom_components` Ordner falls nicht vorhanden
4. Lade die Integration herunter:

```bash
# Über Terminal Add-on oder SSH Add-on
cd /config
wget https://github.com/grimmpp/home-assistant-eltako/archive/main.zip
unzip main.zip
cp -r home-assistant-eltako-main/custom_components/eltako custom_components/
rm -rf home-assistant-eltako-main main.zip
```

#### Über Studio Code Server Add-on
1. Installiere "Studio Code Server" Add-on
2. Öffne Terminal in VS Code
3. Führe Git-Befehle aus wie oben beschrieben

### 5. 🔄 Automatische Updates mit Git

#### Setup für automatische Updates
```bash
# Im Home Assistant config Verzeichnis
cd /config

# Repository klonen
git clone https://github.com/grimmpp/home-assistant-eltako.git eltako-repo

# Update-Script erstellen
cat > update_eltako.sh << 'EOF'
#!/bin/bash
cd /config/eltako-repo
git pull origin main
cp -r custom_components/eltako ../custom_components/
echo "Eltako Integration updated. Restart Home Assistant to apply changes."
EOF

chmod +x update_eltako.sh
```

#### Updates ausführen
```bash
# Updates holen und installieren
./update_eltako.sh

# Home Assistant neustarten
# Über UI: Developer Tools > YAML > Restart
```

### 6. 🛠️ Entwicklungssetup

```bash
# Für Entwickler - mit editierbarem Setup
cd /config
git clone https://github.com/grimmpp/home-assistant-eltako.git
cd home-assistant-eltako

# Symlink für live editing
ln -sf $(pwd)/custom_components/eltako /config/custom_components/eltako

# Dependencies installieren (falls nötig)
pip install -r requirements.txt
```

## ✅ Installation verifizieren

### Nach der Installation:

1. **Home Assistant neustarten**
   ```bash
   # Über UI: Settings > System > Restart
   # Oder CLI: ha core restart
   ```

2. **Integration hinzufügen**
   - Gehe zu Settings > Devices & Services
   - Klicke "Add Integration"
   - Suche nach "Eltako"

3. **Logs prüfen**
   ```yaml
   # configuration.yaml - für Debug-Logs
   logger:
     logs:
       custom_components.eltako: debug
   ```

4. **Integration Status prüfen**
   - Settings > Devices & Services > Eltako
   - Developer Tools > States (suche nach `eltako`)

## 🔧 Konfiguration

### Beispiel configuration.yaml
```yaml
# Automatische Erkennung über Config Flow empfohlen
# Oder manuelle Konfiguration:
eltako:
  gateway:
    - id: 0
      device_type: enocean-usb2
      serial_path: /dev/ttyUSB0
      base_id: FF-AA-00-00
```

## 🚨 Troubleshooting

### Integration nicht gefunden
```bash
# Pfad prüfen
ls -la /config/custom_components/eltako/

# Manifest prüfen
cat /config/custom_components/eltako/manifest.json
```

### Git nicht verfügbar
```bash
# Git installieren (falls nicht vorhanden)
# Docker: apk add git
# Ubuntu/Debian: apt install git
# Or download ZIP from GitHub
```

### Dependencies fehlen
```bash
# In Home Assistant Container
pip install eltako14bus eltakobus esp2_gateway_adapter
```

## 📈 Update Strategien

### HACS (Automatisch)
- Updates werden automatisch in HACS angezeigt
- Ein-Klick Update über HACS UI

### Git Pull (Manuell)
```bash
cd /config/home-assistant-eltako
git pull origin main
cp -r custom_components/eltako ../custom_components/
# Restart Home Assistant
```

### Webhook Updates (Fortgeschritten)
```yaml
# automation.yaml - Auto-update bei Git push
- alias: "Update Eltako Integration"
  trigger:
    - platform: webhook
      webhook_id: "update_eltako"
  action:
    - service: shell_command.update_eltako
    - service: homeassistant.restart
```

## 🔐 Sicherheit

### Repository verifizieren
```bash
# GPG Signatur prüfen (falls verfügbar)
git log --show-signature

# Repository Authentizität prüfen
git remote -v
```

### Dependencies prüfen
```bash
# Nur vertrauenswürdige Dependencies
pip check
```

Welche Installationsmethode passt am besten zu deinem Setup?