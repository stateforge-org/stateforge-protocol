# Getting started

StateForge Protocol provides the generated messages, gRPC bindings, contract
constants, and semantic validators used by Agent and Provider runtimes. This
guide runs the repository's tested Bootstrap example so you can see those
layers establish a real SFP session.

## Choose your path

<div class="sf-docs-card-grid">
  <a class="sf-docs-card" href="https://github.com/stateforge-org/stateforge-provider-python">
    <span class="sf-docs-card__label">PROVIDER AUTHOR</span>
    <h3>Build with StateForge Provider Python</h3>
    <p>
      Declare operations, triggers, and requirement checks while the framework
      owns the SFP server and runtime behavior.
    </p>
  </a>
  <a class="sf-docs-card" href="#run-your-first-exchange">
    <span class="sf-docs-card__label">RUNTIME IMPLEMENTER</span>
    <h3>Use the Protocol package directly</h3>
    <p>
      Implement an Agent, an alternative Provider runtime, or protocol-aware
      integration using the versioned public contracts.
    </p>
  </a>
  <a class="sf-docs-card" href="../reference/python-contracts/">
    <span class="sf-docs-card__label">TOOLING</span>
    <h3>Inspect and validate contracts</h3>
    <p>
      Use the public messages, constants, validators, schemas, and packaged
      conformance evidence without implementing a runtime.
    </p>
  </a>
</div>

## Install the example

The executable examples live in the repository rather than the Python wheel.
Clone the source, create an isolated environment, and install the package in
editable mode:

=== "macOS and Linux"

    ```bash
    git clone https://github.com/stateforge-org/stateforge-protocol.git
    cd stateforge-protocol
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -e .
    ```

=== "Windows PowerShell"

    ```powershell
    git clone https://github.com/stateforge-org/stateforge-protocol.git
    Set-Location stateforge-protocol
    py -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install -e .
    ```

## Run your first exchange

SFP uses a local Unix socket for Agent-to-Provider communication. Run this
example on Linux or macOS. On Windows, use a Linux environment such as WSL.

Start the minimal Provider-side Bootstrap server:

```console title="Terminal 1 - Provider runtime"
python -m examples.bootstrap.server \
  unix:/tmp/stateforge-bootstrap.sock \
  7f7db7d8-68b4-4f71-9769-065b5c4f941c \
  1
```

The server binds one local endpoint for the supplied Provider instance and
endpoint generation. Leave it running, then open a second terminal with the
same virtual environment activated:

```console title="Terminal 2 - Agent runtime"
python -m examples.bootstrap.client \
  unix:/tmp/stateforge-bootstrap.sock \
  7f7db7d8-68b4-4f71-9769-065b5c4f941c \
  1
```

The client prints the selected wire version, Provider runtime identity, and
fresh session identifier:

```text
Session established: SFP 1.0, Provider runtime <uuid>, session <uuid>
```

The UUIDs created by the example are intentionally different on each run.
Stop the server with `Ctrl+C` when you are finished.

Terminal 1 starts the Provider-side server. Terminal 2 acts as the Agent and
performs one Bootstrap handshake over the local socket. The client accepts the
session only after the request, response, endpoint fences, and selected wire
version all validate.

```stateforge-entity-flow
source: getting-started-overview.yaml
```

!!! note "The command line stands in for endpoint discovery"

    A production Agent reads the Provider instance, endpoint generation, and
    socket from a validated endpoint descriptor. The example accepts those
    values as arguments so it can focus only on Bootstrap.

## What the example proves

| Step | Contract behavior |
| ---: | --- |
| 1 | Both peers configure the shared gRPC channel from Protocol-owned transport ceilings. |
| 2 | The Agent constructs and validates a `HandshakeRequest` bound to the expected Provider instance and endpoint generation. |
| 3 | The Provider validates the request, confirms it matches live endpoint state, and selects the highest mutually supported wire version. |
| 4 | The Provider creates and validates a response containing its runtime identity and a fresh session ID. |
| 5 | The Agent validates the response and compares it with the endpoint and versions it actually offered before accepting the session. |

The example uses the same four public layers available to every independent
runtime implementation:

| Import | Responsibility |
| --- | --- |
| `bootstrap_pb2` | Bootstrap messages and wire serialization |
| `bootstrap_pb2_grpc` | Asynchronous client stub, server interface, and service registration |
| `bootstrap.v1.contract` | Canonical service identity and procedure limits |
| `bootstrap.v1.validation` | Context-independent semantic validation and canonical typed values |

Generated protobuf messages enforce wire types, not the complete StateForge
contract. Validate outgoing and incoming messages, then apply the live-state
checks owned by your runtime.

## Continue through SFP

<div class="sf-docs-card-grid sf-docs-card-grid--two">
  <a class="sf-docs-card" href="../procedures/endpoint-discovery/">
    <span class="sf-docs-card__label">BEFORE BOOTSTRAP</span>
    <h3>Discover the endpoint</h3>
    <p>Publish, observe, validate, and connect to an exact endpoint generation.</p>
  </a>
  <a class="sf-docs-card" href="../bootstrap/">
    <span class="sf-docs-card__label">IMPLEMENT</span>
    <h3>Understand Bootstrap</h3>
    <p>Follow message validation, session fencing, failures, and recovery.</p>
  </a>
  <a class="sf-docs-card" href="../procedures/">
    <span class="sf-docs-card__label">LIFECYCLE</span>
    <h3>Follow every procedure</h3>
    <p>Continue from manifest exchange and Health through work and recovery.</p>
  </a>
  <a class="sf-docs-card" href="../reference/python-contracts/">
    <span class="sf-docs-card__label">REFERENCE</span>
    <h3>Use the complete Python surface</h3>
    <p>Find every generated module, public validator, limit, and shared helper.</p>
  </a>
</div>
