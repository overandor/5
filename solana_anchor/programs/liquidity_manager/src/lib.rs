use anchor_lang::prelude::*;
use anchor_spl::token::{self, TokenAccount, Token, Transfer, Mint};
use pyth_sdk_solana::{PriceFeed, load_price_feed_from_account_info};

declare_id!("Fg6PaFpoGXkYsidMpWTK6W2BeZ7FEfcYkgc2s7Aq5MEo");

#[program]
pub mod liquidity_manager {
    use super::*;

    pub fn initialize(ctx: Context<Initialize>, bump: u8) -> Result<()> {
        let cfg = &mut ctx.accounts.config;
        cfg.owner = *ctx.accounts.authority.key;
        cfg.bump = bump;
        cfg.tranche_interval = 86_400;
        cfg.max_tx_percent_bp = 100;
        Ok(())
    }

    pub fn submit_order(ctx: Context<SubmitOrder>, total_amount: u64, tranche_amount: u64) -> Result<()> {
        let order = &mut ctx.accounts.order;
        order.seller = *ctx.accounts.seller.key;
        order.total = total_amount;
        order.remaining = total_amount;
        order.tranche = tranche_amount;
        order.start_time = Clock::get()?.unix_timestamp;
        order.last_executed = 0;
        order.active = true;

        let cpi_accounts = Transfer {
            from: ctx.accounts.seller_token_account.to_account_info(),
            to: ctx.accounts.vault_shift.to_account_info(),
            authority: ctx.accounts.seller.to_account_info(),
        };
        let cpi_program = ctx.accounts.token_program.to_account_info();
        token::transfer(CpiContext::new(cpi_program, cpi_accounts), total_amount)?;
        Ok(())
    }

    pub fn execute_tranche(ctx: Context<ExecuteTranche>, expected_anchor_out: u64) -> Result<()> {
        let order = &mut ctx.accounts.order;
        require!(order.active && order.remaining > 0, ErrorCode::OrderInactive);

        let now = Clock::get()?.unix_timestamp;
        if order.last_executed != 0 {
            require!(now >= order.last_executed + ctx.accounts.config.tranche_interval as i64, ErrorCode::TrancheNotReady);
        }

        let mut tranche = order.tranche;
        if tranche > order.remaining { tranche = order.remaining; }

        let anchor_balance = ctx.accounts.vault_anchor.amount;
        require!(anchor_balance >= expected_anchor_out, ErrorCode::InsufficientAnchor);

        // reward 10% to keeper
        let reward = tranche / 10;
        token::transfer(
            CpiContext::new(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.vault_shift.to_account_info(),
                    to: ctx.accounts.keeper_token.to_account_info(),
                    authority: ctx.accounts.program_authority.clone(),
                },
            ),
            reward,
        )?;

        token::transfer(
            CpiContext::new(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.vault_anchor.to_account_info(),
                    to: ctx.accounts.seller_anchor.to_account_info(),
                    authority: ctx.accounts.program_authority.clone(),
                },
            ),
            expected_anchor_out,
        )?;

        order.remaining = order.remaining.checked_sub(tranche).unwrap();
        order.last_executed = now;
        if order.remaining == 0 { order.active = false; }
        Ok(())
    }

    pub fn trigger_rebase(ctx: Context<TriggerRebase>) -> Result<()> {
        let price_feed: PriceFeed = load_price_feed_from_account_info(&ctx.accounts.pyth_price.to_account_info())
            .map_err(|_| error!(ErrorCode::BadOracle))?;
        let price = price_feed.get_price_unchecked().price;
        let holders = ctx.accounts.holder_count.count;
        let shrink_bp: u64 = if holders > 1_000 { 50 } else { 500 };
        emit!(RebaseSignal { shrink_bp, price: price as i128 });
        Ok(())
    }
}

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(init, payer = authority, space = 8 + 64)]
    pub config: Account<'info, Config>,
    #[account(mut)]
    pub authority: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct SubmitOrder<'info> {
    #[account(mut)]
    pub seller: Signer<'info>,
    #[account(init, payer = seller, space = 8 + 128)]
    pub order: Account<'info, WhaleOrder>,
    #[account(mut)]
    pub seller_token_account: Account<'info, TokenAccount>,
    #[account(mut)]
    pub vault_shift: Account<'info, TokenAccount>,
    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct ExecuteTranche<'info> {
    #[account(mut)]
    pub keeper: Signer<'info>,
    #[account(mut)]
    pub order: Account<'info, WhaleOrder>,
    #[account(mut)]
    pub vault_shift: Account<'info, TokenAccount>,
    #[account(mut)]
    pub vault_anchor: Account<'info, TokenAccount>,
    #[account(mut)]
    pub keeper_token: Account<'info, TokenAccount>,
    #[account(mut)]
    pub seller_anchor: Account<'info, TokenAccount>,
    #[account(mut)]
    pub config: Account<'info, Config>,
    /// CHECK: PDA with signer seeds
    pub program_authority: UncheckedAccount<'info>,
    pub token_program: Program<'info, Token>,
}

#[derive(Accounts)]
pub struct TriggerRebase<'info> {
    #[account(mut)]
    pub config: Account<'info, Config>,
    /// CHECK: Pyth price account
    pub pyth_price: AccountInfo<'info>,
    pub holder_count: Account<'info, HolderCount>,
}

#[account] pub struct Config { pub owner: Pubkey, pub bump: u8, pub tranche_interval: u64, pub max_tx_percent_bp: u64 }
#[account] pub struct WhaleOrder { pub seller: Pubkey, pub total: u64, pub remaining: u64, pub tranche: u64, pub start_time: i64, pub last_executed: i64, pub active: bool }
#[account] pub struct HolderCount { pub count: u64 }

#[error_code]
pub enum ErrorCode {
    #[msg("Order inactive or finished")] OrderInactive,
    #[msg("Tranche not ready")] TrancheNotReady,
    #[msg("Insufficient anchor")] InsufficientAnchor,
    #[msg("Bad oracle")] BadOracle,
}

#[event] pub struct RebaseSignal { pub shrink_bp: u64, pub price: i128 }
