# Arbitrage Bot for ParaSwap and KyberSwap

This bot is designed to exploit arbitrage opportunities between the ParaSwap and KyberSwap decentralized finance (DeFi) platforms. It monitors price discrepancies across these platforms and executes trades to profit from the differences.

## Features

- Monitors real-time prices on ParaSwap and KyberSwap.
- Executes flash loans and arbitrage trades when profitable opportunities are detected.
- Utilizes smart contracts for secure transaction execution.
- Supports proxy rotation for API requests to minimize rate-limiting issues.
- Detailed logging for monitoring bot activity and debugging.

## Requirements

- Python 3.x
- `web3.py` library
- Ethereum wallet with ETH for gas and transaction fees
- Private key management
- API access to ParaSwap and KyberSwap

## Installation

1. Clone the repository:
2. Install dependencies:

```bash
python arbitrage_bot.py
```

## Configuration

- Create a `config` directory in the root of your project.
- Inside `config`, create a `bot_config.json` file with the following structure:

```json
{
 "log_level": "DEBUG",
 "mode": "test",
 "gas_limit": 8000000,
 "slippage": 2000,
 "arbitrage_address": "0xYourContractAddress",
 "testnet_rpc": "https://data-seed-prebsc-1-s1.binance.org:8545/",
 "mainnet_rpc": "https://bsc-dataseed.binance.org/",
 "flashloan_address": "0xFlashloanContractAddress",
 "arbitrage_abi_filename": "arbitrage_contract_abi.json",
 "token_filename": "token_config.json",
 "loan_token_filename": "loan_token_config.json",
 "production_private_key": "YourProductionPrivateKey"
}
```

## Usage

Run the script with Python:

```bash
python arb_bot.py {src_token} {dest_token}
```

## Security Considerations

Ensure your private keys are stored securely and never hard-coded directly into your configuration files. Use environment variables or secure key management solutions.

## Disclaimer

This bot is for educational and development purposes only.
