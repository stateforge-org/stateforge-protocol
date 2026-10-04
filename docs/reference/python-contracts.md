# Generated Python contracts

!!! warning

    These modules are generated from Protocol Buffers. Treat the `.proto`
    schema as the authoritative contract and never edit generated modules.

The bootstrap, manifest, capability-assessment, operation-admission,
operation-lifecycle, and trigger-publication schemas generate these Python
modules:

```python
from stateforge_protocol.sfp.bootstrap.v1 import bootstrap_pb2
from stateforge_protocol.sfp.bootstrap.v1 import bootstrap_pb2_grpc
from stateforge_protocol.sfp.manifest.v1 import manifest_pb2
from stateforge_protocol.sfp.manifest.v1 import manifest_pb2_grpc
from stateforge_protocol.sfp.capability_assessment.v1 import (
    capability_assessment_pb2,
)
from stateforge_protocol.sfp.capability_assessment.v1 import (
    capability_assessment_pb2_grpc,
)
from stateforge_protocol.sfp.operation_admission.v1 import (
    operation_admission_pb2,
)
from stateforge_protocol.sfp.operation_admission.v1 import (
    operation_admission_pb2_grpc,
)
from stateforge_protocol.sfp.operation_lifecycle.v1 import (
    operation_lifecycle_pb2,
    operation_lifecycle_pb2_grpc,
)
from stateforge_protocol.sfp.trigger_publication.v1 import (
    trigger_publication_pb2,
)
from stateforge_protocol.sfp.trigger_publication.v1 import (
    trigger_publication_pb2_grpc,
)
```

The `_pb2` modules contain message classes; `_pb2_grpc` modules contain client
and server bindings. Both include generated `.pyi` typing contracts. Manifest
bindings expose `ManifestService.GetManifest`, its request/response, and typed
Provider, operation, runtime-requirement, platform, and trigger declarations.
Capability-assessment bindings expose
`CapabilityAssessmentService.AssessCapabilities`, its request/response, and
typed finding, requirement, reason, and constraint messages.
Operation-admission bindings expose
`OperationAdmissionService.StartOperation`, the immutable invocation and
session-binding messages, admission record, dispositions, modes, and structured
error detail.
Operation-lifecycle bindings expose
`OperationLifecycleService.WatchOperation` (server streaming) and
`CancelOperation` (unary), complete operation snapshots, typed terminal
outcomes, progress, cancellation dispositions, and structured RPC error detail.
They reuse the Operation Admission session-binding and admission-record types.
Trigger-publication bindings expose the bidirectional
`TriggerPublicationService.StreamTriggers` stream, session/manifest binding,
schema-bound publication envelope, acknowledgements, and structured rejection
reasons.

The versioned Operation Lifecycle `contract` module exposes normative procedure
limits that consuming runtimes must enforce outside ordinary protobuf or JSON
Schema validation. For example:

```python
from stateforge_protocol.sfp.operation_lifecycle.v1 import contract

server_receive_limit = contract.MAX_REQUEST_BYTES
server_send_limit = contract.MAX_RESPONSE_BYTES
```

Use the packaged validation schema with a Draft 2020-12 validator when building
the consuming runtime. Validation libraries are development dependencies here;
consumers choose their own compliant implementation.

```python
import json
from importlib.resources import files

from google.protobuf.json_format import MessageToDict
from jsonschema import Draft202012Validator

from stateforge_protocol.sfp.manifest.v1 import manifest_pb2

schema = json.loads(
    files("stateforge_protocol.sfp.manifest.v1")
    .joinpath("manifest.schema.json")
    .read_text()
)


def validate_structure(response: manifest_pb2.GetManifestResponse) -> None:
    """Validate structure before the runtime's semantic and session checks."""
    Draft202012Validator(schema).validate(
        MessageToDict(response, always_print_fields_with_no_presence=True)
    )
```

The [manifest procedure](../procedures/provider-manifest.md) defines required
session checks, schema negotiation, revision calculation, privacy, resource
limits and caching behavior. Constructing a generated message does not enforce
those requirements. Populate `GetManifestRequest.expected_session_id` from
`HandshakeResponse.session_id`. Before accepting a manifest, match the response
`session_id` to both that request and the Agent's current session, even when
reusing a cached manifest revision. JSON Schema checks the opaque string's
shape; consumer runtimes enforce the active-session relationship.

The same pattern validates a capability-assessment response:

```python
import json
from importlib.resources import files

from google.protobuf.json_format import MessageToDict
from jsonschema import Draft202012Validator

from stateforge_protocol.sfp.capability_assessment.v1 import (
    capability_assessment_pb2,
)

schema = json.loads(
    files("stateforge_protocol.sfp.capability_assessment.v1")
    .joinpath("capability_assessment.schema.json")
    .read_text()
)


def validate_assessment(
    response: capability_assessment_pb2.AssessCapabilitiesResponse,
) -> None:
    """Validate structure before the runtime's semantic and session checks."""
    Draft202012Validator(schema).validate(
        MessageToDict(response, always_print_fields_with_no_presence=True)
    )
```

The [capability-assessment procedure](../procedures/capability-assessment.md)
defines required session/manifest fencing, normalized findings, cross-field
invariants, and failure mapping. Constructing a generated message does not
enforce those requirements.

Operation-admission structure is validated with the schema packaged beside
`operation_admission_pb2` in the same way. The
[operation-admission procedure](../procedures/operation-admission.md) defines
the canonical RFC 8785 fingerprint, current-session checks, validation order,
atomic admission behavior, retry modes, retention, and structured error
mapping. Constructing a generated message does not implement an operation
registry or make dispatch idempotent by itself.

For lifecycle messages, load `operation_lifecycle.schema.json` from
`stateforge_protocol.sfp.operation_lifecycle.v1`. Its root validates a
`WatchOperationResponse`; select `$defs.watchOperationRequest`,
`$defs.cancelOperationRequest`, or `$defs.cancelOperationResponse` for other
messages, retaining the complete `$defs` map. The
[lifecycle procedure](../procedures/progress-results-cancellation.md) defines
session/fingerprint checks, sequence gaps, immutable terminal outcomes,
cancellation races, and bounded retention. Validate a success result against
the originally admitted operation's pinned result schema as a separate step.
These bindings do not provide an execution manager or enforce runtime state
transitions, sanitization, or backpressure.

Trigger-publication stream messages are validated with the schema packaged
beside `trigger_publication_pb2`. The
[trigger-publication procedure](../procedures/triggers.md) defines the exact
manifest schema selection, stream fencing, canonical publication equality,
acknowledgement boundary, retry behavior, flow control, and failure mapping.
Constructing a generated publication does not validate its `payload` against
the selected manifest declaration or make delivery durable by itself.

Generated modules are deliberately excluded from mkdocstrings API rendering.
Their signatures are generated by the Protocol Buffer toolchain, and their
documentation belongs to the source schemas and their procedure pages.
