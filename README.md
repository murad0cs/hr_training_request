# HR Training Request

An Odoo module that lets employees request external training / certifications
and routes each request through a **role-gated Manager → HR approval workflow**.

- **Odoo version:** 17.0 (Community). The code uses the modern view syntax
  (`invisible=`/`readonly=` expressions, no `attrs`/`states`), so it also loads
  on 18.0 — on 18 you'd rename the `<tree>` tags to `<list>`.
- **Depends on:** `hr`, `mail`

---

## 1. Installation & testing

```bash
# from your Odoo root, with this module on the addons path:
./odoo-bin -d <db> -i hr_training_request --dev=all
# include demo data (don't pass --without-demo) to get the demo users below
```

Demo users (password = login):

| Login   | Name        | Role                     |
|---------|-------------|--------------------------|
| `sarah` | Sarah Chen  | Training Requester       |
| `james` | James Patel | Training Manager Approver (Sarah's manager) |
| `dana`  | Dana Ortiz  | Training HR Approver     |

The built-in **Administrator** is also granted the HR Approver role so you can
inspect everything from one login. Open **Training** in the top menu.

**Suggested walkthrough** (mirrors the three wireframes):
1. Log in as `sarah`, open the "AWS Solutions Architect" draft → **Submit**.
2. Log in as `james` → **Team Requests** opens on his pending approvals →
   **Approve** (or Reject). Fields are read-only; no HR Notes tab.
3. Log in as `dana` → **HR Approvals** opens on "Pending HR Approval" →
   **Final Approve**. Only Dana sees the **HR Notes** tab/field.

### Running the tests

```bash
./odoo-bin -d <db> -i hr_training_request --test-enable --stop-after-init
```

The suite in `tests/` covers the security-critical paths: role-gated
transitions, blocked illegal jumps via raw `write`, record-rule visibility per
role, the HR-only field being stripped for non-HR users, the cost/date
validations, and the access-filtered smart-button count.

---

## 2. Security group hierarchy (and why)

```
Training HR Approver        (final approval, sees ALL company requests + HR notes)
      └── implies ──▶ Training Manager Approver   (approve/reject direct reports)
                            └── implies ──▶ Training Requester   (own requests)
                                                  └── implies ──▶ base.group_user
Training HR Approver also implies hr.group_hr_user  (reuse standard HR read access)
```

A **linear hierarchy** was chosen because access is genuinely cumulative in this
process: HR does everything a manager can *plus* more, a manager does everything
a requester can *plus* more. Implication means I only describe the *delta* at
each level, and record rules widen automatically as you go up. HR additionally
implies the stock `hr.group_hr_user` group, reusing existing HR access rather
than reinventing employee-data permissions.

### Two independent layers of enforcement

Row-level security does **not** rely on view hiding. It is enforced twice:

1. **`ir.model.access.csv`** — table-level CRUD per group (requester/manager can
   read/write/create; HR can also unlink).
2. **Record rules (`ir.rule`)** — row-level visibility:
   - Requester → `employee_id.user_id == uid OR create_uid == uid` (own only)
   - Manager Approver → own **+** direct reports (`manager_id.user_id == uid`)
   - HR Approver → all requests in the user's allowed companies
     (`company_id in company_ids`, so multi-company stays isolated)

   Rules for the same operation are OR-combined across a user's groups, so the
   hierarchy makes visibility widen automatically.

### State transitions are guarded in Python, not just in XML

`groups=` and `invisible=` on the buttons are **UI convenience only**. The real
enforcement is server-side in `write()` → `_check_state_transition()`, which:

- rejects any transition not in the `_TRANSITIONS` map (no illegal state jumps
  from the UI, XML-RPC or the shell), and
- checks the acting user's role for the specific transition (owner submits/
  cancels; the employee's **manager** approves/rejects at *submitted*; an **HR
  Approver** approves/rejects at *manager_approved*).

Because all six button actions funnel through `write()`, there is exactly one
place where authorisation lives. The computed `can_submit` / `can_cancel` /
`can_manager_review` / `can_hr_review` fields reuse the *same* role predicates to
drive button visibility, so UI and server can never disagree.

The **HR Notes** field carries `groups="...group_training_hr_approver"` at the
**field** level, so the ORM strips it from reads/writes for non-HR users — it is
invisible even over XML-RPC, not merely hidden in the form.

**No `sudo()` is used anywhere** — nothing silently bypasses the access checks.
The employee smart-button count is computed with a normal `read_group`, which
runs as the current user and therefore already respects the record rules.

---

## 3. State machine

```
        submit                 manager approve            hr approve
draft ──────────▶ submitted ───────────────▶ manager_approved ──────────▶ hr_approved
  │                  │  │                          │
  │ cancel           │  │ manager reject           │ hr reject
  ▼                  ▼  ▼                          ▼
cancelled        cancelled   rejected          rejected
```

- `rejected` is reachable from `submitted` (manager) or `manager_approved` (HR).
- `cancelled` is reachable only from `draft` or `submitted`, and only by the owner.
- `hr_approved`, `rejected`, `cancelled` are terminal.
- Validation on submit: `end_date >= start_date` and `cost` not negative
  (also enforced continuously via `@api.constrains`).

State changes are tracked in the chatter (`mail.thread`).

---

## 4. Assumptions

- **"The employee's manager (or someone in the Manager Approver group)"** is
  read as: the acting user must be in the Manager Approver group **and** be the
  employee's direct manager (`manager_id.user_id == uid`). This is consistent
  with the record rule that only lets managers *see* their reports' requests, so
  a manager can never act on someone they don't manage. HR is intentionally kept
  separate from manager approval.
- **`justification`** is surfaced as the **"Description"** notebook tab (matches
  the wireframes), since it is the free-text rationale for the request.
- **`end_date`** may equal `start_date` (single-day courses are common); the
  rule enforced is "not before", messaged as "on or after".
- **Reference number** (`TR0001…`) is added via an `ir.sequence` for a friendlier
  record name — the spec didn't require it but the wireframes show one.
- `employee_id` is editable while in *draft* (defaults to the current user) so
  that HR can raise a request on someone's behalf; it locks once submitted.
- Multi-company is supported via `company_id` + the company-scoped HR rule.

---

## 5. What I'd improve with more time

- A **reject reason** wizard (capture a mandatory comment, post it to chatter and
  optionally email the requester) instead of a bare Reject button.
- **Activity scheduling**: on submit, schedule a "To approve" activity for the
  manager; on manager approval, one for HR — so approvals show up in each
  approver's inbox rather than being pull-only.
- **Email templates / notifications** on each transition.
- Budget/approval-limit logic (e.g. auto-route high-cost requests to a second
  approver) and reporting (pivot/graph views by cost, provider, period).
