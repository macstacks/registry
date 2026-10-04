#!/usr/bin/env python3
"""Tests for scripts/validate.py: the coverage-areas checks.

Usage: python3 scripts/test_validate.py
Plain stdlib (unittest, no pytest, no network). Every test builds a throwaway
registry in a temp dir, copies the real validate.py into it (the script finds its
root from its own location) and runs it as a subprocess, so the exit code and the
printed messages are what CI sees.
"""
import functools
import http.server
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

REAL_ROOT = pathlib.Path(__file__).parent.parent
VALIDATE = REAL_ROOT / "scripts" / "validate.py"


def area(id, examples=None, **over):
    a = {"id": id, "kind": "section", "name": id.title(), "description": f"About {id}",
         "examples": [] if examples is None else examples}
    a.update(over)
    return a


def coverage(*areas, **over):
    d = {"version": "1.0.0", "areas": list(areas)}
    d.update(over)
    return d


def marketplace(*names):
    return {"name": "test-market", "plugins": [{"name": n, "source": f"./{n}"} for n in names]}


def schema(description):
    return {"$defs": {"coverageArea": {"$ref": "#/$defs/slug", "description": description}}}


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "registry"
        (self.root / "scripts").mkdir(parents=True)
        for d in ("software", "entities", "triggers", "agents"):
            (self.root / d).mkdir()
        shutil.copy(VALIDATE, self.root / "scripts" / "validate.py")
        self.write("software-categories.json", {"categories": [{"id": "crm"}]})
        self.write("coverage-areas.json", coverage(area("alpha", ["plug-a"]), area("beta-two", ["plug-b"])))
        self.inputs = self.tmp / "inputs"
        self.inputs.mkdir()

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data))

    def put(self, name, data):
        p = self.inputs / name
        p.write_text(json.dumps(data))
        return str(p)

    def run_validate(self, *args):
        r = subprocess.run([sys.executable, str(self.root / "scripts" / "validate.py"), *args],
                           capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout + r.stderr

    def assertFails(self, out_code, out, *fragments):
        self.assertEqual(out_code, 1, out)
        for f in fragments:
            self.assertIn(f, out)

    def assertPasses(self, code, out):
        self.assertEqual(code, 0, out)
        self.assertIn("registry OK", out)

    def serve_inputs(self):
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(self.inputs))
        handler.log_message = lambda *a, **k: None
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}"


