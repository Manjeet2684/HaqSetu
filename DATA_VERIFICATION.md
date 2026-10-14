# HaqSetu Policy Evidence & Human Verification Protocol

## 1. Source Hierarchy

| Tier | Source Type | Permitted Use |
|------|-------------|---------------|
| **Tier 1** | Official Ministry guidelines PDFs, Government Orders (Shasanadesh), official scholarship portals (`scholarships.gov.in`, `scholarship.up.gov.in`) | Authoritative basis for eligibility rules, conditions, documents |
| **Tier 2** | Official government aggregators (`myscheme.gov.in`) | Discovery and navigation aid only; not a source for rule thresholds |
| **Tier 3** | Private blogs, news summaries, AI-extracted assertions | **Prohibited** for eligibility rules |

AI research alone is **never** treated as human verification.

---

## 2. Current Scheme Verification Status

### PM-USP Central Sector Scheme (`pmsp-central-sector`)

**Observed Portal Facts (source-backed):**
- Hosted on National Scholarship Portal: https://scholarships.gov.in
- Ministry of Education CSSS FAQ/Guidelines PDF published at: https://scholarships.gov.in/public/schemeGuidelines/FAQ_DOHE_CSSS.pdf
- NSP Helpdesk page (updated June 2026): https://scholarships.gov.in/fresh1819/nsphelpdesk — `helpdesk@nsp.gov.in` | `0120-6619540` | 8:00 AM–8:00 PM except government holidays
- NSP Nodal Officer directory (updated June 2026): https://scholarships.gov.in/iver/nodelOfficerDetails
- CPGRAMS general grievance portal: https://pgportal.gov.in/Home/ — general government route; applicability to this specific scheme must be confirmed

**Current Status: `LISTING_ONLY`**

**Unverified (requires human inspection):**
- Exact income ceiling (₹ per annum) for the current academic year
- Class 12 board marks percentage cutoff for fresh applicants
- GPA/attendance requirements for renewal
- Course exclusions (diploma, distance/correspondence)
- Concurrent central scholarship exclusion rules
- Application window open/close dates for current cycle

---

### UP Pre-Matric Scholarship (`up-pre-matric-scholarship`)

**Observed Portal Facts (source-backed):**
- Official state portal: https://scholarship.up.gov.in
- CPGRAMS general grievance portal: https://pgportal.gov.in/Home/ — general route; applicability to this specific category variant must be confirmed in the Government Order

**Current Status: `LISTING_ONLY`**

**Unverified (requires human inspection):**
- Which beneficiary variant to model (SC / ST / General / OBC / Minority)
- Class eligibility for the selected category (e.g., Class 9 and Class 10 — confirm in current-year GO)
- Family income threshold for the chosen category
- Required documents for the chosen category and current year
- Application window for the current academic year
- Shasanadesh (Government Order) reference and timetable

---

## 3. Mandatory Checklist Before Promoting a Real Scheme from `LISTING_ONLY` to `ASSESSABLE`

A human reviewer must:

1. Open the Tier 1 source for the **active academic cycle**
2. Record the following metadata in the scheme's `EvidenceReference` objects:
   - `verified: true`
   - `fictional: false`
   - `source_url`: direct `https://` URL to the official guideline document
   - `academic_cycle`: active cycle (e.g., `"2025-26"`)
   - `section_or_page`: exact section/page reference
   - `excerpt`: verbatim quoted clause
   - `access_date`: ISO date when the page was read
   - `verification_date`: ISO date when the rule was verified
   - `verified_by`: full name or role of the human reviewer
3. Update the `SchemeRecord` metadata:
   - `human_verified: true`
   - `verified_by`: reviewer name/role
   - `verification_date`: ISO date
   - `official_source_inspected: true`
   - `official_source_url`: official guideline URL
   - `academic_year_verified`: active cycle
4. Run `python -m pytest -v` to confirm all validation checks pass

Only after all 4 steps may `readiness` be changed to `ASSESSABLE`.

---

## 4. What HaqSetu Never Fabricates

- Award amounts
- Income limits or marks thresholds (for real schemes)
- Application windows or deadlines
- Mandatory document specifications
- Processing times or SLAs
- Official names, designations, or phone numbers
- Grievance channel details not backed by a source URL

---

## 5. Aadhaar and Bank Data Policy

HaqSetu does **not** ask users to enter Aadhaar numbers, bank account numbers, or passwords. The verification checklists mention that users should verify such requirements exist in the official Government Order — they do not imply HaqSetu collects this data.
