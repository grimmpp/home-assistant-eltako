#!/usr/bin/env python
"""Check if Eltako dependencies are installed in Home Assistant."""

import sys
import subprocess
from typing import List, Dict, Any

def check_dependency(package_name: str, version_spec: str = None) -> Dict[str, Any]:
    """Check if a specific dependency is installed."""
    try:
        if package_name == "StrEnum":
            # StrEnum is a special case - it's actually 'strenum'
            import strenum
            return {
                "name": package_name,
                "installed": True,
                "version": getattr(strenum, "__version__", "unknown"),
                "location": strenum.__file__
            }
        elif package_name.startswith("eltako14bus"):
            import eltako14bus
            return {
                "name": package_name,
                "installed": True,
                "version": getattr(eltako14bus, "__version__", "unknown"),
                "location": eltako14bus.__file__
            }
        elif package_name.startswith("enocean"):
            import enocean
            return {
                "name": package_name,
                "installed": True,
                "version": getattr(enocean, "__version__", "unknown"),
                "location": enocean.__file__
            }
        elif package_name.startswith("esp2-gateway-adapter"):
            import esp2_gateway_adapter
            return {
                "name": package_name,
                "installed": True,
                "version": getattr(esp2_gateway_adapter, "__version__", "unknown"),
                "location": esp2_gateway_adapter.__file__
            }
        else:
            __import__(package_name)
            module = sys.modules[package_name]
            return {
                "name": package_name,
                "installed": True,
                "version": getattr(module, "__version__", "unknown"),
                "location": getattr(module, "__file__", "unknown")
            }
    except ImportError as e:
        return {
            "name": package_name,
            "installed": False,
            "error": str(e),
            "version": None,
            "location": None
        }

def check_all_eltako_dependencies() -> None:
    """Check all Eltako integration dependencies."""
    print("🔍 Checking Eltako Integration Dependencies\n")

    # Dependencies from manifest.json
    dependencies = [
        ("eltako14bus", "0.0.61"),
        ("enocean", "0.60.1"),
        ("StrEnum", None),
        ("esp2-gateway-adapter", "0.2.11"),
    ]

    print("📋 Required Dependencies:")
    print("-" * 60)

    all_installed = True
    for dep_name, min_version in dependencies:
        result = check_dependency(dep_name, min_version)

        if result["installed"]:
            print(f"✅ {dep_name:<25} v{result['version']}")
            if result["location"]:
                print(f"   📁 {result['location']}")
        else:
            print(f"❌ {dep_name:<25} NOT INSTALLED")
            print(f"   Error: {result['error']}")
            all_installed = False
        print()

    if all_installed:
        print("🎉 All dependencies are installed!")
    else:
        print("💥 Some dependencies are missing!")
        print_installation_instructions()

def print_installation_instructions() -> None:
    """Print dependency installation instructions."""
    print("\n📦 Installation Instructions:")
    print("=" * 60)

    print("\n🏠 Home Assistant OS/Supervised:")
    print("Dependencies should install automatically when you add the integration.")
    print("If not, restart Home Assistant and try again.")

    print("\n🐳 Home Assistant Docker/Container:")
    print("# Enter the container:")
    print("docker exec -it homeassistant bash")
    print("# Install dependencies:")
    print("pip install eltako14bus==0.0.61 enocean>=0.60.1 strenum esp2-gateway-adapter==0.2.11")

    print("\n🖥️ Home Assistant Core:")
    print("# In your Home Assistant virtual environment:")
    print("pip install eltako14bus==0.0.61 enocean>=0.60.1 strenum esp2-gateway-adapter==0.2.11")

    print("\n⚠️ Note about StrEnum:")
    print("StrEnum in manifest.json should be 'strenum' (lowercase)")

def check_pip_packages() -> None:
    """Check installed packages via pip list."""
    print("\n🔍 Checking via pip list:")
    print("-" * 40)

    try:
        result = subprocess.run(
            ["pip", "list"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            lines = result.stdout.split('\n')
            eltako_packages = [line for line in lines if 'eltako' in line.lower() or 'enocean' in line.lower() or 'strenum' in line.lower() or 'esp2' in line.lower()]

            if eltako_packages:
                print("Found related packages:")
                for pkg in eltako_packages:
                    print(f"  {pkg}")
            else:
                print("No Eltako-related packages found in pip list")
        else:
            print(f"Error running pip list: {result.stderr}")

    except Exception as e:
        print(f"Could not run pip list: {e}")

def main():
    """Main function."""
    check_all_eltako_dependencies()
    check_pip_packages()

    print("\n🔧 Troubleshooting Tips:")
    print("-" * 40)
    print("1. Dependencies install when Home Assistant loads the integration")
    print("2. Check Home Assistant logs for installation errors")
    print("3. Restart Home Assistant after dependency issues")
    print("4. For Docker: dependencies might need manual installation")
    print("5. Check manifest.json for correct requirement specifications")

if __name__ == "__main__":
    main()