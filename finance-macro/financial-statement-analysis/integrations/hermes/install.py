"""Install the small opt-in Runs API bridge against known Hermes/caller seams.

Fails on source drift; makes content-addressed backups before changing files.
Run only as host maintenance, never from a financial-analysis agent.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"unsupported source seam ({text.count(old)} matches): {old[:100]}")
    return text.replace(old, new, 1)


def patch_api(text):
    if '"financial_artifact_delivery": True' not in text:
        text = replace_once(text, '                "run_submission": True,\n',
                            '                "run_submission": True,\n'
                            '                "financial_artifact_delivery": True,\n')
    if "# financial-artifact-delivery-v1" in text:
        return text
    text = replace_once(text,
        '        current = self._run_statuses.get(run_id, {})\n        current.update({',
        '        current = self._run_statuses.get(run_id, {})\n'
        '        # Terminal delivery cannot be revived by late worker/approval events.\n'
        '        if current.get("status") in {"completed", "failed", "cancelled", "interrupted"}:\n'
        '            return current\n'
        '        current.update({')
    start = text.index('    async def _handle_runs(')
    end = text.index('    async def _handle_get_run(', start)
    run = text[start:end]
    run = replace_once(run,
        '        ephemeral_system_prompt = instructions\n',
        '''        # financial-artifact-delivery-v1: opt-in; legacy requests are unchanged.
        delivery = None
        mode = body.get("completion_mode")
        if mode is not None:
            if mode != "financial_statement_analysis":
                return web.json_response(_openai_error("Unknown completion_mode"), status=400)
            try:
                from hermes_cli.config import get_hermes_home
                from gateway.financial_delivery import FinancialDelivery
                delivery = FinancialDelivery(
                    get_hermes_home() / "skills" / "financial-statement-analysis",
                    run_id, body.get("completion_source_url"),
                )
            except (OSError, ValueError) as exc:
                return web.json_response(_openai_error(str(exc)), status=400)
        ephemeral_system_prompt = ((instructions or "") + delivery.instructions
                                   if delivery else instructions)
''')
    run = replace_once(run,
        '        async def _run_and_close():\n            try:\n',
        '''        def _publish_delivery(**fields):
            if self._run_statuses.get(run_id, {}).get("status") in {
                "completed", "failed", "cancelled", "interrupted"
            }:
                return
            status = "failed" if "error" in fields else "completed"
            event = "run." + status
            self._set_run_status(run_id, status, last_event=event,
                                 completion_mode="financial_statement_analysis", **fields)
            q.put_nowait({"event": event, "run_id": run_id,
                          "timestamp": time.time(), **fields})
            # Close the event stream now; keep the worker in the concurrency ledger
            # until run_conversation and its resource cleanup actually return.
            q.put_nowait(None)

        async def _run_and_close():
            delivery_task = None
            try:
''')
    run = replace_once(run,
        '                self._active_run_agents[run_id] = agent\n',
        '''                self._active_run_agents[run_id] = agent
                if delivery:
                    delivery.configure_agent(agent)
                    delivery_task = asyncio.create_task(delivery.watch(agent, _publish_delivery))
''')
    run = replace_once(run,
        '                result, usage = await asyncio.get_running_loop().run_in_executor(None, _run_sync)\n',
        '''                result, usage = await asyncio.get_running_loop().run_in_executor(None, _run_sync)
                if delivery:
                    await delivery.check_once(agent, _publish_delivery)
                    if not delivery.terminal:
                        _publish_delivery(error="Financial agent exited without an accepted completion receipt")
                    return
''')
    run = replace_once(run,
        '            except asyncio.CancelledError:\n',
        '''            except asyncio.CancelledError:
                if delivery and delivery.terminal:
                    return
''')
    run = replace_once(run,
        '            except Exception as exc:\n                logger.exception',
        '''            except Exception as exc:
                if delivery and delivery.terminal:
                    return
                logger.exception''')
    run = replace_once(run,
        '            finally:\n                # If the asyncio wrapper',
        '''            finally:
                if delivery_task is not None:
                    delivery_task.cancel()
                    await asyncio.gather(delivery_task, return_exceptions=True)
                # If the asyncio wrapper''')
    return text[:start] + run + text[end:]


def patch_client(text):
    if '"completion_mode": "financial_statement_analysis"' in text:
        return text
    text = replace_once(text, '        json={"input": prompt},',
                        '        json={"input": prompt, "completion_mode": "financial_statement_analysis",\n'
                        '              "completion_source_url": pdf_url},')
    text = replace_once(text,
        '        "2. 之后输出完整财务分析 Markdown，含主要报表数据、同比变化与数据质量评估。\\n"',
        '        "2. 将完整财务分析写入 analysis.md，含主要报表数据、同比变化与数据质量评估。\\n"\n'
        '        "完成语义复核后运行 finish --semantic-reviewed；成功后停止工具，只回复简短完成通知。\\n"\n'
        '        "宿主直接读取报告文件，无需在最后回复重复全文。\\n"')
    return text


def install_file(path, content):
    if path.exists():
        old = path.read_bytes()
        if old == content:
            return
        backup = path.with_name(path.name + ".delivery-backup-" + hashlib.sha256(old).hexdigest()[:12])
        if not backup.exists():
            shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    print(f"updated {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-root", type=Path, required=True)
    parser.add_argument("--caller-root", type=Path, required=True)
    args = parser.parse_args()
    api = args.hermes_root / "gateway" / "platforms" / "api_server.py"
    client = args.caller_root / "hermes_client.py"
    # Validate every replacement before performing any mutation.
    api_text = patch_api(api.read_text(encoding="utf-8"))
    client_text = patch_client(client.read_text(encoding="utf-8"))
    compile(api_text, str(api), "exec")
    compile(client_text, str(client), "exec")
    install_file(args.hermes_root / "gateway" / "financial_delivery.py",
                 Path(__file__).with_name("financial_delivery.py").read_bytes())
    install_file(api, api_text.encode("utf-8"))
    install_file(client, client_text.encode("utf-8"))


if __name__ == "__main__":
    main()
