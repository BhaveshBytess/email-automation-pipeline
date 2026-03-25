"""
Fallback email templates for the Cold Email Pipeline.

Used when Gemini API fails or returns invalid output.
Conforms to contracts.md Section 6.4 and agent_project.md Section 5.2.

Each template:
- Under 150 words
- References company name
- References a resume project
- Uses .format() placeholders — no KeyError possible
"""

import logging
import random

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Templates — 4 variants, each < 150 words
# ---------------------------------------------------------------------------

_TEMPLATES = [
    {
        "subject_options": [
            "Quick question about {company}'s engineering stack",
            "{person_name} — ML work relevant to {company}",
            "Could {project_name} help at {company}?",
        ],
        "body": (
            "Hi {person_name},\n\n"
            "Saw {company} is building in {relevant_skill} — nice problem space. "
            "I recently shipped {project_name}: {project_desc}. "
            "The approach might translate well to what your team is tackling.\n\n"
            "Would a quick chat make sense? Happy to share specifics.\n\n"
            "Cheers,\nBhavesh"
        ),
    },
    {
        "subject_options": [
            "Re: {company}'s {relevant_skill} team",
            "{person_name}, quick note on {relevant_skill}",
            "Relevant work for {company}",
        ],
        "body": (
            "Hey {person_name},\n\n"
            "I noticed {company} is working on some interesting {relevant_skill} problems. "
            "Figured I'd reach out since I just wrapped up {project_name} — {project_desc}.\n\n"
            "Not trying to waste your time. If the work sounds relevant, I'd love to "
            "hear what you're building.\n\n"
            "Best,\nBhavesh"
        ),
    },
    {
        "subject_options": [
            "{relevant_skill} engineer — built {project_name}",
            "Short intro for {company}'s team",
            "{person_name}, thought this might be relevant",
        ],
        "body": (
            "Hi {person_name},\n\n"
            "I'm a CS undergrad at IIIT Kota focused on {relevant_skill}. "
            "My most recent project was {project_name}: {project_desc}. "
            "Given what {company} is doing, I think there's a real overlap.\n\n"
            "Open to a 15-minute call if it makes sense on your end. "
            "Either way, cool stuff you're building.\n\n"
            "— Bhavesh"
        ),
    },
    {
        "subject_options": [
            "Possible fit at {company}?",
            "{project_name} + {company}",
            "{person_name} — {relevant_skill} background, quick intro",
        ],
        "body": (
            "{person_name},\n\n"
            "Stumbled across {company} while researching {relevant_skill} companies. "
            "I built {project_name} — {project_desc}. "
            "Think the approach could be useful for your team.\n\n"
            "No pressure. If you're open to a short conversation, "
            "I can walk through the technical details.\n\n"
            "Talk soon,\nBhavesh"
        ),
    },
]


def generate_fallback(
    person_name: str,
    company: str,
    relevant_skill: str,
    project_name: str,
    project_desc: str,
) -> dict:
    """Generate an email from a hardcoded template.

    Returns ``{"subject_options": [str, str, str], "body": str}``.
    All placeholders are filled from arguments — never raises KeyError.
    """
    template = random.choice(_TEMPLATES)
    fmt = {
        "person_name": person_name,
        "company": company,
        "relevant_skill": relevant_skill,
        "project_name": project_name,
        "project_desc": project_desc,
    }

    body = template["body"].format(**fmt)
    subjects = [s.format(**fmt) for s in template["subject_options"]]

    logger.info("Fallback template used for %s at %s", person_name, company)
    return {"subject_options": subjects, "body": body}
