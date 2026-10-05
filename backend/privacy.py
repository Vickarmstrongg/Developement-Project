MIN_STUDENTS_THRESHOLD = 10

def is_suppressed(distinct_student_count: int) -> bool:
    """Returns True if a data point must be hidden for privacy (fewer than 10 students)."""
    return distinct_student_count < MIN_STUDENTS_THRESHOLD