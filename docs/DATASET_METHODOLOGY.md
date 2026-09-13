# Dataset Methodology — exact sources, features, and mapping

This chapter answers, precisely, the three questions an examiner will ask:
**which dataset, which features, how mapped** — and confronts the
Portuguese-school-data-for-an-Indian-ERP objection head-on instead of hoping
nobody raises it.

## 1. Source dataset (exact identification)

**UCI Machine Learning Repository, dataset #320: "Student Performance"**
P. Cortez and A. Silva, "Using Data Mining to Predict Secondary School
Student Performance," Proc. 5th FUture BUsiness TEChnology Conference
(FUBUTEC 2008), Porto, 2008.
Download: https://archive.ics.uci.edu/dataset/320/student+performance
Files used: `student-mat.csv` (n=395) and `student-por.csv` (n=649),
concatenated → **n=1,044** student records. Cached under
`ml/data/external/student/`; processed by `ml/calibrate.py`.

## 2. Feature mapping (exact formulas)

| UCI feature | MAWOS variable | Mapping | Estimated (n=1,044) |
|---|---|---|---|
| `G3` final grade, 0–20 (rows with G3>0; G3=0 codes dropout, not a grade) | CGPA, 4.0–10.0 | `cgpa = 4 + 6·(G3/20)` (linear range map) | mean 7.585, std 0.874 |
| `absences` days, 0–93 | attendance % | `att = 100·(1 − absences/93)`, 93 = max observed ≈ one year of course sessions | mean 95.23, std 6.68 |
| `failures` count of past class failures, 0–4 | backlog count | identity (both count failed courses) | P = [0.825, 0.115, 0.032, 0.029, 0.0] |
| *(pairwise structure of the three above)* | correlation matrix | Pearson correlations on the mapped values | cgpa↔att +0.218, cgpa↔backlogs −0.349, att↔backlogs −0.151 |

**Correlation preservation.** The generator does *not* sample features
independently — that would destroy the real relationships (better-attending
students earn better grades; past failures predict lower grades). Instead it
uses a **Gaussian copula**: draw z ~ N(0, C) with C the correlation matrix
estimated above, then apply each variable's calibrated marginal (Gaussian for
CGPA and attendance; quantile-mapping onto the empirical count distribution
for backlogs). Verify in `ml/generate_datasets.py::sample_correlated_profile`;
the synthetic correlations reproduce the real ones to within sampling error.

## 3. Variables NOT in UCI — explicit assumptions

| Variable | Model used | Justification |
|---|---|---|
| Family income | log-normal, median ≈ ₹4.4 L, clipped ₹0.6 L–₹30 L | Household income is conventionally modelled as log-normal; India-specific income microdata with academic features is not publicly available. Stated as an assumption. |
| Fee clearance | Bernoulli(0.82), independent | No public source pairs fee status with academics; the rate mirrors the seeded institution's defaulter share. Stated as an assumption. |
| Scholarship label | banded committee scoring (income slabs, CGPA/attendance bands) + N(0, 0.15) committee noise + 3% label flips + injected hardship borderline cases | Indian scholarship schemes literally score by slabs/bands; noise terms ensure the label is not a re-encoding of any rule. |
| Placement label | Bernoulli draw from a logistic model centred on the calibrated population means | Identical profiles can differ in outcome, as in reality; base rate lands at ~47%, consistent with typical tier-2 campus placement rates. |

## 4. Threats to validity (say this before the examiner does)

**"Portuguese secondary-school data for an Indian engineering ERP?"**
The claim is deliberately narrow. We do **not** claim UCI students are
statistically exchangeable with VTU students. We claim only that the
*marginal shapes and the sign/magnitude of the correlations* among
(grades, attendance, prior failures) are more defensible when estimated from
1,044 real student records than when invented by the authors — which was the
alternative on the table (no Indian institution shares student records, and
DPDP Act 2023 constraints make that unlikely to change). The pipeline is
**re-runnable against any dataset**: when institutional data becomes
available (e.g. via the federated set-up in `fl/`), `calibrate.py` re-estimates
every parameter from it and nothing else changes. Calibration source,
formulas, and estimated values are all version-controlled
(`ml/data/calibration.json`), so the paper's numbers are exactly reproducible.

**Known distribution shifts we accept and disclose:**
- UCI absenteeism is low (mean attendance ≈95%); Indian engineering colleges
  enforce a 75% rule precisely because the left tail is heavier. The
  *operational* seed data therefore uses a wider attendance spread to
  exercise shortage workflows; the *training* data stays UCI-calibrated, and
  the rule pre-filter guarantees the ML model only ever scores students with
  ≥75% attendance — inside the well-supported region.
- Grade scales differ (0–20 continuous vs 10-point CGPA); the linear map
  preserves rank and shape, not institutional grading culture.

## 5. Reproduction

```bash
python ml/calibrate.py           # re-estimates every parameter from the raw CSVs
python ml/generate_datasets.py   # correlated synthetic data from calibration.json
python ml/train.py               # CART + RF, held-out test + 5-fold CV
```
