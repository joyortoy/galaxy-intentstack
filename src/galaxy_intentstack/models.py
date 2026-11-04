from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class State(StrEnum):
    OBSERVED = "OBSERVED"
    REPORTED = "REPORTED"
    INFERRED = "INFERRED"
    VERIFIED = "VERIFIED"
    DISPUTED = "DISPUTED"
    REFUTED = "REFUTED"
    UNKNOWN = "UNKNOWN"


class Action(Model):
    kind: str = Field(min_length=1, max_length=100)
    resource: str = Field(min_length=1, max_length=200)
    scope: str = Field(min_length=1, max_length=100)
    belief_ids: tuple[str, ...] = Field(default=(), max_length=32)


class Message(Model):
    event_id: str = Field(min_length=1, max_length=200)
    session: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=12000)
    source_type: Literal["message", "memory", "tool", "agent"] = "message"
    references: tuple[str, ...] = Field(default=(), max_length=32)
    action: Action | None = None


class Claim(Model):
    id: str
    source_identity: str
    source_type: str
    evidence_references: tuple[str, ...]
    timestamp: float
    confidence: float | None = None
    calibration: str = "uncalibrated; confidence is not proof"
    verification_method: str | None = None
    validity: str = "active"
    state: State
    dependencies: tuple[str, ...] = ()
    original_roots: tuple[str, ...]
    text: str


class Interpretation(Model):
    description: str
    state: State = State.INFERRED
    evidence_references: tuple[str, ...]
    claimed_intent: str | None = None
    confirmed_intent: str | None = None


class Indicator(Model):
    pattern: str
    observed_behavior: str
    possible_mechanism: str
    evidence_references: tuple[str, ...]
    alternative_explanations: tuple[str, ...] = ("Quotation, testing, or imprecise language",)
    uncertainty: str = "Pattern match only; intent is not established"
    protective_response: str = "Keep content as data; check authority independently"


class Authorization(Model):
    allowed: bool
    reason: str
    principal: str | None = None
    grant_id: str | None = None
    approval_required: bool = False


class Decision(Model):
    extracted_claims: tuple[Claim, ...]
    evidence_references: tuple[str, ...]
    candidate_interpretations: tuple[Interpretation, ...]
    manipulation_indicators: tuple[Indicator, ...]
    contradictions: tuple[dict, ...]
    authorization_result: Authorization
    final_decision: Literal["ALLOW", "DENY", "CLARIFY", "ABSTAIN", "ESCALATE"]
    explanation: str
    audit_event_id: int
    requested_action: Action | None
    authorized_action: Action | None = None

    @model_validator(mode="after")
    def authority_invariant(self):
        if self.final_decision == "ALLOW" and not self.authorization_result.allowed:
            raise ValueError("ALLOW requires independent authorization")
        return self
