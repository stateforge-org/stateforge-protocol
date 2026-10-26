<div class="sf-docs-home">
  <section class="sf-docs-hero">
    <div class="sf-docs-hero__grid">
      <div>
        <div class="sf-docs-eyebrow">StateForge / Protocol</div>
        <h1>A precise contract for local operations.</h1>
        <p class="sf-docs-hero__lead">
          StateForge Protocol (SFP) defines how a StateForge Agent discovers,
          understands, and communicates with independently running Provider
          processes.
        </p>
        <div class="sf-docs-actions">
          <a class="sf-docs-button sf-docs-button--primary" href="v0.1.0/">
            Read v0.1.0
          </a>
          <a class="sf-docs-button sf-docs-button--secondary" href="https://github.com/stateforge-org/stateforge-protocol">
            View source
          </a>
        </div>
      </div>
      <div class="sf-docs-hero__mark" aria-hidden="true">
        <img class="sf-docs-hero__logo--light" src="assets/images/stateforge-mark-black.svg" alt="">
        <img class="sf-docs-hero__logo--dark" src="assets/images/stateforge-mark.svg" alt="">
      </div>
    </div>
  </section>

  <section class="sf-docs-section">
    <div>
      <div class="sf-docs-section__eyebrow">Protocol lifecycle</div>
      <h2>From discovery to safe recovery.</h2>
    </div>
    <p class="sf-docs-section__intro">
      SFP defines the sequence and fences that keep Agent&ndash;Provider
      communication correct from discovery through reconnection.
    </p>
    <div class="sf-docs-lifecycle" data-sf-lifecycle data-prompt="Select a stage to play its exchange" aria-busy="false">
      <div class="sf-docs-lifecycle__exchange" aria-label="Selected protocol lifecycle exchange">
        <div class="sf-docs-lifecycle__actor" data-sf-flow-actor="source">
          <span>Provider</span>
          <strong data-sf-flow-source-state>Publishes the endpoint</strong>
        </div>
        <div class="sf-docs-lifecycle__rail" aria-hidden="true">
          <span class="sf-docs-lifecycle__line"></span>
          <span class="sf-docs-lifecycle__packet" data-sf-flow-packet></span>
          <code class="sf-docs-lifecycle__message" data-sf-flow-message>endpoint descriptor</code>
        </div>
        <div class="sf-docs-lifecycle__actor" data-sf-flow-actor="target">
          <span>Agent</span>
          <strong data-sf-flow-target-state>Verifies the generation</strong>
        </div>
      </div>
      <p class="sf-docs-lifecycle__status" data-sf-flow-status aria-live="polite">Select a stage to play its exchange</p>
      <div class="sf-docs-flow">
        <button
          class="sf-docs-flow__step"
          type="button"
          data-sf-flow-step
          data-stage="discover"
          data-source-state="Publishes the endpoint"
          data-target-state="Verifies the generation"
          data-result="Endpoint generation accepted"
          data-events='[
            {"direction":"forward","label":"endpoint descriptor","detail":"Provider publishes an atomic descriptor"},
            {"direction":"reverse","label":"connect","detail":"Agent connects to the verified endpoint"}
          ]'
          aria-pressed="true"
        >
          <span class="sf-docs-flow__action" data-sf-flow-action aria-hidden="true">Replay</span>
          <span class="sf-docs-flow__number">01 / DISCOVER</span>
          <h3>Find and identify</h3>
          <p>A Provider publishes an endpoint descriptor. The Agent verifies it and connects to that exact endpoint generation.</p>
        </button>
        <button
          class="sf-docs-flow__step"
          type="button"
          data-sf-flow-step
          data-stage="establish"
          data-source-state="Issues a fenced session"
          data-target-state="Negotiates and validates"
          data-result="Session fenced and Provider eligible"
          data-events='[
            {"direction":"reverse","label":"HandshakeRequest","detail":"Agent presents the expected identity and generation"},
            {"direction":"forward","label":"HandshakeResponse","detail":"Provider issues a fresh fenced session"},
            {"direction":"forward","label":"Provider manifest","detail":"Agent learns the declared protocol surface"},
            {"direction":"forward","label":"Health: SERVING","detail":"Runtime prerequisites establish availability"}
          ]'
          aria-pressed="false"
        >
          <span class="sf-docs-flow__action" data-sf-flow-action aria-hidden="true">Play</span>
          <span class="sf-docs-flow__number">02 / ESTABLISH</span>
          <h3>Fence the session</h3>
          <p>Bootstrap creates a fenced session for one endpoint generation. The Agent retrieves the manifest, watches process health, and assesses declared operations for the target.</p>
        </button>
        <button
          class="sf-docs-flow__step"
          type="button"
          data-sf-flow-step
          data-stage="operate"
          data-source-state="Executes and reports"
          data-target-state="Admits and reconciles"
          data-result="Lifecycle state synchronized"
          data-events='[
            {"direction":"reverse","label":"OperationRequest","detail":"Agent submits admitted work"},
            {"direction":"forward","label":"Progress + Result","detail":"Provider reports the operation lifecycle"},
            {"direction":"forward","label":"Trigger","detail":"Provider publishes a declared event"},
            {"direction":"reverse","label":"Acknowledgement","detail":"Agent returns the trigger disposition"},
            {"direction":"reverse","label":"Reconcile","detail":"A new session reconciles retained state"}
          ]'
          aria-pressed="false"
        >
          <span class="sf-docs-flow__action" data-sf-flow-action aria-hidden="true">Play</span>
          <span class="sf-docs-flow__number">03 / OPERATE</span>
          <h3>Run and reconcile</h3>
          <p>The Agent submits admitted operations and receives their progress and results. Providers publish triggers; reconnecting peers reconcile retained state.</p>
        </button>
      </div>
    </div>
  </section>

  <section class="sf-docs-section">
    <div>
      <div class="sf-docs-section__eyebrow">Read the contract</div>
      <h2>Choose the surface you need.</h2>
    </div>
    <div class="sf-docs-card-grid">
      <a class="sf-docs-card" href="v0.1.0/procedures/">
        <span class="sf-docs-card__label">PROCEDURES</span>
        <h3>Follow the complete flow</h3>
        <p>Read each SFP procedure in lifecycle order, from endpoint discovery through reconnection.</p>
      </a>
      <a class="sf-docs-card" href="v0.1.0/reference/python-contracts/">
        <span class="sf-docs-card__label">PYTHON</span>
        <h3>Implement against the package</h3>
        <p>Use generated messages, service bindings, validators, schemas, and canonical limits.</p>
      </a>
      <a class="sf-docs-card" href="v0.1.0/reference/responsibility-boundaries/">
        <span class="sf-docs-card__label">OWNERSHIP</span>
        <h3>Keep boundaries explicit</h3>
        <p>See which guarantees belong to Protocol, Agent runtime, and Provider implementation.</p>
      </a>
    </div>
  </section>

  <section class="sf-docs-release">
    <div>
      <strong>Current documentation: <code>v0.1.0</code></strong>
    </div>
    <a class="sf-docs-button sf-docs-button--primary" href="v0.1.0/">Open the protocol</a>
  </section>
</div>
