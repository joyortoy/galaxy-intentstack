"""Conservative observable language rules; no score establishes intent or execution authority."""

import re

from .models import Indicator, Interpretation

RULES = (
    ("false_authority", r"\bi am your (administrator|admin|owner)\b"),
    (
        "prompt_injection",
        r"ignore (?:all |previous )?(?:restrictions|instructions|rules)|system prompt",
    ),
    ("artificial_urgency", r"\b(?:immediately|right now|last chance)\b"),
    ("guilt_pressure", r"if you (?:really )?cared|you owe me|anyone who values .{1,40} would"),
    (
        "threat",
        r"\b(?:or else|i will hurt|i will punish)\b|if you want .{1,60} (?:stay safe|keep (?:your|their) job)",
    ),
    ("dependency_exploitation", r"only i can help|you cannot survive without"),
    ("history_rewrite", r"pretend (?:that )?(?:never|it never)|erase (?:the )?history"),
    (
        "selective_evidence",
        r"ignore (?:the )?(?:contrary|contradictory) evidence|only (?:the )?favorable results.{0,40}omit",
    ),
    (
        "permission_escalation",
        r"all future requests|pre.approved|grant yourself|approvals (?:are )?unnecessary",
    ),
    (
        "unsupported_promotion",
        r"you (?:already )?(?:said|concluded|interpreted)|as you established|(?:speculation|interpretation|guess).{0,50}(?:verified|confirmed) permission",
    ),
    ("veiled_threat", r"(?:people|colleagues).*refuse.*lose (?:their )?(?:careers|jobs)"),
    (
        "review_bypass_urgency",
        r"(?:window|offer|opportunity).*?(?:close|expire).*?(?:review|skip)|no time.*?(?:verify|check|review)|approval later|before (?:compliance|reviewers) (?:sees?|review)",
    ),
    (
        "contradictory_commitments",
        r"i promise to (?P<commitment>\w+).*but i (?:won.t|will not) (?P=commitment)\b",
    ),
    (
        "security_bypass",
        r"(?:disable|turn off|remove|skip|bypass|override).{0,35}(?:access guard|security check|authorization|approval|review|permission check)",
    ),
    (
        "claimed_authority_sensitive_request",
        r"(?:system owner|security team|administrator).{0,80}(?:collect|send|reveal|unlock).{0,40}(?:password|credential|confidential|private)",
    ),
    (
        "instruction_laundering",
        r"(?:developer rule|security policy update|highest.priority instruction).{0,100}(?:disable|treat|override)|(?:treat|follow).{0,60}(?:highest.priority instruction|developer rule)",
    ),
)


def assess(text, evidence_id, source_type):
    # Explicit analysis/quotation framing is narrower than mentioning "training example".
    # It never exempts the content from independent authorization.
    if source_type == "message" and re.match(
        r"^(?:the training example says:|analy[sz]e this phishing phrase:|"
        r"the security lesson describes how attackers claim)",
        text,
        re.IGNORECASE,
    ):
        return ()
    scanned = re.sub(r"'[^'\n]+'|\"[^\"\n]+\"", "[quoted content]", text)
    authority_context = re.search(
        r"ignore|transfer|give me access|grant yourself|bypass|override", scanned, re.IGNORECASE
    )
    urgency_context = re.search(
        r"skip|without review|no time.*(?:verify|review)|give me access|grant access|transfer.*funds",
        scanned,
        re.IGNORECASE,
    )
    ordinary_check = re.search(
        r"normal checks|after (?:the )?(?:normal |usual )?(?:checks|approval)|approved payment",
        scanned,
        re.IGNORECASE,
    )
    promotion_context = re.search(
        r"authoriz|approv|permission|access|funds", scanned, re.IGNORECASE
    )
    indicators = []
    for name, pattern in RULES:
        match = re.search(pattern, scanned, re.IGNORECASE)
        if not match:
            continue
        if name == "false_authority" and not authority_context:
            continue
        if name == "artificial_urgency" and (not urgency_context or ordinary_check):
            continue
        if name == "unsupported_promotion" and not promotion_context:
            continue
        if name == "security_bypass":
            prefix = scanned[max(0, match.start() - 35) : match.start()]
            if re.search(
                r"(?:nobody should|never|do not|must not|should not)\s*$", prefix, re.IGNORECASE
            ):
                continue
        indicators.append(
            Indicator(
                pattern=name,
                observed_behavior=match.group(),
                possible_mechanism=name.replace("_", " "),
                evidence_references=(evidence_id,),
            )
        )
    if source_type in ("memory", "tool", "agent") and any(
        i.pattern in ("prompt_injection", "permission_escalation", "instruction_laundering")
        for i in indicators
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
