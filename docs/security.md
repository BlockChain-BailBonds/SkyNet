# Security, privacy, and authorization

- Public artifacts contain no tokens, participant addresses, or private telemetry. Human authorization and device identity are separate.
- Existing SMS enrollment remains explicit, versioned, time-limited, revocable, and RAM-only. Camera, microphone, location, and motion are never enabled automatically.
- Browser model downloads are user initiated. Model assets stay in browser-managed caches and can be cleared. The application passes only bounded public snapshots to the local runtime.
- Feed parsing caps payload size, rejects malformed/naive timestamps, and HTML output is escaped. Alert IDs deduplicate; expiration is mandatory.
- Workflow permissions are least privilege. Actions use GitHub ephemeral credentials only where publishing requires them. No write credential belongs in firmware.
- Device messages require a signature, a timestamp window, and a unique nonce. The simulator uses HMAC and is explicitly **SIMULATED**; production firmware identity requires device-generated Ed25519 keys in protected storage.
- GitHub Pages and scheduled Actions are best-effort and are not emergency-service-grade or guaranteed life-safety delivery.
