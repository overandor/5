// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../src/RebaseToken.sol";
import "../src/WhaleQueue.sol";
import "../src/SelfLiquidityV2.sol";
import "../src/StraddleVault.sol";

contract Deploy is Script {
    function run() external {
        vm.startBroadcast();
        RebaseToken r = new RebaseToken("Paradox", "PDX", 18);
        // Dummy addresses until wired to a stable
        address anchor = address(0xdead);
        address treasury = msg.sender;
        WhaleQueue q = new WhaleQueue(address(r), anchor, treasury);
        SelfLiquidityV2 sl = new SelfLiquidityV2("SelfLiq", "SLQ",
            10 ether, 5 ether, 1 ether, 1 ether
        );
        StraddleVault sv = new StraddleVault(address(sl), address(r));
        vm.stopBroadcast();
    }
}
