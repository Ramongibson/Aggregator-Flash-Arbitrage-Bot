import sys
from web3 import Web3
from web3.exceptions import ValidationError
from web3.middleware import geth_poa_middleware
import traceback
import json
import time
import threading
from eth_account import Account
import requests
from decimal import Decimal
import os
from loguru import logger as log
from hexbytes import HexBytes
from itertools import cycle


PARASWAP_API_URL = "https://apiv5.paraswap.io"
KYBERSWAP_API_URL = "https://aggregator-api.kyberswap.com/bsc/api/v1"
USER_ADDRESS = "0xe7804c37c13166fF0b37F5aE0BB07A3aEbb6e245"
global_gas_price = None
gas_price_lock = threading.Lock()
proxy_list = [
    "http://pvM109.201.152.168:1080",
    "http://p109.201.152.179:1080",
    "http://p77.247.181.215:1080",
]
proxy_cycle = cycle(proxy_list)


def connect_to_network(network_rpc):
    w3 = Web3(Web3.HTTPProvider(network_rpc))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    return w3


def load_file(filename):
    with open(filename, "r") as json_file:
        file = json.load(json_file)
    return file


class Token:
    def __init__(self, symbol, token_info, vault=None, profit=None):
        self.symbol = symbol
        self.address = Web3.to_checksum_address(token_info["address"])
        self.decimals = token_info["decimals"]
        self.vault = vault
        self.profit = profit


def get_gas_price(w3):
    try:
        gas_price = w3.eth.gas_price
        gas_price = w3.from_wei(gas_price, "Gwei")
        return gas_price
    except Exception as e:
        traceback.print_exc()
        return None


def watch_gas_price(w3):
    global global_gas_price
    while True:
        gas_price = get_gas_price(w3)
        if gas_price is not None:
            with gas_price_lock:
                global_gas_price = gas_price
        else:
            print("Failed to retrieve gas price.")

        time.sleep(1)


class Networks:
    BSC = 56


class Address(str):
    pass


class Symbol(str):
    pass


class NumberAsString(str):
    pass


class SwapSide:
    SELL = "SELL"
    BUY = "BUY"


def get_token_list(token_filename):
    if os.path.exists(token_filename):
        tokens = load_file(token_filename)
        return tokens

    tokens_url = f"{PARASWAP_API_URL}/tokens/{Networks.BSC}"
    response = requests.get(tokens_url)
    response.raise_for_status()

    json_response = json.dumps(response.json(), indent=2)
    log.debug(json_response)
    tokens = {}
    for item in response.json()["tokens"]:
        tokens[item["symbol"]] = {
            "address": item["address"],
            "decimals": item["decimals"],
        }
    with open(token_filename, "w") as json_file:
        json.dump(tokens, json_file, indent=2)
    return tokens


def get_swap_route_kyberswap(
    src_token: Token, dest_token: Token, src_amount: NumberAsString
):
    route_path = f"{KYBERSWAP_API_URL}/routes"

    # Specify the call parameters (only the required params are specified here, see Docs for full list)
    target_path_config = {
        "params": {
            "tokenIn": src_token.address,
            "tokenOut": dest_token.address,
            "amountIn": str(src_amount),
            "source": "v1swapper",
        },
        "headers": {"x-client-id": "v1swapper"},
    }

    params = target_path_config.get("params")
    headers = target_path_config.get("headers")
    # Call the API with requests to handle async calls
    try:
        proxy = next(proxy_cycle)
        proxies = {"http": proxy}
        response = requests.get(
            route_path, headers=headers, params=params, proxies=proxies
        )
        response.raise_for_status()
        json_response = json.dumps(response.json(), indent=2)
        log.debug(json_response)
        price_route = response.json()
        return price_route["data"]
    except requests.exceptions.HTTPError as http_err:
        log.error(f"HTTP error occurred: {http_err}")
        log.error(response.content)
        return None
    except requests.exceptions.RequestException as req_err:
        log.error(f"Request error occurred: {req_err}")
        return None


