"""Fictional name pools.

Every person, company and subject name in a generated institution comes from
here. No real individual is represented: v3 seeded four real team members at
their real USNs, and R1 removes that along with the rest of the real
institutional identity (`docs/v4/04_DATA_MODEL.md` §3).

Given names are common South-Indian forenames and surnames, which keeps the
generated institution regionally plausible without naming anybody real —
plausibility is the point, since the timetable and fee workflows are meant to
look like a real college's.
"""
from __future__ import annotations

import random

FIRST = ["Aditi", "Rahul", "Sneha", "Kiran", "Divya", "Manoj", "Pooja",
         "Vikas", "Anusha", "Rohan", "Shreya", "Karthik", "Meghana", "Nithin",
         "Bhavana", "Suhas", "Ramya", "Akash", "Deeksha", "Varun", "Ishita",
         "Tejas", "Nandini", "Yashas", "Prerana", "Chetan", "Sanjana", "Om",
         "Harsha", "Lavanya", "Girish", "Swathi", "Ravindra", "Keerthi",
         "Sandesh", "Aishwarya", "Nikhil", "Trupti", "Gagan", "Vaishnavi"]

LAST = ["Shetty", "Rao", "Kamath", "Hegde", "Nayak", "Pai", "Kulkarni",
        "Bhat", "Acharya", "Salian", "Poojary", "Kini", "Prabhu", "Suvarna",
        "Ballal", "Amin", "Shenoy", "Mallya", "Karkera", "Devadiga",
        "Alva", "Bangera", "Chowta", "Hebbar", "Kotian", "Padiyar",
        "Rai", "Sherigar", "Tantri", "Upadhya"]

DESIGNATIONS = ["Professor", "Associate Professor", "Assistant Professor",
                "Assistant Professor", "Assistant Professor"]

CATEGORIES = ["GM", "GM", "OBC", "SC", "ST", "CAT-1"]

COMPANIES = ["Northwind Systems", "Cobalt Analytics", "Meridian Softworks",
             "Trellis Technologies", "Ironwood Digital", "Vertex Labs",
             "Silverline Consulting", "Kestrel Robotics", "Halcyon Data",
             "Bluepeak Engineering", "Arclight Semiconductors",
             "Foundry Interactive", "Lumen Infotech", "Redwood Automation",
             "Solstice Networks", "Granite Cloud", "Pinnacle Motors",
             "Aether Aerospace", "Copperfield Energy", "Wavelet AI",
             "Quarry Analytics", "Beacon Fintech", "Corvus Security",
             "Tidewater Infra", "Zenith Materials"]

JOB_ROLES = ["Software Engineer", "Systems Engineer", "Data Analyst",
             "Graduate Engineer Trainee", "Associate Consultant",
             "QA Engineer", "ML Engineer", "Design Engineer",
             "Site Reliability Engineer", "Embedded Engineer"]

LEAVE_REASONS = ["conference travel", "medical", "personal",
                 "university duty", "workshop", "examination duty"]

SUBJECT_POOLS = {
    "AIML": ["Machine Learning", "Deep Learning", "Data Mining",
             "Natural Language Processing", "Computer Vision",
             "Big Data Analytics", "Reinforcement Learning", "MLOps",
             "AI Ethics", "Pattern Recognition", "Neural Networks",
             "Data Visualization", "Statistics for ML", "Python Programming",
             "Discrete Mathematics", "Database Systems", "Operating Systems",
             "Computer Networks", "Software Engineering", "Linear Algebra"],
    "CSE": ["Data Structures", "Algorithms", "Operating Systems",
            "Database Systems", "Computer Networks", "Compiler Design",
            "Web Technologies", "Cloud Computing", "Cyber Security",
            "Distributed Systems", "Software Engineering",
            "Theory of Computation", "Java Programming", "Microprocessors",
            "Discrete Mathematics", "Computer Graphics", "IoT Systems",
            "Mobile Computing", "DevOps", "System Design"],
    "ECE": ["Digital Electronics", "Analog Circuits", "Signals & Systems",
            "Communication Systems", "VLSI Design", "Embedded Systems",
            "Microwave Engineering", "Antenna Theory", "Control Systems",
            "Digital Signal Processing", "Network Analysis",
            "Electromagnetics", "Optical Communication", "Wireless Networks",
            "Circuit Theory", "Power Electronics", "Satellite Communication",
            "Radar Systems", "FPGA Design", "5G Systems"],
    "ME": ["Thermodynamics", "Fluid Mechanics", "Machine Design",
           "Manufacturing Processes", "Heat Transfer",
           "Dynamics of Machinery", "CAD/CAM", "Robotics",
           "Automobile Engineering", "Turbomachines", "Material Science",
           "Engineering Mechanics", "Metrology", "Operations Research",
           "IC Engines", "Mechatronics", "Finite Element Analysis",
           "Refrigeration & Air Conditioning", "Kinematics",
           "Industrial Engineering"],
    "CV": ["Structural Analysis", "Concrete Technology",
           "Geotechnical Engineering", "Surveying",
           "Transportation Engineering", "Environmental Engineering",
           "Hydraulics", "Steel Structures", "Construction Management",
           "Estimation & Costing", "Building Materials",
           "Earthquake Engineering", "Foundation Engineering",
           "Water Resources", "Highway Engineering", "Remote Sensing & GIS",
           "Prestressed Concrete", "Bridge Engineering",
           "Irrigation Engineering", "Green Buildings"],
}

#: Used when a department code has no bespoke pool, so adding a department to
#: institution.yaml never crashes the generator.
GENERIC_POOL = [f"Core Subject {i + 1}" for i in range(20)]


def person_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def designation(index: int) -> str:
    return DESIGNATIONS[min(index // 3, len(DESIGNATIONS) - 1)]


def category(rng: random.Random) -> str:
    return rng.choice(CATEGORIES)


def company(rng: random.Random) -> str:
    return rng.choice(COMPANIES)


def job_role(rng: random.Random) -> str:
    return rng.choice(JOB_ROLES)


def leave_reason(rng: random.Random) -> str:
    return rng.choice(LEAVE_REASONS)


def subject_pool(dept_code: str) -> list[str]:
    return SUBJECT_POOLS.get(dept_code, GENERIC_POOL)
