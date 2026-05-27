// SPDX-License-Identifier: MIT
pragma solidity 0.8.35;

import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";

/// @title XcashVaultSlotTemplate
/// @notice Native coin and ERC20 vault slot that forwards funds to its slot-encoded vault.
contract XcashVaultSlotTemplate {
    error ZeroVault();
    error InvalidVaultArgs();
    error ZeroAmount();
    error ForwardFailed();
    error ERC20TransferFailed();

    event XcashNativeReceived(address indexed from, uint256 amount);
    event XcashCollected(address indexed token, uint256 amount);

    receive() external payable {
        _forwardNative();
    }

    function collect(address token) external {
        if (token == address(0)) {
            uint256 amount = address(this).balance;
            if (amount == 0) revert ZeroAmount();
            emit XcashCollected(address(0), amount);
            (bool ok,) = vault().call{value: amount}("");
            if (!ok) revert ForwardFailed();
        } else {
            _collectERC20(token);
        }
    }

    function _collectERC20(address token) private {
        uint256 amount = IERC20BalanceOf(token).balanceOf(address(this));
        if (amount == 0) revert ZeroAmount();
        address payable vault_ = vault();
        emit XcashCollected(token, amount);

        (bool ok, bytes memory data) =
            token.call(abi.encodeCall(IERC20Transfer.transfer, (vault_, amount)));
        if (!ok || !_isERC20TransferReturnSuccess(data)) {
            revert ERC20TransferFailed();
        }
    }

    function vault() public view returns (address payable vault_) {
        bytes memory args = Clones.fetchCloneArgs(address(this));
        if (args.length != 20) revert InvalidVaultArgs();

        uint160 rawVault;
        assembly ("memory-safe") {
            rawVault := shr(96, mload(add(args, 32)))
        }
        vault_ = payable(address(rawVault));
        if (vault_ == address(0)) revert ZeroVault();
    }

    function _isERC20TransferReturnSuccess(bytes memory data) private pure returns (bool) {
        if (data.length == 0) return true;
        if (data.length != 32) return false;

        uint256 value;
        assembly ("memory-safe") {
            value := mload(add(data, 32))
        }
        return value == 1;
    }

    function _forwardNative() private {
        if (msg.value == 0) revert ZeroAmount();
        emit XcashNativeReceived(msg.sender, msg.value);

        (bool ok,) = vault().call{value: msg.value}("");
        if (!ok) revert ForwardFailed();
    }
}

interface IERC20BalanceOf {
    function balanceOf(address account) external view returns (uint256);
}

interface IERC20Transfer {
    function transfer(address to, uint256 amount) external returns (bool);
}
