---
status: exploratory
owner: technical
purpose: ADR-083 — after a failed converge, the same digest is retried with back-off rather than on every timer pass
---

# ADR-083 — A failed digest is retried with back-off, not on every pass

**Proposed:** 2026-11-24 (Life Scientific, contributed as a pull request; awaiting Brian).

**Adds:** `BR-DEPLOY-027`. **Relates to:** `ADR-025`, `ADR-026`, `ADR-081`, `ADR-082`.

## Context

A failed converge halts and reports (`ADR-025`). Nothing stops the next timer pass from trying
the same digest again, because the environment tag still names it. On a target whose timer
runs every 15 seconds, a deploy whose `bench migrate` fails is retried four times a minute:
each attempt pulls, runs the configurator and migrates again, and each one loads the database
the old code is still serving. `ADR-025`'s own concern, that a fault could flap rather than
halt, applies to the retry as much as to a rollback.

It matters more once a migrate is meant to fail on purpose. Life Scientific plans to make a
migrate give up quickly when it cannot take a table lock, rather than queue every user's
request behind it for up to five minutes. A quick failure is only safe if cairn does not then
retry it at once, in a loop.

## Decision

**Remember the failed digest, in `/run`.** When a pass fails to converge, cairn writes
`/run/cairn/failed-deploy`: the digest, when it last failed, how many times, and the first
line of the error. `/run` is tmpfs, so a reboot clears it, as it clears the drained-workers
list. Nothing in it is a secret or a log line; it holds one record and is overwritten.

**Wait before trying that digest again.** A pass whose desired digest is the remembered one
does nothing until 1 minute after the first failure, then 5, then 15, then 60 minutes after
each later one. While waiting, the pass reports *waiting*: the digest, the failure, how many
attempts, and when it will try again. It exits as a failure, so `systemctl is-failed` and
`doctor` keep showing that the environment is not where its tag says. A waiting pass prints
no deploy record (`ADR-082`), because it does not start to converge.

**Three things end the wait.**

- A different digest. Pushing a fix, or moving the tag back, is the operator's answer, and it
  goes ahead at once.
- A converged stack, however it got there.
- `cairn-adopt reconcile --retry-now`, for an operator who has fixed something outside the
  image (a locked table, a full disk) and wants to try now. `start` and `restart` are attended
  verbs and retry at once too.

## What it does not do

- **No rollback.** The old code keeps serving exactly as `ADR-025` leaves it.
- **No limit on attempts.** After 60 minutes it keeps trying hourly. Giving up entirely would
  need someone to notice; the failure exit code already asks for that.
- **No change to a pass that succeeds.** The state is cleared and nothing else differs.

## Rejected alternatives

- **Place a hold after a failure.** A hold (`BR-DEPLOY-024`) stops every digest, including the
  fix. It is the operator's tool, and cairn placing one would be cairn deciding on its own.
- **Keep the state in `/var/lib`.** A reboot is a reasonable point to try again, and `/run`
  keeps cairn without durable state of its own (`ADR-026`).
- **A descriptor key for the schedule.** No target has asked for a different one yet.

## Open for Brian

1. Is a waiting pass a failure for the exit code, or should it exit 0 like a held pass?
2. Should `start` and `restart` honour the back-off instead of retrying at once?

*(BR-DEPLOY-016, BR-DEPLOY-018, BR-DEPLOY-024, BR-DEPLOY-026, BR-DEPLOY-027)*
