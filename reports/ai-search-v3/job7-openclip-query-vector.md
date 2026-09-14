# Job 7 OpenCLIP query vector

- Provider: existing local OpenCLIP implementation
- Model: `ViT-B-32 / laion2b_s34b_b79k`
- Dimension: 512
- Normalization: unit-normalized and finite
- Live production service: `127.0.0.1:8765`, health PASS
- Live post-deployment vector test: 512 values, 6,712 ms cold-path request
- Controlled benchmark median embedding time: 55.49 ms after model load

The exact existing approved model was reused. No existing asset vectors were regenerated.
