# Xcash

<p align="center">
  <strong>Open-Source Self-Hosted Cryptocurrency Payment Gateway</strong>
  <br />
  Accept USDT, ETH, and 100+ blockchain assets with zero platform fees and full self-custody.
</p>

<p align="center">
  <a href="https://xca.sh"><img src="https://img.shields.io/badge/Website-xca.sh-blue" alt="Website"></a>
  <a href="https://github.com/xca-sh/xcash/stargazers"><img src="https://img.shields.io/github/stars/xca-sh/xcash" alt="GitHub Stars"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.13-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/django-5.2-green.svg" alt="Django">
</p>

<p align="center">
  English | <a href="README.md">Simplified Chinese</a>
</p>

## What is Xcash?

**Xcash** is an open-source, self-hosted **cryptocurrency payment gateway** for businesses, SaaS products, exchanges, and wallet platforms. It helps you accept crypto payments, USDT payments, on-chain deposits, and withdrawals directly through your own infrastructure.

Unlike hosted payment processors such as CoinGate or OpenNode, Xcash is **fully self-custodial**: private keys stay on your infrastructure, payments go directly to your wallet addresses, and Xcash does not take a platform fee. It is designed for teams that need multi-chain payment collection, deposits, withdrawals, and webhook notifications.

**Use cases:** e-commerce crypto payments, USDT deposit and withdrawal systems, cross-border stablecoin settlement, SaaS subscription billing in crypto, exchange-style wallet infrastructure, and internal treasury operations.

## Key Capabilities

| Feature | Detail |
|---------|--------|
| Payment gateway | Accept USDT, ETH, and other crypto assets on 100+ chains |
| Self-custody | Private keys stay on your own infrastructure |
| Zero platform fees | No percentage cuts, pay only blockchain gas |
| Deposit and withdrawal | Exchange-style crypto deposit and withdrawal flows |
| Webhooks | Real-time payment, deposit, and withdrawal event notifications |
| Risk control | MistTrack on-chain address risk scoring for payments and deposits |
| EasyPay compatibility | Compatible with EasyPay V1 payment integrations |
| Docker deployment | Production deployment with Docker Compose |

## Supported Chains

| Feature | ETH | BNB Chain | Arbitrum | Base | Tron | Polygon | Avalanche | Optimism | Other EVM |
|:-------:|:---:|:---------:|:--------:|:----:|:----:|:-------:|:---------:|:--------:|:---------:|
| Payment | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Deposit | Yes | Yes | Yes | Yes | No | Yes | Yes | Yes | Yes |
| Withdrawal | Yes | Yes | Yes | Yes | No | Yes | Yes | Yes | Yes |

All EVM-compatible chains can be enabled from the admin panel without code changes.

## Token Support

EVM chains support arbitrary ERC-20 tokens. Add the token contract address in the admin panel to enable assets such as USDT, USDC, or custom business tokens.

Tron currently supports payment flows only and is focused on TRC20-USDT collection.

## Risk Control

Xcash includes risk query, caching, persistence, and display capabilities. Address risk detection is provided by external MistTrack services; Xcash does not maintain its own blacklist or custom risk model.

Risk checks currently cover two core fund entry points:

- **Payment invoices:** after an invoice is matched with an on-chain payment, Xcash asynchronously checks the payer address and stores the risk level and risk score.
- **User deposits:** after a deposit record is created, Xcash asynchronously checks the source address and stores the risk level and risk score.

Risk results are stored in dedicated risk assessment records with status, target type, source address, transaction hash, risk level, risk score, reasons, report URL, and error summary. The Django admin, API responses, and webhooks expose risk information so operators and merchant systems can review or react to suspicious funds.

Xcash supports MistTrack OpenAPI V3 first and can fall back to the QuickNode MistTrack add-on when no MistTrack OpenAPI key is configured.

## Why Xcash?

| vs. | Xcash | CoinGate | OpenNode |
|---|---|---|---|
| Self-hosted | Yes | No | No |
| 100+ chains | Yes | Yes | No |
| Zero platform fees | Yes | No | No |
| Deposit and withdrawal | Yes | No | No |
| Risk control | Yes | No | No |
| EasyPay compatibility | Yes | No | No |
| Docker deployment | Yes | N/A | N/A |

## Screenshots

![Xcash admin dashboard](xcash/static/xcash-dashboard.jpeg)

## Architecture

