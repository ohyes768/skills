# F10-only design

Retain deterministic calculation and bound reports; replace the source boundary.

prepare --code CODE --period YYYY-MM-DD --run-dir RUN validates identity, fetches existing F10 endpoints and writes document.json (report metadata) plus structured_financials.json (archive). A run binds to one code/date. compute maps saved fields into facts and returns bounded analysis context; no analyst fact input.

Facts carry source_ref with report name/kind, date, field, security and response digest. financials binds to archive SHA-256. Verify facts against exact archived fields. Derived gross profit lists its input facts. Missing source stays null; malformed source fails closed.

Claims carry source_refs instead of page references. Rendering formats source metadata separately from narrative numbers. Validation checks source closure, actual body and units. Independent review retains structure, scope, identities and arithmetic; archived-field checking replaces excerpt matching.

Remove obsolete scripts/fixtures/tests; retain financial arithmetic and mutation protections. Rewrite active references, acceptance and repository listing. Preserve shared field-map exports. Runtime deployment/client migration is outside this change.
