"""Explicit response contracts for the Principal and Admin dashboards."""
from pydantic import BaseModel, Field


class DepartmentAnalyticsResponse(BaseModel):
    dept: str
    students: int = 0
    faculty: int = 0
    shortage_students: int = 0
    avg_attendance: float = 0.0
    avg_cgpa: float = 0.0
    by_year: dict[int, int] = Field(default_factory=dict)


class DepartmentFeeCollectionResponse(BaseModel):
    due: float = 0.0
    collected: float = 0.0
    pct: float = 0.0


class FeeCollectionResponse(BaseModel):
    total_due: float = 0.0
    total_collected: float = 0.0
    total_outstanding: float = 0.0
    by_department: dict[str, DepartmentFeeCollectionResponse] = Field(
        default_factory=dict)


class PlacementStatsResponse(BaseModel):
    upcoming_drives: int = 0
    eligible_finalists: int = 0
    eligible_finalists_by_dept: dict[str, int] = Field(default_factory=dict)


class DepartmentAdmissionsResponse(BaseModel):
    intake: int = 0
    applications: int = 0
    allotted: int = 0


class AdmissionsFunnelResponse(BaseModel):
    stages: dict[str, int] = Field(default_factory=dict)
    departments: dict[str, DepartmentAdmissionsResponse] = Field(default_factory=dict)


class PrincipalAnalyticsResponse(BaseModel):
    departments: list[DepartmentAnalyticsResponse] = Field(default_factory=list)
    fee_collection: FeeCollectionResponse = Field(default_factory=FeeCollectionResponse)
    placements: PlacementStatsResponse = Field(default_factory=PlacementStatsResponse)
    admissions: AdmissionsFunnelResponse = Field(default_factory=AdmissionsFunnelResponse)


class AdmissionApplicationResponse(BaseModel):
    id: int
    applicant_name: str
    dept_code: str
    category: str
    tenth_pct: float
    twelfth_pct: float
    entrance_score: float
    status: str
    merit_score: float | None = None
    merit_rank: int | None = None
    allotted_usn: str | None = None
    notes: str = ""


class AdminAdmissionsResponse(BaseModel):
    funnel: AdmissionsFunnelResponse = Field(default_factory=AdmissionsFunnelResponse)
    applications: list[AdmissionApplicationResponse] = Field(default_factory=list)
