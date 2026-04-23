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

## Headless / serverless (no browser)

For agents running in a serverless environment (no browser to open), use the device-code flow. The agent prints a code; the user opens the URL on any device, signs in, and approves.

```bash
stockpro auth device-login
```

Output:

```
Open https://stockpro-production-11c8.up.railway.app/app/device?user_code=ABCD1234 on any browser,
sign in, and confirm code: ABCD1234
(expires in 10 min). Waiting...
```

Once approved, the token is saved to `~/.stockpro/config.json` just like `auth login`.

### Token injection via env var

If the agent already has a token (e.g. generated from the Settings -> CLI tokens page on the web app), skip the device flow entirely:

```bash
export STOCKPRO_TOKEN=sp_xxxxxxxxxxxxxxxx
stockpro portfolio list
```

`STOCKPRO_TOKEN` takes precedence over `~/.stockpro/config.json`. Perfect for injecting into serverless runtimes as a secret.

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
