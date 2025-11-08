// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "openzeppelin-contracts/access/Ownable.sol";
import "openzeppelin-contracts/security/ReentrancyGuard.sol";

// Minimal interface to tap SelfLiquidityV2 price band signal via priceWad()
interface ISelfLiquidityV2 {
    function priceWad() external view returns (uint256);
}

interface IERC20Like {
    function transfer(address,uint256) external returns(bool);
    function transferFrom(address,address,uint256) external returns(bool);
}

// Single-epoch straddle market with “impermanent gain” rebate for LP-like addresses that stay through reversion.
// Premium in base ERC20 (e.g., stable). Payouts in same token.
contract StraddleVault is Ownable, ReentrancyGuard {
    struct Market {
        uint64  expiry;           // unix time
        uint256 strikeWad;        // WAD price, e.g., 1e18 ~ $1
        uint256 lotSize;          // size per lot in “token units”
        uint256 sigmaBP;          // premium coefficient in bps (heuristic)
        bool    active;
    }

    IERC20Like public premiumToken;       // e.g., USDC-like
    IERC20Like public baseToken;          // the oscillating token or its ERC20 representation (if bridged)
    ISelfLiquidityV2 public oracle;       // reads priceWad() for band signal

    Market public m;

    mapping(address => uint256) public lotsBought;
    mapping(address => uint256) public lotsSold;     // seller inventory
    uint256 public totalSold;
    uint256 public totalBought;

    // Impermanent gain pool fed by protocol fees off-chain; can be topped up by owner.
    uint256 public igPool;

    event MarketCreated(uint64 expiry, uint256 strikeWad, uint256 lotSize, uint256 sigmaBP);
    event BuyStraddle(address indexed user, uint256 lots, uint256 premium);
    event SellStraddle(address indexed seller, uint256 lots, uint256 collateralPosted);
    event Settled(uint256 spotWad);
    event Claim(address indexed user, uint256 payout);
    event FundIG(uint256 amount);

    constructor(address _oracle, address _baseToken) {
        oracle = ISelfLiquidityV2(_oracle);
        baseToken = IERC20Like(_baseToken);
        premiumToken = IERC20Like(address(0)); // set later if using a different ERC20 for premium
    }

    function setPremiumToken(address p) external onlyOwner { premiumToken = IERC20Like(p); }

    function createMarket(uint64 expiry, uint256 strikeWad, uint256 lotSize, uint256 sigmaBP) external onlyOwner {
        require(!m.active, "market active");
        require(expiry > block.timestamp + 1 hours, "expiry soon");
        m = Market({ expiry: expiry, strikeWad: strikeWad, lotSize: lotSize, sigmaBP: sigmaBP, active: true });
        emit MarketCreated(expiry, strikeWad, lotSize, sigmaBP);
    }

    // Heuristic premium = lotSize * strike * sigma * sqrt(T) (T normalized to 1 for simplicity)
    function _premiumPerLot() internal view returns (uint256) {
        return (m.lotSize * m.strikeWad * m.sigmaBP) / (1e4 * 1e18);
    }

    function buyStraddle(uint256 lots) external nonReentrant {
        require(m.active && block.timestamp < m.expiry, "closed");
        uint256 prem = _premiumPerLot() * lots;
        require(prem > 0, "prem 0");
        require(premiumToken.transferFrom(msg.sender, address(this), prem), "prem xfer");
        lotsBought[msg.sender] += lots;
        totalBought += lots;
        emit BuyStraddle(msg.sender, lots, prem);
    }

    // Sellers post base token collateral; worst-case payout per lot is lotSize (one side max(K-spot,0) <= K)
    function sellStraddle(uint256 lots) external nonReentrant {
        require(m.active && block.timestamp < m.expiry, "closed");
        uint256 collateral = m.lotSize * lots;
        require(baseToken.transferFrom(msg.sender, address(this), collateral), "coll xfer");
        lotsSold[msg.sender] += lots;
        totalSold += lots;
        emit SellStraddle(msg.sender, lots, collateral);
    }

    // Settlement: payout buyers = |spot - strike| * lots. Sellers receive remaining collateral + share of premium + IG rebate.
    bool public settled;
    uint256 public spotWad;

    function settle() external nonReentrant {
        require(m.active && block.timestamp >= m.expiry, "not expired");
        require(!settled, "settled");
        spotWad = oracle.priceWad();
        settled = true;
        m.active = false;
        emit Settled(spotWad);
    }

    function claimBuyer() external nonReentrant returns (uint256) {
        require(settled, "no");
        uint256 lots = lotsBought[msg.sender]; require(lots > 0, "0");
        lotsBought[msg.sender] = 0;
        uint256 diffWad = spotWad > m.strikeWad ? spotWad - m.strikeWad : m.strikeWad - spotWad;
        uint256 payout = (diffWad * m.lotSize * lots) / 1e18;
        require(baseToken.transfer(msg.sender, payout), "payout");
        emit Claim(msg.sender, payout);
        return payout;
    }

    // Sellers get remaining collateral + premium share + impermanent-gain rebate if spot reverted inside band (close to strike)
    function claimSeller() external nonReentrant returns (uint256) {
        require(settled, "no");
        uint256 lots = lotsSold[msg.sender]; require(lots > 0, "0");
        lotsSold[msg.sender] = 0;

        uint256 diffWad = spotWad > m.strikeWad ? spotWad - m.strikeWad : m.strikeWad - spotWad;
        uint256 buyerPayoutPerLot = (diffWad * m.lotSize) / 1e18;
        uint256 collateralPosted = m.lotSize * lots;
        uint256 maxBuyerPayout = buyerPayoutPerLot * (totalBought > 0 ? (lots * totalBought) / totalSold : 0);

        uint256 remaining = collateralPosted > maxBuyerPayout ? collateralPosted - maxBuyerPayout : 0;

        // Premium share proportional to lots
        // premiumToken balance is all accumulated premiums
        // For simplicity we pay out premium in baseToken via treasury refill off-chain or use same token for premium/base.
        // Here we assume premiumToken == baseToken for minimal deploy.
        uint256 vaultPrem = _bal(baseToken, address(this)) > 0 ? _bal(baseToken, address(this)) : 0;
        uint256 premShare = totalSold > 0 ? (vaultPrem * lots) / totalSold : 0;

        // Impermanent gain rebate: if spot inside ±5% of strike, rebate from IG pool to sellers who stayed till expiry
        bool insideBand = (diffWad * 10000) / m.strikeWad <= 500;  // 5%
        uint256 igShare = insideBand && igPool > 0 ? (igPool * lots) / totalSold : 0;
        if (insideBand && igShare > 0) igPool -= igShare;

        uint256 payout = remaining + premShare + igShare;
        require(baseToken.transfer(msg.sender, payout), "seller payout");
        emit Claim(msg.sender, payout);
        return payout;
    }

    function fundIG(uint256 amt) external onlyOwner {
        require(baseToken.transferFrom(msg.sender, address(this), amt), "fund");
        igPool += amt;
        emit FundIG(amt);
    }

    function _bal(IERC20Like t, address a) internal view returns (uint256) {
        try t.balanceOf(a) returns (uint256 b) { return b; } catch { return 0; }
    }
}
