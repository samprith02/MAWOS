export type Role = 'student' | 'faculty' | 'hod' | 'principal' | 'admin'

export interface User { username: string; role: Role; name: string; usn?: string | null; dept?: string | null; ai_mode?: string }
export interface AuthResponse { token: string; user: User; ai_mode: string }
export interface AttendanceSubject { subject: string; held: number; attended: number; pct: number; shortage: boolean }
export interface FeeItem { id: number; type: string; amount_due: number; fine: number; status: string; due_date: string }
export interface Timetable { dept?: string; year?: number; section?: string; days: string[]; periods: string[]; cells: Record<string, { subject: string; subject_name: string; faculty?: string; room: string; class?: string }> }
export interface StudentDashboard { profile: { usn: string; name: string; dept: string; dept_name: string; year: number; semester: number; section: string; cgpa: number; backlogs: number; category: string; admission_year: number }; attendance: { overall: number; subjects: AttendanceSubject[] }; marks: { subject: string; name: string; internals: Record<string, number>; cie_average: number | null }[]; fees: { cleared: boolean; total_outstanding: number; items: FeeItem[] }; hall_ticket: { eligible: boolean; reasons: string[] } | null; scholarship: { status: string; ml_score: number | null; reasons: string[] } | null; placements: Placement[]; timetable: Timetable; exams: Exam[]; notifications: Notification[] }
export interface Placement { company: string; role: string; package_lpa: number; date: string; departments: string; eligible: boolean; probability: number | null; reasons: string }
export interface Exam { date: string; session: string; subject: string; subject_name?: string }
export interface Notification { title: string; message: string; at: string }
export interface Assignment { subject: string; subject_name: string; dept: string; year: number; section: string; credits: number }
export interface FacultyOverview { assignments: Assignment[]; timetable: Timetable; notifications: Notification[] }
export interface RosterStudent { usn: string; name: string; cgpa: number; attendance: number }
export interface HODAnalytics { dept: string; students: number; shortage_students: number; avg_attendance: number; avg_cgpa: number; by_year: Record<string, number>; fee_defaulters: Defaulter[]; sections: { year: number; section: string }[] }
export interface Defaulter { usn: string; name: string; dept: string; year: number; fee_type: string; amount_due: number; fine: number }
export interface PrincipalAnalytics { departments: Record<string, HODAnalytics>; fee_collection: Record<string, { due: number; collected: number; pct: number }>; placements: { upcoming_drives: number; eligible_finalists_by_dept: Record<string, number> }; admissions: AdmissionsFunnel }
export interface AdmissionsFunnel { stages: Record<string, number>; departments: Record<string, { intake: number; applications: number; allotted: number }> }
export interface Application { id: number; name: string; dept: string; category: string; tenth: number; twelfth: number; entrance: number; status: string; merit_score: number | null; merit_rank: number | null; usn: string | null; notes: string }
export interface AdmissionsResponse { funnel: AdmissionsFunnel; applications: Application[] }
export interface WorkflowSummary { workflow_id: string; started_at: string; duration_ms: number; events: number; depth_hops: number }
export interface WorkflowTrace { workflow_id: string; events: { topic: string; agent: string; hop: number; elapsed_ms: number; at: string }[] }
export interface Agent { name: string; description: string }
export interface Metrics { intent: Record<string, number | boolean | null>; propagation: Record<string, number | boolean>; notifications_generated: number; bus_events_logged: number }
