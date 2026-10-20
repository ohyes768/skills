"""Opt-in Runs API delivery adapter. Installed as gateway.financial_delivery.

Keeps the worker accounted for until it exits, but publishes an accepted artifact
without waiting for another model response or post-turn cleanup.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse


class FinancialDelivery:
    def __init__(self, skill_root, run_id, source_url, *, python_executable=None):
        if not run_id.startswith("run_") or Path(run_id).name != run_id:
            raise ValueError("invalid financial run ID")
        if not isinstance(source_url, str) or urlparse(source_url).scheme not in {"https", "http"}:
            raise ValueError("completion_source_url must be an HTTP(S) PDF URL")
        self.skill_root = Path(skill_root).resolve()
        self.verifier = self.skill_root / "scripts" / "completion.py"
        self.python = (Path(python_executable) if python_executable else
                       self.skill_root / ".venv" / "bin" / "python")
        if not self.verifier.is_file() or not self.python.is_file():
            raise ValueError("financial completion verifier/runtime is not installed")
        self.run_dir = self.skill_root.parent / "output" / "financial-statement-analysis" / run_id
        self.source_url = source_url
        self.terminal = False
        self._lock = asyncio.Lock()

    @property
    def instructions(self):
        return (
            "\nFinancial artifact delivery contract:\n"
            f"Use only this run directory: {self.run_dir}\n"
            f"Source PDF URL: {self.source_url}\n"
            "Use run_pipeline evidence to extract and read together; compute returns analysis data. "
            "Complete semantic review before finish --semantic-reviewed. "
            "After finish returns terminal=true, stop tools and return only a short completion notice. "
            "The host reads analysis.md directly; never reproduce the full report in the chat."
        )

    def configure_agent(self, agent):
        # Financial jobs must not spend an additional unbounded model call on a
        # budget-exhaustion summary. The host accepts only a verified receipt.
        agent._handle_max_iterations = lambda messages, count: (
            "Iteration budget exhausted; financial delivery requires an accepted completion receipt."
        )

    async def check_once(self, agent, publish):
        async with self._lock:
            if self.terminal or not (self.run_dir / "completion.json").is_file():
                return
            process = None
            try:
                process = await asyncio.create_subprocess_exec(
                    str(self.python), str(self.verifier), "--run-dir", str(self.run_dir),
                    "--expected-url", self.source_url,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=30)
                result = json.loads(stdout)
                if process.returncode != 0 or result.get("accepted") is not True:
                    raise ValueError(result.get("error", "independent financial verification failed"))
                self.terminal = True
                publish(output=result["output"])
            except asyncio.CancelledError:
                raise
            except (TimeoutError, OSError, ValueError, KeyError) as exc:
                self.terminal = True
                publish(error=f"financial delivery rejected: {exc}")
            finally:
                if process is not None and process.returncode is None:
                    process.kill()
                    await process.wait()
            agent.interrupt("Financial artifact delivery finished")

    async def watch(self, agent, publish):
        while not self.terminal:
            await self.check_once(agent, publish)
            if not self.terminal:
                await asyncio.sleep(1)
