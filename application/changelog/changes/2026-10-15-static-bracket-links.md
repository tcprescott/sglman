### Fixed

- The lightweight bracket pages (the `/live/brackets` links you send to viewers) no longer sometimes point their links at the wrong address when a community is reachable both on its own domain and under `/t/<name>`.

### Security

- The lightweight bracket pages now double-check stream links, avatar images and the community colour before putting them on the page, instead of trusting that they were checked earlier.