```mermaid
graph LR
    Buyer["Buyer<br/>Payment page"]
    Merchant["Merchant system"]

    subgraph Xcash
        API["Xcash API"]
        Worker["Xcash Worker<br/>Monitoring / Collection / State transitions"]
        Signer["Xcash Signer<br/>Standalone signing service"]
        Webhook["Xcash Webhook<br/>Event notification"]
    end

    Blockchain["Blockchain networks<br/>EVM / Tron"]

    Buyer -->|Pay| API
    Merchant <-->|Create invoice / query| API
    API <--> Worker
    API <--> Signer
    Worker <-->|Monitor / Broadcast| Blockchain
    Webhook -->|Push events| Merchant
```

## Deployment Requirements

Before deploying Xcash, prepare the following:

- Linux server, recommended Ubuntu 22.04+ or Debian 12+
- Docker and Docker Compose
- A domain name pointing to the server
- RPC endpoints for the chains you want to enable
- A TronGrid API key if you want to enable Tron payments

Recommended server profiles:

| Performance mode | Hardware | Payment only | Native coin scanning enabled |
|:----------------:|:--------:|:------------:|:----------------------------:|
| low | 1 CPU / 2 GB RAM | 5 - 10 EVM chains | 2 - 3 EVM chains |
| medium | 4 CPU / 8 GB RAM | 15 - 30 EVM chains | 8 - 15 EVM chains |
| high | 8 CPU / 16 GB RAM | 30+ EVM chains | 15 - 30 EVM chains |

Set `PERFORMANCE` in `.env` to `low`, `medium`, or `high`. If it is not set, Xcash uses `low`.

Native EVM coin scanning is disabled by default. Deposit and withdrawal flows depend on native coin scanning because gas distribution, collection, and chain confirmation require continuous block polling. Enable it in the admin panel under **System -> Platform parameters** only when your RPC provider can handle high-frequency calls.

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/xca-sh/xcash.git
cd xcash
```

### 2. Initialize environment variables

```bash
make init-env
```

This generates two env files with auto-filled random secrets:

- `.env` — shared by the main app containers (django/worker/beat), docker compose interpolation, and local dev. Holds the Django secret key, main DB password, signer shared secret, etc. It deliberately does **not** contain the signer mnemonic decryption key.
- `.env.signer` — loaded only by the signer container. Holds the most sensitive credentials including `SIGNER_MNEMONIC_ENCRYPTION_KEY`; created with `chmod 600`.

> ⚠️ Do **not** modify `.env.signer` after it is generated, especially `SIGNER_MNEMONIC_ENCRYPTION_KEY`: changing it makes every encrypted mnemonic in the database permanently undecryptable and loses the hot-wallet private keys. Back up both files offline and never commit them.

### 3. Configure your domain

Edit `.env` and set `SITE_DOMAIN`:

```env
SITE_DOMAIN=xcash.example.com
```

Point the domain to your server and configure a reverse proxy such as Nginx or Caddy to forward traffic to `http://localhost:6688`.

### 4. Start services

```bash
make up
```

On first startup, if no admin account exists, Xcash creates the default admin account:

```text
username: admin
password: Admin@123456
```

Change the default password immediately after first login. OTP setup is required during the first admin login flow.

### 5. Stop services

```bash
make down
```

This stops and removes the production Docker Compose service containers without deleting database volumes.

### 6. Configure chain RPC endpoints

Open the admin panel and go to **Chain management**. Fill in RPC endpoints for the chains you want to use.

Recommended RPC providers include [QuickNode](https://www.quicknode.com/), [Alchemy](https://www.alchemy.com/), and [Infura](https://www.infura.io/). Tron payments require a [TronGrid](https://www.trongrid.io/) API key.

### 7. Upgrade to the latest version

```bash
make upgrade
```

This pulls the latest `main` branch and runs the full production upgrade flow.

## API Integration

After deployment, see [API.md](API.md) to integrate payments, deposits, withdrawals, and webhook callbacks.

Invoice creation can include an invoice-level `notify_url` to override the project default webhook. The EasyPay V1-compatible `submit.php` endpoint also maps `notify_url` to the invoice-level notification URL.

## Tech Stack

- **Backend:** Django 5.2 + Django REST Framework
- **Queue:** Celery + Redis
- **Database:** PostgreSQL
- **Blockchain:** web3.py for EVM
- **Wallet derivation:** BIP44 HD wallets with bip-utils
- **Payment frontend:** React 19 + Vite + Tailwind CSS
- **Deployment:** Docker Compose

## Roadmap

- [ ] Solana support
- [x] Tron support
- [ ] Documentation website

## Cloud Service

If you do not want to deploy and maintain Xcash yourself, you can use the hosted version:

**[xca.sh](https://xca.sh)** - ready to use, no self-hosting required, continuously updated.

## Commercial Support

For deployment, integration, or operational support, contact:

tech@xca.sh

## Contributing

Issues and pull requests are welcome.

## License

[MIT](LICENSE)
