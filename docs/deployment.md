# Deployment and rollback

Run `python3 -m unittest discover -s tests -v` locally. Pull requests run CI and security checks. `pages.yml` packages the root application, preserved legacy static routes, public snapshots, model metadata, and documentation. Main-branch deployment is replaceable: rollback by reverting the merge commit through a reviewed pull request and allowing Pages to redeploy.

Scheduled ingestion is best-effort and may be delayed. It must not be represented as real-time warning transport. External ChatGPT Health Watch automation remains outside this repository; the browser cannot monitor while closed.
