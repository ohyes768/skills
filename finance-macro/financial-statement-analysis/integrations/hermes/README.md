# Hermes financial artifact delivery

This optional bridge makes the host, rather than a final model summary, own delivery.
It is maintenance code; financial-analysis agents must not install or edit it.

## Contract

The caller submits `completion_mode: financial_statement_analysis` and
`completion_source_url` alongside the normal `input`. The host chooses a unique `run_<uuid>`
directory under the skill's sibling `output/financial-statement-analysis/` and supplies it in
the initial instructions. Legacy requests retain their original behavior.

The agent finishes semantic review and calls `run_pipeline finish --semantic-reviewed`.
The host checks completion.json once per second, invokes the installed completion.py in the
skill runtime with a 30-second verification deadline, checks the requested source URL and
current artifact hashes, and independently validates Markdown/claims. It returns analysis.md
as `output`, marks the API run completed, closes its event stream and interrupts the agent.
The active worker remains tracked until its actual return. Rejection is a failed terminal
result; an agent response without an accepted receipt is also failed. Financial budget
exhaustion uses a static fallback, not an extra model request.

`verified` and `semantic_reviewed` remain separate assertions. Hashes are consistency checks,
not authentication; this bridge does not establish the separate protected-mode permission
boundary. Do not use it to publish partial reports or recover unrelated historical directories.

## Installation

Confirm the actual import location with the service's interpreter, from its working directory:

```sh
/path/to/service/python -c 'import gateway.platforms.api_server as a; print(a.__file__)'
```

Run the installer against the directory containing that imported `gateway` package:

```sh
python integrations/hermes/install.py --hermes-root /actual/package/root --caller-root /path/to/stock-info-dingding
```

The installer validates every known source seam and compiles both transformed files before
writing. It stores content-addressed backups beside changed files. Deploy/update the skill
first; install and test the adapter before switching the live caller. Restart only the idle
target gateway. Authenticated `/v1/capabilities` must advertise
`features.financial_artifact_delivery=true`. Hermes upgrades can overwrite this local bridge;
re-test/reinstall after an upgrade. Unknown source seams cause installation to fail.

`test_api_delivery.py` belongs in the Hermes `tests/gateway/` suite; preload the actual installed
adapter before collecting source-checkout tests. `test_client_delivery.py` belongs alongside
the caller tests. Neither test invokes a model or a publishing service.

## Current installation (2026-10-20)

- Runtime root: `/home/ohyes768/agent/hermes-agent/venv/lib/python3.11/site-packages`.
- Profile gateway: `hermes-gateway-ohyes768.service`; authenticated capability checked after restart.
- Caller is bind-mounted into n8n-webhook-1; new worker processes load the changed client.
- Original API backup: `gateway/platforms/api_server.py.delivery-backup-2b8725863c99`.
- Skill backup: `/home/ohyes768/.local/state/financial-delivery-backups/20261020/skill-before.tgz`.
- Roll back the caller and API together from their original delivery-backup files, restore the
  backed-up skill if needed, and restart the idle gateway. Never roll back validation results
  or reuse an old completion receipt for a new request.
