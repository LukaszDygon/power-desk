# Services

Long-running processes that receive what publishers push and land it with dlt, as it arrives. They
run on Kubernetes (Helm chart) and locally (minikube, or plain `uv run`).

| Service | Publisher feed | Delivery | Lands into |
|---|---|---|---|
| `iris` | [Elexon IRIS](https://bmrs.elexon.co.uk/iris): BMRS datasets in near real time | Azure Service Bus queue we consume (AMQP) | `iris/<dataset>/` |
| `entsoe-subscription` | [ENTSO-E subscriptions](https://transparencyplatform.zendesk.com/hc/en-us/articles/15230327975828-Subscription-Service-Introduction-Guide-for-Data-Consumers): data items as published | SOAP 1.2 web service the platform calls (IEC 62325-504) | `entsoe_subscription/<document kind>/` |

## Design

- **Landing zone, not the warehouse.** Each batch is one dlt load into a filesystem destination
  (gzipped JSONL, a local path or `s3://`), appended as published. DuckDB allows one writer, which
  stays the orchestrator; it loads the landing zone into `raw` like any other source.
- **At least once.** A message is acknowledged (IRIS: completed; ENTSO-E: answered) only after its
  load; a crash re-delivers it, and the warehouse load keeps one row per natural key.
- **IRIS** batches messages (500 or 30 s), lands a table per dataset, and dead-letters messages that are
  not JSON records. Messages expire after 3 days in the queue (fill gaps from the API); one connection
  per queue, so one replica.
- **ENTSO-E** lands each pushed document (header fields + the XML), then acknowledges it with an
  `Acknowledgement_MarketDocument`. A malformed request gets a SOAP fault (HTTP 500, never 400, which
  fails the channel check). Unacknowledged pushes are retried 100 times before the channel is disabled.
- **Shared** (`settings.py`, `landing.py`, `runtime.py`): environment, dlt landing, SIGTERM handling and
  `/healthz`. Credentials are dlt secrets. Logs follow the [log standard](../docs/logging.md) (JSON on
  stderr in the image); every landing is a `dlt.load` event naming its load id, logged by the shared dlt
  hook.
- **One image** for every service; the argument picks one: `power-desk-service <name>`.

## Settings

| Variable | |
|---|---|
| `POWER_DESK_LANDING_URL` | landing zone (default `data/landing`); other shared variables in `settings.py` |
| `SOURCES__IRIS__CREDENTIALS__CLIENT_ID`, `..._CLIENT_SECRET`, `SOURCES__IRIS__QUEUE_NAME` | from the IRIS page of the Insights Solution |
| `DESTINATION__FILESYSTEM__CREDENTIALS__*` | object storage, when the landing zone is a bucket |

ENTSO-E needs no credentials here: the endpoint is registered as a web service channel in the
Transparency Platform (after requesting subscription rights from transparency@entsoe.eu).

## Run

```bash
uv run power-desk-service entsoe-subscription     # http://localhost:8080/subscriptions
uv run power-desk-service iris                    # needs the IRIS credentials in .env
uv run pytest services/tests
```

Local Kubernetes (minikube with the Docker driver, Helm); `data/landing` is mounted as the landing zone,
so the local orchestrator sees what the services land:

```bash
make -C services dev       # cluster, image (built in the cluster), Secret from .env, release
make -C services forward   # then, in another terminal: make -C services push
make -C services logs SERVICE=iris
make -C platform down      # deletes the cluster; data/ stays
```

If Docker Hub refuses pulls, add `DOCKER_BUILD_ARGS="--build-arg PYTHON_IMAGE=mirror.gcr.io/library/python:3.13-slim"`.

## Deploy

`helm/power-desk-services` deploys every enabled service as a single-pod Deployment (`Recreate`,
non-root, read-only root filesystem, probes, one landing claim per service). For a real cluster:

- push the image to a registry (`image.repository`, `image.tag`);
- credentials in an existing Secret (`existingSecret`), e.g. from External Secrets;
- landing zone in object storage: `landing.url: s3://...`, `landing.volume.enabled: false`;
- ENTSO-E: `services.entsoe-subscription.ingress` with a public host, a certificate from a public CA
  (cert-manager) and a source allowlist for 4.185.182.62 and 4.182.105.72; register
  `https://<host>/subscriptions` as the channel URL.

## Open

- Loading the landing zone into the warehouse (`raw.iris__*`, `raw.entsoe_subscription__*`) through
  `onboard-source`, including the natural keys and parsing ENTSO-E XML.
- ENTSO-E: verifying the push's XML signature against the platform's certificate; the response copies
  it, as ENTSO-E's sample subscriber does.
