// SPDX-License-Identifier: MIT
pragma solidity 0.8.35;

import {Test} from "forge-std/Test.sol";
import {NativeCollectorReference} from "../reference/NativeCollectorReference.sol";

contract NativeCollectorReferenceTest is Test {
    address payable internal recipient = payable(address(0xBEEF));

    function test_native_reference_transfers_all_eth_to_recipient() public {
        address predicted = computeCreateAddress(address(this), vm.getNonce(address(this)));
        vm.deal(predicted, 1.5 ether);

        new NativeCollectorReference(recipient);

        assertEq(recipient.balance, 1.5 ether);
        assertEq(predicted.balance, 0);
        assertEq(predicted.code.length, 0);
    }

    function test_native_reference_allows_zero_balance() public {
        new NativeCollectorReference(recipient);
        assertEq(recipient.balance, 0);
    }
}
