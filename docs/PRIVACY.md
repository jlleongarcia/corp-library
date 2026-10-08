# Corp Library — Privacy and the duty to inform

_Last updated: 2026-10-08. Context: the app is run by a **public institution in Spain** for its own staff._

> **Status: DRAFT, pending expert review.** Neither this analysis nor the notice in the app
> (`PrivacyPage.tsx`, `privacy.tsx`) has been assessed yet by the DPO or the institution's legal
> service. Don't treat them as approved, and don't let people use the app until they are (BUG-033).

This document explains why Corp Library must show a privacy notice, what the notice says and on what
legal grounds, and what the institution must do before the app goes live. It is the reasoning behind
`frontend/src/pages/PrivacyPage.tsx` (the full notice) and `frontend/src/components/privacy.tsx` (the
first layer at the bottom of every page). It is a technical write-up for the data protection officer
and the institution's legal service to review, not legal advice.

---

## 1. Why the app needs a notice

Corp Library processes personal data of the staff who use it, so the GDPR's duty of transparency
applies: people must be told, **when the data is collected**, who processes it, why, on what basis,
for how long, who receives it, and what rights they have (GDPR arts. 12–14; LOPDGDD art. 11).

What makes it unavoidable is the **activity log**. Every sign-in, search (with the words typed),
document view, preview, download and denied attempt is stored with the person's username and IP
address for a year. That is the monitoring of employees' use of a digital work tool, which Spanish law
allows only if staff have been informed beforehand, clearly and expressly (LOPDGDD art. 87; TREBEP
art. 14.j bis; for staff under employment contracts, Estatuto de los Trabajadores art. 20.3). Without
a notice:

- the processing breaches GDPR arts. 5.1.a and 13 (transparency), a sanctionable infringement even for
  public bodies (LOPDGDD art. 77: declaration of infringement and disciplinary measures);
- the log loses its value: information obtained by monitoring that staff weren't told about can be
  challenged as evidence in disciplinary or court proceedings.

A notice is required even though Windows already controls access to the documents: the app creates
new personal data (the log) that the file server alone doesn't.

## 2. What the app processes

| Data | Where | Kept | Code |
| --- | --- | --- | --- |
| Username, name, email, SID, AD groups | `users`, `sessions.token_sids` | Account: until `AUDIT_RETENTION_DAYS` after the last sign-in. Groups: re-read every `GROUPS_REFRESH_HOURS` | `auth/sessions.py`, `worker.py::housekeeping` |
| Session: sign-in time, last activity, method, IP, browser | `sessions` | Until sign-out or `SESSION_DAYS` without use | `auth/sessions.py` |
| Activity log: sign-ins (and failures), sign-outs, searches with their text and filters, views, previews, downloads, denied attempts, admin queries of the log | `audit_events` | `AUDIT_RETENTION_DAYS` (365) | `services/audit.py` |
| All of the above, in backups | `BACKUP_DIR` | `BACKUP_KEEP_DAYS` (14) more | `deploy/backup.sh` |

Not processed: passwords (checked against AD, never stored), anything sent outside the network (no
cloud, no third-party AI, no external fonts or scripts: BUG-034).

The documents themselves contain personal data of other people. Indexing them doesn't widen who can
read them (each person only sees what Windows lets them open), but that processing belongs to each
share's own purpose and record of processing, not to this notice.

## 3. Why the activity log is necessary (and proportionate)

Monitoring staff must pass the proportionality test the Constitutional Court and the European Court of
Human Rights apply (suitable, necessary, proportionate; *Bărbulescu v. Romania*, 2017; *López Ribalda
v. Spain*, 2019). The log passes it:

- **It is the only record of access through the app.** The app opens files with the scanner's service
  account, so the file server's own audit sees that account, never the person. Without this log,
  nobody could say who viewed or downloaded a document through Corp Library.
- **Searches are accesses too.** Results show excerpts of the documents' text (snippets). Someone could
  read personal data from snippets without opening a single document; without logging searches, that
  would leave no trace. (Considered and rejected on 2026-10-08: dropping per-user search logging.)
- **It is legally required.** The Esquema Nacional de Seguridad, which every public sector information
  system must apply (Ley 40/2015 art. 156; Real Decreto 311/2022; LOPDGDD first additional provision),
  requires logging users' activity, and GDPR art. 32 requires being able to detect and investigate
  breaches.
- **It is limited.** Only this app; a fixed retention period; restricted access; every query of the log
  is itself logged (`audit_read`); never used to assess performance or working hours.

## 4. Legal framework for a public institution

