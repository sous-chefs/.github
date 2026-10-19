"""Exercise cache resolution without network calls or a Workstation install."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("cache.sh")


class CacheResolutionTest(unittest.TestCase):
    def resolve(self, distro="ubuntu", metadata=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "os-release").write_text(f'ID={distro}\nVERSION_ID="24.04"\n')
            if metadata is None:
                metadata = "version\t26.3.0\nsha256\t" + "a" * 64 + "\n"
            (root / "metadata").write_text(metadata)
            curl = root / "curl"
            curl.write_text('#!/bin/bash\ncat "$TEST_METADATA"\n')
            curl.chmod(0o755)
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}",
                       CINC_OS_RELEASE=str(root / "os-release"),
                       TEST_METADATA=str(root / "metadata"),
                       CINC_VERSION="latest", CINC_CHANNEL="stable",
                       RUNNER_TEMP=str(root), GITHUB_OUTPUT=str(root / "output"))
            result = subprocess.run(["bash", str(SCRIPT), "resolve"], env=env,
                                    capture_output=True, text=True, check=False)
            output = root / "output"
            return result.returncode, output.read_text() if output.exists() else ""

    def test_exact_version_and_checksum_in_key(self):
        code, output = self.resolve()
        self.assertEqual(code, 0)
        self.assertIn("enabled=true\nversion=26.3.0\n", output)
        self.assertIn("-stable-26.3.0-" + "a" * 64, output)
        self.assertIn("path=", output)

    def test_other_linux_distributions_keep_existing_installer(self):
        self.assertEqual(self.resolve(distro="debian"), (0, ""))

    def test_invalid_metadata_cannot_create_cache_key(self):
        code, output = self.resolve(metadata="version\tlatest\nsha256\tinvalid\n")
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")

    def test_action_exposes_cache_and_uses_remote_action_path(self):
        action = SCRIPT.parent.parent.joinpath("action.yml").read_text()
        self.assertIn("value: ${{ steps.restore.outputs.cache-hit }}", action)
        self.assertIn("value: ${{ steps.resolve.outputs.version }}", action)
        for phase in ("resolve", "pack", "restore"):
            self.assertIn(f'bash "$GITHUB_ACTION_PATH/scripts/cache.sh" {phase}', action)


if __name__ == "__main__":
    unittest.main()
