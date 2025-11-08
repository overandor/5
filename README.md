# Paradox Liquidity — unified mono-repo (Solana + L2)

Modules
- **solana_anchor**: Anchor program (whale queue, tranche keeper hooks, rebase signal)
- **l2_foundry**: Solidity suite (RebaseToken, WhaleQueue, SelfLiquidityV2 AMM-like reserve engine, StraddleVault)
- **infra**: Local orchestration (anvil + solana-test-validator) and a tiny Flask hook

Quickstart

## L2 / Foundry

cd l2_foundry
forge install OpenZeppelin/openzeppelin-contracts@v5.0.2
forge test -vv
forge create src/RebaseToken.sol:RebaseToken
–constructor-args “Paradox” “PDX” 18
–private-key $PK –rpc-url $L2_RPC

## Solana / Anchor

cd solana_anchor
anchor build
anchor test
anchor deploy –provider.cluster devnet

Security
- Use a multisig for all `onlyOwner` contracts.
- Keep keeper keys isolated; consider bond/slashing for keeper quality.
