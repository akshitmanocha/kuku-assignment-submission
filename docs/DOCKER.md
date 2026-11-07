# Run Promo Lab with Docker

Build from the repository root and publish the port on your computer's loopback address.

```bash
docker build -t promo-lab .
docker run --rm --init \
  -p 127.0.0.1:8765:8765 \
  -v promo-lab-data:/app/output \
  promo-lab
```

Open `http://127.0.0.1:8765`. The image uses Python 3.12 and opens a saved Nemotron analysis of the original fictional screenplay without an API call. A named volume stores your analyses, reading records and synthetic runs between containers. The build context is limited to application source and the public example. [Docker port publishing](https://docs.docker.com/engine/network/port-publishing/) · [Docker build context](https://docs.docker.com/build/concepts/context/#dockerignore-files)

## Run with model settings

Copy `.env.example` to `.env` and fill in the desired settings. Pass the file when starting the container. See the [provider guide](PROVIDERS.md).

```bash
docker run --rm --init \
  --env-file .env \
  -p 127.0.0.1:8765:8765 \
  -v promo-lab-data:/app/output \
  promo-lab
```

The container supports the offline demo and remote HTTPS model endpoints. Use the Python launch to connect to Ollama on your computer through its local endpoint. Upload your own screenplay from **New analysis** and export results from **Run history**.

## Pick another port

The browser port and the server port must match because the app checks the request's host and origin. If the native app is already using port 8765, use a different port on both sides.

```bash
docker run --rm --init \
  -p 127.0.0.1:8766:8766 \
  -v promo-lab-data:/app/output \
  promo-lab python -m promo_lab serve --host 0.0.0.0 --port 8766
```

Open `http://127.0.0.1:8766`. Each volume is a separate workspace, so use a separate named volume when running two instances concurrently. The native Python launch stores its data in the checkout's `output/` directory.
