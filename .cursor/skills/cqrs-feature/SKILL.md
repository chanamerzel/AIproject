---
name: cqrs-feature
description: Implements a complete FitScreen feature using CQRS and Event Sourcing. Use when adding a user-facing feature, a command, a projection, or a Flask screen for jobs or applications.
---

# Implement a CQRS feature

## Steps

1. Open `docs/04-features.md` and identify the feature id (F1–F8).
2. If the feature writes data:
   - Add a command DTO and handler under `app/commands/`.
   - Append a typed event via `EventStore.append`.
   - Handle the event in `app/projections.py`.
3. If the feature reads data:
   - Add a function under `app/queries/` that only SELECTs.
4. Add or update a view in `app/views/` and a Jinja template.
5. Protect the route with `@login_required` and `@role_required`.
6. Add a pytest in `tests/` matching `docs/06-testing.md`.
7. Update `docs/07-traceability.md` if a new file was introduced.

## Example

Applying to a job: `SubmitApplication` → `ApplicationSubmitted` → projection inserts `applications` and increments `jobs.applicant_count` → query `get_job` shows the new count.
