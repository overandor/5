// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "openzeppelin-contracts/security/ReentrancyGuard.sol";
import "openzeppelin-contracts/security/Pausable.sol";
import "openzeppelin-contracts/access/Ownable.sol";

contract SelfLiquidityV2 is Ownable, Pausable, ReentrancyGuard {
    uint256 public constant WAD = 1e18;

    uint256 public totalReserve;    // ETH
    uint256 public activeA;         // ETH
    uint16  public feeBps = 30;
    uint16  public burnBps = 5;
    uint256 public maxMintPerTx = 100_000 * 1e18;
    uint256 public minActive;
    uint256 public haltBelow;

    uint32  public thawIntervalSec = 60;
    uint256 public lambdaNum = 5;
    uint256 public lambdaDen = 100;
    uint256 public lastThawTimestamp;

    address public timelockController;
    uint256 public protectedReserveFloor;

    event Bought(address indexed buyer, uint256 ethIn, uint256 tokensOut, uint256 fee);
    event Sold(address indexed seller, uint256 tokensBurned, uint256 ethOut, uint256 fee);
    event Thawed(uint256 released, uint256 newActive);
    event Deposit(address indexed from, uint256 amount);
    event EmergencyDrain(address indexed to, uint256 amount);
    event ParamsUpdated();
    event TimelockSet(address indexed newTimelock);

    modifier onlyTimelock() { require(msg.sender == timelockController, "only timelock"); _; }

    string public name; string public symbol; uint8 public decimals = 18;
    mapping(address=>uint256) internal _bal;
    uint256 internal _supply;

    constructor(string memory n,string memory s,uint256 initR,uint256 initA,uint256 minA,uint256 protectedFloor) {
        require(initA <= initR, "bad init");
        name=n; symbol=s;
        totalReserve = initR; activeA = initA; minActive = minA; protectedReserveFloor = protectedFloor;
        lastThawTimestamp = block.timestamp;
    }

    // ERC20-like for position tokens
    function totalSupply() public view returns(uint256){ return _supply; }
    function balanceOf(address a) public view returns(uint256){ return _bal[a]; }
    event Transfer(address indexed from,address indexed to,uint256 value);

    function _mint(address to,uint256 a) internal { _supply+=a; _bal[to]+=a; emit Transfer(address(0),to,a); }
    function _burn(address from,uint256 a) internal { require(_bal[from]>=a,"bal"); unchecked{_bal[from]-=a;} _supply-=a; emit Transfer(from,address(0),a); }

    // Views
    function dormantD() public view returns (uint256) { return totalReserve >= activeA ? totalReserve - activeA : 0; }
    function priceWad() public view returns (uint256 pWad) {
        uint256 Aeff = activeA >= minActive ? activeA : minActive;
        uint256 D = dormantD(); if (D == 0) return type(uint256).max; pWad = (D * WAD) / Aeff;
    }

    // Admin
    function setFeeBps(uint16 v) external onlyOwner { require(v<=1000,"high"); feeBps=v; emit ParamsUpdated(); }
    function setBurnBps(uint16 v) external onlyOwner { require(v<=10000,"inv"); burnBps=v; emit ParamsUpdated(); }
    function setMinActive(uint256 v) external onlyOwner { minActive=v; emit ParamsUpdated(); }
    function setHaltBelow(uint256 v) external onlyOwner { haltBelow=v; emit ParamsUpdated(); }
    function setTimelock(address t) external onlyOwner { timelockController=t; emit TimelockSet(t); }
    function setProtectedFloor(uint256 f) external onlyOwner { protectedReserveFloor=f; }
    function setLambda(uint256 n,uint256 d,uint32 i) external onlyOwner { require(d>0 && n<=d,"lambda"); lambdaNum=n; lambdaDen=d; thawIntervalSec=i; emit ParamsUpdated(); }
    function pause() external onlyOwner { _pause(); } function unpause() external onlyOwner { _unpause(); }

    // Deposits
    receive() external payable { deposit(); }
    function deposit() public payable whenNotPaused { require(msg.value>0,"zero"); totalReserve += msg.value; activeA += msg.value; emit Deposit(msg.sender,msg.value); }

    // Buy
    function buy(uint256 minTokensOut) external payable nonReentrant whenNotPaused returns(uint256 out) {
        require(msg.value>0,"0"); require(activeA>=haltBelow,"halt");
        uint256 fee = (msg.value * feeBps) / 10000;
        uint256 feeBurn = (fee * burnBps) / 10000;
        uint256 feeToActive = fee - feeBurn;
        uint256 netEth = msg.value - fee;

        uint256 Aeff = activeA >= minActive ? activeA : minActive;
        uint256 D = dormantD(); require(D>0,"no D");
        out = (netEth * Aeff) / D; require(out>0,"0 out"); require(out<=maxMintPerTx,"cap"); require(out>=minTokensOut,"slip");

        activeA += netEth + feeToActive;
        totalReserve += msg.value;

        _mint(msg.sender, out);
        emit Bought(msg.sender, msg.value, out, fee);
    }

    // Sell
    function sell(uint256 tokenAmount, uint256 minEthOut) external nonReentrant whenNotPaused returns(uint256 ethOut) {
        require(tokenAmount>0,"0"); require(_bal[msg.sender]>=tokenAmount,"bal"); require(activeA>=haltBelow,"halt");
        uint256 Aeff = activeA >= minActive ? activeA : minActive;
        uint256 D = dormantD(); require(D>0,"no D");
        uint256 gross = (tokenAmount * D) / Aeff;
        uint256 fee = (gross * feeBps) / 10000;
        uint256 feeBurn = (fee * burnBps) / 10000;
        uint256 feeToActive = fee - feeBurn;
        uint256 net = gross > fee ? gross - fee : 0;
        require(net>0,"net 0"); require(net>=minEthOut,"slip");

        if (activeA >= net) activeA -= net; else activeA = 0;
        totalReserve -= net;
        activeA += feeToActive;

        _burn(msg.sender, tokenAmount);
        (bool ok,) = payable(msg.sender).call{value: net}(""); require(ok,"xfer");
        emit Sold(msg.sender, tokenAmount, net, fee);
        ethOut = net;
    }

    // Thaw
    function thaw() external whenNotPaused returns (uint256 released) {
        require(block.timestamp >= lastThawTimestamp + thawIntervalSec, "soon");
        uint256 D = dormantD();
        if (D <= activeA) { lastThawTimestamp = block.timestamp; emit Thawed(0, activeA); return 0; }
        uint256 gap = D - activeA;
        uint256 numer = lambdaNum * (block.timestamp - lastThawTimestamp);
        uint256 denom = lambdaDen * thawIntervalSec; if (denom==0) denom=1;
        uint256 factorWad = (numer * WAD) / denom;
        released = (gap * factorWad) / WAD; if (released > gap) released = gap;
        activeA += released; lastThawTimestamp = block.timestamp; emit Thawed(released, activeA);
    }

    // Emergency
    function emergencyDrain(address payable to, uint256 amount) external nonReentrant onlyTimelock {
        require(to!=address(0) && amount>0,"bad");
        require(totalReserve > protectedReserveFloor, "no excess");
        uint256 excess = totalReserve - protectedReserveFloor; require(amount<=excess, "too large");
        if (activeA >= amount) activeA -= amount; else activeA = 0;
        totalReserve -= amount; (bool ok,) = to.call{value: amount}(""); require(ok,"drain");
        emit EmergencyDrain(to, amount);
    }
}
