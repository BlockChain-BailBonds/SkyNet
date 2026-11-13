# SkyNet Pocket enrollment

Target candidate: original ESP32E N4 CYD / ESP32-2432S028R, 2.8-inch ILI9341. Pin definitions are isolated in `platformio.ini`; confirm the board revision against the physical unit before flashing. No hardware was flashed or validated.

On first authorized provisioning, generate a non-exportable device signing key, display its public-key thumbprint, and enroll that public key at a trusted gateway. Each message signs its canonical payload, device ID, timestamp, and nonce. The receiver verifies the signature, ±5-minute clock window, and nonce uniqueness. A thumbprint alone is not authentication.

Alert retrieval is public read-only HTTPS. Autonomous telemetry upload to GitHub Pages is **BLOCKED**. The minimal gateway needs TLS, registered public keys, replay storage, payload/rate limits, retention controls, and a private persistence path. Never embed a GitHub token.
