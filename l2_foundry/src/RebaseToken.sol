// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import "openzeppelin-contracts/token/ERC20/IERC20.sol";
import "openzeppelin-contracts/access/Ownable.sol";

contract RebaseToken is Ownable {
    string public name;
    string public symbol;
    uint8 public immutable decimals;

    uint256 private _totalSupply;
    mapping(address => uint256) private _gons;
    mapping(address => mapping(address => uint256)) public allowance;

    uint256 private constant INITIAL_FRAGMENTS_SUPPLY = 1_000_000 * 1e18;
    uint256 private _gonsPerFragment;
    uint256 private _totalGons;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event Rebase(uint256 oldSupply, uint256 newSupply);

    constructor(string memory _n, string memory _s, uint8 _d) {
        name = _n; symbol = _s; decimals = _d;
        _totalSupply = INITIAL_FRAGMENTS_SUPPLY;
        _totalGons = type(uint256).max - (type(uint256).max % _totalSupply);
        _gonsPerFragment = _totalGons / _totalSupply;
        _gons[msg.sender] = _totalGons;
        emit Transfer(address(0), msg.sender, _totalSupply);
    }
    function totalSupply() public view returns (uint256) { return _totalSupply; }
    function balanceOf(address a) public view returns (uint256) { return _gons[a] / _gonsPerFragment; }
    function _fragmentToGons(uint256 a) internal view returns (uint256) { return a * _gonsPerFragment; }

    function approve(address s, uint256 a) external returns (bool) {
        allowance[msg.sender][s] = a; emit Approval(msg.sender, s, a); return true;
    }
    function transfer(address to, uint256 a) external returns (bool) { _transfer(msg.sender, to, a); return true; }
    function transferFrom(address f, address t, uint256 a) external returns (bool) {
        uint256 al = allowance[f][msg.sender]; require(al >= a, "allowance");
        unchecked { allowance[f][msg.sender] = al - a; } _transfer(f,t,a); return true;
    }
    function _transfer(address f, address t, uint256 a) internal {
        require(t != address(0), "zero"); uint256 g = _fragmentToGons(a);
        require(_gons[f] >= g, "bal"); unchecked { _gons[f] -= g; _gons[t] += g; }
        emit Transfer(f,t,a);
    }
    function rebase(uint256 newTotalSupply) external onlyOwner returns (uint256) {
        require(newTotalSupply > 0, "new=0"); uint256 old = _totalSupply; _totalSupply = newTotalSupply;
        _gonsPerFragment = _totalGons / _totalSupply; emit Rebase(old, newTotalSupply); return _totalSupply;
    }
    function mint(address to, uint256 a) external onlyOwner {
        uint256 g = _fragmentToGons(a); _gons[to] += g; _totalSupply += a; _totalGons += g;
        _gonsPerFragment = _totalGons / _totalSupply; emit Transfer(address(0), to, a);
    }
    function burn(address from, uint256 a) external onlyOwner {
        uint256 g = _fragmentToGons(a); require(_gons[from] >= g, "burn bal");
        unchecked { _gons[from] -= g; } _totalSupply -= a; _totalGons -= g;
        _gonsPerFragment = _totalGons / _totalSupply; emit Transfer(from, address(0), a);
    }
}
