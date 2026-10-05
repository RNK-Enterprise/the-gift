"""Tests for the monitoring scripts in deploy/: gift-healthcheck.sh and
deadman.sh. Each script runs for real against temp state/log files and a
fake sendmail that records what would have been emailed.

Run with: python3 -m unittest test_deploy_scripts
"""

import os
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

import server as gift

HERE = Path(__file__).resolve().parent
HEALTHCHECK = HERE / "deploy" / "gift-healthcheck.sh"
DEADMAN = HERE / "deploy" / "deadman.sh"


class ScriptTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.mailbox = self.dir / "mailbox"
        sendmail = self.dir / "sendmail"
        # every message is appended to the mailbox, separated by a marker line
        sendmail.write_text(f'#!/bin/sh\n{{ cat; echo "=== END"; }} >> "{self.mailbox}"\n')
        sendmail.chmod(sendmail.stat().st_mode | stat.S_IXUSR)
        self.sendmail = str(sendmail)

    def tearDown(self):
        self.tmp.cleanup()

    def mails(self):
        if not self.mailbox.exists():
            return []
        return [m for m in self.mailbox.read_text().split("=== END\n") if m.strip()]

    def subjects(self):
        return [line[len("Subject: "):] for m in self.mails()
                for line in m.splitlines() if line.startswith("Subject: ")]


class HealthcheckTest(ScriptTestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = gift.BoundedThreadingHTTPServer(("127.0.0.1", 0), gift.Handler)
        cls.up_url = f"http://127.0.0.1:{cls.httpd.server_address[1]}/healthz"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        super().setUp()
        self.state = self.dir / "health.state"
        self.log = self.dir / "health.log"
        self.beat = self.dir / "deadman.beat"
        self.beat.touch()

    def run_check(self, up=True):
        env = dict(os.environ,
                   GIFT_HEALTH_URL=self.up_url if up else "http://127.0.0.1:9/healthz",
                   GIFT_HEALTH_STATE=str(self.state),
                   GIFT_HEALTH_LOG=str(self.log),
                   GIFT_HEALTH_SENDMAIL=self.sendmail,
                   GIFT_DEADMAN_BEAT=str(self.beat))
        subprocess.run(["bash", str(HEALTHCHECK)], env=env, check=True,
                       capture_output=True, timeout=60)

    def down_for(self, minutes):
        """Pretend the service has been down for `minutes` (plus a few
        seconds of cron jitter)."""
        self.state.write_text(str(int(time.time()) - minutes * 60 - 7))

    def test_healthy_logs_ok_and_stays_quiet(self):
        self.run_check(up=True)
        self.assertIn("ok", self.log.read_text())
        self.assertEqual(self.mails(), [])

    def test_down_alerts_once_then_recovers(self):
        self.run_check(up=False)
        self.assertEqual(self.subjects(), ["[DOWN] gift.rnkstudios.uk is not answering"])
        self.assertTrue(self.state.exists())
        self.run_check(up=True)
        self.assertEqual(self.subjects()[-1], "[OK] gift.rnkstudios.uk recovered")
        self.assertFalse(self.state.exists())

    def test_still_down_reminds_exactly_once_per_hour(self):
        """Simulate a 3-hour outage at the 5-minute cron cadence: one reminder
        each at the 1h, 2h and 3h marks, never two in the same hour."""
        for minutes in range(5, 181, 5):
            self.down_for(minutes)
            self.run_check(up=False)
        reminders = [s for s in self.subjects() if "still down" in s]
        self.assertEqual(reminders, [
            "[DOWN] gift.rnkstudios.uk still down (60 min)",
            "[DOWN] gift.rnkstudios.uk still down (120 min)",
            "[DOWN] gift.rnkstudios.uk still down (180 min)",
        ])

    def test_stale_deadman_heartbeat_alerts_once(self):
        old = time.time() - 30 * 60
        os.utime(self.beat, (old, old))
        self.run_check(up=True)
        self.run_check(up=True)
        self.assertEqual(self.subjects(), ["[WARN] gift deadman switch not running"])
        self.beat.touch()
        self.run_check(up=True)
        self.assertIn("deadman heartbeat fresh again", self.log.read_text())
        self.assertEqual(len(self.mails()), 1)


class DeadmanTest(ScriptTestCase):
    def setUp(self):
        super().setUp()
        self.watched = self.dir / "gift-health.log"
        self.log = self.dir / "deadman.log"
        self.beat = self.dir / "deadman.beat"

    def run_deadman(self, **extra):
        env = dict(os.environ,
                   DEADMAN_WATCH=f"gift-health|{self.watched}|11",
                   DEADMAN_STATE=str(self.dir / "deadman.state"),
                   DEADMAN_LOG=str(self.log),
                   DEADMAN_BEAT=str(self.beat),
                   DEADMAN_SENDMAIL=self.sendmail, **extra)
        subprocess.run(["bash", str(DEADMAN)], env=env, check=True,
                       capture_output=True, timeout=30)

    def make_stale(self):
        self.watched.touch()
        old = time.time() - 20 * 60
        os.utime(self.watched, (old, old))

    def test_fresh_is_quiet_and_beats(self):
        self.watched.touch()
        self.run_deadman()
        self.assertTrue(self.beat.exists())
        self.assertEqual(self.mails(), [])

    def test_stale_emails_once_then_recovery(self):
        self.make_stale()
        self.run_deadman()
        self.run_deadman()
        self.assertEqual(len(self.mails()), 1)
        self.assertIn("STALE: gift-health", self.mails()[0])
        self.watched.touch()
        self.run_deadman()
        self.assertEqual(len(self.mails()), 2)
        self.assertIn("RECOVERED: gift-health", self.mails()[1])

    def test_notify_none_is_log_only(self):
        self.make_stale()
        self.run_deadman(DEADMAN_NOTIFY="none")
        self.assertIn("STALE", self.log.read_text())
        self.assertEqual(self.mails(), [])


if __name__ == "__main__":
    unittest.main()
