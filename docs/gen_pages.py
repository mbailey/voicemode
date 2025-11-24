#!/usr/bin/env python3
"""
Generate documentation pages for MkDocs.
This script is run by mkdocs-gen-files plugin during the build process.
"""
import mkdocs_gen_files
import re

# Read the root README.md
with open("README.md", "r") as f:
    readme_content = f.read()

# Fix relative links by removing docs/ prefix
readme_content = re.sub(r'\[([^\]]+)\]\(docs/([^)]+)\)', r'[\1](\2)', readme_content)

# Write the processed README to the virtual docs directory
with mkdocs_gen_files.open("README.md", "w") as f:
    f.write(readme_content)

# Set the edit path to point to the actual README.md in root
mkdocs_gen_files.set_edit_path("README.md", "../README.md")