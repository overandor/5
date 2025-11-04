// SPDX-License-Identifier: MIT
pragma solidity ^0.8.21;

contract KPIOracle {
    address public signer;
    uint256 public epoch;
    uint256 public value; // 1e18 scale
    event Update(uint256 epoch, uint256 value);

    constructor(address _signer){ signer=_signer; }

    modifier onlySigner() {
        require(msg.sender == signer, "Not authorized signer");
        _;
    }

    function update(uint256 _epoch, uint256 _value, bytes calldata sig) external onlySigner {
        // In a real implementation, the signature would be verified on-chain
        // using ECDSA.recover to ensure data integrity.
        // e.g., require(signer == ecrecover(keccak256(abi.encodePacked(_epoch, _value)), ...), "Invalid signature");

        require(_epoch > epoch, "Stale epoch");
        epoch = _epoch;
        value = _value;
        emit Update(_epoch, _value);
    }
}
