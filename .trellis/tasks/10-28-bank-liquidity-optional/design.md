# Design
Move LCR/NSFR from required snapshot metrics to optional scored liquidity metrics. Preserve finite-value/provenance validation for supplied non-null records and existing regime applicability checks. Emit liquidity_status plus warnings; absent pair yields a non-scoring check rather than a default 5. A single verified metric can only cap quality using existing bands, never certify complete liquidity coverage. Rename policy to bank-research-v2 to identify changed missingness contract.

Separate accepted evidence topics from required ones for bank financial research. Keep liquidity accepted for backward compatibility; missing-topic checks require the other three topics. Insurance unchanged. Keep ten-field final output; agent must disclose limitation in report/watch_points.