class CoverageStructure(ValidateTest):
    def test_valid_file_passes_and_notes_skipped_checks(self):
        code, out = self.run_validate()
        self.assertPasses(code, out)
        self.assertIn("--marketplace not given", out)
        self.assertIn("--schema not given", out)

    def test_missing_file_is_an_error(self):
        (self.root / "coverage-areas.json").unlink()
        code, out = self.run_validate()
        self.assertFails(code, out, "coverage-areas.json")

    def test_missing_version(self):
        self.write("coverage-areas.json", {"areas": [area("alpha")]})
        code, out = self.run_validate()
        self.assertFails(code, out, "coverage-areas: version")

    def test_empty_version(self):
        self.write("coverage-areas.json", coverage(area("alpha"), version=""))
        code, out = self.run_validate()
        self.assertFails(code, out, "coverage-areas: version")

    def test_areas_must_be_a_list(self):
        self.write("coverage-areas.json", {"version": "1.0.0", "areas": {}})
        code, out = self.run_validate()
        self.assertFails(code, out, "coverage-areas: areas")

    def test_id_not_kebab_case(self):
        self.write("coverage-areas.json", coverage(area("Not_Kebab")))
        code, out = self.run_validate()
        self.assertFails(code, out, "'Not_Kebab' is not kebab-case")

    def test_duplicate_id(self):
        self.write("coverage-areas.json", coverage(area("alpha"), area("alpha")))
        code, out = self.run_validate()
        self.assertFails(code, out, "duplicate area id 'alpha'")

    def test_each_required_field(self):
        for field in ("id", "kind", "name", "description", "examples"):
            with self.subTest(field=field):
                a = area("alpha")
                del a[field]
                self.write("coverage-areas.json", coverage(a))
                code, out = self.run_validate()
                self.assertFails(code, out, f"{field} required")

    def test_empty_name_or_description(self):
        for field in ("name", "description"):
            with self.subTest(field=field):
                self.write("coverage-areas.json", coverage(area("alpha", **{field: " "})))
                code, out = self.run_validate()
                self.assertFails(code, out, f"area 'alpha': {field} required")

    def test_unknown_kind(self):
        self.write("coverage-areas.json", coverage(area("alpha", kind="mystery")))
        code, out = self.run_validate()
        self.assertFails(code, out, "area 'alpha': kind 'mystery'")

    def test_examples_must_be_an_array_of_strings(self):
        for bad in ("plug-a", {"x": 1}, [1], [None]):
            with self.subTest(bad=bad):
                self.write("coverage-areas.json", coverage(area("alpha", examples=bad)))
                code, out = self.run_validate()
                self.assertFails(code, out, "area 'alpha': examples must be an array of strings")

    def test_empty_examples_are_allowed(self):
        self.write("coverage-areas.json", coverage(area("alpha", examples=[])))
        code, out = self.run_validate()
        self.assertPasses(code, out)

    def test_real_registry_file_passes_the_structure_check(self):
        r = subprocess.run([sys.executable, str(VALIDATE)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class PluginNames(ValidateTest):
    def test_known_names_pass(self):
        code, out = self.run_validate("--marketplace", self.put("m.json", marketplace("plug-a", "plug-b", "extra")))
        self.assertPasses(code, out)
        self.assertNotIn("--marketplace not given", out)

    def test_unknown_name_names_area_and_plugin(self):
        code, out = self.run_validate("--marketplace", self.put("m.json", marketplace("plug-a")))
        self.assertFails(code, out, "area 'beta-two'", "'plug-b'")
        self.assertNotIn("area 'alpha'", out)

    def test_name_in_any_one_of_several_marketplaces_is_enough(self):
        code, out = self.run_validate("--marketplace", self.put("m1.json", marketplace("plug-a")),
                                      "--marketplace", self.put("m2.json", marketplace("plug-b")))
        self.assertPasses(code, out)

    def test_name_in_no_marketplace_fails_with_several(self):
        code, out = self.run_validate("--marketplace", self.put("m1.json", marketplace("plug-a")),
                                      "--marketplace", self.put("m2.json", marketplace("other")))
        self.assertFails(code, out, "area 'beta-two'", "'plug-b'")

    def test_unknown_name_is_ignored_without_the_flag(self):
        code, out = self.run_validate()
        self.assertPasses(code, out)

    def test_unreadable_marketplace_is_an_error(self):
        code, out = self.run_validate("--marketplace", str(self.inputs / "nope.json"))
        self.assertFails(code, out, "marketplace", "nope.json")

    def test_marketplace_without_plugins_is_an_error(self):
        code, out = self.run_validate("--marketplace", self.put("m.json", {"name": "x"}))
        self.assertFails(code, out, "marketplace", "plugins")

    def test_marketplace_over_http(self):
        self.put("m.json", marketplace("plug-a", "plug-b"))
        base = self.serve_inputs()
        code, out = self.run_validate("--marketplace", f"{base}/m.json")
        self.assertPasses(code, out)

    def test_marketplace_over_http_with_unknown_name(self):
        self.put("m.json", marketplace("plug-a"))
        base = self.serve_inputs()
        code, out = self.run_validate("--marketplace", f"{base}/m.json")
        self.assertFails(code, out, "area 'beta-two'", "'plug-b'")

    def test_unfetchable_url_is_an_error(self):
        base = self.serve_inputs()
        code, out = self.run_validate("--marketplace", f"{base}/missing.json")
        self.assertFails(code, out, "marketplace", "missing.json")


class StandardSchema(ValidateTest):
    def test_all_ids_in_description_pass(self):
        code, out = self.run_validate("--schema", self.put("s.json", schema("Areas: alpha, beta-two.")))
        self.assertPasses(code, out)
        self.assertNotIn("--schema not given", out)

    def test_missing_id_is_reported_by_name(self):
        code, out = self.run_validate("--schema", self.put("s.json", schema("Areas: alpha only.")))
        self.assertFails(code, out, "'beta-two'", "coverageArea")
        self.assertNotIn("'alpha'", out)

    def test_every_missing_id_is_reported(self):
        code, out = self.run_validate("--schema", self.put("s.json", schema("nothing here")))
        self.assertFails(code, out, "'alpha'", "'beta-two'")

    def test_id_must_match_as_a_whole_word(self):
        # 'alpha' must not be satisfied by 'alphabet', 'beta-two' not by 'beta-twofold'
        code, out = self.run_validate("--schema", self.put("s.json", schema("alphabet, beta-twofold")))
        self.assertFails(code, out, "'alpha'", "'beta-two'")

    def test_id_is_found_between_punctuation(self):
        code, out = self.run_validate("--schema", self.put("s.json", schema("(alpha, beta-two)")))
        self.assertPasses(code, out)

    def test_enum_must_match_exactly(self):
        s = {"$defs": {"coverageArea": {"enum": ["alpha", "beta-two", "gamma"]}}}
        code, out = self.run_validate("--schema", self.put("s.json", s))
        self.assertFails(code, out, "'gamma'", "enum")

    def test_enum_missing_a_registry_id(self):
        s = {"$defs": {"coverageArea": {"enum": ["alpha"]}}}
        code, out = self.run_validate("--schema", self.put("s.json", s))
        self.assertFails(code, out, "'beta-two'", "enum")

    def test_enum_equal_passes(self):
        s = {"$defs": {"coverageArea": {"enum": ["beta-two", "alpha"]}}}
        code, out = self.run_validate("--schema", self.put("s.json", s))
        self.assertPasses(code, out)

    def test_schema_without_the_def_is_an_error(self):
        code, out = self.run_validate("--schema", self.put("s.json", {"$defs": {}}))
        self.assertFails(code, out, "coverageArea")

    def test_def_without_vocabulary_is_an_error(self):
        code, out = self.run_validate("--schema", self.put("s.json", {"$defs": {"coverageArea": {"$ref": "#/$defs/slug"}}}))
        self.assertFails(code, out, "coverageArea")

    def test_unreadable_schema_is_an_error(self):
        code, out = self.run_validate("--schema", str(self.inputs / "nope.json"))
        self.assertFails(code, out, "schema", "nope.json")

    def test_schema_over_http(self):
        self.put("s.json", schema("alpha, beta-two"))
        base = self.serve_inputs()
        code, out = self.run_validate("--schema", f"{base}/s.json")
        self.assertPasses(code, out)

    def test_schema_skipped_without_the_flag_even_if_ids_are_absent(self):
        code, out = self.run_validate()
        self.assertPasses(code, out)


class Cli(ValidateTest):
    def test_both_flags_together(self):
        code, out = self.run_validate("--marketplace", self.put("m.json", marketplace("plug-a", "plug-b")),
                                      "--schema", self.put("s.json", schema("alpha beta-two")))
        self.assertPasses(code, out)

    def test_unknown_flag_is_rejected(self):
        code, out = self.run_validate("--bogus")
        self.assertNotEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
