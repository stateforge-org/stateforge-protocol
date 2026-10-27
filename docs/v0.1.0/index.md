# SFP v0.1.0

This is the documentation for the `v0.1.0` wire contract. Choose the
path that matches what you need to do.

<div class="sf-docs-card-grid sf-docs-card-grid--two">
  <a class="sf-docs-card" href="getting-started/">
    <span class="sf-docs-card__label">START</span>
    <h3>Run your first exchange</h3>
    <p>Install the package and establish a validated Bootstrap session.</p>
  </a>
  <a class="sf-docs-card" href="procedures/">
    <span class="sf-docs-card__label">LEARN</span>
    <h3>Follow the protocol lifecycle</h3>
    <p>Read the procedures in order, from endpoint discovery through recovery.</p>
  </a>
  <a class="sf-docs-card" href="reference/python-contracts/">
    <span class="sf-docs-card__label">IMPLEMENT</span>
    <h3>Use the Python contracts</h3>
    <p>Find the generated messages, service bindings, validators, and limits.</p>
  </a>
  <a class="sf-docs-card" href="reference/responsibility-boundaries/">
    <span class="sf-docs-card__label">INTEGRATE</span>
    <h3>Keep ownership explicit</h3>
    <p>See which guarantees belong to Protocol, Agent, and Provider code.</p>
  </a>
  <a class="sf-docs-card" href="reference/status-errors/">
    <span class="sf-docs-card__label">RECOVER</span>
    <h3>Handle errors correctly</h3>
    <p>Distinguish RPC failures, structured reasons, and business outcomes.</p>
  </a>
  <a class="sf-docs-card" href="reference/security-trust-boundary/">
    <span class="sf-docs-card__label">SECURE</span>
    <h3>Protect the local boundary</h3>
    <p>Understand host trust, session fences, authorization, and secret handling.</p>
  </a>
  <a class="sf-docs-card" href="reference/glossary/">
    <span class="sf-docs-card__label">REFERENCE</span>
    <h3>Use precise SFP terminology</h3>
    <p>Distinguish identities, sessions, declarations, evidence, and work state.</p>
  </a>
</div>

## Contract surface

<div class="sf-docs-card-grid sf-docs-card-grid--two">
  <article class="sf-docs-card">
    <span class="sf-docs-card__label">01 / ESTABLISH</span>
    <h3>Establish a session</h3>
    <p>
      <a href="procedures/endpoint-discovery/">Endpoint discovery</a>,
      <a href="bootstrap/">Bootstrap</a>, and
      <a href="procedures/provider-manifest/">Provider manifest exchange</a>
    </p>
  </article>
  <article class="sf-docs-card">
    <span class="sf-docs-card__label">02 / QUALIFY</span>
    <h3>Establish eligibility</h3>
    <p>
      <a href="procedures/health/">Health monitoring</a> and
      <a href="procedures/capability-assessment/">capability assessment</a>
    </p>
  </article>
  <article class="sf-docs-card">
    <span class="sf-docs-card__label">03 / EXCHANGE</span>
    <h3>Exchange work</h3>
    <p>
      <a href="procedures/operation-admission/">Operation admission</a>,
      <a href="procedures/progress-results-cancellation/">progress and results</a>,
      and <a href="procedures/triggers/">trigger publication</a>
    </p>
  </article>
  <article class="sf-docs-card">
    <span class="sf-docs-card__label">04 / RECOVER</span>
    <h3>Recover safely</h3>
    <p>
      <a href="procedures/disconnection-recovery/">Disconnection and recovery</a>
    </p>
  </article>
</div>

## Verification

<div class="sf-docs-card-grid sf-docs-card-grid--two">
  <a class="sf-docs-card" href="reference/conformance-coverage/">
    <span class="sf-docs-card__label">CONFORMANCE</span>
    <h3>Verification coverage</h3>
    <p>The executable checks that cover the contract surface.</p>
  </a>
  <a class="sf-docs-card" href="reference/ci-automation/">
    <span class="sf-docs-card__label">DELIVERY</span>
    <h3>Artifact verification</h3>
    <p>How the published package is built and checked.</p>
  </a>
  <a class="sf-docs-card" href="reference/versioning-compatibility/">
    <span class="sf-docs-card__label">COMPATIBILITY</span>
    <h3>Understand every version</h3>
    <p>Keep package, wire, schema, and declaration versions distinct.</p>
  </a>
</div>
