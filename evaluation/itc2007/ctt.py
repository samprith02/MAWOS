"""CB-CTT instance format and cost model — a port of the official validator.

This module is the risky part of P1b. Plan 4.4 says it in as many words:
a subtly wrong mapping "produces a meaningless number, which is worse than
no number". So the cost functions below are not written from the prose on
the competition website; they are transcribed from `validator.cc` v1.1
(Schaerf and Di Gaspero, 25 Oct 2007), function by function, and
`crosscheck.py` then runs both implementations on random instances and
random solutions until they agree on every one of the eight components.

Where the official code has a quirk, this file reproduces the quirk rather
than the intent — see `curriculum_compactness`. The validator is the
definition of the score; being cleverer than it would make our number
incomparable to every published result, which is the whole point of doing
this at all.

Format (competition input spec):

    Name: ToyExample
    Courses: 4 / Rooms: 2 / Days: 5 / Periods_per_day: 4
    Curricula: 2 / Constraints: 8
    COURSES:      <id> <teacher> <#lectures> <minWorkingDays> <#students>
    ROOMS:        <id> <capacity>
    CURRICULA:    <id> <#courses> <member> ...
    UNAVAILABILITY_CONSTRAINTS: <course> <day> <period-in-day>
    END.

A solution is `{(course_index, period): room_index}` with room indices
1-based, matching the validator's `tt[c][p]` where 0 means "unscheduled".
A course can hold at most one lecture per period by construction, exactly
as in the validator, which skips repeated (course, period) entries.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Fixed by the competition. Not tunable, not ours to choose.
MIN_WORKING_DAYS_COST = 5
CURRICULUM_COMPACTNESS_COST = 2
ROOM_STABILITY_COST = 1


@dataclass(frozen=True)
class Course:
    name: str
    teacher: str
    lectures: int
    min_working_days: int
    students: int


@dataclass(frozen=True)
class Room:
    name: str
    capacity: int


@dataclass
class Instance:
    name: str
    days: int
    periods_per_day: int
    courses: list[Course]
    rooms: list[Room]
    curricula: dict[str, list[int]]
    unavailable: set[tuple[int, int]]

    course_index: dict[str, int] = field(default_factory=dict)
    room_index: dict[str, int] = field(default_factory=dict)
    conflict: list[set[int]] = field(default_factory=list)
    member_of: list[list[int]] = field(default_factory=list)

    @property
    def periods(self) -> int:
        return self.days * self.periods_per_day

    @property
    def total_lectures(self) -> int:
        return sum(c.lectures for c in self.courses)

    def __post_init__(self) -> None:
        self.course_index = {c.name: i for i, c in enumerate(self.courses)}
        # Room 0 is "unscheduled" in the validator, so real rooms are 1-based.
        self.room_index = {r.name: i + 1 for i, r in enumerate(self.rooms)}

        # Two courses conflict if they share a curriculum OR a teacher.
        # The validator stores this as a boolean matrix, so a pair that is
        # both is still one conflict, never two.
        self.conflict = [set() for _ in self.courses]
        for members in self.curricula.values():
            for i, c1 in enumerate(members):
                for c2 in members[:i]:
                    self.conflict[c1].add(c2)
                    self.conflict[c2].add(c1)
        for i, a in enumerate(self.courses):
            for j in range(i + 1, len(self.courses)):
                if a.teacher == self.courses[j].teacher:
                    self.conflict[i].add(j)
                    self.conflict[j].add(i)

        names = list(self.curricula)
        self.member_of = [[] for _ in self.courses]
        for gi, g in enumerate(names):
            for c in self.curricula[g]:
                self.member_of[c].append(gi)

    def curriculum_names(self) -> list[str]:
        return list(self.curricula)

    def available(self, course: int, period: int) -> bool:
        return (course, period) not in self.unavailable

    def room_capacity(self, room: int) -> int:
        return self.rooms[room - 1].capacity


_HEADER = re.compile(r"^\s*([A-Za-z_]+)\s*:\s*(.+?)\s*$")


def parse(text: str) -> Instance:
    """Read a .ctt file. Section order is fixed by the spec, so this reads
    positionally rather than searching for headers out of order."""
    tokens = text.split()
    header: dict[str, str] = {}
    for line in text.splitlines():
        m = _HEADER.match(line)
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2)
        if key in ("name", "courses", "rooms", "days", "periods_per_day",
                   "curricula", "constraints") and key not in header:
            header[key] = val
        if key == "constraints":
            break

    def head(key: str) -> int:
        return int(header[key])

    i = 0

    def seek(word: str) -> None:
        nonlocal i
        while i < len(tokens) and tokens[i] != word:
            i += 1
        i += 1

    seek("COURSES:")
    courses = []
    for _ in range(head("courses")):
        name, teacher, lec, mwd, stu = tokens[i:i + 5]
        i += 5
        courses.append(Course(name, teacher, int(lec), int(mwd), int(stu)))

    seek("ROOMS:")
    rooms = []
    for _ in range(head("rooms")):
        name, cap = tokens[i:i + 2]
        i += 2
        rooms.append(Room(name, int(cap)))

    cindex = {c.name: k for k, c in enumerate(courses)}

    seek("CURRICULA:")
    curricula: dict[str, list[int]] = {}
    for _ in range(head("curricula")):
        cur_name = tokens[i]
        size = int(tokens[i + 1])
        i += 2
        curricula[cur_name] = [cindex[tokens[i + k]] for k in range(size)]
        i += size

    seek("UNAVAILABILITY_CONSTRAINTS:")
    ppd = head("periods_per_day")
    unavailable: set[tuple[int, int]] = set()
    for _ in range(head("constraints")):
        cname, day, per = tokens[i:i + 3]
        i += 3
        unavailable.add((cindex[cname], int(day) * ppd + int(per)))

    return Instance(
        name=header.get("name", "unnamed"),
        days=head("days"),
        periods_per_day=ppd,
        courses=courses,
        rooms=rooms,
        curricula=curricula,
        unavailable=unavailable,
    )


def render_solution(inst: Instance, tt: dict[tuple[int, int], int]) -> str:
    """Competition output format: `<CourseID> <RoomID> <Day> <Day_Period>`."""
    lines = []
    for (c, p), r in sorted(tt.items()):
        lines.append("%s %s %d %d" % (
            inst.courses[c].name, inst.rooms[r - 1].name,
            p // inst.periods_per_day, p % inst.periods_per_day))
    return chr(10).join(lines) + chr(10)


@dataclass(frozen=True)
class Cost:
    """The validator's eight numbers, plus its two summary figures.

    Soft components are stored already weighted, matching what the
    validator prints, so `total` is a plain sum.
    """
    lectures: int
    conflicts: int
    availability: int
    room_occupation: int
    room_capacity: int
    min_working_days: int
    curriculum_compactness: int
    room_stability: int

    @property
    def violations(self) -> int:
        """Distance to feasibility. Compared before soft cost, always."""
        return (self.lectures + self.conflicts + self.availability
                + self.room_occupation)

    @property
    def total(self) -> int:
        return (self.room_capacity + self.min_working_days
                + self.curriculum_compactness + self.room_stability)

    def as_dict(self) -> dict:
        return {
            "lectures": self.lectures, "conflicts": self.conflicts,
            "availability": self.availability,
            "room_occupation": self.room_occupation,
            "room_capacity": self.room_capacity,
            "min_working_days": self.min_working_days,
            "curriculum_compactness": self.curriculum_compactness,
            "room_stability": self.room_stability,
            "violations": self.violations, "total": self.total,
        }


def cost(inst: Instance, tt: dict[tuple[int, int], int]) -> Cost:
    """Score a solution exactly as `validator.cc` does."""
    ncourses = len(inst.courses)
    periods = inst.periods
    ppd = inst.periods_per_day

    by_course: list[dict[int, int]] = [{} for _ in range(ncourses)]
    for (c, p), r in tt.items():
        by_course[c][p] = r

    # --- Lectures: a missing or an extra lecture each count 1.
    lectures = sum(abs(len(by_course[c]) - inst.courses[c].lectures)
                   for c in range(ncourses))

    # --- Conflicts: per unordered conflicting pair, per shared period.
    conflicts = 0
    for c1 in range(ncourses):
        for c2 in inst.conflict[c1]:
            if c2 <= c1:
                continue
            conflicts += len(by_course[c1].keys() & by_course[c2].keys())

    # --- Availability: each lecture in a period the course cannot use.
    availability = sum(1 for c in range(ncourses) for p in by_course[c]
                       if not inst.available(c, p))

    # --- RoomOccupation: every lecture beyond the first in a room-period.
    room_lectures: dict[tuple[int, int], int] = {}
    for c in range(ncourses):
        for p, r in by_course[c].items():
            room_lectures[(r, p)] = room_lectures.get((r, p), 0) + 1
    room_occupation = sum(n - 1 for n in room_lectures.values() if n > 1)

    # --- RoomCapacity: one point per student over the room's seats.
    room_capacity = 0
    for c in range(ncourses):
        students = inst.courses[c].students
        for r in by_course[c].values():
            over = students - inst.room_capacity(r)
            if over > 0:
                room_capacity += over

    # --- MinWorkingDays: 5 points per day below the course's minimum.
    min_working_days = 0
    for c in range(ncourses):
        used_days = {p // ppd for p in by_course[c]}
        short = inst.courses[c].min_working_days - len(used_days)
        if short > 0:
            min_working_days += short
    min_working_days *= MIN_WORKING_DAYS_COST

    # --- CurriculumCompactness: 2 points per isolated lecture.
    #
    # Transcribed branch for branch from CostsOnCurriculumCompactness().
    # Two things here are the validator's behaviour rather than the
    # website's wording, and both are deliberate:
    #   * the count added is the number of lectures of that curriculum in
    #     the period, which can exceed 1 when the solution is infeasible;
    #   * `at()` returns 0 outside the period range, where the C++ reads
    #     the array directly. That only differs when periods_per_day == 1,
    #     because then every period takes the lookahead branch and the
    #     last one reads past the end of the row -- undefined behaviour in
    #     the reference implementation. No competition instance has
    #     ppd == 1 (comp01-comp21 use 4 to 6), so crosscheck.py excludes
    #     that case rather than pretending either answer is correct.
    ncur = len(inst.curricula)
    cpl = [[0] * periods for _ in range(ncur)]
    for c in range(ncourses):
        for gi in inst.member_of[c]:
            row = cpl[gi]
            for p in by_course[c]:
                row[p] += 1

    def at(row: list[int], p: int) -> int:
        return row[p] if 0 <= p < periods else 0

    compact = 0
    for row in cpl:
        for p in range(periods):
            n = row[p]
            if n == 0:
                continue
            if p % ppd == 0:
                if at(row, p + 1) == 0:
                    compact += n
            elif p % ppd == ppd - 1:
                if at(row, p - 1) == 0:
                    compact += n
            elif at(row, p + 1) == 0 and at(row, p - 1) == 0:
                compact += n
    compact *= CURRICULUM_COMPACTNESS_COST

    # --- RoomStability: one point per distinct room past the first.
    stability = 0
    for c in range(ncourses):
        used = len(set(by_course[c].values()))
        if used > 1:
            stability += used - 1
    stability *= ROOM_STABILITY_COST

    return Cost(lectures=lectures, conflicts=conflicts,
                availability=availability, room_occupation=room_occupation,
                room_capacity=room_capacity,
                min_working_days=min_working_days,
                curriculum_compactness=compact, room_stability=stability)
