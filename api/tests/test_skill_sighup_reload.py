"""Real-process SIGHUP reload test for the C1 skill registry.

Spawns a child Python process that loads a temporary skills directory,
installs the SIGHUP handler, then waits for SIGHUP. The parent test
mutates the skills directory, sends SIGHUP, and asserts the child's
registry reflects the new state.

This is gated under the `integration` marker because it spawns a
subprocess and uses real signals (it would be misleading under the
in-process unit-test pattern).
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parent.parent


def _make_skill(folder: Path, name: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Synthetic SIGHUP test fixture.\n---\n# {name}\n"
    )


@pytest.mark.integration
@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="SIGHUP not available")
def test_sighup_reload_in_child_process(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    _make_skill(skills_dir / "first", "first")

    output_path = tmp_path / "output.txt"

    # The child process loads the registry, installs the SIGHUP handler,
    # writes the current names to output_path, then waits to receive
    # SIGHUP. On SIGHUP it re-loads, writes the new names, and exits.
    program = textwrap.dedent(
        f"""
        import signal, sys, time
        from pathlib import Path
        sys.path.insert(0, {str(API_DIR)!r})
        from app.skills import load_registry, install_sighup_reload
        from app.skills.registry import MutableSkillRegistry

        skills_dir = Path({str(skills_dir)!r})
        out = Path({str(output_path)!r})

        holder = MutableSkillRegistry(load_registry(skills_dir))
        install_sighup_reload(holder, skills_dir)

        # Write a "ready" marker plus the initial skills.
        with out.open("w") as fh:
            fh.write("ready\\n")
            fh.write(",".join(holder.current().names()) + "\\n")
            fh.flush()

        # Pause for the parent to send SIGHUP. Use a polling loop that
        # respects the already-installed signal handler — `signal.pause`
        # would also work but is not portable.
        prior_count = len(holder.current().names())
        for _ in range(100):  # up to ~10 seconds
            time.sleep(0.1)
            if len(holder.current().names()) != prior_count:
                break

        with out.open("a") as fh:
            fh.write(",".join(holder.current().names()) + "\\n")
        """
    )

    proc = subprocess.Popen(
        [sys.executable, "-c", program],
        env={**os.environ},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # Wait for the child to write "ready".
        deadline = time.monotonic() + 10.0
        ready = False
        while time.monotonic() < deadline:
            if output_path.exists():
                contents = output_path.read_text()
                if contents.startswith("ready\n"):
                    ready = True
                    break
            time.sleep(0.1)
        if not ready:
            stdout, stderr = proc.communicate(timeout=2)
            raise AssertionError(
                f"child never reached ready state. stdout={stdout!r} stderr={stderr!r}"
            )

        # Mutate the skills directory: add a second skill.
        _make_skill(skills_dir / "second", "second")

        # Send SIGHUP.
        os.kill(proc.pid, signal.SIGHUP)

        # Wait for the child to exit.
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=2)
            raise AssertionError(
                f"child did not exit after SIGHUP. stdout={stdout!r} stderr={stderr!r}"
            ) from exc

        # Read the output: line 1 is "ready", line 2 is initial names,
        # line 3 is post-reload names.
        lines = output_path.read_text().splitlines()
        assert lines[0] == "ready"
        initial_names = set(lines[1].split(",")) if lines[1] else set()
        post_names = set(lines[2].split(",")) if len(lines) > 2 and lines[2] else set()
        assert initial_names == {"first"}
        assert post_names == {"first", "second"}
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)
        # Cleanup is handled by tmp_path; explicit shutil.rmtree is just
        # defensive against lingering FDs from the child.
        if skills_dir.exists():
            shutil.rmtree(skills_dir, ignore_errors=True)
