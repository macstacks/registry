#!/usr/bin/env python3
"""Validate the MACSTACK registry: categories, software passports, entity/trigger/agent templates.

Usage: python3 scripts/validate.py [--marketplace PATH_OR_URL ...] [--schema PATH_OR_URL]

  --marketplace  a plugin marketplace.json (repeatable). When given, every plugin name in
                 coverage-areas.json `examples` must be a plugins[].name in at least one of them.
  --schema       the standard's macstack.schema.json. When given, the area ids in
                 coverage-areas.json must match the vocabulary its $defs/coverageArea describes.

Both take a local path or an http(s) URL; a check whose flag is absent is skipped with a note,
so a local run without network still works. Exit code 0 = valid, 1 = errors.
"""
import argparse
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).parent.parent
SLUG = re.compile(r"^[a-z0-9]+([-.][a-z0-9]+)*$")
LAYERS = {"data", "logic", "interface", "infrastructure"}
SW_TYPES = {"ready_made", "constructor", "framework", "library", "custom"}
FORMS = {"web", "cli", "desktop", "mobile", "api_service", "library"}
LICENSES = {"open_source", "saas", "proprietary"}
TRIGGER_TYPES = {"schedule", "webhook", "db_event", "form", "email", "queue", "manual"}
CHANNEL = (True, False, "partial")
AREA_KINDS = {"section", "cross-cutting"}
WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

ap = argparse.ArgumentParser(description="Validate the MACSTACK registry.")
ap.add_argument("--marketplace", action="append", default=[], metavar="PATH_OR_URL",
                help="plugin marketplace.json to check coverage-areas examples against (repeatable)")
ap.add_argument("--schema", metavar="PATH_OR_URL",
                help="macstack.schema.json to check the coverage-area ids against")
args = ap.parse_args()

errors = []
notes = []


def err(msg):
    errors.append(msg)


def load(src):
    """JSON from a local path or an http(s) URL."""
    if re.match(r"https?://", src):
        req = urllib.request.Request(src, headers={"User-Agent": "macstack-registry-validate"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    return json.load(open(src))


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

# coverage-areas.json: structure, then (optionally) cross-checks against the plugins and the standard
areas_doc = None
try:
    areas_doc = json.load(open(ROOT / "coverage-areas.json"))
except (OSError, ValueError) as e:
    err(f"coverage-areas.json: cannot read ({e})")
if areas_doc is not None:
    if not isinstance(areas_doc.get("version"), str) or not areas_doc["version"].strip():
        err("coverage-areas: version required")
    areas = areas_doc.get("areas")
    if not isinstance(areas, list) or not areas:
        err("coverage-areas: areas must be a non-empty array")
        areas = []
    seen = set()
    for i, a in enumerate(areas, 1):
        aid = a.get("id")
        label = f"area '{aid}'" if isinstance(aid, str) and aid else f"area #{i}"
        if not isinstance(aid, str) or not aid:
            err(f"coverage-areas: {label}: id required")
        else:
            if not SLUG.match(aid):
                err(f"coverage-areas: {label}: '{aid}' is not kebab-case")
            if aid in seen:
                err(f"coverage-areas: duplicate area id '{aid}'")
            seen.add(aid)
        if "kind" not in a:
            err(f"coverage-areas: {label}: kind required")
        elif a["kind"] not in AREA_KINDS:
            err(f"coverage-areas: {label}: kind '{a['kind']}' is not one of {sorted(AREA_KINDS)}")
        for k in ("name", "description"):
            if not isinstance(a.get(k), str) or not a[k].strip():
                err(f"coverage-areas: {label}: {k} required")
        ex = a.get("examples")
        if "examples" not in a:
            err(f"coverage-areas: {label}: examples required")
        elif not isinstance(ex, list) or not all(isinstance(x, str) and x for x in ex):
            err(f"coverage-areas: {label}: examples must be an array of strings (may be empty)")

    ids = [a["id"] for a in areas if isinstance(a.get("id"), str)]

    # every example must be a real plugin: the lists drifted for weeks once with CI green
    if not args.marketplace:
        notes.append("note: --marketplace not given, skipping the plugin-name check of coverage-areas examples")
    else:
        plugins = set()
        for src in args.marketplace:
            try:
                plugs = load(src)["plugins"]
                plugins |= {p["name"] for p in plugs}
            except Exception as e:
                err(f"marketplace {src}: cannot read plugins[].name ({type(e).__name__}: {e})")
        if plugins:
            for a in areas:
                ex = a.get("examples")
                if isinstance(ex, list):
                    for name in ex:
                        if isinstance(name, str) and name not in plugins:
                            err(f"coverage-areas: area '{a.get('id')}': example '{name}' is not a plugin "
                                f"in any given marketplace")

    # the standard's $defs/coverageArea must describe the same vocabulary
    if not args.schema:
        notes.append("note: --schema not given, skipping the cross-check of area ids with the standard")
    else:
        try:
            d = load(args.schema)["$defs"]["coverageArea"]
        except Exception as e:
            err(f"schema {args.schema}: cannot read $defs/coverageArea ({type(e).__name__}: {e})")
            d = None
        if d is not None:
            if isinstance(d.get("enum"), list):
                vocab = set(d["enum"])
                for i in sorted(set(ids) - vocab):
                    err(f"schema $defs/coverageArea: enum lacks registry area id '{i}'")
                for i in sorted(vocab - set(ids)):
                    err(f"schema $defs/coverageArea: enum has '{i}', which is not in coverage-areas.json")
            elif isinstance(d.get("description"), str) and d["description"].strip():
                words = set(WORD.findall(d["description"].lower()))
                for i in ids:
                    if i not in words:
                        err(f"schema $defs/coverageArea: description does not mention registry area id '{i}'")
            else:
                err("schema $defs/coverageArea: neither an enum nor a description names the vocabulary")

for n in notes:
    print(n)
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
