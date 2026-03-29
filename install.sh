#!/bin/bash
# ARC — Adaptive Rule Context
# Installation script
# Usage: ./install.sh

set -e

ARC_DIR="$HOME/.arc"
HOOKS_DIR="$HOME/.claude/hooks"
SETTINGS_FILE="$HOME/.claude/settings.json"

echo "Installing ARC — Adaptive Rule Context"
echo "======================================="

# 1. Create .arc domain directory
echo ""
echo "1. Setting up domains directory at $ARC_DIR..."
mkdir -p "$ARC_DIR/sessions"

# Copy example domains
for domain in domains/*; do
  name=$(basename "$domain")
  dest="$ARC_DIR/$name"
  if [ -f "$dest" ]; then
    echo "   ⚠  $name already exists — skipping (keeping yours)"
  else
    cp "$domain" "$dest"
    echo "   ✓  $name"
  fi
done

# 2. Install hooks
echo ""
echo "2. Installing hooks to $HOOKS_DIR..."
mkdir -p "$HOOKS_DIR"

for hook in hooks/*; do
  name=$(basename "$hook")
  dest="$HOOKS_DIR/$name"
  if [ -f "$dest" ]; then
    echo "   ⚠  $name already exists — skipping (keeping yours)"
  else
    cp "$hook" "$dest"
    chmod +x "$dest"
    echo "   ✓  $name"
  fi
done

# 3. Configure Claude Code settings
echo ""
echo "3. Configuring Claude Code settings..."

if [ ! -f "$SETTINGS_FILE" ]; then
  echo '{}' > "$SETTINGS_FILE"
fi

# Check if arc-hook is already registered
if grep -q "arc-hook.py" "$SETTINGS_FILE" 2>/dev/null; then
  echo "   ⚠  arc-hook.py already registered in settings.json"
else
  echo ""
  echo "   Add the following to your $SETTINGS_FILE under 'hooks':"
  echo ""
  cat << 'EOF'
  {
    "hooks": {
      "UserPromptSubmit": [
        {
          "matcher": "",
          "hooks": [
            {
              "type": "command",
              "command": "python3 ~/.claude/hooks/arc-hook.py"
            }
          ]
        }
      ],
      "PostToolUse": [
        {
          "matcher": "Bash",
          "hooks": [
            {
              "type": "command",
              "command": "python3 ~/.claude/hooks/output-trimmer.py"
            }
          ]
        }
      ],
      "PreToolUse": [
        {
          "matcher": "Bash",
          "hooks": [
            {
              "type": "command",
              "command": "python3 ~/.claude/hooks/secret-scanner.py"
            }
          ]
        }
      ]
    }
  }
EOF
  echo ""
  echo "   (Automatic settings.json merge coming in a future version)"
fi

echo ""
echo "======================================="
echo "✓ ARC installed!"
echo ""
echo "Next steps:"
echo "  1. Edit ~/.arc/global to add your own rules"
echo "  2. Create new domains in ~/.arc/ following the examples"
echo "  3. Update ~/.arc/manifest to register your domains"
echo "  4. Restart Claude Code"
echo ""
echo "Docs: https://github.com/vasyl-pavlyuchok/arc"
