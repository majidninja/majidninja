#!/usr/bin/env python3
"""Turn README.md (GitHub flavour) into the GitLab profile README.

Usage: python3 scripts/gitlab_readme.py OUT_DIR

GitLab strips <picture>, so each card becomes its light <img>. Project links
point at the GitLab copies, and the GitLab button becomes a GitHub button.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS = ["whatchanged-action", "whatchanged", "rotcheck"]


def convert(md):
    md = re.sub(r"[ \t]*<picture>\s*<source[^>]*>\s*(<img[^>]*>)\s*</picture>", r"  \1", md)
    md = md.replace(
        '<a href="https://gitlab.com/majidninja"><img alt="GitLab" '
        'src="https://img.shields.io/badge/GitLab-0d1117?style=for-the-badge&logo=gitlab&logoColor=FC6D26"></a>',
        '<a href="https://github.com/majidninja"><img alt="GitHub" '
        'src="https://img.shields.io/badge/GitHub-0d1117?style=for-the-badge&logo=github&logoColor=white"></a>')
    for p in PROJECTS:
        md = md.replace("(https://github.com/majidninja/%s)" % p, "(https://gitlab.com/majidninja/%s)" % p)
    md = md.replace(
        "Merged pull requests in other people's projects. This table updates itself every week.",
        "Merged pull requests in other people's projects (they live on GitHub). "
        "This table updates itself every week.")
    md = re.sub(r"<!--.*?-->\n*", "", md, count=1, flags=re.S)  # GitHub-specific source note
    md = md.replace("username=majidninja&", "username=majidninja-gitlab&")
    return md


def main():
    out = sys.argv[1]
    with open(os.path.join(ROOT, "README.md")) as f:
        md = convert(f.read())
    if "<picture>" in md:
        raise SystemExit("a <picture> block was not converted")
    with open(os.path.join(out, "README.md"), "w") as f:
        f.write(md)


if __name__ == "__main__":
    main()
