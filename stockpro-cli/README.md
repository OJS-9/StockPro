# StockPro CLI

AI-powered stock research from your terminal. Talks to the StockPro backend over HTTPS.

By default the CLI targets the live deployment at `https://stockpro-production-11c8.up.railway.app`.

## Install

From the repo root:

```bash
pip install -e stockpro-cli/
```

This registers the `stockpro` command.

## First-time sign-in

```bash
stockpro auth login
```

Opens your browser to the StockPro Clerk sign-in page. After Google OAuth completes, the browser redirects to a short-lived local callback and the CLI stores your token at `~/.stockpro/config.json` (file mode `0600`).

Confirm:

```bash
stockpro auth status
```

Sign out (clears the stored token):

```bash
stockpro auth logout
```

## Pointing at local Flask (dev)

Precedence: `--api-url` flag > `STOCKPRO_API_URL` env var > `~/.stockpro/config.json` > default.

Per invocation:

```bash
stockpro --api-url http://127.0.0.1:5000 auth status
```

Shell session:

```bash
export STOCKPRO_API_URL=http://127.0.0.1:5000
stockpro auth status
```

Persist in the config file (only if you pass `--api-url` during `auth login`):

```bash
stockpro --api-url http://127.0.0.1:5000 auth login
```

## Commands

Run `stockpro --help` for the full list. Common ones:

- `stockpro auth login | logout | status`
- `stockpro portfolio list`
- `stockpro report list`
- `stockpro watchlist list`
