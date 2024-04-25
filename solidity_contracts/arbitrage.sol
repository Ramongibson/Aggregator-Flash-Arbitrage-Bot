// SPDX-License-Identifier: MIT
pragma solidity 0.8.19;
import "@openzeppelin/contracts@4.9.3/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts@4.9.3/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts@4.9.3/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts@4.9.3/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/math/SafeMath.sol";

interface IERC3156FlashLender {
    function maxFlashLoan(address token) external returns (uint256);
    function flashLoan(
        address receiver,
        address token,
        uint256 amount,
        bytes calldata data
    ) external returns (bool);
}

interface IERC3156FlashBorrower {
    function onFlashLoan(
        address initiator,
        address token,
        uint256 amount,
        uint256 fee,
        bytes calldata data
    ) external returns (bytes32);
}

contract ParaSwapSwapper is IERC3156FlashBorrower {
    using SafeERC20 for IERC20;
    using SafeMath for uint256;

    address private owner;
    address private constant AUGUSTUS_SWAPPER_ADDRESS = 0xDEF171Fe48CF0115B1d80b88dc8eAB59176FEe57;
    address private constant TOKEN_TRANSFER_PROXY_ADDRESS = 0x216B4B4Ba9F3e719726886d34a177484278Bfcae;
    address private constant MetaAggregationRouterV2 = 0x6131B5fae19EA4f9D964eAc0408E4408b66337b5;

    modifier onlyOwner() {
        require(msg.sender == owner, "Not the contract owner");
        _;
    }

    struct FlashCallbackData {
        address lender;
        uint256 loanAmount;
        address srcToken;
        address destToken;
        int256 swapOrder;
        bytes paraswapCalldata;
        bytes kyberswapCalldata;
    }

    constructor() {
        owner = msg.sender;
    }

    function executeFlashArbitrage(
        address _lender,
        uint256 _loanAmount,
        address _srcToken,
        address _destToken,
        int256 _swapOrder,
        bytes calldata _paraswapCalldata,
        bytes calldata _kyberswapCalldata
    ) external onlyOwner {
        IERC3156FlashLender flashLender = IERC3156FlashLender(_lender);
        require(_loanAmount > 0, "Flash loan not available");
        uint256 acquiredAmount  = _loanAmount;
        approve(_srcToken, _lender, acquiredAmount);

        bytes memory data = abi.encode(
            FlashCallbackData({
                lender: _lender,
                loanAmount: acquiredAmount,
                srcToken: _srcToken,
                destToken: _destToken,
                swapOrder: _swapOrder,
                paraswapCalldata: _paraswapCalldata,
                kyberswapCalldata: _kyberswapCalldata
            })
        );

        require(flashLender.flashLoan(address(this), _srcToken, acquiredAmount, data), "Flash loan failed");
    }

    function onFlashLoan(
        address initiator,
        address token,
        uint256 amount,
        uint256 fee,
        bytes calldata data
    ) external override returns (bytes32) {
        require(initiator == address(this), "Invalid loan initiator");

        FlashCallbackData memory decoded = abi.decode(data, (FlashCallbackData));
        address lender = decoded.lender;
        uint256 acquiredAmount = decoded.loanAmount;
        address srcToken = decoded.srcToken;
        address destToken = decoded.destToken;
        int256 swapOrder = decoded.swapOrder;
        bytes memory paraswapCalldata = decoded.paraswapCalldata;
        bytes memory kyberswapCalldata = decoded.kyberswapCalldata;
        require(token == srcToken, "Invalid token returned");
        require(amount == acquiredAmount, "Invalid loan amount returned");
        require(msg.sender == lender, "Unauthorized Lender");
        uint256 balance = 0;
        if(swapOrder == 0){
            uint256 swappedAmount = paraswap(srcToken, destToken, acquiredAmount, paraswapCalldata);
            balance = kyberswap(destToken, srcToken, swappedAmount, kyberswapCalldata);
        } else {
            uint256 swappedAmount = kyberswap(srcToken, destToken, acquiredAmount, kyberswapCalldata);
            balance = paraswap(destToken, srcToken, swappedAmount, paraswapCalldata);
        }
        IERC20(srcToken).safeTransfer(owner, balance - acquiredAmount);
        return keccak256('ERC3156FlashBorrower.onFlashLoan');
    }

    function paraswap(
        address srcToken,
        address destToken,
        uint256 amount,
        bytes memory swapCalldata
    ) internal returns (uint256) {
        // Approve TokenTransferProxy to spend fromToken
        approve(srcToken, TOKEN_TRANSFER_PROXY_ADDRESS, amount);

        (bool success, bytes memory returnData) = AUGUSTUS_SWAPPER_ADDRESS.call(swapCalldata);
        require(success);
        uint256 balance = IERC20(destToken).balanceOf(address(this));
        return balance;
    }

    function kyberswap(
        address srcToken,
        address destToken,
        uint256 amount,
        bytes memory swapCalldata
    ) internal returns (uint256) {
        approve(srcToken, MetaAggregationRouterV2, amount);

        (bool success, bytes memory returnData) = MetaAggregationRouterV2.call(swapCalldata);
        require(success);
        uint256 balance = IERC20(destToken).balanceOf(address(this));
        return balance;
    }

    function approve(address token, address spender, uint256 amount) internal {
        IERC20(token).approve(spender, amount);
    }
}
