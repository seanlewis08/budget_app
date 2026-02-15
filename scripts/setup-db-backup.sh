#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Budget App — Database Backup Setup
#
# This script initializes a private Git repo at ~/BudgetApp
# for automatic database backups. Run this ONCE, then the
# sync daemon handles everything automatically.
#
# Prerequisites:
#   1. Create a PRIVATE repo on GitHub (e.g., budget-app-data)
#   2. Make sure your SSH key is set up with GitHub
#
# Usage:
#   bash scripts/setup-db-backup.sh
# ─────────────────────────────────────────────────────────────

set -e

BUDGET_DIR="$HOME/BudgetApp"
REPO_URL="${1:-git@github.com:seanlewis08/budget-app-data.git}"

echo "═══════════════════════════════════════════════"
echo "  Budget App — Database Backup Setup"
echo "═══════════════════════════════════════════════"
echo ""

# Check that the database exists
if [ ! -f "$BUDGET_DIR/budget.db" ]; then
    echo "ERROR: $BUDGET_DIR/budget.db not found."
    echo "Run the app first to create the database."
    exit 1
fi

cd "$BUDGET_DIR"

# Initialize Git repo if needed
if [ ! -d ".git" ]; then
    echo "→ Initializing Git repo at $BUDGET_DIR..."
    git init
else
    echo "→ Git repo already exists."
fi

# Create .gitignore (exclude logs and temp files)
cat > .gitignore << 'EOF'
# Only track the database — exclude everything else
logs/
*.db-journal
*.db-wal
*.db-shm
*.log
*.tmp
EOF

echo "→ Created .gitignore"

# Set up remote
EXISTING_REMOTE=$(git remote -v 2>/dev/null | grep origin || true)
if [ -z "$EXISTING_REMOTE" ]; then
    echo "→ Adding remote: $REPO_URL"
    git remote add origin "$REPO_URL"
else
    echo "→ Remote 'origin' already configured."
fi

# Initial commit
git add .gitignore budget.db
git commit -m "Initial database backup — $(date '+%Y-%m-%d %H:%M')" 2>/dev/null || echo "→ Nothing new to commit."

# Push
git branch -M main
echo "→ Pushing to remote..."
git push -u origin main

echo ""
echo "═══════════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  Your database will be backed up to GitHub"
echo "  automatically after every Plaid sync."
echo ""
echo "  Manual backup:  cd ~/BudgetApp && git add budget.db && git commit -m 'backup' && git push"
echo "  View logs:      cat ~/BudgetApp/logs/sync.log"
echo "═══════════════════════════════════════════════"