| Point | Rule | Consequence in the notice |
| --- | --- | --- |
| Legal basis | **Legitimate interest (GDPR art. 6.1.f) is not available** to public authorities performing their tasks (art. 6.1, last paragraph) | Bases are 6.1.e (public interest task) for providing the tool, 6.1.c (legal obligation: GDPR art. 32, LOPDGDD 1st additional provision, ENS) for the log, plus 6.1.b for staff under employment contracts |
| Data Protection Officer | Mandatory for public bodies (GDPR art. 37.1.a; LOPDGDD art. 34) | DPO contact is required (`PRIVACY_DPO`); people may go to the DPO before complaining (LOPDGDD art. 37) |
| Record of processing | Public bodies must publish it, with the legal basis (LOPDGDD art. 31.2) | The notice links to this processing's entry (`PRIVACY_RECORD_URL`) |
| Supervisory authority | The AEPD, unless the institution belongs to an autonomous community with its own authority for its public sector (LOPDGDD art. 57: e.g. Catalonia, the Basque Country, Andalusia) | Configurable: `PRIVACY_AUTHORITY_NAME` / `PRIVACY_AUTHORITY_URL` (AEPD by default) |
| Staff | Civil servants: TREBEP (privacy in digital devices art. 14.j bis; discretion art. 53.12; disciplinary regime art. 95). Contract staff: also Estatuto de los Trabajadores art. 20.3 | Both cited; misuse may lead to disciplinary proceedings, stated openly |
| Portability | Doesn't apply to processing based on 6.1.c or 6.1.e (GDPR art. 20) | Offered only for data processed under an employment contract |
| Objection | Applies to 6.1.e processing, but may yield to compelling grounds such as system security (GDPR art. 21.1) | Stated |
| Erasure after the period | Data may need to be blocked rather than erased (LOPDGDD art. 32) | Stated |
| Security incidents | ENS incident handling involves the competent CSIRT (CCN-CERT) | Listed as a possible recipient |

## 5. How the information is given

Two layers, as LOPDGDD art. 11 allows:

1. **First layer** (`PrivacyFooter`): at the bottom of every page *and* on the sign-in page. With Kerberos
   SSO people may never see the sign-in page, and data is collected from the first request, so the
   footer is on every page. It gives the controller, DPO, purpose, legal basis, recipients, rights and
   the authority, and links to:
2. **Second layer** (`/privacy`, public, no sign-in needed): the full GDPR arts. 13–14 notice in Spanish
   (authoritative) and English, plus the conditions of use: confidentiality duty, handling of
   downloaded copies, reporting documents one shouldn't see, and a disclaimer on the accuracy of search
   results and OCR text.

Facts about the institution come from `.env` (`PRIVACY_*`, served by `GET /api/privacy`). Until they
are filled in, the notice shows `[pendiente: …]` in amber and the API logs a warning at startup.
Retention periods are read from the settings the code applies, so the notice can't drift from them.

## 6. Keeping the notice true

The notice makes promises the code (or the institution) must keep. Change them together.

| The notice says | Guaranteed by |
| --- | --- |
| Logged: sign-ins, searches with their text, views, previews, downloads, denied attempts | `audit.record` calls in `routers/auth.py`, `routers/library.py` |
| Reading the log is itself logged | `routers/reports.py::audit_log` (`audit_read`) |
| Log deleted after `AUDIT_RETENTION_DAYS`; idle accounts too | `worker.py::housekeeping`, `audit.purge_old` |
| Sessions end after `SESSION_DAYS` without use; groups re-read every `GROUPS_REFRESH_HOURS` | `auth/sessions.py` |
| Backups kept `BACKUP_KEEP_DAYS` | `deploy/backup.sh` (same variable, read by the API for the notice) |
| Passwords never stored | `auth/ldap_client.py` (bind only) |
| Nothing leaves the network; no external resources | CSP in `frontend/nginx.conf`; smoke test checks `index.html` |
| Each person only sees what Windows lets them open | `services/access.py`; tests in `test_search.py` |
| Not used to assess performance; individual records only consulted for a specific incident or authority request | **The institution**: an internal procedure must say who may authorise a consultation |
| Aggregated statistics without identifying anyone | Phase 4 (not built yet): must not reuse the per-user log in a way that identifies people |

When the text changes: update both languages, bump `NOTICE_VERSION` in `components/privacy.tsx`, and tell
users in the app (section 12 of the notice promises it).

## 7. Before go-live: what the institution must do

- [ ] DPO and legal service review this document and the notice text (pending: the notice is a draft)
- [ ] Fill in `PRIVACY_CONTROLLER`, `PRIVACY_CONTROLLER_ID`, `PRIVACY_CONTROLLER_ADDRESS`, `PRIVACY_CONTACT`,
      `PRIVACY_DPO` (and `PRIVACY_AUTHORITY_*` if a regional authority is competent)
- [ ] Add this processing to the Record of Processing Activities, publish it (LOPDGDD art. 31.2) and set
      `PRIVACY_RECORD_URL`
- [ ] Include the system in the institution's ENS scope: categorisation, security policy, and approval of
      the log's retention period (`AUDIT_RETENTION_DAYS`)
- [ ] Assess whether an impact assessment (DPIA, GDPR art. 35) is required: systematic monitoring of staff
      is on the AEPD's list of indicators; document the conclusion either way
- [ ] Inform the staff representatives (juntas de personal, comités de empresa) and set the criteria for
      using digital devices with their participation (LOPDGDD art. 87.3)
- [ ] Write the internal procedure for consulting individual log records (who authorises, who may consult,
      how it is documented) and for answering rights requests
- [ ] Appoint the app administrators (`ADMIN_USERS`) formally, with a confidentiality commitment
