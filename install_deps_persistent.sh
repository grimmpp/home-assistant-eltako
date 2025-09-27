#!/bin/bash
# Script to install Eltako dependencies persistently in Home Assistant

echo "🔧 Installing Eltako dependencies persistently..."

# Create persistent python modules directory
mkdir -p /config/python_modules

# Install dependencies to persistent location
python -m pip install --target /config/python_modules \
    "eltako14bus>=0.0.61,<1.0.0" \
    "enocean>=0.60.1" \
    "strenum>=0.4.0" \
    "esp2-gateway-adapter>=0.2.11,<1.0.0"

echo "✅ Dependencies installed to /config/python_modules"

# Create or update Python path setup
cat > /config/python_modules/__init__.py << 'EOF'
"""Eltako dependencies module path setup."""
import sys
import os

# Add this directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
EOF

echo "📝 Created __init__.py for path setup"

# Create startup script for Home Assistant
cat > /config/shell_commands.yaml << 'EOF'
# Shell commands for Eltako setup
setup_eltako_python_path: |
  python3 -c "
  import sys
  import os
  path = '/config/python_modules'
  if path not in sys.path:
      sys.path.insert(0, path)
  print(f'Added {path} to Python path')
  "
EOF

echo "🎯 Created shell command configuration"
echo ""
echo "📋 Next steps:"
echo "1. Add to configuration.yaml:"
echo "   shell_command: !include shell_commands.yaml"
echo ""
echo "2. Restart Home Assistant"
echo ""
echo "3. Run this service to setup path:"
echo "   Developer Tools > Services > shell_command.setup_eltako_python_path"
echo ""
echo "4. Try adding Eltako integration"