// SPDX-License-Identifier: MIT
pragma solidity 0.8.35;

import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";

/// @title XcashDepositFactory
/// @notice Deploys XcashDepositSlot addresses with immutable vault args at deterministic CREATE2 addresses.
contract XcashDepositFactory {
    error ZeroDepositTemplate();
    error InvalidDepositTemplate();
    error ZeroVault();

    event XcashDepositSlotDeployed(
        address indexed depositSlot, address indexed vault, bytes32 indexed salt
    );

    address public immutable depositTemplate;

    constructor(address depositTemplate_) {
        if (depositTemplate_ == address(0)) revert ZeroDepositTemplate();
        if (depositTemplate_.code.length == 0) revert InvalidDepositTemplate();
        depositTemplate = depositTemplate_;
    }

    function deployDepositSlot(address payable vault, bytes32 salt)
        external
        returns (address depositSlot)
    {
        if (vault == address(0)) revert ZeroVault();
        depositSlot = Clones.cloneDeterministicWithImmutableArgs(
            depositTemplate, _encodeVaultArg(vault), salt
        );
        emit XcashDepositSlotDeployed(depositSlot, vault, salt);
    }

    function predictDepositSlot(address payable vault, bytes32 salt)
        external
        view
        returns (address)
    {
        if (vault == address(0)) revert ZeroVault();
        return Clones.predictDeterministicAddressWithImmutableArgs(
            depositTemplate, _encodeVaultArg(vault), salt, address(this)
        );
    }

    function _encodeVaultArg(address payable vault) private pure returns (bytes memory) {
        return abi.encodePacked(vault);
    }
}
