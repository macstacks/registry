# MACSTACK Registry

Reusable, machine-readable building blocks for
[`macstack.json`](https://github.com/macstacks/macstack) files. Tools (like the
[`macstack-dev`](https://github.com/Agents-Store/claude-plugins/tree/main/plugins/macstack-dev)
Claude plugin) read this registry instead of re-inventing values, so every stack
speaks the same vocabulary.

| Path | What it is | Reuse rule |
|---|---|---|
| [`software-categories.json`](software-categories.json) | The canonical category vocabulary for `software[].category` + slug rules | Linters check against it; a new niche = a kebab-case slug added via PR |
| [`software/`](software/) | **Software passports** — the stack-independent half of a `software[]` entry: category, type, form, license, layers, Agentic-IT-Ready passport, docs URL | Copy into your macstack.json and add the stack-specific half: `role`, `value`, `hosting`, `instances[]`, `cost`, `components[]` |
| [`entities/`](entities/) | **Entity templates** — typical business entities with attributes | Copy and add the stack-specific half: `stores[]` (software + instance + role) and the single `master` |
| [`triggers/`](triggers/) | **Trigger presets** — schedule/webhook/db-event/form/manual with config templates | Copy, set `software` + `instance`, replace the `<placeholders>` |
| [`agents/`](agents/) | **Managed-agent presets** — model + instructions + tools/invocations templates | Copy, replace the `<placeholders>` with your connection/workflow/trigger ids |

## Contributing

1. One file = one item; the filename equals the item's `id` (kebab-case:
   `trigger-dev`, not `trigger.dev`; `postgresql`, not `postgres`).
2. Software passports carry **no stack-specific fields** (no role/instances/cost) —
   those belong in each project's macstack.json.
3. `agentic.rating` must match the channels: 3×true = full, 2 = good, 1 = basic,
   only "partial" = partial, none = none.
4. Run the validator before a PR — CI runs the same check, plus its own tests
   (`python3 scripts/test_validate.py`):

   ```sh
   python3 scripts/validate.py \
     --marketplace <path-or-URL to Agents-Store/claude-plugins .claude-plugin/marketplace.json> \
     --schema <path-or-URL to macstacks/macstack schema/macstack.schema.json>
   ```

   - `--marketplace` (repeatable): every plugin name in `coverage-areas.json` `examples`
     must exist in one of the given marketplaces.
   - `--schema`: the area ids in `coverage-areas.json` must match the vocabulary the
     standard's `$defs/coverageArea` describes.
   - Both take a local path or an `https://` URL. Without a flag its check is skipped
     with a note, so a plain `python3 scripts/validate.py` still works offline; CI always
     passes both. `coverage-areas.json` structure (version, unique kebab-case ids, kind,
     name, description, examples) is checked in every run.

## Relation to the ecosystem

- The **standard** (schema, examples, linter): [macstacks/macstack](https://github.com/macstacks/macstack)
- This registry is also the machine-readable backend for the future Software
  Directory on macstack.ai (every passport carries the Agentic IT Ready rating:
  MCP + API + CLI).
