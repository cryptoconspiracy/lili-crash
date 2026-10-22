# Second Diolinux feedback: implementation and limits

This change implements a local-first diagnostic profile, explainable early warnings,
portable incident reports and a remote-session privacy gate. It does not claim to
train a specialist model, predict arbitrary failures, deploy a fleet server or repair
machines automatically.

## Local diagnosis

New settings select Ollama. Saved provider/model choices are preserved. Setup uses
the selected base model (default `qwen3.5:4b`) and creates a versioned alias with a
Linux diagnosis system prompt and a 64k context. Updating the instructions changes
the alias, so an older prepared model cannot be mistaken for the new profile.
Setup may download OpenCode/Ollama/model files; it never falls back to a remote model
if installation or inference fails. The UI indicates when setup is needed.

The profile emphasizes impact, chronological evidence, distro notes, uncertainty,
log-injection resistance, prevention and explicit permission before repairs. It is
prompt specialization, not fine-tuning. The implementation uses Ollama's documented
[`system` field](https://docs.ollama.com/api/create). OpenCode's
[provider allowlist and permissions](https://opencode.ai/docs/config/) constrain the
session, but do not provide an operating-system network sandbox.

## Preventive monitoring

The existing user service samples every 60 seconds, without root, network or AI.
`lili-crash health` prints a single measurement without saving it or notifying.
`lili-crash config set preventive off` pauses monitoring; `on` resumes it. The same
control is available in Plasma settings and the non-Plasma tray.

| Rule | Evidence needed |
|---|---|
| Disk space | Available space below both 10% and 10 GiB |
| Inodes | Available file entries below 5% on a filesystem reporting inode counts |
| Disk trend | At least 6 samples spanning 15 minutes; at least 100 MiB consumed; space decreases in at least 80% of intervals; extrapolated exhaustion within 24 hours |
| Memory | MemAvailable below 10%, with memory PSI `some avg60` at least 10% |
| Kernel storage/GPU/hardware | Recognized errors at 3 distinct timestamps within the last 10 minutes |

All rules need 3 consecutive samples spanning at least 120 seconds. Short spikes do
not warn. `/`, `/var` and the user's home are checked, once per filesystem; other
mounts and SMART sensors are not monitored. Disk trends assume recent growth
continues; a changing workload invalidates the estimate. Kernel errors have already
occurred: their repetition is a risk signal for further disruption, not advance
knowledge of the first error.

An episode notifies once, is stored across restarts, appears in the normal history,
and supports diagnosis/resolve/ignore. Three healthy samples close an episode.
Missing measurements do not prove recovery. Gaps longer than 3 minutes reset
confirmation streaks. The last hour of metrics, up to 100 closed episodes and all
active warnings are kept in `~/.local/state/lili/health.json` with mode 0600.
Only numeric/categorical evidence is saved, never raw kernel messages. Journal
access failure is reported in `unavailable`; lack of permission is not a healthy
result. Kernel scanning is bounded to the last 300 messages in the time window.

## Standard reports

```sh
lili-crash report export machine-a.json --days 30
lili-crash report export machine-b.json --days 30
lili-crash report aggregate machine-a.json machine-b.json --output fleet.json
```

Export defaults to 30 days (1–365 supported); omit the filename to print JSON.
The panel/tray Save action opens a file chooser. Exports are mode 0600 and refuse
to overwrite an existing file. Copying to other machines or uploading is always
outside this command. An export contains only incidents still available in the
journal, Steam logs and Lili history; it is not a complete audit archive.

`lili.incidents/v1` has a random per-installation `machine_id`, generation time,
window and events. Each event contains `id`, `time`, `kind`, `component`, `category`,
`fingerprint` and `status`. Kinds cover crashes, freezes, Steam exits, launch errors,
updater errors and preventive warnings. A fingerprint groups the kind, component
and category; an event ID identifies one occurrence. Stable machine IDs live in
`report-machine-id`; preserve them across exports, and don't clone them onto other
machines. They identify user installations, not hardware or all users of a host.

The export allowlist excludes raw logs, PIDs, hostnames, usernames, paths and
free-text diagnostic summaries. Standard binary names, desktop IDs and Steam app
IDs remain useful for comparison; custom executable paths are hashed. This is
data minimization and pseudonymization, not a promise of anonymous data. Review
application identifiers and event times before sharing reports.

`lili.fleet/v1` groups matching symptoms, reports occurrence counts, affected
installation IDs and first/last occurrence, and flags recurring groups. Identical
event IDs from one installation are counted once even across overlapping exports.
The newest export supplies the event status. Different collection windows remain
visible; counts are not normalized rates. Matching signals do not establish a
shared root cause. There is no central ingestion service, dashboard, authentication
or automatic fleet-wide remediation in this version.

## Remote privacy gate

Every non-Ollama provider and every non-loopback Ollama endpoint is treated as
potentially remote, even if a generic agent was configured locally by the user.
Before the agent starts, the visible terminal requires `SEND`; Enter/EOF cancels.
Consent is not persisted. Common credentials, private keys, email and IPv4 addresses
in the initial prompt are masked. Later output read by a third-party agent is not
intercepted; secrets can evade pattern matching. The notice states these limits.

## Verification

`make check` includes lifecycle tests (transients, recurrence, restarts, recovery,
missing data), deterministic trend fixtures, fleet deduplication/schema validation,
private export permissions, redaction and actual shell execution of consent/cancel.
These tests validate rules and plumbing, not the clinical accuracy of an LLM or a
statistical prediction accuracy score. A trained model needs a separate consented,
redacted dataset and held-out evaluation before being advertised as specialized.
