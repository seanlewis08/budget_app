#!/usr/bin/env python3
"""
Build HTML documentation pages from the walkthrough markdown files.
Converts markdown to HTML and wraps in the site template.

Usage:
    python build-docs.py

Requires: pip install markdown
"""

import re
from pathlib import Path

try:
    import markdown
except ImportError:
    print("Installing markdown...")
    import subprocess
    subprocess.check_call(["pip", "install", "markdown", "--break-system-packages", "-q"])
    import markdown

WALKTHROUGH_DIR = Path(__file__).parent.parent / "walkthrough"
OUTPUT_DIR = Path(__file__).parent

PAGES = [
    ("01-project-setup.md", "01-project-setup.html", "Project Setup & Foundation"),
    ("02-database-and-models.md", "02-database-and-models.html", "Database Models & Backend Core"),
    ("03-plaid-integration.md", "03-plaid-integration.html", "Plaid Integration & Accounts"),
    ("04-categorization-engine.md", "04-categorization-engine.html", "Categorization Engine"),
    ("05-frontend-react.md", "05-frontend-react.html", "Frontend & React UI"),
    ("06-advanced-features.md", "06-advanced-features.html", "Advanced Features"),
    ("07-electron-and-deployment.md", "07-electron-and-deployment.html", "Electron & Deployment"),
]


def get_nav_html(active_file):
    links = []
    for md_file, html_file, title in PAGES:
        num = md_file[:2]
        active = ' class="active"' if html_file == active_file else ""
        links.append(
            f'        <a href="{html_file}"{active}>\n'
            f'          <span class="docs-nav-num">{num}</span>\n'
            f"          {title}\n"
            f"        </a>"
        )
    return "\n".join(links)


def get_prev_next(current_index):
    prev_html = ""
    next_html = ""
    if current_index > 0:
        _, href, title = PAGES[current_index - 1]
        prev_html = (
            f'<a href="{href}" class="docs-nav-link prev">\n'
            f'  <span class="label">&larr; Previous</span>\n'
            f'  <span class="title">{title}</span>\n'
            f"</a>"
        )
    if current_index < len(PAGES) - 1:
        _, href, title = PAGES[current_index + 1]
        next_html = (
            f'<a href="{href}" class="docs-nav-link next">\n'
            f'  <span class="label">Next &rarr;</span>\n'
            f'  <span class="title">{title}</span>\n'
            f"</a>"
        )
    return prev_html, next_html


TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} — Budget App Docs</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="../styles.css" />
  <link rel="stylesheet" href="docs.css" />
</head>
<body>
  <nav class="nav scrolled" id="nav">
    <div class="nav-inner">
      <a href="../" class="nav-logo">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none"><rect width="28" height="28" rx="6" fill="#6c5ce7"/><path d="M7 20V8h4.5c2.5 0 4 1.2 4 3.2 0 1.5-.9 2.5-2.2 2.9l2.8 5.9h-2.8l-2.4-5.3H9.4V20H7zm2.4-7.2h2c1.2 0 1.8-.6 1.8-1.5s-.6-1.5-1.8-1.5h-2v3z" fill="white"/><circle cx="20" cy="20" r="4" fill="#a29bfe"/></svg>
        <span>Budget App</span>
      </a>
      <div class="nav-links">
        <a href="../#features">Features</a>
        <a href="./">Docs</a>
        <a href="https://github.com/seanlewis08/budget-app" class="nav-cta" target="_blank" rel="noopener">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
          GitHub
        </a>
      </div>
    </div>
  </nav>

  <div class="docs-layout">
    <aside class="docs-sidebar">
      <h3>Walkthrough</h3>
      <nav class="docs-nav">
{nav}
      </nav>
    </aside>

    <main class="docs-content">
      <div class="md-content">
{content}
      </div>
      <div class="docs-nav-footer">
        {prev}
        {next}
      </div>
    </main>
  </div>
</body>
</html>
"""


def build():
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc"],
        output_format="html5",
    )

    for i, (md_file, html_file, title) in enumerate(PAGES):
        md_path = WALKTHROUGH_DIR / md_file
        if not md_path.exists():
            print(f"  SKIP {md_file} (not found)")
            continue

        md.reset()
        content = md_path.read_text()
        html_content = md.convert(content)

        nav_html = get_nav_html(html_file)
        prev_html, next_html = get_prev_next(i)

        output = TEMPLATE.format(
            title=title,
            nav=nav_html,
            content=html_content,
            prev=prev_html,
            next=next_html,
        )

        out_path = OUTPUT_DIR / html_file
        out_path.write_text(output)
        print(f"  Built {html_file}")

    print(f"\nDone! {len(PAGES)} pages built in {OUTPUT_DIR}")


if __name__ == "__main__":
    build()
