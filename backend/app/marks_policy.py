"""Institutional CIE marks policy shared by API validation and persistence."""

MAX_MARKS = 50.0
INTERNALS = (1, 2, 3)


def assessments() -> list[dict]:
    """The API representation consumed by the faculty marks form."""
    return [
        {"internal": internal, "label": f"CIE-{internal}",
         "max_marks": MAX_MARKS}
        for internal in INTERNALS
    ]
