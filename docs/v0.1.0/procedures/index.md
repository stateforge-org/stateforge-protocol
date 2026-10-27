# SFP procedure map

<p class="sf-procedure-map__intro">
  SFP procedures form four lifecycle phases. Establish one trusted session,
  determine what the Provider can accept, exchange work over two independent
  paths, and reconcile retained state after a disconnect.
</p>

## 01 / Connect

<p class="sf-procedure-map__phase-summary">
  Turn one generation-specific endpoint into a negotiated session with an
  accepted declaration surface.
</p>

<div class="sf-docs-card-grid sf-docs-card-grid--three">
  <a class="sf-docs-card sf-procedure-map__card" href="endpoint-discovery/">
    <span class="sf-procedure-map__meta">
      <span class="sf-docs-card__label">01 / DISCOVER</span>
      <span class="sf-procedure-map__direction">Filesystem + channel</span>
    </span>
    <h3>Endpoint discovery</h3>
    <p>Validate one atomic descriptor and open a provisional channel to that exact endpoint generation.</p>
  </a>
  <a class="sf-docs-card sf-procedure-map__card" href="../bootstrap/">
    <span class="sf-procedure-map__meta">
      <span class="sf-docs-card__label">02 / NEGOTIATE</span>
      <span class="sf-procedure-map__direction">Agent → Provider</span>
    </span>
    <h3>Handshake and version negotiation</h3>
    <p>Confirm endpoint identity, select one wire version, and issue a fresh fenced session.</p>
  </a>
  <a class="sf-docs-card sf-procedure-map__card" href="provider-manifest/">
    <span class="sf-procedure-map__meta">
      <span class="sf-docs-card__label">03 / DECLARE</span>
      <span class="sf-procedure-map__direction">Agent → Provider</span>
    </span>
    <h3>Provider manifest exchange</h3>
    <p>Accept the Provider's operations, triggers, schemas, requirements, and configuration declaration.</p>
  </a>
</div>

## 02 / Qualify

<p class="sf-procedure-map__phase-summary">
  Combine process-wide availability with operation-specific evidence from the
  current runtime.
</p>

<div class="sf-docs-card-grid sf-docs-card-grid--two">
  <a class="sf-docs-card sf-procedure-map__card" href="health/">
    <span class="sf-procedure-map__meta">
      <span class="sf-docs-card__label">04 / OBSERVE</span>
      <span class="sf-procedure-map__direction">Health watch</span>
    </span>
    <h3>Health and availability</h3>
    <p>Watch process-wide health while the Agent derives whether new operation admission is allowed.</p>
  </a>
  <a class="sf-docs-card sf-procedure-map__card" href="capability-assessment/">
    <span class="sf-procedure-map__meta">
      <span class="sf-docs-card__label">05 / ASSESS</span>
      <span class="sf-procedure-map__direction">Agent → Provider</span>
    </span>
    <h3>Capability assessment</h3>
    <p>Evaluate requested operations against current runtime evidence without executing them.</p>
  </a>
</div>

## 03 / Exchange

<p class="sf-procedure-map__phase-summary">
  Operations and triggers use independent directions after the session is
  established and the Provider is eligible.
</p>

<div class="sf-procedure-map__lanes">
  <section class="sf-procedure-map__lane" aria-labelledby="operation-path-title">
    <div class="sf-procedure-map__lane-header">
      <strong id="operation-path-title">Operation path</strong>
      <span>Agent initiated</span>
    </div>
    <div class="sf-docs-card-grid">
      <a class="sf-docs-card sf-procedure-map__card" href="operation-admission/">
        <span class="sf-procedure-map__meta">
          <span class="sf-docs-card__label">06 / ADMIT</span>
          <span class="sf-procedure-map__direction">Agent → Provider</span>
        </span>
        <h3>Operation admission</h3>
        <p>Record an immutable admission before dispatch and resolve duplicate identities without executing twice.</p>
      </a>
      <a class="sf-docs-card sf-procedure-map__card" href="progress-results-cancellation/">
        <span class="sf-procedure-map__meta">
          <span class="sf-docs-card__label">07 / OBSERVE</span>
          <span class="sf-procedure-map__direction">Bidirectional</span>
        </span>
        <h3>Progress, results, and cancellation</h3>
        <p>Stream operation snapshots and request cooperative cancellation without creating new work.</p>
      </a>
    </div>
  </section>
  <section class="sf-procedure-map__lane sf-procedure-map__lane--single" aria-labelledby="trigger-path-title">
    <div class="sf-procedure-map__lane-header">
      <strong id="trigger-path-title">Trigger path</strong>
      <span>Provider initiated</span>
    </div>
    <div class="sf-docs-card-grid">
      <a class="sf-docs-card sf-procedure-map__card" href="triggers/">
        <span class="sf-procedure-map__meta">
          <span class="sf-docs-card__label">08 / PUBLISH</span>
          <span class="sf-procedure-map__direction">Provider → Agent</span>
        </span>
        <h3>Trigger publication</h3>
        <p>Publish declared events and receive one terminal acknowledgement for each publication.</p>
      </a>
    </div>
  </section>
</div>

## 04 / Recover

<p class="sf-procedure-map__phase-summary">
  Replace lost transport state without guessing whether already admitted work
  stopped.
</p>

<div class="sf-docs-card-grid sf-docs-card-grid--one">
  <a class="sf-docs-card sf-procedure-map__card" href="disconnection-recovery/">
    <span class="sf-procedure-map__meta">
      <span class="sf-docs-card__label">09 / RECONCILE</span>
      <span class="sf-procedure-map__direction">New fenced session</span>
    </span>
    <h3>Disconnection and recovery</h3>
    <p>Fence stale traffic, establish a new session, and reconcile retained operation and trigger state.</p>
  </a>
</div>
