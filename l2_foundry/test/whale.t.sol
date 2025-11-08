// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import "forge-std/Test.sol";
import "../src/RebaseToken.sol";
import "../src/WhaleQueue.sol";

contract WhaleTest is Test {
    RebaseToken t;
    WhaleQueue q;

    address seller = address(0xBEEF);
    address anchor = address(0xA11CE);
    address treasury = address(this);

    function setUp() public {
        t = new RebaseToken("Paradox","PDX",18);
        q = new WhaleQueue(address(t), anchor, treasury);
        // seed seller
        vm.startPrank(address(this));
        t.transfer(seller, 1000 ether);
        vm.stopPrank();
        vm.prank(seller);
        t.approve(address(q), type(uint256).max);
    }

    function testCreateAndCancel() public {
        vm.prank(seller);
        uint256 id = q.createOrder(100 ether, 10 ether);
        assertEq(id, 0);
        vm.prank(seller);
        q.cancelOrder(id);
    }
}
