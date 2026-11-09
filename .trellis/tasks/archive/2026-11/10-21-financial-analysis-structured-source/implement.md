# Implementation plan

- [x] Add failing F10-only source and end-to-end tests.
- [x] Replace source mapping with archived-field provenance; preserve field-map API.
- [x] Replace prepare/compute/context stages and remove extraction commands.
- [x] Replace report citations and source validation; retain independent arithmetic.
- [x] Remove obsolete scripts/dependencies/source tests; rewrite active references.
- [x] Run full skill tests, Ruff, relevant sibling tests and skill validation.
- [x] Review final diff and realistic independent skill use; record verification without commit/deploy.

Rollback: uncommitted Git diff. Existing runtime artifacts are not migrated or edited.

Verification: 127 skill tests and Ruff passed; independent source/spec and full code reviews passed. Real F10 prepare/compute for 002093 2026-06-30 succeeded. No commit/deployment.

Independent realistic use: copied only live F10 archive/metadata, consumed bounded packets, authored a report and reached verified with 414 independent checks. Fixed the inventory flag-ID adapter found during this test; documented derived-fact claim typing.
