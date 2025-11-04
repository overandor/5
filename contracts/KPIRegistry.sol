// SPDX-License-Identifier: MIT
pragma solidity ^0.8.21;

import "./KPIToken.sol";
import "./KPIOracle.sol";

contract KPIRegistry {
    struct KPIInfo {
        address token;
        address oracle;
        bytes32 dslHash;
        string  symbol;
        string  name;
        bool    live;
    }

    mapping(bytes32 => KPIInfo) public kpis; // symbol hash → info
    event KPIListed(string symbol, address token, address oracle);

    function listKPI(
        string memory symbol,
        string memory name,
        bytes32 dslHash,
        address oracleSigner,
        address emissionsReceiver
    ) external returns (address token, address oracle) {
        bytes32 key = keccak256(bytes(symbol));
        require(kpis[key].token == address(0), "Symbol is already taken");
        KPIOracle o = new KPIOracle(oracleSigner);
        KPIToken t = new KPIToken(symbol, name, address(o), emissionsReceiver);
        kpis[key] = KPIInfo(address(t), address(o), dslHash, symbol, name, true);
        emit KPIListed(symbol, address(t), address(o));
        return (address(t), address(o));
    }
}
