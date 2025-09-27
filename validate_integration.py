#!/usr/bin/env python
"""Validate the Eltako integration structure and basic functionality."""
import json
import sys
from pathlib import Path
from typing import Dict, Any

def validate_manifest() -> Dict[str, Any]:
    """Validate manifest.json exists and has required fields."""
    print("🔍 Validating manifest.json...")

    manifest_path = Path("custom_components/eltako/manifest.json")
    if not manifest_path.exists():
        print("❌ manifest.json not found")
        return {"valid": False, "error": "manifest.json not found"}

    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in manifest.json: {e}")
        return {"valid": False, "error": f"Invalid JSON: {e}"}

    required_fields = ["domain", "name", "version", "documentation", "requirements"]
    missing_fields = [field for field in required_fields if field not in manifest]

    if missing_fields:
        print(f"❌ Missing required fields: {missing_fields}")
        return {"valid": False, "error": f"Missing fields: {missing_fields}"}

    if manifest["domain"] != "eltako":
        print(f"❌ Domain should be 'eltako', got '{manifest['domain']}'")
        return {"valid": False, "error": f"Wrong domain: {manifest['domain']}"}

    print("✅ manifest.json is valid")
    return {"valid": True, "manifest": manifest}

def validate_file_structure() -> Dict[str, Any]:
    """Validate the integration file structure."""
    print("🔍 Validating file structure...")

    base_path = Path("custom_components/eltako")
    required_files = [
        "__init__.py",
        "config_flow.py",
        "const.py",
        "manifest.json"
    ]

    missing_files = []
    for file_name in required_files:
        file_path = base_path / file_name
        if not file_path.exists():
            missing_files.append(file_name)

    if missing_files:
        print(f"❌ Missing required files: {missing_files}")
        return {"valid": False, "error": f"Missing files: {missing_files}"}

    # Check for platform files
    platform_files = ["sensor.py", "light.py", "switch.py"]
    existing_platforms = []
    for platform_file in platform_files:
        platform_path = base_path / platform_file
        if platform_path.exists():
            existing_platforms.append(platform_file.replace(".py", ""))

    print(f"✅ File structure is valid. Found platforms: {existing_platforms}")
    return {"valid": True, "platforms": existing_platforms}

def validate_init_file() -> Dict[str, Any]:
    """Validate __init__.py has required functions."""
    print("🔍 Validating __init__.py...")

    init_path = Path("custom_components/eltako/__init__.py")
    if not init_path.exists():
        print("❌ __init__.py not found")
        return {"valid": False, "error": "__init__.py not found"}

    try:
        with open(init_path) as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Error reading __init__.py: {e}")
        return {"valid": False, "error": f"Read error: {e}"}

    required_functions = ["async_setup", "async_setup_entry", "async_unload_entry"]
    missing_functions = []

    for func_name in required_functions:
        if f"def {func_name}" not in content and f"async def {func_name}" not in content:
            missing_functions.append(func_name)

    if missing_functions:
        print(f"❌ Missing required functions: {missing_functions}")
        return {"valid": False, "error": f"Missing functions: {missing_functions}"}

    print("✅ __init__.py has required functions")
    return {"valid": True}

def validate_config_flow() -> Dict[str, Any]:
    """Validate config_flow.py exists and has required classes."""
    print("🔍 Validating config_flow.py...")

    config_flow_path = Path("custom_components/eltako/config_flow.py")
    if not config_flow_path.exists():
        print("❌ config_flow.py not found")
        return {"valid": False, "error": "config_flow.py not found"}

    try:
        with open(config_flow_path) as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Error reading config_flow.py: {e}")
        return {"valid": False, "error": f"Read error: {e}"}

    required_classes = ["EltakoFlowHandler"]
    missing_classes = []

    for class_name in required_classes:
        if f"class {class_name}" not in content:
            missing_classes.append(class_name)

    if missing_classes:
        print(f"❌ Missing required classes: {missing_classes}")
        return {"valid": False, "error": f"Missing classes: {missing_classes}"}

    print("✅ config_flow.py has required classes")
    return {"valid": True}

def validate_test_structure() -> Dict[str, Any]:
    """Validate test structure."""
    print("🔍 Validating test structure...")

    test_path = Path("tests_new")
    if not test_path.exists():
        print("❌ tests_new directory not found")
        return {"valid": False, "error": "tests_new directory not found"}

    test_files = list(test_path.glob("test_*.py"))
    if not test_files:
        print("❌ No test files found")
        return {"valid": False, "error": "No test files found"}

    required_test_files = [
        "test_init.py",
        "test_config_flow.py",
        "test_coordinator.py"
    ]

    existing_test_files = [f.name for f in test_files]
    missing_test_files = [f for f in required_test_files if f not in existing_test_files]

    if missing_test_files:
        print(f"⚠️  Missing recommended test files: {missing_test_files}")

    print(f"✅ Test structure is valid. Found {len(test_files)} test files")
    return {"valid": True, "test_files": existing_test_files}

def count_test_functions() -> Dict[str, Any]:
    """Count test functions in test files."""
    print("🔍 Counting test functions...")

    test_path = Path("tests_new")
    test_files = list(test_path.glob("test_*.py"))

    total_tests = 0
    test_counts = {}

    for test_file in test_files:
        try:
            with open(test_file) as f:
                content = f.read()

            # Count test functions (def test_* and async def test_*)
            test_functions = content.count("def test_") + content.count("async def test_")
            test_counts[test_file.name] = test_functions
            total_tests += test_functions

        except Exception as e:
            print(f"⚠️  Error reading {test_file}: {e}")
            test_counts[test_file.name] = 0

    print(f"✅ Found {total_tests} test functions across {len(test_files)} files")
    return {"valid": True, "total_tests": total_tests, "test_counts": test_counts}

def main():
    """Run all validations."""
    print("🚀 Starting Eltako Integration Validation\n")

    validations = [
        ("Manifest", validate_manifest),
        ("File Structure", validate_file_structure),
        ("Init File", validate_init_file),
        ("Config Flow", validate_config_flow),
        ("Test Structure", validate_test_structure),
        ("Test Count", count_test_functions),
    ]

    results = {}
    all_valid = True

    for name, validation_func in validations:
        try:
            result = validation_func()
            results[name] = result
            if not result.get("valid", True):
                all_valid = False
        except Exception as e:
            print(f"❌ Error during {name} validation: {e}")
            results[name] = {"valid": False, "error": str(e)}
            all_valid = False
        print()  # Empty line for readability

    # Summary
    print("📊 Validation Summary:")
    print("=" * 50)

    for name, result in results.items():
        status = "✅ PASS" if result.get("valid", True) else "❌ FAIL"
        print(f"{name:<20} {status}")
        if not result.get("valid", True) and "error" in result:
            print(f"                     Error: {result['error']}")

    print()
    if all_valid:
        print("🎉 All validations passed! The integration structure looks good.")

        # Show summary stats
        if "Test Count" in results and results["Test Count"].get("valid"):
            total_tests = results["Test Count"].get("total_tests", 0)
            print(f"📈 Integration contains {total_tests} test functions")

        return 0
    else:
        print("💥 Some validations failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())