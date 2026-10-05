MIN_STUDENTS_THRESHOLD = 5  # TEMP for demo — Byte & Bite stated 10 in Session 1 BRD NFR-01, revert before final build unless they approve the change

def is_suppressed(distinct_student_count: int) -> bool:
    """Returns True if a data point must be hidden for privacy (fewer than 5 students)."""
    return distinct_student_count < MIN_STUDENTS_THRESHOLD