#!/usr/bin/env python
"""Fix eltako imports to use conditional loading for Home Assistant compatibility."""

import os
import re
from pathlib import Path

# Template for conditional imports
CONDITIONAL_IMPORT_TEMPLATE = '''# Conditional imports to avoid early dependency loading
try:
    {original_imports}
    ELTAKO_DEPENDENCIES_AVAILABLE = True
except ImportError:
    # Dependencies not yet installed, will be imported later
    {null_assignments}
    ELTAKO_DEPENDENCIES_AVAILABLE = False


def _ensure_dependencies():
    """Ensure eltako dependencies are loaded."""
    global {globals_list}, ELTAKO_DEPENDENCIES_AVAILABLE

    if not ELTAKO_DEPENDENCIES_AVAILABLE:
        try:
            {lazy_imports}
            {assignments}
            ELTAKO_DEPENDENCIES_AVAILABLE = True
        except ImportError as e:
            raise ImportError(f"Eltako dependencies not available: {{e}}")

'''

def extract_eltako_imports(file_content):
    """Extract all eltako-related imports from file content."""
    import_lines = []

    # Find all from eltako... import ... lines
    pattern = r'^from (eltako[^.]*(?:\.[^.]*)*) import (.+)$'

    for line in file_content.split('\n'):
        line = line.strip()
        if line.startswith('from eltako') and ' import ' in line:
            import_lines.append(line)

    return import_lines

def parse_imports(import_lines):
    """Parse import lines and extract module and imported items."""
    imports = {}

    for line in import_lines:
        if 'from eltako' in line and ' import ' in line:
            # Parse: from eltakobus.util import AddressExpression, b2a
            parts = line.split(' import ')
            if len(parts) == 2:
                module = parts[0].replace('from ', '')
                items = parts[1]

                if module not in imports:
                    imports[module] = []

                # Handle wildcard imports
                if items.strip() == '*':
                    imports[module].append('*')
                else:
                    # Split by comma and clean
                    for item in items.split(','):
                        item = item.strip()
                        if item:
                            imports[module].append(item)

    return imports

def generate_conditional_import(imports):
    """Generate conditional import code."""
    if not imports:
        return ""

    original_imports = []
    null_assignments = []
    lazy_imports = []
    assignments = []
    all_symbols = []

    for module, items in imports.items():
        if '*' in items:
            # Handle wildcard imports
            original_imports.append(f"from {module} import *")
            # For wildcard, we can't easily null assign, so skip
            continue

        items_str = ', '.join(items)
        original_imports.append(f"from {module} import {items_str}")

        # Create null assignments
        for item in items:
            null_assignments.append(f"{item} = None")
            all_symbols.append(item)

        # Create lazy imports with aliases
        lazy_items = [f"{item} as _{item}" for item in items]
        lazy_imports.append(f"from {module} import {', '.join(lazy_items)}")

        # Create assignments
        for item in items:
            assignments.append(f"{item} = _{item}")

    if not all_symbols:
        return ""

    return CONDITIONAL_IMPORT_TEMPLATE.format(
        original_imports='\n    '.join(original_imports),
        null_assignments='\n    '.join(null_assignments),
        globals_list=', '.join(all_symbols),
        lazy_imports='\n            '.join(lazy_imports),
        assignments='\n            '.join(assignments)
    )

def fix_file(file_path):
    """Fix imports in a single file."""
    print(f"Processing {file_path}...")

    with open(file_path, 'r') as f:
        content = f.read()

    # Skip files that already have conditional imports
    if 'ELTAKO_DEPENDENCIES_AVAILABLE' in content:
        print(f"  Skipping {file_path} - already has conditional imports")
        return False

    # Extract eltako imports
    import_lines = extract_eltako_imports(content)

    if not import_lines:
        print(f"  No eltako imports found in {file_path}")
        return False

    print(f"  Found {len(import_lines)} eltako imports")

    # Parse imports
    imports = parse_imports(import_lines)

    # Generate conditional import code
    conditional_code = generate_conditional_import(imports)

    if not conditional_code:
        print(f"  Could not generate conditional imports for {file_path}")
        return False

    # Remove original import lines
    lines = content.split('\n')
    new_lines = []
    skip_next_empty = False

    for line in lines:
        if any(imp.strip() == line.strip() for imp in import_lines):
            # Skip this import line
            skip_next_empty = True
            continue
        elif skip_next_empty and line.strip() == '':
            # Skip empty line after imports
            skip_next_empty = False
            continue
        else:
            new_lines.append(line)
            skip_next_empty = False

    # Find insertion point (after other imports, before functions/classes)
    insertion_point = 0
    for i, line in enumerate(new_lines):
        if (line.strip().startswith('from homeassistant') or
            line.strip().startswith('import ') or
            line.strip().startswith('from .')):
            insertion_point = i + 1
        elif line.strip().startswith(('def ', 'class ', 'async def ')):
            break

    # Insert conditional import code
    new_lines.insert(insertion_point, '\n' + conditional_code)

    # Write back
    with open(file_path, 'w') as f:
        f.write('\n'.join(new_lines))

    print(f"  Fixed {file_path}")
    return True

def main():
    """Fix all platform files."""
    base_path = Path("custom_components/eltako")

    # Platform files to fix
    platform_files = [
        "sensor.py",
        "light.py",
        "switch.py",
        "cover.py",
        "binary_sensor.py",
        "button.py",
        "climate.py",
        "device.py",
        "schema.py"
    ]

    fixed_count = 0

    for filename in platform_files:
        file_path = base_path / filename
        if file_path.exists():
            if fix_file(file_path):
                fixed_count += 1
        else:
            print(f"File not found: {file_path}")

    print(f"\nFixed {fixed_count} files")

    if fixed_count > 0:
        print("\n⚠️  Important notes:")
        print("1. Review the generated conditional imports")
        print("2. Add _ensure_dependencies() calls where needed")
        print("3. Test the integration loading")
        print("4. Some wildcard imports (*) may need manual fixing")

if __name__ == "__main__":
    main()