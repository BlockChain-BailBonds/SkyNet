# Browser model runtime

The MVP selects Transformers.js 3.8.1 and the quantized ONNX Llama 3.2 1B Instruct community conversion because it offers a WebGPU path and a WASM fallback through one maintained browser API. WebLLM was evaluated architecturally but would add a second model packaging/runtime contract. The pinned metadata is in `agent/model-manifest.json`; weights remain on the approved host and are never committed.

Download is explicit. The UI reports approximate size/memory, readiness, and errors, and exposes cache clearing. Optional 3B and 7B entries are metadata only. Real model loading requires a compatible browser, network access, available storage, and model-license acceptance. CI validates the pinned manifest and degradation path; full browser weight download is currently **BLOCKED** in this environment and is not claimed as passed.
