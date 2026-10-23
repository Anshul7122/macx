# Releasing MacX

Release builds come from CI (`.github/workflows/build.yml`) on a clean Apple silicon runner, so every `.dmg` is built
the same way. The website picks up the newest published release automatically.

1. Bump `VERSION` (e.g. `0.1.2`) and commit to `main`.
2. Tag and push: `git tag v0.1.2 && git push origin v0.1.2`. The tag must match `VERSION`.
3. CI builds the engine kit and `MacX-0.1.2.dmg`, and attaches the `.dmg` and its `.sha256` to a **draft** release.
4. Test the draft's `.dmg` before publishing, ideally in a fresh macOS user account:
   - Opens after the Gatekeeper "Open Anyway" step.
   - The setup screen passes every check and installs the engines (Wine 11, DXVK, DXMT, D3DMetal from Game Porting
     Toolkit).
   - Steam starts from the Steam tab; a DirectX 12 game (GTA V Enhanced) reaches gameplay on D3DMetal.
   - A DirectX 11 game runs on DXMT.
   - *Check & repair setup* reports everything green.
5. Write the release notes (what changed, the SHA-256 line CI added) and publish the release.

To try the build without releasing anything, run **Actions → Build → Run workflow**: it builds the `.dmg` and uploads it as a workflow artifact (no release is created).

Building by hand still works: `scripts/build-engine-kit.sh && scripts/build-app.sh --dmg` (see README).
