# Operation Lifecycle conformance vectors

These offline vectors describe observable contract obligations. They do not
simulate a Provider task manager, prove runtime sanitization, or implement
cancellation/transport enforcement.

- `watch-request.json`, `cancel-request.json`, `watch-terminal.json`, and
  `cancel-requested.json` are complete default-emitting ProtoJSON messages.
- `snapshots.json` contains alternate histories for the **same** admitted
  operation. Each named snapshot is independently wire-valid. Two snapshots
  with the same sequence in different histories must never be combined.
- `transitions.json` is the committed-change table, including progress-only
  changes in RUNNING and CANCELLATION_REQUESTED. A replay is not a transition.
- `traces.json` selects adjacent commits and declares whether the trace is
  legal. It includes cancellation/completion races and terminal mutation.
- `watch-cases.json` selects delivered snapshots, requested cursor, gap flags,
  final gRPC status, and resulting evidence. Delivery can skip commits;
  termination with no terminal evidence remains indeterminate. `valid: false`
  means the transcript violates the contract, not that the operation failed.
- `cancel-cases.json` describes atomic cancellation decisions and the number of
  new logical interruption requests. Zero means no new request, not that an
  earlier cancellation was undone. The fixture tests do not invoke author code.
- `result-schema.json` is an illustrative pinned Draft 2020-12 result schema for
  Operation Admission's generic maintenance operation. It is not a standardized
  compliance profile or a replacement for the real admitted manifest. Negative
  author values and invalid wire/cross-field values are parametrized in the
  tests.
- `error-cases.json` distinguishes RPC rejection from a terminal operation
  outcome. Unknown IDs, lost state, and expiry never dispatch work.

All snapshots copy the Operation Admission sample's immutable admission record,
operation identifier, and manifest pin. Session/generation belong to the reply
envelope, so recovery can replay an identical snapshot under a newly negotiated
session.
The synthetic deadline-failure snapshot occurs after Operation Admission's
business deadline;
its unchanged expiry does not imply that an active record was deleted.

The full retention and backpressure obligations are normative in
`docs/procedures/progress-results-cancellation.md`: retain current/latest state
and terminal results while the admission record exists; intermediate history
may be lost; bound observer queues and stall duration. Provider and Agent
runtime implementations must test actual concurrency, cancellation isolation,
persistence claims, and slow transports against these obligations.
