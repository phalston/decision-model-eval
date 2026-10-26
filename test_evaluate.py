#!/usr/bin/env python3
"""End-to-end check of evaluate.py with canned answers (no model, no network): python3 -m unittest test_evaluate"""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TASK = os.path.join(HERE, "tasks", "ticket-triage-example", "task.json")
# One canned answer per outcome. Misfiled: 01 12 14 caught; 10 other wrong type; 02 (low confidence) and 09 (order flip)
# review; 05 07 missed. Correctly filed: 03 04 11 accepted; 06 false alarm; 08 review; 13 has no answer.
FIXTURE = {
    "EX-01": {"fwd": ["new_capability", 0.95], "rev": ["new_capability", 0.93]},
    "EX-02": {"fwd": ["security_incident", 0.90], "rev": ["security_incident", 0.60]},
    "EX-03": {"fwd": ["enable_feature", 0.90], "rev": ["enable_feature", 0.90]},
    "EX-04": {"fwd": ["access_request", 0.99], "rev": ["access_request", 0.99]},
    "EX-05": {"fwd": ["how_to", 0.95], "rev": ["how_to", 0.95]},
    "EX-06": {"fwd": ["how_to", 0.90], "rev": ["how_to", 0.90]},
    "EX-07": {"fwd": ["access_request", 0.90], "rev": ["access_request", 0.90]},
    "EX-08": {"fwd": ["how_to", 0.90], "rev": ["how_to", 0.50]},
    "EX-09": {"fwd": ["incident", 0.70], "rev": ["how_to", 0.80]},
    "EX-10": {"fwd": ["incident", 0.90], "rev": ["incident", 0.90]},
    "EX-11": {"fwd": ["security_incident", 0.97], "rev": ["security_incident", 0.97]},
    "EX-12": {"fwd": ["enable_feature", 0.99], "rev": ["enable_feature", 0.99]},
    "EX-14": {"fwd": ["new_capability", 0.90], "rev": ["new_capability", 0.88]},
}


def run(*args):
    return subprocess.run([sys.executable, os.path.join(HERE, "evaluate.py")] + list(args), capture_output=True, text=True)


def row(report, label):
    line = next(l for l in report.splitlines() if l.startswith("| " + label))
    return line.split("|")[-2].strip()


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fixture = os.path.join(self.tmp, "fixture.json")
        json.dump(FIXTURE, open(self.fixture, "w"))
        r = run("ask", TASK, "fixture", "--fixture", self.fixture, "--results", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run("report", TASK, "--results", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.report = open(os.path.join(self.tmp, "ticket-triage-example", "report.md")).read()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_misfiled(self):
        self.assertEqual(row(self.report, "**Caught**"), "3/8")
        self.assertEqual(row(self.report, "Reclassified, but"), "1/8")
        self.assertEqual(row(self.report, "Sent to review"), "2/8")
        self.assertEqual(row(self.report, "**Missed**"), "2/8")

    def test_wellfiled(self):
        self.assertEqual(row(self.report, "Accepted"), "3/6")
        self.assertEqual(row(self.report, "**False alarm**"), "1/6")

    def test_overall_and_high_stakes(self):
        self.assertEqual(row(self.report, "Right type, forward order"), "8/13")
        self.assertEqual(row(self.report, "Decided by the rule"), "10/14")
        self.assertEqual(row(self.report, "Right type when decided"), "6/10")
        self.assertEqual(row(self.report, "Type changed"), "1/13")
        self.assertEqual(row(self.report, "security_incident: surfaced"), "2/4")
        self.assertEqual(row(self.report, "security_incident: raised"), "0/10")

    def test_changed_spec_is_refused(self):
        task = json.load(open(TASK))
        task["options"]["other"] = "Anything else"
        d = os.path.join(self.tmp, "t")
        os.makedirs(d)
        shutil.copy(os.path.join(os.path.dirname(TASK), "tickets.csv"), d)
        json.dump(task, open(os.path.join(d, "task.json"), "w"))
        shutil.copytree(os.path.join(self.tmp, "ticket-triage-example"), os.path.join(self.tmp, "r", "ticket-triage-example"))
        r = run("ask", os.path.join(d, "task.json"), "fixture", "--fixture", self.fixture, "--results", os.path.join(self.tmp, "r"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("different question/options", r.stderr)

    def _task_copy(self, csv_text):
        d = tempfile.mkdtemp(dir=self.tmp)
        shutil.copy(TASK, d)
        open(os.path.join(d, "tickets.csv"), "w", encoding="utf-8").write(csv_text)
        return os.path.join(d, "task.json")

    def test_submitted_display_name_is_refused(self):
        csv_text = open(os.path.join(os.path.dirname(TASK), "tickets.csv"), encoding="utf-8").read()
        task = self._task_copy(csv_text.replace("EX-03,enable_feature,", "EX-03,Feature Request,"))
        r = run("report", task, "--results", self.tmp)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Feature Request", r.stderr)

    def test_bom_csv_loads(self):
        csv_text = open(os.path.join(os.path.dirname(TASK), "tickets.csv"), encoding="utf-8").read()
        task = self._task_copy("\ufeff" + csv_text)
        r = run("report", task, "--results", self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
