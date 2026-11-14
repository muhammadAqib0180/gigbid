from rag.verify import is_experience_claim, split_claims, verify_claims

EV = [{"evidence_id": "e1", "item_id": "case-ticket-router", "type": "case_study",
       "snippet": "I fine-tuned a compact transformer on 80,000 historical tickets. Routing accuracy of 91%."}]


def test_split_and_classify():
    claims = split_claims("I built a router. Could we talk Thursday?\n\nFor this job I would start with an audit.")
    flags = [is_experience_claim(s) for _, s in claims]
    assert flags == [True, False, False]


def test_unsupported_claims_removed_supported_kept():
    draft = ("On my ticket work, I fine-tuned a compact transformer on 80,000 historical tickets. "
             "On my pricing work, revenue rose 40% for 12 clients. I have 10 years of experience with Kubernetes. "
             "Which part matters most?")
    fixed, rep = verify_claims(draft, EV)
    assert "80,000 historical tickets" in fixed
    assert "Kubernetes" not in fixed and "40%" not in fixed
    assert rep.unsupported_before == 2 and rep.unsupported_after == 0
    assert rep.rate_before > rep.rate_after


def test_numbers_must_match_evidence():
    fixed, rep = verify_claims("I fine-tuned a compact transformer on 95,000 historical tickets.", EV)
    assert "95,000" not in fixed            # the unverifiable number is removed (claim dropped or softened)
    assert rep.unsupported_before + len(rep.softened) >= 1
