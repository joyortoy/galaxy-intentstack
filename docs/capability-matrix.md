# Discovery before implementation

Inspected read-only on host joy, 2026-11-05. Target GitHub repository was empty.
No code from the other repositories was copied; only public interface shapes were studied.
Source inspection and documentation are evidence of implementation, not independent runtime qualification.

| Capability | Existing evidence | Assessment | Galaxy boundary |
|---|---|---|---|
| Intent classification | IntentStack current/src/intentstack/intent.py | Implemented lexical routing | Preserve classifier suggestions as inferred candidates |
| Memory and corrections | IntentStack current/src/intentstack/store.py, models.py | Implemented SQLite revisions, expected_revision, source_ref | Read-only memory adapter; no canonical writes |
| Confirmation and identity | IntentStack auth.py, api.py | Configured principals and capabilities | Host authenticates before supplying identity |
| Approval | IntentStack promotion request/approval; JoyCtl policy.py | Separate approver; scoped grants | Local test authority, no replacement of JoyCtl |
| Provenance | JoyEvidence README and IntentStack evidence_sources.py | Transactional outbox and authenticated ledger | Expose audit ingestion without claiming authenticated federation |
| Audit | JoyEvidence HMAC chain; IntentStack SQLite audit/outbox | Implemented and documented | Local commitment chain, weaker than existing authenticated ledger |
| Authorization | joyctl/src/joyctl/policy.py | Deterministic PolicyDecision / ExecutionGrant | Additional veto; ALLOW never substitutes for execution grant |
| Untrusted ingress | joyctl/src/joyctl/intentdeck.py | Quarantine / MemoryCandidate / PromotionDecision | Keep external input as evidence only |
| Runtime enforcement | JoyMux AGENTS.md, docs boundary | Runtime, peer identity, Unix hooks and forensic enforcement | No MCP connection or runtime change |
| Memory routing | memory-joyclaw README; IntentStack retrieval.py | Isolated public/deep vault and bounded retrieval | Adapter assumes already permission-filtered input |
| Memory decay | No inspected source established automatic semantic decay | Unverified | No invented decay |
| Contradictions | JoyEvidence federation reports conflicts | Partial: observations preserved | Add local semantic slot conflicts and dependent staleness |
| Truth validation | Confirmation and provenance exist | Partial; authenticity does not prove truth | Explicit verifier capability; no language-based promotion |
| Belief dependency graph | No inspected source established equivalent graph | Unverified | New bounded downstream invalidation |
| Manipulation patterns | IntentDeck instruction-like classification | Partial | Conservative observable rules, uncertainty and alternatives |

Snapshots: JoyCtl 959d8b1; JoyMux 3642ff8. IntentStack inspected release
20261010-4d5acdb-389af3e (current symlink). JoyEvidence is the sibling in that release.
Additional accessible repositories discovered through GitHub names: intent-handoff,
intentautoresearch, joymux-control-plane. Not inspected; their capabilities remain unverified.
No production databases, credentials, services, or policy were modified.
