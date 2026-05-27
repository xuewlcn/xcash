// SPDX-License-Identifier: MIT
pragma solidity 0.8.35;

import {Test} from "forge-std/Test.sol";
import {XcashVaultSlotTemplate} from "../src/XcashVaultSlotTemplate.sol";
import {XcashVaultSlotFactory} from "../src/XcashVaultSlotFactory.sol";
import {MockERC20} from "./helpers/MockERC20.sol";
import {MockFalseReturnERC20} from "./helpers/MockFalseReturnERC20.sol";
import {MockMalformedReturnERC20} from "./helpers/MockMalformedReturnERC20.sol";
import {MockUsdtLike} from "./helpers/MockUsdtLike.sol";

contract XcashVaultSlotTest is Test {
    event XcashNativeReceived(address indexed from, uint256 amount);
    event XcashCollected(address indexed token, uint256 amount);

    address payable internal vault = payable(address(0xBEEF));
    XcashVaultSlotFactory internal factory;

    function setUp() public {
        XcashVaultSlotTemplate vaultSlotTemplate = new XcashVaultSlotTemplate();
        factory = new XcashVaultSlotFactory(address(vaultSlotTemplate));
    }

    function test_reverts_when_vault_is_zero() public {
        vm.expectRevert(XcashVaultSlotFactory.ZeroVault.selector);
        factory.deployVaultSlot(payable(address(0)), keccak256("zero-vault"));
    }

    function test_receive_forwards_native_coin_to_vault_and_emits_event() public {
        XcashVaultSlotTemplate slot = _deployVaultSlot("receive-native");
        address payer = address(0xA11CE);
        vm.deal(payer, 2 ether);

        vm.expectEmit(true, true, true, true, address(slot));
        emit XcashNativeReceived(payer, 2 ether);

        vm.prank(payer);
        (bool ok,) = address(slot).call{value: 2 ether}("");

        assertTrue(ok);
        assertEq(vault.balance, 2 ether);
        assertEq(address(slot).balance, 0);
    }

    function test_receive_only_forwards_msg_value_leaving_preexisting_balance() public {
        XcashVaultSlotTemplate slot = _deployVaultSlot("existing-native");
        vm.deal(address(slot), 0.4 ether);
        address payer = address(0xA11CE);
        vm.deal(payer, 0.6 ether);

        vm.expectEmit(true, true, true, true, address(slot));
        emit XcashNativeReceived(payer, 0.6 ether);

        vm.prank(payer);
        (bool ok,) = address(slot).call{value: 0.6 ether}("");

        assertTrue(ok);
        // receive 只转出 msg.value，预存的 0.4 ether 留在 slot 等显式清扫。
        assertEq(vault.balance, 0.6 ether);
        assertEq(address(slot).balance, 0.4 ether);

        vm.expectEmit(true, true, true, true, address(slot));
        emit XcashCollected(address(0), 0.4 ether);
        slot.collect(address(0));

        assertEq(vault.balance, 1 ether);
        assertEq(address(slot).balance, 0);
    }

    function test_reverts_when_amount_is_zero() public {
        XcashVaultSlotTemplate slot = _deployVaultSlot("zero-amount");

        (bool ok, bytes memory data) = address(slot).call{value: 0}("");

        assertFalse(ok);
        assertEq(data, abi.encodeWithSelector(XcashVaultSlotTemplate.ZeroAmount.selector));
    }

    function test_reverts_when_vault_rejects_native_coin() public {
        RejectingVault rejectingVault = new RejectingVault();
        XcashVaultSlotTemplate slot =
            _deployVaultSlot(payable(address(rejectingVault)), "reject-native");

        (bool ok, bytes memory data) = address(slot).call{value: 1 ether}("");

        assertFalse(ok);
        assertEq(data, abi.encodeWithSelector(XcashVaultSlotTemplate.ForwardFailed.selector));
        assertEq(address(slot).balance, 0);
        assertEq(address(rejectingVault).balance, 0);
    }

    function test_unknown_selector_with_value_reverts_without_fallback() public {
        // 移除 fallback() 后，带未知 selector 的调用必须直接 revert，资金不能被吞掉。
        XcashVaultSlotTemplate slot = _deployVaultSlot("no-fallback");
        address payer = address(0xCAFE);
        vm.deal(payer, 1 ether);

        vm.prank(payer);
        (bool ok,) = address(slot).call{value: 1 ether}(hex"12345678");

        assertFalse(ok);
        assertEq(vault.balance, 0);
        assertEq(address(slot).balance, 0);
        assertEq(payer.balance, 1 ether);
    }

    function test_collect_native_transfers_balance_to_vault() public {
        XcashVaultSlotTemplate slot = _deployVaultSlot("collect-native");
        vm.deal(address(slot), 1.5 ether);

        vm.expectEmit(true, true, true, true, address(slot));
        emit XcashCollected(address(0), 1.5 ether);

        slot.collect(address(0));

        assertEq(vault.balance, 1.5 ether);
        assertEq(address(slot).balance, 0);
    }

    function test_collect_native_reverts_when_balance_is_zero() public {
        XcashVaultSlotTemplate slot = _deployVaultSlot("collect-native-zero");

        vm.expectRevert(XcashVaultSlotTemplate.ZeroAmount.selector);
        slot.collect(address(0));
    }

    function test_collect_native_reverts_when_vault_rejects() public {
        RejectingVault rejectingVault = new RejectingVault();
        XcashVaultSlotTemplate slot =
            _deployVaultSlot(payable(address(rejectingVault)), "collect-native-reject");
        vm.deal(address(slot), 1 ether);

        vm.expectRevert(XcashVaultSlotTemplate.ForwardFailed.selector);
        slot.collect(address(0));

        assertEq(address(slot).balance, 1 ether);
        assertEq(address(rejectingVault).balance, 0);
    }

    function test_collect_erc20_transfers_full_balance_to_vault() public {
        XcashVaultSlotTemplate slot = _deployVaultSlot("erc20-standard");
        MockERC20 token = new MockERC20();
        token.mint(address(slot), 1000e18);

        vm.expectEmit(true, true, true, true, address(slot));
        emit XcashCollected(address(token), 1000e18);

        slot.collect(address(token));

        assertEq(token.balanceOf(vault), 1000e18);
        assertEq(token.balanceOf(address(slot)), 0);
    }

    function test_collect_erc20_supports_usdt_like_token() public {
        XcashVaultSlotTemplate slot = _deployVaultSlot("erc20-usdt-like");
        MockUsdtLike token = new MockUsdtLike();
        token.mint(address(slot), 500e6);

        vm.expectEmit(true, true, true, true, address(slot));
        emit XcashCollected(address(token), 500e6);

        slot.collect(address(token));

        assertEq(token.balanceOf(vault), 500e6);
        assertEq(token.balanceOf(address(slot)), 0);
    }

    function test_collect_erc20_reverts_when_balance_is_zero() public {
        XcashVaultSlotTemplate slot = _deployVaultSlot("erc20-zero");
        MockERC20 token = new MockERC20();

        vm.expectRevert(XcashVaultSlotTemplate.ZeroAmount.selector);
        slot.collect(address(token));
    }

    function test_collect_erc20_reverts_when_token_returns_false() public {
        XcashVaultSlotTemplate slot = _deployVaultSlot("erc20-false");
        MockFalseReturnERC20 token = new MockFalseReturnERC20();
        token.mint(address(slot), 1);

        vm.expectRevert(XcashVaultSlotTemplate.ERC20TransferFailed.selector);
        slot.collect(address(token));
    }

    function test_collect_erc20_reverts_when_token_returns_malformed_bool() public {
        XcashVaultSlotTemplate slot = _deployVaultSlot("erc20-malformed");
        MockMalformedReturnERC20 token = new MockMalformedReturnERC20();
        token.mint(address(slot), 1);

        vm.expectRevert(XcashVaultSlotTemplate.ERC20TransferFailed.selector);
        slot.collect(address(token));
    }

    function _deployVaultSlot(string memory saltLabel) private returns (XcashVaultSlotTemplate) {
        return _deployVaultSlot(vault, saltLabel);
    }

    function _deployVaultSlot(address payable vault_, string memory saltLabel)
        private
        returns (XcashVaultSlotTemplate)
    {
        return XcashVaultSlotTemplate(
            payable(factory.deployVaultSlot(vault_, keccak256(bytes(saltLabel))))
        );
    }
}

contract RejectingVault {
    receive() external payable {
        revert("reject");
    }
}
