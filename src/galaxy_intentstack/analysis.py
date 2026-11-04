"""Conservative finite rules. Indicators describe behavior, never a person's diagnosis."""

import re

from .models import Indicator, Interpretation

RULES = (
    ("false_authority", r"\bi am your (administrator|admin|owner)\b"),
    (
        "prompt_injection",
        r"ignore (?:all |previous )?(?:restrictions|instructions|rules)|system prompt",
    ),
    ("artificial_urgency", r"\b(?:immediately|right now|last chance)\b"),
    ("guilt_pressure", r"if you (?:really )?cared|you owe me"),
    ("threat", r"\b(?:or else|i will hurt|i will punish)\b"),
    ("dependency_exploitation", r"only i can help|you cannot survive without"),
    ("history_rewrite", r"pretend (?:that )?(?:never|it never)|erase (?:the )?history"),
    ("selective_evidence", r"ignore (?:the )?(?:contrary|contradictory) evidence"),
    ("permission_escalation", r"(?:all future requests|pre.approved|grant yourself)"),
    (
        "unsupported_promotion",
        r"(?:you (?:already )?(?:said|concluded|interpreted)|as you established)",
    ),
    ("contradictory_commitments", r"i promise.*(?:but i won.t|but i will not)"),
)


def assess(text, evidence_id, source_type):
    indicators = []
    for name, pattern in RULES:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            indicators.append(
                Indicator(
                    pattern=name,
                    observed_behavior=match.group(),
                    possible_mechanism=name.replace("_", " "),
                    evidence_references=(evidence_id,),
                )
            )
    if source_type in ("memory", "tool", "agent") and any(
        i.pattern in ("prompt_injection", "permission_escalation") for i in indicators
    ):
        indicators.append(
            Indicator(
                pattern="memory_poisoning" if source_type == "memory" else "tool_output_laundering",
                observed_behavior="External content proposes policy changes",
                possible_mechanism="Data presented as execution authority",
                evidence_references=(evidence_id,),
            )
        )
    return tuple(indicators)


def interpret(text, evidence_id):
    descriptions = ["Literal statement or request; purpose remains unconfirmed"]
    if re.search(r"\bgalax(?:y|ies)\b", text, re.IGNORECASE):
        descriptions = [
            "Literal statement about galaxies",
            "Possible metaphor about small beginnings; recipient and purpose unknown",
        ]
    return tuple(
        Interpretation(description=d, evidence_references=(evidence_id,)) for d in descriptions
    )


def requested_action(text):
    # Safety hint only. Explicit typed requests still require exact scoped permission.
    return bool(
        re.search(r"transfer (?:the )?funds|give me access|change .*calendar", text, re.IGNORECASE)
    )
