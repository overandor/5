import * as anchor from "@project-serum/anchor";
import { Program } from "@project-serum/anchor";
import { PublicKey, Keypair } from "@solana/web3.js";
import { assert } from "chai";

describe("liquidity_manager", () => {
  const provider = anchor.AnchorProvider.local();
  anchor.setProvider(provider);
  it("builds", async () => {
    assert.ok(true);
  });
});
