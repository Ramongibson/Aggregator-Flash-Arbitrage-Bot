import unittest
from unittest.mock import patch, MagicMock
from scripts.arb_bot import (
    connect_to_network,
    get_gas_price,
    get_token_list,
    Token,
    get_swap_route_kyberswap,
    get_swap_route_paraswap,
    execute_flash_arbitrage,
    build_swap_paraswap,
    build_swap_kyberswap,
)


class TestArbitrageBot(unittest.TestCase):

    def test_connect_to_network(self):
        with patch("scripts.arb_bot.Web3") as mock_web3:
            mock_web3.HTTPProvider.return_value = None
            mock_web3.middleware_onion.inject.return_value = None
            connect_to_network("http://localhost:8545")
            mock_web3.HTTPProvider.assert_called_with("http://localhost:8545")
            mock_web3.middleware_onion.inject.assert_called()

    def test_get_gas_price(self):
        mock_w3 = MagicMock()
        mock_w3.eth.gas_price = 1000000000  # 1 Gwei
        with patch("scripts.arb_bot.Web3", mock_w3):
            gas_price = get_gas_price(mock_w3)
            self.assertEqual(gas_price, Decimal("1"))

    def test_get_token_list_existing_file(self):
        with patch("scripts.arb_bot.os.path.exists") as mock_exists, patch(
            "scripts.arb_bot.load_file"
        ) as mock_load_file:
            mock_exists.return_value = True
            mock_load_file.return_value = {"DAI": {"address": "0x...", "decimals": 18}}
            tokens = get_token_list("tokens.json")
            mock_load_file.assert_called_with("tokens.json")
            self.assertIn("DAI", tokens)

    def test_get_token_list_api_call(self):
        with patch("scripts.arb_bot.requests.get") as mock_get, patch(
            "scripts.arb_bot.json.load"
        ), patch("scripts.arb_bot.open", unittest.mock.mock_open()), patch(
            "scripts.arb_bot.os.path.exists"
        ) as mock_exists:
            mock_exists.return_value = False
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {
                "tokens": [{"symbol": "ETH", "address": "0x...", "decimals": 18}]
            }
            mock_get.return_value = mock_response
            tokens = get_token_list("tokens.json")
            self.assertIn("ETH", tokens)
            self.assertEqual(tokens["ETH"]["address"], "0x...")

    def test_get_swap_route_kyberswap(self):
        mock_token = Token("ETH", {"address": "0x123", "decimals": 18})
        dest_token = Token("DAI", {"address": "0x456", "decimals": 18})
        src_amount = "1000000000000000000"  # 1 ETH in wei

        with patch("scripts.arb_bot.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"data": {"route": "best_route"}}
            mock_get.return_value = mock_response
            result = get_swap_route_kyberswap(mock_token, dest_token, src_amount)
            self.assertEqual(result, {"route": "best_route"})
            mock_get.assert_called_once()

    def test_get_swap_route_paraswap(self):
        mock_token = Token("ETH", {"address": "0x123", "decimals": 18})
        dest_token = Token("DAI", {"address": "0x456", "decimals": 18})
        src_amount = "1000000000000000000"

        with patch("scripts.arb_bot.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"priceRoute": {"bestPrice": "100"}}
            mock_get.return_value = mock_response
            result = get_swap_route_paraswap(mock_token, dest_token, src_amount, [])
            self.assertEqual(result, {"bestPrice": "100"})
            mock_get.assert_called_once()

    def test_execute_flash_arbitrage(self):
        mock_w3 = MagicMock()
        mock_contract = MagicMock()
        mock_transaction = MagicMock(build_transaction=MagicMock())
        mock_contract.functions.executeFlashArbitrage.return_value = mock_transaction

        with patch("scripts.arb_bot.w3", mock_w3), patch(
            "scripts.arb_bot.Web3.to_checksum_address"
        ), patch("scripts.arb_bot.HexBytes"):
            execute_flash_arbitrage(
                "0x123",
                "0x456",
                "0x789",
                {},
                "private_key",
                100,
                None,
                None,
                "calldata1",
                "calldata2",
                mock_w3,
                1,
                0,
            )
            mock_transaction.build_transaction.assert_called()

    def test_build_swap_paraswap(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": "tx_data"}

        with patch(
            "scripts.arb_bot.requests.post", return_value=mock_response
        ) as mock_post:
            result = build_swap_paraswap(
                None,
                None,
                "1000000000000000000",
                {"bestPrice": "100"},
                "0x123",
                "0x456",
            )
            self.assertEqual(result, "tx_data")
            mock_post.assert_called_once()

    def test_build_swap_kyberswap(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": {"data": "tx_data"}}

        with patch(
            "scripts.arb_bot.requests.post", return_value=mock_response
        ) as mock_post:
            result = build_swap_kyberswap({"routeSummary": "summary"}, "0x123")
            self.assertEqual(result, "tx_data")
            mock_post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
