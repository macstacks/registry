#!/usr/bin/env python3
"""Validate the MACSTACK registry: categories, software passports, entity/trigger/agent templates.

Usage: python3 scripts/validate.py
Exit code 0 = valid, 1 = errors.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).parent.parent
SLUG = re.compile(r"^[a-z0-9]+([-.][a-z0-9]+)*$")
LAYERS = {"data", "logic", "interface", "infrastructure"}
SW_TYPES = {"ready_made", "constructor", "framework", "library", "custom"}
FORMS = {"web", "cli", "desktop", "mobile", "api_service", "library"}
LICENSES = {"open_source", "saas", "proprietary"}
TRIGGER_TYPES = {"schedule", "webhook", "db_event", "form", "email", "queue", "manual"}
CHANNEL = (True, False, "partial")

errors = []


def err(msg):
    errors.append(msg)


cats_doc = json.load(open(ROOT / "software-categories.json"))
cats = {c["id"] for c in cats_doc["categories"]}
for c in cats_doc["categories"]:
    if not SLUG.match(c["id"]):
        err(f"categories: '{c['id']}' is not kebab-case")

for f in sorted((ROOT / "software").glob("*.json")):
    d = json.load(open(f))
    if d["id"] != f.stem:
        err(f"{f.name}: id != filename")
    if not SLUG.match(d["id"]):
        err(f"{f.name}: id not kebab-case")
    if d.get("category") not in cats:
        err(f"{f.name}: category '{d.get('category')}' not in software-categories.json")
    if d.get("type") not in SW_TYPES:
        err(f"{f.name}: bad type")
    if not set(d.get("layers", [])) <= LAYERS or not d.get("layers"):
        err(f"{f.name}: bad layers")
    if len(set(d.get("layers", []))) != len(d.get("layers", [])):
        err(f"{f.name}: duplicate layers")
    if not set(d.get("form", [])) <= FORMS:
        err(f"{f.name}: bad form")
    if d.get("license") not in LICENSES:
        err(f"{f.name}: bad license")
    ag = d.get("agentic", {})
    for k in ("mcp", "api", "cli"):
        if ag.get(k) not in CHANNEL:
            err(f"{f.name}: agentic.{k} must be true/false/'partial'")
    n = sum(1 for k in ("mcp", "api", "cli") if ag.get(k) is True)
    p = sum(1 for k in ("mcp", "api", "cli") if ag.get(k) == "partial")
    expected = "full" if n == 3 else "good" if n == 2 else "basic" if n == 1 else ("partial" if p else "none")
    if ag.get("rating") != expected:
        err(f"{f.name}: rating '{ag.get('rating')}' vs computed '{expected}'")

for f in sorted((ROOT / "entities").glob("*.json")):
    d = json.load(open(f))
    if d["id"] != f.stem:
        err(f"{f.name}: id != filename")
    if not d.get("name") or not d.get("attributes"):
        err(f"{f.name}: name/attributes required")
    for a in d.get("attributes", []):
        if "name" not in a or "type" not in a:
            err(f"{f.name}: attribute missing name/type")
    if "stores" in d or "master" in d:
        err(f"{f.name}: templates must NOT carry stores/master (stack-specific)")

for f in sorted((ROOT / "triggers").glob("*.json")):
    d = json.load(open(f))
    if d["id"] != f.stem:
        err(f"{f.name}: id != filename")
    if d.get("type") not in TRIGGER_TYPES:
        err(f"{f.name}: bad trigger type")

for f in sorted((ROOT / "agents").glob("*.json")):
    d = json.load(open(f))
    if d["id"] != f.stem:
        err(f"{f.name}: id != filename")
    for k in ("name", "model", "instructions"):
        if not d.get(k):
            err(f"{f.name}: {k} required")

if errors:
    print("ERRORS:")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print(f"registry OK: {len(cats)} categories, "
      f"{len(list((ROOT/'software').glob('*.json')))} software passports, "
      f"{len(list((ROOT/'entities').glob('*.json')))} entities, "
      f"{len(list((ROOT/'triggers').glob('*.json')))} triggers, "
      f"{len(list((ROOT/'agents').glob('*.json')))} agents")
