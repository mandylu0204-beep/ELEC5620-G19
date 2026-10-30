"""Versioned text envelope in existing feedback scopes; no shared DTO change."""
import json

PREFIX='CampMate review-linked revision v1\n'


def linked_feedback(review,instructions):
    return PREFIX+json.dumps({'source_review_id':review['review_id'],
        'reviewed_version_id':review['version_context']['plan_version_id'],
        'reviewer_feedback':review['reason'],'camper_instructions':instructions.strip(),
        'authority':'ADVISORY_ONLY'},ensure_ascii=False,sort_keys=True,separators=(',',':'))


def linked_payload(feedback):
    value=(feedback or '').strip()
    if value.startswith(PREFIX):
        try:
            payload=json.loads(value[len(PREFIX):])
            if (set(payload)=={'source_review_id','reviewed_version_id','reviewer_feedback','camper_instructions','authority'}
                    and payload['authority']=='ADVISORY_ONLY'
                    and all(isinstance(payload[key],str) for key in payload)):
                return payload
        except (ValueError,TypeError):pass
    return None


def model_feedback_text(feedback):
    payload=linked_payload(feedback)
    if payload:
        reason=payload['reviewer_feedback'].strip();instructions=payload['camper_instructions'].strip()
        # The model receives human instructions, never workflow/review IDs.
        # Identical adoption does not send the same opinion twice.
        return reason if not instructions or reason==instructions else 'Reviewer feedback:\n'+reason+'\nCamper instructions:\n'+instructions
    return (feedback or '').strip()


def revision_goal(feedback):
    payload=linked_payload(feedback)
    value=(payload['camper_instructions'] or payload['reviewer_feedback']) if payload else (feedback or '')
    # This recognises existing goals; it never authorises a review or approval.
    return value.strip().casefold()
