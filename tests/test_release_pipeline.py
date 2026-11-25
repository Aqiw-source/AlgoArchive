"""Release-version and package-contract regression checks."""

from pathlib import Path
import unittest

import app


PROJECT = Path(__file__).resolve().parents[1]


class ReleasePipelineTests(unittest.TestCase):
    def test_application_version_is_250(self):
        self.assertEqual(app.APP_VERSION, "2.5.0")

    def test_release_workflow_builds_launcher_for_the_validated_tag(self):
        workflow = (PROJECT / ".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("build-launcher.ps1", workflow)
        self.assertIn("RELEASE_VERSION", workflow)
        self.assertIn("RELEASE_GXX", workflow)
        self.assertIn("APP_VERSION", workflow)

    def test_installer_version_is_compile_time_overridable(self):
        installer = (PROJECT / "installer/AlgoArchive.iss").read_text(
            encoding="utf-8"
        )
        build = (PROJECT / "scripts/build-release.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("#ifndef MyAppVersion", installer)
        self.assertIn("/DMyAppVersion=$Version", build)

    def test_portable_build_runs_actual_bundled_runtime_api_smoke(self):
        build = (PROJECT / "scripts/build-portable.ps1").read_text(
            encoding="utf-8"
        )
        smoke = (PROJECT / "scripts/smoke-release-package.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("smoke-release-package.py", build)
        for contract in (
            '"/api/health"',
            '"POST", "/api/problems"',
            '"PUT", problem_path',
            '"DELETE", problem_path',
            '"POST", "/api/shutdown"',
        ):
            self.assertIn(contract, smoke)


if __name__ == "__main__":
    unittest.main(verbosity=2)
