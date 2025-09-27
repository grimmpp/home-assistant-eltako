#!/usr/bin/env python
"""Debug script for Eltako integration installation issues."""

import json
import sys
from pathlib import Path

def check_installation_in_ha():
    """Check if integration is properly installed in Home Assistant."""
    print("🔍 Debugging Eltako Integration Installation\n")

    # Check common HA installation paths
    possible_paths = [
        "/config/custom_components/eltako",
        "/usr/src/homeassistant/config/custom_components/eltako",
        "/homeassistant/config/custom_components/eltako",
        "/config/custom_components/eltako",
    ]

    found_path = None
    for path in possible_paths:
        if Path(path).exists():
            found_path = path
            break

    if not found_path:
        print("❌ Integration NOT found in any common HA paths")
        print("   Expected locations:")
        for path in possible_paths:
            print(f"   - {path}")
        return False

    print(f"✅ Integration found at: {found_path}")

    # Check required files
    required_files = [
        "__init__.py",
        "manifest.json",
        "config_flow.py",
        "const.py"
    ]

    missing_files = []
    for file_name in required_files:
        file_path = Path(found_path) / file_name
        if not file_path.exists():
            missing_files.append(file_name)

    if missing_files:
        print(f"❌ Missing files: {missing_files}")
        return False

    print("✅ All required files present")

    # Check manifest.json
    try:
        with open(Path(found_path) / "manifest.json") as f:
            manifest = json.load(f)

        if manifest.get("domain") != "eltako":
            print(f"❌ Wrong domain in manifest: {manifest.get('domain')}")
            return False

        if not manifest.get("config_flow"):
            print("❌ config_flow not enabled in manifest")
            return False

        print("✅ Manifest.json is valid")

    except Exception as e:
        print(f"❌ Error reading manifest.json: {e}")
        return False

    # Check imports
    try:
        import sys
        sys.path.insert(0, str(Path(found_path).parent))

        print("🔍 Testing imports...")

        # Test basic import
        import eltako
        print("✅ Basic eltako import works")

        # Test config flow import
        from eltako.config_flow import EltakoFlowHandler
        print("✅ Config flow import works")

        # Test if handler is properly configured
        if hasattr(EltakoFlowHandler, 'VERSION'):
            print(f"✅ Config flow handler version: {EltakoFlowHandler.VERSION}")
        else:
            print("⚠️  Config flow handler missing VERSION")

    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

    print("\n🎉 Integration installation looks good!")
    return True

def generate_install_commands():
    """Generate installation commands for user."""
    print("\n📋 Installation Commands:")
    print("="*50)

    commands = [
        "# Method 1: Direct download",
        "cd /config",
        "wget https://github.com/nonsenseMB/home-assistant-eltako/archive/main.zip",
        "unzip main.zip",
        "mkdir -p custom_components",
        "cp -r home-assistant-eltako-main/custom_components/eltako custom_components/",
        "rm -rf home-assistant-eltako-main main.zip",
        "",
        "# Method 2: Git clone",
        "cd /config",
        "git clone https://github.com/nonsenseMB/home-assistant-eltako.git temp",
        "mkdir -p custom_components",
        "cp -r temp/custom_components/eltako custom_components/",
        "rm -rf temp",
        "",
        "# After installation:",
        "# 1. Restart Home Assistant",
        "# 2. Go to Settings > Devices & Services",
        "# 3. Click 'Add Integration'",
        "# 4. Search for 'Eltako'"
    ]

    for cmd in commands:
        print(cmd)

def check_ha_logs():
    """Instructions for checking HA logs."""
    print("\n🔍 How to check Home Assistant logs:")
    print("="*50)

    instructions = [
        "1. In HA UI: Settings > System > Logs",
        "2. Look for errors containing 'eltako' or 'config_flow'",
        "3. Or check log file directly:",
        "   tail -f /config/home-assistant.log | grep -i eltako",
        "",
        "4. Enable debug logging (configuration.yaml):",
        "   logger:",
        "     logs:",
        "       custom_components.eltako: debug",
        "",
        "5. Common error patterns to look for:",
        "   - 'ModuleNotFoundError'",
        "   - 'Invalid handler specified'",
        "   - 'ImportError'",
        "   - 'AttributeError'"
    ]

    for instruction in instructions:
        print(instruction)

if __name__ == "__main__":
    success = check_installation_in_ha()

    if not success:
        generate_install_commands()

    check_ha_logs()

    sys.exit(0 if success else 1)