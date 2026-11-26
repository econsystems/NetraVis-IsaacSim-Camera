# Changelog

## [0.1.0]

- First public release.

### Update 2026-11-25 (same version)

- Camera asset now passes the NVIDIA Isaac Sim sensor asset validator: OmniSensorAPI and 30 Hz tick rate on every camera, a render product per camera, and complete pseudo-depth outputs. The IR lenses use the full-frame OpenCV pinhole form of the same equidistant lens, so Isaac Sim 6.2 renders the whole image (IR_Right valid depth 55 % to 72 % in our test scene). Prim names and paths are unchanged.
- IR dot projector ships visible with intensity 0 (off) and is switched on by setting `inputs:intensity` on both emitters to 1.0 (stored as `info:projector:on_intensity`).