def get_swap_route_paraswap(
    src_token: Token, dest_token: Token, src_amount: NumberAsString, paraswap_dexs
):
    try:
        requestOptions = {
            "params": {
                "srcToken": src_token.address,
                "srcDecimals": str(src_token.decimals),
                "destToken": dest_token.address,
                "destDecimals": str(dest_token.decimals),
                "amount": str(src_amount),
                "side": SwapSide.SELL,
                "network": Networks.BSC,
                "maxImpact": 100,
                # "includeDEXS": paraswap_dexs,
            }
        }

        prices_url = f"{PARASWAP_API_URL}/prices"
        params = requestOptions.get("params", {})
        proxy = next(proxy_cycle)
        proxies = {"http": proxy}
        response = requests.get(prices_url, params=params, proxies=proxies)
        response.raise_for_status()

        # Convert the response to JSON format and log it
        json_response = json.dumps(response.json(), indent=2)
        log.debug(json_response)
    except requests.exceptions.HTTPError as http_err:
        log.error(f"HTTP error occurred: {http_err}")
        log.error(response.content)
        return None
    except requests.exceptions.RequestException as req_err:
        log.error(f"Request error occurred: {req_err}")
        return None

    # Ensure that the response contains the expected structure
    if "priceRoute" in response.json():
        price_route = response.json()["priceRoute"]
        return price_route
    else:
        log.error("Unexpected response format.")
        return None


def execute_flash_arbitrage(
    flashloan_address,
    account_address,
    contract_address,
    contract_abi,
    private_key,
    loan_amount,
    src_token,
    dest_token,
    paraswap_calldata,
    kyberswap_calldata,
    w3,
    gas_price,
    swap_order,
):
    contract = w3.eth.contract(
        address=w3.to_checksum_address(contract_address), abi=contract_abi
    )
    gas_price_wei = w3.to_wei(gas_price, "gwei")
    tx_params = {
        "from": account_address,
        "gas": 8000000,
        "gasPrice": gas_price_wei,
        "nonce": w3.eth.get_transaction_count(account_address),
    }

    paraswap_calldataParam = HexBytes(paraswap_calldata)
    kyberswap_calldataParam = HexBytes(kyberswap_calldata)
    transaction = contract.functions.executeFlashArbitrage(
        flashloan_address,
        loan_amount,
        w3.to_checksum_address(src_token.address),
        w3.to_checksum_address(dest_token.address),
        swap_order,
        paraswap_calldataParam,
        kyberswap_calldataParam,
    ).build_transaction(tx_params)

    estimated_gas = w3.eth.estimate_gas(tx_params, block_identifier=None)
    log.info(f"Estimated gas for transaction: {estimated_gas}")

    # Sign transaction
    signed_transaction = w3.eth.account.sign_transaction(transaction, private_key)

    # Send transaction
    tx_hash = w3.eth.send_raw_transaction(signed_transaction.rawTransaction)
    log.info(f"Arbitrage transaction sent: {tx_hash.hex()}")

    # Wait for the transaction receipt
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    log.info(f"Arbitrage transaction mined in block: {receipt['blockNumber']}")
    sys.exit(1)


def build_swap_paraswap(
    src_token: Token,
    dest_token: Token,
    src_amount: NumberAsString,
    price_route,
    contract_address: str,
    receiver_address: str,
):
    try:
        tx_url = f"{PARASWAP_API_URL}/transactions/{Networks.BSC}"

        tx_config = {
            "priceRoute": price_route,
            "userAddress": contract_address,
            "srcToken": src_token.address,
            "srcDecimals": str(src_token.decimals),
            "destToken": dest_token.address,
            "destDecimals": str(dest_token.decimals),
            "srcAmount": str(src_amount),
            "slippage": 9000,
            "receiver": receiver_address,
        }

        query_params = {"ignoreChecks": "true"}

        response = requests.post(tx_url, params=query_params, json=tx_config)
        response.raise_for_status()

        tx_params = response.json()
        if tx_params is not None:
            json_response = json.dumps(tx_params, indent=2)
            log.debug(json_response)
        return tx_params["data"]
    except requests.exceptions.HTTPError as http_err:
        log.error(f"HTTP error occurred: {http_err}")
        log.error(response.content)
        return None
    except requests.exceptions.RequestException as req_err:
        log.error(f"Request error occurred: {req_err}")
        return None


