# 0009. A release image from GHCR, published to the private network from the loopback port

## Status

Accepted, 2026-11-05.

## Context

The app should run all the time on a server, reachable from the user's devices and from nowhere else, without a login (the private network is the access control). One uvicorn process already serves the API and the built frontend, and the data lives in a git repository ([ADR 0001](0001-git-repository-as-user-data-store.md)) with rebuildable state beside it ([ADR 0004](0004-sqlite-and-chroma-locally-postgres-later.md)). The server may run other services, and the data repository's remote can also be changed from other machines.

## Decision

- **Image from a registry.** Pushing a `v*` tag builds a `linux/amd64` image in GitHub Actions and publishes it to the GitHub container registry (GHCR); `latest` follows only non-prerelease tags. The server pulls it, so it never compiles Node or installs Chromium. The package is public: the image holds only public code and a browser, and CI searches it for secret and data files.
- **One container, loopback only.** Compose publishes the container's port on `127.0.0.1:${JOBADVAISOR_PORT:-8710}`. A forwarder on the host publishes that loopback port to the private network; the worked example is `tailscale serve --bg --https=<https-port> http://127.0.0.1:<port>`, which gives HTTPS with the certificate Tailscale issues for the server's name and leaves an existing entry on port 443 alone. Any other forwarder works.
- **Settings from the host.** Non-secret settings are in `settings.env`, secrets in `secrets.env` (mode 600), the release in the Compose project `.env` (`JOBADVAISOR_TAG`). None is in the image.
- **The data directory is a clone of the data repository's remote.** The user commits and pushes by hand with the service running. If the push is rejected, a documented recovery stops the service, fetches, rebases and pushes, then starts the service; a conflict is resolved or aborted by the user on the server. Nothing is force-pushed. [#63](https://github.com/therealmodbom/jobadvaisor/issues/63) replaces this with an automatic sync.

## Alternatives considered

- **Build the image on the server.** Every update would compile the frontend and install Chromium on a machine that may run other services. Rejected for the registry.
- **A private package with a `docker login` on the server.** Safe, but it needs a token on the server for a package that holds nothing private. Rejected; the public package is set once in GitHub.
- **Publish on the Tailscale address in Compose.** It gives plain HTTP, and the container fails to start if Docker comes up before Tailscale. Rejected for the loopback port plus a forwarder.
- **Two containers (frontend and backend).** The backend already serves the built frontend; a second container would add a proxy for nothing.
- **The server as the only writer of the data, other machines only pulling.** It cannot be enforced and contradicts ADR 0001, where external tools may write the data. The server instead works on a clone and meets a conflict explicitly.

## Consequences

- An update is `docker compose pull` and `docker compose up -d`; a changed port also needs `up -d`, since `restart` keeps the old mapping.
- The service is reachable by anyone on the private network. A shared network would need access rules first.
- Ratings exist only on the server until they are pushed; a lost server loses the unpushed ones until #63.
- During a recovery the service is down and the browser shows a connection error; there is no maintenance page.
- The image is large (about 3 GB uncompressed) because of Chromium, and is pulled once per release. An ARM server needs `linux/arm64` added to the release workflow.
- Several open devices do not see each other's changes until they reload ([#66](https://github.com/therealmodbom/jobadvaisor/issues/66)).
