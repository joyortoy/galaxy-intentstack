# Threat model and limitations

This document describes the Phase 1 compatibility layer. For the implemented Phase 2 real
integration and current boundaries, see [Phase 2 architecture](phase2-architecture.md).

## Boundary

External text, retrieved documents, memories and agent outputs are untrusted. The trusted host
owns identity authentication, session selection, source registration, policy configuration,
approval requirements, the SQLite file and all operator methods. A standalone database is one
local tenant; this is not a multi-tenant HTTP service. No arbitrary database paths or operator
methods may be selected by remote content.

## Threat coverage

| Threat | Local defense | Residual limit |
|---|---|---|
| Direct/indirect injection | Text stays evidence; explicit grants independent of text | Lexical detector can miss paraphrases |
| Forged authority | Body claim does not authenticate principal | Host must not trust sender-provided source identity |
| Malicious retrieval / poisoned memory | Memory adapter never imports permissions or confirmed status | Host must permission-filter retrieval and authenticate provenance |
| Compromised model output | Classifier labels remain inferred; citations retain roots | Fabricated uncited claims are still recorded as reports |
| Cross-session contamination | References and grants are session-scoped | Host must bind session to authenticated caller |
| Multi-turn laundering | Cited roots/dependencies retained; no automatic promotion | No general semantic equivalence or cross-source mirror resolver |
| Emotional coercion | Pattern uncertainty/alternatives; authority independent | Benign urgency/quotation can be flagged |
| Unauthorized escalation | Exact deterministic grants and independent approval | Trusted host compromise defeats local policy |
| Revocation | Recheck at local invocation; disabled approvers checked | Distributed TOCTOU needs owning runtime cooperation |
| Historical rewrite | Original evidence and appended revisions remain | DB owner can drop triggers/rewrite data |
| Resource exhaustion | Bounded message/ref/export sizes and traversal budget | Total tenants/sessions/database require host quotas |

The audit chain is unkeyed and locally held. It detects broken links under the tested mutation;
it does not prove authenticity or detect suffix deletion without an external retained head.
It does not replace JoyEvidence's HMAC ledger. Projection tampering by a database owner,
full-disk loss, encryption, forensic retention and authenticated backups are not addressed.

Common secret formats are rejected. Unknown secrets may still enter private evidence storage;
no universal detector can guarantee otherwise. Do not ingest credentials or private reasoning.
Audit identifiers must be host-generated, non-secret metadata. No raw content is sent to logs.

There is no general-purpose fact extractor: one whole-message claim and a narrow meeting-day
slot are implemented. Evidence selection, sarcasm, implicit coercion, veiled threats and broader
contradictions remain incomplete. The fixture benchmark deliberately exposes false positives and
misses. The detector never diagnoses a speaker or establishes malicious intent.

Source verification is an explicit attestation, not a truth oracle. Independent human identity
requires operational separation; two credentials held by one person do not establish two reviewers.
The operator decides which actions require approval; automatic risk classification is not provided.

The local callback executor is for bounded, nonexternal test operations. Exactly-once remote
effects, crash-after-effect-before-commit recovery, automatic retry and cancellation are not
implemented. A callback exception is audited and the action remains consumed. A process crash can
roll back that consumption. Do not route real transfers, calendar writes or privileged tools here.