def build_swap_kyberswap(
    data,
    contract_address: str,
):
    try:
        tx_url = f"{KYBERSWAP_API_URL}/route/build"

        tx_config = {
            "routeSummary": data["routeSummary"],
            "sender": contract_address,
            "recipient": contract_address,
            "slippageTolerance": 2000,
        }
        headers = {"x-client-id": "v1swapper"}

        response = requests.post(tx_url, headers=headers, json=tx_config)
        response.raise_for_status()

        tx_params = response.json()
        if tx_params is not None:
            json_response = json.dumps(tx_params, indent=2)
            log.debug(json_response)
        return tx_params["data"]["data"]
    except requests.exceptions.HTTPError as http_err:
        log.error(f"HTTP error occurred: {http_err}")
        log.error(response.content)
        return None
    except requests.exceptions.RequestException as req_err:
        log.error(f"Request error occurred: {req_err}")
        return None


def subtract_percentage(wad, percentage):
    result = wad - (percentage / 100) * wad
    return int(result)


def main():
    config_filename = "config/bot_config.json"
    config = load_file(config_filename)
    log.remove()
    log.add(sys.stdout, level=config["log_level"])
    log.opt(colors=True)
    mode = config["mode"]
    gas_limit = config["gas_limit"]
    slippage = config["slippage"]
    arbitrage_address = config["arbitrage_address"]
    arbitrage_abi = load_file(config["arbitrage_abi_filename"])
    # min_bnb_balance = global_config["global_config"]["min_bnb_balance"]
    network_rpc = config["testnet_rpc"] if mode == "test" else config["mainnet_rpc"]
    w3 = connect_to_network(network_rpc)
    flashloan_address = w3.to_checksum_address(config["flashloan_address"])
    flashloan_abi = load_file(config["flashloan_abi_filename"])
    private_key = (
        config["test_private_key"]
        if mode == "test"
        else config["production_private_key"]
    )
    account = Account.from_key(private_key)
    if not w3.eth.get_balance(account.address):
        raise ValueError("Wallet is not unlocked or does not exist")

    # Start a separate thread or process to watch gas price
    watch_gas_price_thread = threading.Thread(target=watch_gas_price, args=(w3,))
    watch_gas_price_thread.start()
    tokens = get_token_list(config["token_filename"])
    loan_tokens = get_token_list(config["loan_token_filename"])
    if len(sys.argv) < 2:
        log.error("Missing argument")
        sys.exit(1)
    if sys.argv[1] != "BUSD" and sys.argv[1] != "WBNB":
        log.error("Invalid source token")
        sys.exit(1)
    src_token_info = loan_tokens.get(sys.argv[1])
    dest_token_info = tokens.get(sys.argv[2])
    src_token = Token(
        sys.argv[1],
        src_token_info,
        src_token_info["vault"],
        int(src_token_info["profit"] * (10**18)),
    )
    dest_token = Token(sys.argv[2], dest_token_info)
    flashloan_contract = w3.eth.contract(address=flashloan_address, abi=flashloan_abi)
    paraswap_dexs = "Uniswap, Kyber, Bancor, AugustusRFQ, Oasis, Compound, Fulcrum, 0x, MakerDAO, Chai, Aave, Aave2, MultiPath, MegaPath, Curve, Curve3, Saddle, IronV2, BDai, idle, Weth, Beth, UniswapV2, Balancer, 0xRFQt, SushiSwap, LINKSWAP, Synthetix, DefiSwap, Swerve, CoFiX, Shell, DODOV1, DODOV2, OnChainPricing, PancakeSwap, PancakeSwapV2, ApeSwap, Wbnb, acryptos, streetswap, bakeryswap, julswap, vswap, vpegswap, beltfi, ellipsis, QuickSwap, COMETH, Wmatic, Nerve, Dfyn, UniswapV3, Smoothy, PantherSwap, OMM1, OneInchLP, CurveV2, mStable, WaultFinance, MDEX, ShibaSwap, CoinSwap, SakeSwap, JetSwap, Biswap, BProtocol"
    while True:
        balance_wei = w3.eth.get_balance(account.address)
        wallet_balance = w3.from_wei(balance_wei, "Gwei")
        max_flash_loan_amount_decimals = flashloan_contract.functions.maxFlashLoan(
            src_token.address
        ).call()
        max_flash_loan_amount = max_flash_loan_amount_decimals / (10**18)
        desired_amount = max_flash_loan_amount_decimals + src_token.profit
        log.info(f"desired_amount: {desired_amount}")
        log.debug(
            f"Flashloan amount {src_token.symbol}: {max_flash_loan_amount_decimals}={max_flash_loan_amount}"
        )
        paraswap_results = get_swap_route_paraswap(
            src_token, dest_token, max_flash_loan_amount_decimals, paraswap_dexs
        )
        log.info(
            f"Paraswap/Kyberswap srcToken: {src_token.symbol}, destoken: {dest_token.symbol}"
        )
        if paraswap_results is not None:
            log.info(f'Paraswap amountOut: {paraswap_results["destAmount"]}')
            kyberswap_results = get_swap_route_kyberswap(
                dest_token, src_token, paraswap_results["destAmount"]
            )
            if kyberswap_results is not None:
                log.info(
                    f'Kyberswap amountOut: {kyberswap_results["routeSummary"]["amountOut"]}'
                )

                if int(kyberswap_results["routeSummary"]["amountOut"]) > desired_amount:
                    log.success(
                        f"Arbitrage found Paraswap/Kyberswap, srcToken: {src_token.symbol}, destoken: {dest_token.symbol}"
                    )
                    paraswap_tx_params = build_swap_paraswap(
                        src_token,
                        dest_token,
                        paraswap_results["srcAmount"],
                        paraswap_results,
                        src_token.vault,
                        arbitrage_address,
                    )
                    kyberswap_tx_params = build_swap_kyberswap(
                        kyberswap_results, arbitrage_address
                    )
                    if (
                        paraswap_tx_params is not None
                        and kyberswap_tx_params is not None
                    ):
                        execute_flash_arbitrage(
                            flashloan_address,
                            account.address,
                            arbitrage_address,
                            arbitrage_abi,
                            private_key,
                            max_flash_loan_amount_decimals,
                            src_token,
                            dest_token,
                            paraswap_tx_params,
                            kyberswap_tx_params,
                            w3,
                            global_gas_price,
                            0,
                        )
            time.sleep(1)
            kyberswap_results = get_swap_route_kyberswap(
                src_token, dest_token, max_flash_loan_amount_decimals
            )
            log.info(f"srcToken: {src_token.symbol}, destoken: {dest_token.symbol}")
            if kyberswap_results is not None:
                log.info(
                    f'Kyberswap2 amountOut: {kyberswap_results["routeSummary"]["amountOut"]}'
                )
                paraswap_results = get_swap_route_paraswap(
                    dest_token,
                    src_token,
                    kyberswap_results["routeSummary"]["amountOut"],
                    paraswap_dexs,
                )
                if paraswap_results is not None:
                    log.info(f'Paraswap2 amountOut: {paraswap_results["destAmount"]}')
                    if int(paraswap_results["destAmount"]) > desired_amount:
                        log.success(
                            f"Arbitrage found Kyberswap/Paraswap, srcToken: {src_token.symbol}, destoken: {dest_token.symbol}"
                        )
                        paraswap_tx_params = build_swap_paraswap(
                            dest_token,
                            src_token,
                            paraswap_results["srcAmount"],
                            paraswap_results,
                            arbitrage_address,
                            arbitrage_address,
                        )
                        kyberswap_tx_params = build_swap_kyberswap(
                            kyberswap_results, arbitrage_address
                        )
                        if (
                            paraswap_tx_params is not None
                            and kyberswap_tx_params is not None
                        ):
                            execute_flash_arbitrage(
                                flashloan_address,
                                account.address,
                                arbitrage_address,
                                arbitrage_abi,
                                private_key,
                                max_flash_loan_amount_decimals,
                                src_token,
                                dest_token,
                                paraswap_tx_params,
                                kyberswap_tx_params,
                                w3,
                                global_gas_price,
                                1,
                            )
        time.sleep(1)


if __name__ == "__main__":
    main()
