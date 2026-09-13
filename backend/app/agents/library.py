"""Library Agent — automated catalogue, requests, issue/return, fines, and
recommendations, modeling a real physical library:

  - The agent decides availability/eligibility automatically (including a
    fine-threshold check) -- no human approves individual reservations.
  - A successful reservation produces an acknowledgement slip; the
    student shows this to the librarian in person, who then confirms the
    actual pickup. This is the "librarian hands you the book" moment.
  - Returning mirrors that: the student submits a return request (with an
    optional review), then the librarian confirms they actually received
    the book back (or rejects a false claim). Fine calculation uses the
    student's declared return time, not whenever the librarian gets
    around to confirming it.
  - Walk-in counter service (issue_book / return_book) remains for a
    librarian handling a book with no prior digital reservation at all --
    the physical handover and the system confirmation happen in the same
    instant there, since the librarian is right there.

Fines are their own small table (LibraryFine) rather than being folded into
FeeRecord: Finance's refresh_status() recomputes fee.fine from a daily
grace-period formula on every call, which would silently overwrite a
library fine's fixed one-time amount if the two shared a table.
"""
import datetime as dt
import secrets

from sqlalchemy import func

from .. import config
from ..models import Book, BookIssue, BookRequest, BookReview, LibraryFine, Student
from ..seed import DEPARTMENTS, SUBJECT_POOLS
from .base import BaseAgent

# Branch -> preferred categories, derived from the institution's own
# subject catalogue (seed.py::SUBJECT_POOLS) rather than a separate
# hardcoded list, so it stays consistent with the rest of MAWOS and
# isn't hardcoded to any one department.
DEPT_CATEGORY_MAP: dict[str, list[str]] = {code: SUBJECT_POOLS.get(code, [])
                                           for code, _, _ in DEPARTMENTS}

# Scoring weights for personalized recommendations -- simple, explainable,
# content-based. No ML model: every point on a book's score traces back to
# a specific, statable reason.
SCORE_HISTORY_MATCH = 5
SCORE_BRANCH_MATCH = 4
SCORE_HIGHLY_RATED = 3
SCORE_AVAILABILITY = 2
SCORE_POPULARITY = 1
AVAILABILITY_HIGH_THRESHOLD = 0.5
POPULARITY_HIGH_THRESHOLD = 10
HIGHLY_RATED_THRESHOLD = 4.0


