// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./RebaseToken.sol";
import "openzeppelin-contracts/access/Ownable.sol";
import "openzeppelin-contracts/security/ReentrancyGuard.sol";

interface IERC20Like { function transfer(address,uint256) external returns(bool); function balanceOf(address) external view returns(uint256); }

contract WhaleQueue is Ownable, ReentrancyGuard {
    RebaseToken public token;
    IERC20Like public anchorToken;
    address public treasury;
    uint256 public maxTxPercentBP = 100;       // 1%
    uint256 public trancheInterval = 1 days;
    uint256 public rewardMultiplierBP = 1000;  // 10%

    struct Order {
        address seller;
        uint256 totalAmount;
        uint256 remaining;
        uint256 trancheSize;
        uint256 startTime;
        uint256 lastExecutedAt;
        bool active;
    }

    Order[] public orders;
    mapping(address => uint256[]) public ordersOf;

    event OrderCreated(uint256 indexed id, address indexed seller, uint256 total, uint256 tranche);
    event TrancheExecuted(uint256 indexed id, address indexed keeper, uint256 trancheAmount, uint256 paidOut);
    event OrderCancelled(uint256 indexed id, address indexed seller);

    constructor(address _token, address _anchor, address _treasury) {
        token = RebaseToken(_token);
        anchorToken = IERC20Like(_anchor);
        treasury = _treasury;
    }

    function createOrder(uint256 totalAmount, uint256 desiredTranche) external nonReentrant returns (uint256) {
        require(totalAmount > 0, "zero amt");
        uint256 circ = token.totalSupply();
        uint256 maxAllowed = (circ * maxTxPercentBP) / 10000;
        require(desiredTranche <= maxAllowed, "tranche too large");

        require(token.transferFrom(msg.sender, address(this), totalAmount), "xferFrom fail");

        orders.push(Order({
            seller: msg.sender,
            totalAmount: totalAmount,
            remaining: totalAmount,
            trancheSize: desiredTranche,
            startTime: block.timestamp,
            lastExecutedAt: 0,
            active: true
        }));
        uint256 id = orders.length - 1;
        ordersOf[msg.sender].push(id);
        emit OrderCreated(id, msg.sender, totalAmount, desiredTranche);
        return id;
    }

    function executeTranche(uint256 id, uint256 minAnchorOut) external nonReentrant returns (uint256) {
        Order storage o = orders[id];
        require(o.active && o.remaining > 0, "inactive");
        if (o.lastExecutedAt != 0) require(block.timestamp >= o.lastExecutedAt + trancheInterval, "not ready");

        uint256 tranche = o.trancheSize; if (tranche > o.remaining) tranche = o.remaining;

        uint256 pre = anchorToken.balanceOf(address(this));

        uint256 reward = (tranche * rewardMultiplierBP) / 10000;
        require(token.transfer(msg.sender, reward), "reward fail");

        require(anchorToken.balanceOf(address(this)) >= pre + minAnchorOut, "anchor short");

        o.remaining -= tranche;
        o.lastExecutedAt = block.timestamp;
        if (o.remaining == 0) o.active = false;

        require(anchorToken.transfer(o.seller, minAnchorOut), "payout fail");
        emit TrancheExecuted(id, msg.sender, tranche, minAnchorOut);
        return minAnchorOut;
    }

    function cancelOrder(uint256 id) external nonReentrant {
        Order storage o = orders[id];
        require(o.active, "inactive");
        require(msg.sender == o.seller || msg.sender == owner(), "auth");
        o.active = false;
        uint256 rem = o.remaining; o.remaining = 0;
        require(token.transfer(o.seller, rem), "return fail");
        emit OrderCancelled(id, o.seller);
    }

    // Gov
    function setMaxTxPercentBP(uint256 bps) external onlyOwner { maxTxPercentBP = bps; }
    function setTrancheInterval(uint256 s) external onlyOwner { trancheInterval = s; }
    function setRewardMultiplierBP(uint256 bps) external onlyOwner { rewardMultiplierBP = bps; }
}
