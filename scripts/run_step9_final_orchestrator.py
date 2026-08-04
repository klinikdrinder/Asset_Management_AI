"""Gate the final Step 9 selection through at most two checkpoint workers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / "tmp" / "step9-b5-final-selection.json"


def main() -> int:
    source_ids = json.loads(SCOPE.read_text(encoding="utf-8"))[
        "source_file_ids"
    ]
    if len(source_ids) != 372:
        raise SystemExit("Final scope must contain exactly 372 rows")
    chunks = [
        source_ids[index : index + 25]
        for index in range(0, len(source_ids), 25)
    ]
    # Split the final 22 rows so the final wave remains bounded at two workers.
    final = chunks.pop()
    chunks.extend((final[:11], final[11:]))
    if len(chunks) != 16 or sum(map(len, chunks)) != 372:
        raise SystemExit("Unexpected checkpoint partition")

    environment = dict(os.environ)
    environment["PYTHONPATH"] = "src"
    completed = 0
    for wave_start in range(0, len(chunks), 2):
        processes = []
        batch_numbers = []
        for offset in range(2):
            chunk_index = wave_start + offset
            batch_number = 21 + chunk_index
            batch_numbers.append(batch_number)
            report = (
                ROOT
                / "tmp"
                / f"step9-b5-final-checkpoint-{batch_number:03d}.json"
            )
            command = [
                sys.executable,
                "scripts/run_step9_hash_batch.py",
                "--execute",
                "--batch-number",
                str(batch_number),
                "--selection-scope-file",
                str(SCOPE),
                "--report",
                str(report),
            ]
            for source_file_id in chunks[chunk_index]:
                command.extend(("--source-file-id", source_file_id))
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=ROOT,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            )
        failures = []
        for batch_number, process in zip(batch_numbers, processes):
            stdout, _ = process.communicate()
            print(stdout.strip(), flush=True)
            report_path = (
                ROOT
                / "tmp"
                / f"step9-b5-final-checkpoint-{batch_number:03d}.json"
            )
            if process.returncode != 0 or not report_path.is_file():
                failures.append(f"CHECKPOINT_{batch_number:03d}_PROCESS_FAILED")
                continue
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if report["stop_condition"]["triggered"]:
                failures.append(
                    report["stop_condition"]["reason"]
                    or f"CHECKPOINT_{batch_number:03d}_STOPPED"
                )
        completed += sum(len(chunks[index]) for index in range(wave_start, wave_start + 2))
        print(
            json.dumps(
                {
                    "progress_completed": completed,
                    "wave": wave_start // 2 + 1,
                    "failures": failures,
                }
            ),
            flush=True,
        )
        if failures:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