class LibraryAgent(BaseAgent):
    name = "library_agent"
    description = ("Automated book catalogue, requests, issue/return, "
                   "overdue fines, and recommendations")

    # ---------- catalogue (read) --------------------------------------------------
    def search_books(self, db, q: str = "", skip: int = 0, limit: int = 20) -> dict:
        query = db.query(Book)
        if q:
            like = f"%{q}%"
            query = query.filter((Book.title.ilike(like)) | (Book.author.ilike(like))
                                 | (Book.category.ilike(like)) | (Book.isbn.ilike(like)))
        total = query.count()
        items = query.order_by(Book.title).offset(skip).limit(limit).all()
        return {"total": total, "items": [self._book_dict(db, b) for b in items]}

    def get_book(self, db, book_id: int) -> dict | None:
        book = db.get(Book, book_id)
        return self._book_dict(db, book) if book else None

    def book_reviews(self, db, book_id: int, limit: int = 20) -> list[dict]:
        """Public to any authenticated student -- lets someone see what
        others thought of a book BEFORE reserving it, not just an
        average number."""
        rows = (db.query(BookReview).filter_by(book_id=book_id)
                .order_by(BookReview.created_at.desc()).limit(limit).all())
        out = []
        for r in rows:
            student = db.get(Student, r.usn)
            out.append({"student_name": student.name if student else r.usn,
                       "rating": r.rating, "comment": r.comment,
                       "created_at": str(r.created_at)})
        return out

    # ---------- catalogue (librarian-managed write access) ------------------------
    def add_book(self, db, payload: dict) -> dict:
        if db.query(Book).filter_by(isbn=payload["isbn"]).first():
            return {"ok": False, "error": "A book with this ISBN already exists"}
        total = int(payload.get("total_copies", 1))
        book = Book(isbn=payload["isbn"], title=payload["title"], author=payload["author"],
                    publisher=payload.get("publisher"), category=payload["category"],
                    dept_relevance=",".join(payload.get("dept_relevance", [])),
                    total_copies=total,
                    available_copies=int(payload.get("available_copies", total)),
                    description=payload.get("description"))
        db.add(book)
        db.commit()
        return {"ok": True, "book": self._book_dict(db, book)}

    def update_book(self, db, book_id: int, payload: dict) -> dict:
        book = db.get(Book, book_id)
        if book is None:
            return {"ok": False, "error": "Book not found"}
        for field in ("title", "author", "publisher", "category", "description"):
            if payload.get(field) is not None:
                setattr(book, field, payload[field])
        if payload.get("dept_relevance") is not None:
            book.dept_relevance = ",".join(payload["dept_relevance"])
        if payload.get("total_copies") is not None:
            new_total = int(payload["total_copies"])
            delta = new_total - book.total_copies
            book.total_copies = new_total
            book.available_copies = max(0, min(new_total, book.available_copies + max(delta, 0)))
        if payload.get("available_copies") is not None:
            book.available_copies = max(0, min(book.total_copies, int(payload["available_copies"])))
        db.commit()
        return {"ok": True, "book": self._book_dict(db, book)}

    def remove_book(self, db, book_id: int) -> dict:
        book = db.get(Book, book_id)
        if book is None:
            return {"ok": False, "error": "Book not found"}
        active_issue = db.query(BookIssue).filter(
            BookIssue.book_id == book_id, BookIssue.status.in_(("issued", "return_pending"))
        ).first()
        if active_issue is not None:
            return {"ok": False, "error": "Cannot remove — a copy is currently out with a student"}
        active_request = db.query(BookRequest).filter_by(book_id=book_id, status="pending").first()
        if active_request is not None:
            return {"ok": False, "error": "Cannot remove — a student has a pending reservation"}
        db.delete(book)
        db.commit()
        return {"ok": True}

    def _avg_rating(self, db, book_id: int) -> float | None:
        avg = db.query(func.avg(BookReview.rating)).filter_by(book_id=book_id).scalar()
        return round(avg, 2) if avg is not None else None

    def _book_dict(self, db, book: Book) -> dict:
        return {"id": book.id, "isbn": book.isbn, "title": book.title, "author": book.author,
                "publisher": book.publisher, "category": book.category,
                "dept_relevance": [d for d in book.dept_relevance.split(",") if d],
                "total_copies": book.total_copies, "available_copies": book.available_copies,
                "description": book.description, "popularity_count": book.popularity_count,
                "avg_rating": self._avg_rating(db, book.id)}

    # ---------- reservations: automatic decision, physical pickup ------------------
    def _unpaid_fines_total(self, db, usn: str) -> float:
        total = db.query(func.sum(LibraryFine.amount)).filter_by(usn=usn, status="unpaid").scalar()
        return round(total, 2) if total is not None else 0.0

    def _generate_slip_code(self, db) -> str:
        """A random 6-digit code, unique across all requests ever made
        (not just pending ones) so an old slip can never collide with a
        fresh one. secrets.randbelow avoids the tiny bias plain
        random.randint(100000, 999999) has near its bounds."""
        for _ in range(20):
            code = f"{secrets.randbelow(1_000_000):06d}"
            if db.query(BookRequest).filter_by(slip_code=code).first() is None:
                return code
        raise RuntimeError("Could not generate a unique slip code")

    async def request_book(self, db, usn: str, book_id: int) -> dict:
        if db.get(Student, usn) is None:
            return {"ok": False, "error": "Student not found"}
        book = db.get(Book, book_id)
        if book is None:
            return {"ok": False, "error": "Book not found"}

        unpaid = self._unpaid_fines_total(db, usn)
        if unpaid >= config.LIBRARY_FINE_THRESHOLD:
            return {"ok": False, "error": (
                f"Cannot reserve — you have ₹{unpaid} in unpaid library fines, at or above "
                f"the ₹{config.LIBRARY_FINE_THRESHOLD} limit. Clear some fines first.")}

        if book.available_copies <= 0:
            return {"ok": False, "error": "Book is currently unavailable"}
        existing = db.query(BookRequest).filter_by(usn=usn, book_id=book_id,
                                                    status="pending").first()
        if existing:
            return {"ok": False, "error": "You already have a pending request for this book"}

        deadline = dt.datetime.utcnow() + dt.timedelta(days=config.LIBRARY_PICKUP_DEADLINE_DAYS)
        slip_code = self._generate_slip_code(db)
        req = BookRequest(usn=usn, book_id=book_id, pickup_deadline=deadline,
                          slip_code=slip_code)
        db.add(req)
        db.commit()
        workflow_id = await self.publish("library.book_requested", {
            "usn": usn, "book_id": book_id, "request_id": req.id,
            "slip_code": slip_code, "pickup_deadline": str(deadline)})
        return {"ok": True, "workflow_id": workflow_id, "request_id": req.id,
                "slip_code": slip_code, "pickup_deadline": str(deadline)}

    def get_request_slip(self, db, request_id: int, usn: str) -> dict:
        """The acknowledgement slip a student shows the librarian in
        person to collect their reserved book. Carries the unique 6-digit
        slip_code the librarian checks at the desk (see verify_slip)."""
        req = db.get(BookRequest, request_id)
        if req is None or req.usn != usn:
            return {"ok": False, "error": "Request not found"}
        book = db.get(Book, req.book_id)
        student = db.get(Student, usn)
        return {"ok": True, "request_id": req.id, "slip_code": req.slip_code,
                "status": req.status,
                "student_name": student.name if student else usn, "usn": usn,
                "book_title": book.title if book else None,
                "book_author": book.author if book else None,
                "requested_at": str(req.requested_at),
                "pickup_deadline": str(req.pickup_deadline)}

    def cancel_request(self, db, request_id: int, usn: str) -> dict:
        req = db.get(BookRequest, request_id)
        if req is None or req.usn != usn:
            return {"ok": False, "error": "Request not found"}
        if req.status != "pending":
            return {"ok": False, "error": f"Request is '{req.status}', cannot be cancelled"}
        req.status = "cancelled"
        db.commit()
        return {"ok": True}

    # ---------- librarian: confirms the physical pickup -----------------------------
    def librarian_pending_pickups(self, db) -> list[dict]:
        """Every reservation the agent has already approved (availability +
        fine-standing check passed) and is now waiting on the librarian to
        hand the book over. slip_code is shown here too, so the librarian
        can match it against the slip the student is holding without a
        separate lookup."""
        rows = db.query(BookRequest).filter_by(status="pending").order_by(
            BookRequest.requested_at).all()
        out = []
        for r in rows:
            book = db.get(Book, r.book_id)
            student = db.get(Student, r.usn)
            out.append({"id": r.id, "usn": r.usn, "student_name": student.name if student else r.usn,
                       "book_id": r.book_id, "title": book.title if book else None,
                       "slip_code": r.slip_code,
                       "requested_at": str(r.requested_at),
                       "pickup_deadline": str(r.pickup_deadline)})
        return out

    def verify_slip(self, db, slip_code: str) -> dict:
        """Librarian-facing lookup: given the 6-digit code off a student's
        slip, confirm it's real and still valid for pickup *before*
        physically handing over the book. Distinguishes "no such code"
        from "valid code, but already used / expired / cancelled" so the
        librarian gets a clear reason rather than a bare not-found."""
        slip_code = (slip_code or "").strip()
        req = db.query(BookRequest).filter_by(slip_code=slip_code).first() if slip_code else None
        if req is None:
            return {"ok": False, "valid": False, "error": "No reservation found for this slip code"}
        book = db.get(Book, req.book_id)
        student = db.get(Student, req.usn)
        info = {"request_id": req.id, "slip_code": req.slip_code, "status": req.status,
               "usn": req.usn, "student_name": student.name if student else req.usn,
               "book_id": req.book_id, "title": book.title if book else None,
               "pickup_deadline": str(req.pickup_deadline)}
        if req.status != "pending":
            return {"ok": True, "valid": False,
                   "error": f"Slip is for a request that is '{req.status}', not awaiting pickup",
                   **info}
        if dt.datetime.utcnow() > req.pickup_deadline:
            return {"ok": True, "valid": False, "error": "Pickup deadline has already passed", **info}
        return {"ok": True, "valid": True, **info}

    async def confirm_collection(self, db, request_id: int) -> dict:
        """Librarian confirms they've physically handed the book to the
        student holding the acknowledgement slip. Availability is
        committed here, at the moment of physical handover."""
        req = db.get(BookRequest, request_id)
        if req is None:
            return {"ok": False, "error": "Request not found"}
        if req.status != "pending":
            return {"ok": False, "error": f"Request is '{req.status}', not pending pickup"}
        if dt.datetime.utcnow() > req.pickup_deadline:
            return {"ok": False, "error": "Pickup deadline has already passed"}

        book = db.get(Book, req.book_id)
        if book is None or book.available_copies <= 0:
            return {"ok": False, "error": "Book is no longer available"}

        req.status = "collected"
        req.collected_at = dt.datetime.utcnow()
        book.available_copies -= 1
        book.popularity_count += 1
        due_date = dt.datetime.utcnow() + dt.timedelta(days=config.LIBRARY_LOAN_DAYS)
        issue = BookIssue(usn=req.usn, book_id=book.id, request_id=req.id, due_date=due_date)
        db.add(issue)
        db.commit()
        workflow_id = await self.publish("library.book_issued", {
            "usn": req.usn, "book_id": book.id, "issue_id": issue.id, "due_date": str(due_date)})
        return {"ok": True, "workflow_id": workflow_id, "issue_id": issue.id,
                "due_date": str(due_date)}

    # ---------- return: student declares intent, librarian confirms receipt --------
    def request_return(self, db, issue_id: int, usn: str, rating: int | None = None,
                       comment: str | None = None) -> dict:
        """Student says "I'm bringing this book back." Fine calculation
        will use THIS moment, not whenever the librarian gets around to
        confirming -- a slow front desk shouldn't cost the student extra
        overdue days. The optional review is saved immediately since it's
        just feedback, independent of whether the physical handover is
        later disputed."""
        issue = db.get(BookIssue, issue_id)
        if issue is None or issue.usn != usn:
            return {"ok": False, "error": "Issue not found"}
        if issue.status != "issued":
            return {"ok": False, "error": f"Issue is '{issue.status}', not currently issued"}

        issue.status = "return_pending"
        issue.return_requested_at = dt.datetime.utcnow()

        review_saved = False
        review_error = None
        if rating is not None:
            if not (1 <= int(rating) <= 5):
                review_error = "Rating must be between 1 and 5 — return request submitted, review was not saved."
            else:
                existing_review = db.query(BookReview).filter_by(issue_id=issue.id).first()
                if existing_review is None:
                    db.add(BookReview(usn=issue.usn, book_id=issue.book_id, issue_id=issue.id,
                                      rating=int(rating), comment=(comment or "").strip() or None))
                    review_saved = True
        db.commit()
        result = {"ok": True, "review_saved": review_saved}
        if review_error:
            result["review_error"] = review_error
        return result

    def librarian_pending_returns(self, db) -> list[dict]:
        rows = db.query(BookIssue).filter_by(status="return_pending").order_by(
            BookIssue.return_requested_at).all()
        return [self._issue_dict(db, i) for i in rows]

    async def confirm_return(self, db, issue_id: int) -> dict:
        """Librarian confirms they've physically received the book back."""
        issue = db.get(BookIssue, issue_id)
        if issue is None:
            return {"ok": False, "error": "Issue not found"}
        if issue.status != "return_pending":
            return {"ok": False, "error": f"Issue is '{issue.status}', no return request to confirm"}

        book = db.get(Book, issue.book_id)
        return_moment = issue.return_requested_at or dt.datetime.utcnow()
        issue.return_date = return_moment
        issue.status = "returned"
        if book is not None and book.available_copies < book.total_copies:
            book.available_copies += 1

        overdue_days = max((return_moment - issue.due_date).days, 0)
        fine_amount = 0.0
        if overdue_days > 0:
            fine_amount = round(overdue_days * config.LIBRARY_FINE_PER_DAY, 2)
            self._generate_fine_idempotent(db, issue.usn, "overdue_return", issue.id,
                                           fine_amount, "BOOK_RETURNED_LATE")
        db.commit()

        workflow_id = await self.publish("library.book_returned", {
            "usn": issue.usn, "book_id": issue.book_id, "issue_id": issue.id,
            "overdue_days": overdue_days, "fine_amount": fine_amount})
        return {"ok": True, "workflow_id": workflow_id, "overdue_days": overdue_days,
                "fine_amount": fine_amount}

    def reject_return(self, db, issue_id: int, reason: str) -> dict:
        """Librarian disputes the return claim -- book was never actually
        handed over. Reverts to 'issued' so the fine clock (based on the
        original due_date) keeps running exactly as if nothing happened."""
        issue = db.get(BookIssue, issue_id)
        if issue is None:
            return {"ok": False, "error": "Issue not found"}
        if issue.status != "return_pending":
            return {"ok": False, "error": f"Issue is '{issue.status}', no return request to reject"}
        if not reason or not reason.strip():
            return {"ok": False, "error": "A reason is required to reject a return claim"}
        issue.status = "issued"
        issue.return_requested_at = None
        db.commit()
        return {"ok": True}

    # ---------- walk-in counter service: instant, librarian-mediated ----------------
    async def issue_book(self, db, usn: str, book_id: int) -> dict:
        """Walk-in counter issue: no prior reservation, librarian hands
        the book over immediately. (Also blocked by the fine threshold --
        same standing check as an online reservation.)"""
        if db.get(Student, usn) is None:
            return {"ok": False, "error": "Student not found"}
        book = db.get(Book, book_id)
        if book is None:
            return {"ok": False, "error": "Book not found"}
        unpaid = self._unpaid_fines_total(db, usn)
        if unpaid >= config.LIBRARY_FINE_THRESHOLD:
            return {"ok": False, "error": (
                f"Cannot issue — student has ₹{unpaid} in unpaid library fines, at or above "
                f"the ₹{config.LIBRARY_FINE_THRESHOLD} limit.")}
        if book.available_copies <= 0:
            return {"ok": False, "error": "Book is currently unavailable"}
        book.available_copies -= 1
        book.popularity_count += 1
        due_date = dt.datetime.utcnow() + dt.timedelta(days=config.LIBRARY_LOAN_DAYS)
        issue = BookIssue(usn=usn, book_id=book_id, due_date=due_date)
        db.add(issue)
        db.commit()
        workflow_id = await self.publish("library.book_issued", {
            "usn": usn, "book_id": book_id, "issue_id": issue.id, "due_date": str(due_date)})
        return {"ok": True, "workflow_id": workflow_id, "issue_id": issue.id,
                "due_date": str(due_date)}

    async def return_book(self, db, issue_id: int, rating: int | None = None,
                          comment: str | None = None) -> dict:
        """Walk-in counter return: student is physically present, so the
        return is processed in one step -- no separate request/confirm
        round-trip needed since the librarian is already looking at the
        book."""
        issue = db.get(BookIssue, issue_id)
        if issue is None:
            return {"ok": False, "error": "Issue not found"}
        if issue.status != "issued":
            return {"ok": False, "error": f"Issue is '{issue.status}', not issued"}

        book = db.get(Book, issue.book_id)
        now = dt.datetime.utcnow()
        issue.return_date = now
        issue.status = "returned"
        if book is not None and book.available_copies < book.total_copies:
            book.available_copies += 1

        overdue_days = max((now - issue.due_date).days, 0)
        fine_amount = 0.0
        if overdue_days > 0:
            fine_amount = round(overdue_days * config.LIBRARY_FINE_PER_DAY, 2)
            self._generate_fine_idempotent(db, issue.usn, "overdue_return", issue.id,
                                           fine_amount, "BOOK_RETURNED_LATE")

        review_saved = False
        if rating is not None and 1 <= int(rating) <= 5:
            if db.query(BookReview).filter_by(issue_id=issue.id).first() is None:
                db.add(BookReview(usn=issue.usn, book_id=issue.book_id, issue_id=issue.id,
                                  rating=int(rating), comment=(comment or "").strip() or None))
                review_saved = True
        db.commit()

        workflow_id = await self.publish("library.book_returned", {
            "usn": issue.usn, "book_id": issue.book_id, "issue_id": issue.id,
            "overdue_days": overdue_days, "fine_amount": fine_amount})
        return {"ok": True, "workflow_id": workflow_id, "overdue_days": overdue_days,
                "fine_amount": fine_amount, "review_saved": review_saved}

    # ---------- student views ----------------------------------------------------
    def student_requests(self, db, usn: str) -> list[dict]:
        rows = db.query(BookRequest).filter_by(usn=usn).order_by(
            BookRequest.requested_at.desc()).all()
        out = []
        for r in rows:
            book = db.get(Book, r.book_id)
            out.append({"id": r.id, "book_id": r.book_id, "title": book.title if book else None,
                       "status": r.status, "pickup_deadline": str(r.pickup_deadline),
                       "collected_at": str(r.collected_at) if r.collected_at else None})
        return out

    def student_borrowed(self, db, usn: str) -> list[dict]:
        rows = db.query(BookIssue).filter(
            BookIssue.usn == usn, BookIssue.status.in_(("issued", "return_pending"))).all()
        return [self._issue_dict(db, i) for i in rows]

    def student_history(self, db, usn: str) -> list[dict]:
        rows = db.query(BookIssue).filter_by(usn=usn).order_by(BookIssue.issue_date.desc()).all()
        return [self._issue_dict(db, i) for i in rows]

    def student_fines(self, db, usn: str) -> dict:
        fines = db.query(LibraryFine).filter_by(usn=usn).order_by(
            LibraryFine.created_at.desc()).all()
        unpaid = round(sum(f.amount for f in fines if f.status == "unpaid"), 2)
        return {"total": len(fines), "total_unpaid": unpaid,
                "threshold": config.LIBRARY_FINE_THRESHOLD, "items": [
            {"id": f.id, "source_type": f.source_type, "amount": f.amount,
             "reason": f.reason, "status": f.status, "created_at": str(f.created_at),
             "paid_at": str(f.paid_at) if f.paid_at else None}
            for f in fines]}

    @staticmethod
    def _issue_dict(db, issue: BookIssue) -> dict:
        book = db.get(Book, issue.book_id)
        student = db.get(Student, issue.usn)
        review = db.query(BookReview).filter_by(issue_id=issue.id).first()
        return {"id": issue.id, "usn": issue.usn,
                "student_name": student.name if student else None,
                "book_id": issue.book_id, "title": book.title if book else None,
                "issue_date": str(issue.issue_date), "due_date": str(issue.due_date),
                "return_requested_at": str(issue.return_requested_at) if issue.return_requested_at else None,
                "return_date": str(issue.return_date) if issue.return_date else None,
                "status": issue.status,
                "review": ({"rating": review.rating, "comment": review.comment}
                          if review else None)}

    # ---------- librarian: institution-wide oversight (read-only) -----------------
    def librarian_all_requests(self, db, status: str | None = None, limit: int = 200) -> list[dict]:
        q = db.query(BookRequest)
        if status:
            q = q.filter_by(status=status)
        rows = q.order_by(BookRequest.requested_at.desc()).limit(limit).all()
        out = []
        for r in rows:
            book = db.get(Book, r.book_id)
            student = db.get(Student, r.usn)
            out.append({"id": r.id, "usn": r.usn, "student_name": student.name if student else None,
                       "book_id": r.book_id, "title": book.title if book else None,
                       "status": r.status, "requested_at": str(r.requested_at),
                       "pickup_deadline": str(r.pickup_deadline)})
        return out

    def librarian_all_issues(self, db, status: str = "issued", limit: int = 200) -> list[dict]:
        rows = (db.query(BookIssue).filter_by(status=status)
                .order_by(BookIssue.issue_date.desc()).limit(limit).all())
        return [self._issue_dict(db, i) for i in rows]

    def librarian_overdue_report(self, db) -> list[dict]:
        now = dt.datetime.utcnow()
        rows = (db.query(BookIssue)
                .filter(BookIssue.status.in_(("issued", "return_pending")),
                        BookIssue.due_date < now).all())
        out = []
        for i in rows:
            d = self._issue_dict(db, i)
            d["overdue_days"] = max((now - i.due_date).days, 0)
            out.append(d)
        return sorted(out, key=lambda d: -d["overdue_days"])

    def librarian_all_fines(self, db, limit: int = 200) -> dict:
        fines = db.query(LibraryFine).order_by(LibraryFine.created_at.desc()).limit(limit).all()
        total_unpaid = round(sum(f.amount for f in fines if f.status == "unpaid"), 2)
        out = []
        for f in fines:
            student = db.get(Student, f.usn)
            out.append({"id": f.id, "usn": f.usn, "student_name": student.name if student else None,
                       "source_type": f.source_type, "amount": f.amount, "reason": f.reason,
                       "status": f.status, "created_at": str(f.created_at),
                       "paid_at": str(f.paid_at) if f.paid_at else None,
                       "collected_by": f.collected_by})
        return {"total": len(out), "total_unpaid": total_unpaid, "items": out}

    def pay_fine(self, db, fine_id: int, librarian_username: str) -> dict:
        """Student pays the fine to the librarian in person (cash at the
        desk -- there's no online payment gateway here); the librarian
        marks it paid and that clears it from the student's outstanding
        balance, which is what unblocks new reservations once the
        remaining unpaid total drops back below LIBRARY_FINE_THRESHOLD."""
        fine = db.get(LibraryFine, fine_id)
        if fine is None:
            return {"ok": False, "error": "Fine not found"}
        if fine.status == "paid":
            return {"ok": False, "error": "This fine is already marked paid"}
        fine.status = "paid"
        fine.paid_at = dt.datetime.utcnow()
        fine.collected_by = librarian_username
        db.commit()
        return {"ok": True, "fine_id": fine.id, "usn": fine.usn, "amount": fine.amount,
               "remaining_unpaid": self._unpaid_fines_total(db, fine.usn)}

    def librarian_all_reviews(self, db, limit: int = 200) -> list[dict]:
        rows = db.query(BookReview).order_by(BookReview.created_at.desc()).limit(limit).all()
        out = []
        for r in rows:
            book = db.get(Book, r.book_id)
            student = db.get(Student, r.usn)
            out.append({"id": r.id, "usn": r.usn, "student_name": student.name if student else None,
                       "book_id": r.book_id, "title": book.title if book else None,
                       "rating": r.rating, "comment": r.comment, "created_at": str(r.created_at)})
        return out

    # ---------- recommendations: three complementary signals ----------------------
    def recommendations(self, db, usn: str, limit: int | None = None) -> dict:
        student = db.get(Student, usn)
        if student is None:
            return {"ok": False, "error": "Student not found"}
        limit = limit or config.LIBRARY_RECOMMENDATION_LIMIT

        history_categories = {c for (c,) in db.query(Book.category)
                              .join(BookIssue, BookIssue.book_id == Book.id)
                              .filter(BookIssue.usn == usn).distinct().all()}
        branch_categories = set(DEPT_CATEGORY_MAP.get(student.dept_code, []))
        borrowed_ids = {b for (b,) in db.query(BookIssue.book_id)
                        .filter(BookIssue.usn == usn,
                                BookIssue.status.in_(("issued", "return_pending"))).all()}

        personalized = self._personalized(db, student, history_categories,
                                          branch_categories, borrowed_ids, limit)
        trending = self._trending_in_branch(db, student, borrowed_ids, limit)
        most_borrowed = self._most_borrowed_overall(db, borrowed_ids, limit)

        return {"usn": usn, "dept": student.dept_code,
                "personalized": personalized,
                "trending_in_branch": trending,
                "most_borrowed_overall": most_borrowed}

    def _personalized(self, db, student, history_categories, branch_categories,
                       borrowed_ids, limit) -> list[dict]:
        candidate_categories = history_categories | branch_categories
        if not candidate_categories:
            return []
        candidates = (db.query(Book)
                      .filter(Book.category.in_(candidate_categories), Book.available_copies > 0)
                      .all())
        candidates = [b for b in candidates if b.id not in borrowed_ids]

        scored = []
        for book in candidates:
            score, reasons = 0, []
            if book.category in history_categories:
                score += SCORE_HISTORY_MATCH
                reasons.append(f"Similar to previously borrowed {book.category} books")
            if book.category in branch_categories:
                score += SCORE_BRANCH_MATCH
                reasons.append(f"Matches {student.dept_code} branch")
            avg_rating = self._avg_rating(db, book.id)
            if avg_rating is not None and avg_rating >= HIGHLY_RATED_THRESHOLD:
                score += SCORE_HIGHLY_RATED
                reasons.append(f"Highly rated by other students ({avg_rating}/5)")
            if book.total_copies > 0 and (book.available_copies / book.total_copies) >= AVAILABILITY_HIGH_THRESHOLD:
                score += SCORE_AVAILABILITY
                reasons.append("Highly available right now")
            if book.popularity_count >= POPULARITY_HIGH_THRESHOLD:
                score += SCORE_POPULARITY
                reasons.append("Popular among other students")
            if score > 0:
                scored.append((score, reasons, book))

        scored.sort(key=lambda t: (-t[0], t[2].title))
        return [{"book_id": b.id, "title": b.title, "category": b.category,
                "score": s, "reason": r, "avg_rating": self._avg_rating(db, b.id)}
                for s, r, b in scored[:limit]]

    def _trending_in_branch(self, db, student, borrowed_ids, limit) -> list[dict]:
        candidates = (db.query(Book)
                      .filter(Book.dept_relevance.ilike(f"%{student.dept_code}%"),
                              Book.available_copies > 0, Book.popularity_count > 0)
                      .order_by(Book.popularity_count.desc())
                      .limit(limit + len(borrowed_ids)).all())
        candidates = [b for b in candidates if b.id not in borrowed_ids][:limit]
        return [{"book_id": b.id, "title": b.title, "category": b.category,
                "popularity_count": b.popularity_count, "avg_rating": self._avg_rating(db, b.id)}
                for b in candidates]

    def _most_borrowed_overall(self, db, borrowed_ids, limit) -> list[dict]:
        candidates = (db.query(Book)
                      .filter(Book.available_copies > 0, Book.popularity_count > 0)
                      .order_by(Book.popularity_count.desc())
                      .limit(limit + len(borrowed_ids)).all())
        candidates = [b for b in candidates if b.id not in borrowed_ids][:limit]
        return [{"book_id": b.id, "title": b.title, "category": b.category,
                "popularity_count": b.popularity_count, "avg_rating": self._avg_rating(db, b.id)}
                for b in candidates]

    # ---------- idempotent fine helper -------------------------------------------
    def _generate_fine_idempotent(self, db, usn: str, source_type: str, source_id: int,
                                   amount: float, reason: str) -> tuple[LibraryFine, bool]:
        existing = db.query(LibraryFine).filter_by(source_type=source_type,
                                                    source_id=source_id).first()
        if existing is not None:
            return existing, False
        fine = LibraryFine(usn=usn, source_type=source_type, source_id=source_id,
                           amount=amount, reason=reason)
        db.add(fine)
        db.flush()
        return fine, True

    # ---------- proactive behaviour: expire uncollected reservations --------------
    async def proactive_scan(self) -> dict:
        """Find PENDING requests whose pickup deadline has passed, expire
        them, and generate a fine -- exactly once per request even if this
        scan runs again later (idempotency guard: uq_library_fine_source)."""
        db = self.session()
        expired_count = 0
        try:
            now = dt.datetime.utcnow()
            expired = db.query(BookRequest).filter(
                BookRequest.status == "pending", BookRequest.pickup_deadline < now).all()
            for req in expired:
                req.status = "expired"
                _, created = self._generate_fine_idempotent(
                    db, req.usn, "pickup_expiry", req.id,
                    config.LIBRARY_PICKUP_FINE, "BOOK_REQUEST_NOT_COLLECTED")
                req.fine_generated = True
                if created:
                    expired_count += 1
            db.commit()
        finally:
            db.close()
        if expired_count:
            await self.publish("library.request_expired", {"count": expired_count})
        return {"expired": expired_count}
