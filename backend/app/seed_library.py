"""Synthetic library catalogue seeder.

Kept as its own module (rather than added to seed.py) so seed.py itself
is untouched. Generates ~500 books spread across the institution's own
subject taxonomy (seed.py::SUBJECT_POOLS), so recommendations have
believable categories to match against from the moment the app starts,
plus a little borrowing history for a handful of existing students.
"""
import datetime as dt
import random

from .auth import hash_password
from .database import SessionLocal
from .models import Book, BookIssue, Student, User
from .seed import DEPARTMENTS, SUBJECT_POOLS

RNG_SEED = 7
TARGET_BOOK_COUNT = 500
LIBRARIAN_USERNAME = "librarian1"
LIBRARIAN_PASSWORD = "librarian123"

AUTHOR_FIRST = ["A.", "R.", "S.", "N.", "K.", "M.", "P.", "V.", "D.", "J."]
AUTHOR_LAST = ["Sharma", "Rao", "Iyer", "Fernandes", "Shetty", "Kumar",
              "Reddy", "Nair", "Gupta", "Pai", "Bhat", "D'Souza"]
TITLE_TEMPLATES = [
    "Introduction to {subject}", "Foundations of {subject}",
    "{subject}: A Practical Guide", "Advanced {subject}",
    "{subject} for Engineers", "Principles of {subject}",
    "{subject} — Concepts and Applications", "Modern {subject}",
    "{subject} Handbook", "Essentials of {subject}",
]


def _make_isbn(rng: random.Random) -> str:
    return f"978-{rng.randint(0,9)}-{rng.randint(100,999)}-{rng.randint(10000,99999)}-{rng.randint(0,9)}"


def _make_author(rng: random.Random) -> str:
    return f"{rng.choice(AUTHOR_FIRST)} {rng.choice(AUTHOR_LAST)}"


def _ensure_librarian_account(db) -> None:
    """Idempotent on its own -- separate from the book-seeding guard, so
    the librarian login exists even if someone clears just the books
    table and re-seeds."""
    if db.query(User).filter_by(username=LIBRARIAN_USERNAME).first() is None:
        db.add(User(username=LIBRARIAN_USERNAME,
                    password_hash=hash_password(LIBRARIAN_PASSWORD),
                    role="librarian", display_name="Meera Kulkarni (Librarian)"))
        db.commit()


def seed_library(per_book_seed: int = RNG_SEED) -> bool:
    """Seeds ~500 books plus a little borrowing history, and the librarian
    login. Returns True if it actually seeded books (idempotent — a
    non-empty books table is left alone, same convention as seed_all())."""
    db = SessionLocal()
    try:
        _ensure_librarian_account(db)

        if db.query(Book).count() > 0:
            return False

        rng = random.Random(per_book_seed)
        dept_codes = [code for code, _, _ in DEPARTMENTS]
        # Flatten (dept_code, subject) pairs so every book has a plausible
        # home category drawn from the real institutional subject list.
        pool = [(code, subj) for code in dept_codes for subj in SUBJECT_POOLS.get(code, [])]
        rng.shuffle(pool)

        books = []
        for i in range(TARGET_BOOK_COUNT):
            dept_code, subject = pool[i % len(pool)]
            total = rng.randint(1, 8)
            available = rng.randint(0, total)
            template = rng.choice(TITLE_TEMPLATES)
            book = Book(
                isbn=_make_isbn(rng), title=template.format(subject=subject),
                author=_make_author(rng), publisher=rng.choice(
                    ["Pearson", "McGraw Hill", "Wiley", "PHI Learning",
                     "Oxford University Press", "Cengage"]),
                category=subject, dept_relevance=dept_code,
                total_copies=total, available_copies=available,
                description=f"A core reference text for {subject}.",
                popularity_count=rng.randint(0, 40),
            )
            books.append(book)
        db.add_all(books)
        db.commit()

        # Give a handful of already-seeded students some returned
        # borrowing history so recommendations have a history signal to
        # work with immediately, without waiting for real usage.
        students = db.query(Student).limit(30).all()
        for student in rng.sample(students, k=min(15, len(students))):
            same_dept_books = [b for b in books if b.dept_relevance == student.dept_code]
            if not same_dept_books:
                continue
            for book in rng.sample(same_dept_books, k=min(rng.randint(1, 3), len(same_dept_books))):
                issue_date = dt.datetime.utcnow() - dt.timedelta(days=rng.randint(20, 150))
                due_date = issue_date + dt.timedelta(days=14)
                return_date = due_date - dt.timedelta(days=rng.randint(-3, 5))
                db.add(BookIssue(usn=student.usn, book_id=book.id, issue_date=issue_date,
                                 due_date=due_date, return_date=return_date, status="returned"))
        db.commit()
        return True
    finally:
        db.close()
