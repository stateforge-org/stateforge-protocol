# Progress, results, and cancellation

The Agent attaches to an admitted operation through `WatchOperation`. The
Developer RPC Library replays current state, normalizes Provider progress,
emits exactly one terminal result or error, and coordinates cancellation
without allowing a cancellation race to overwrite an earlier terminal state.

[![Progress, Results, and Cancellation sequence diagram](../assets/diagrams/progress-results-and-cancellation.png)](../assets/diagrams/progress-results-and-cancellation.png)

_Select the diagram to open the full-resolution version._
