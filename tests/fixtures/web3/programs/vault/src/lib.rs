use anchor_lang::prelude::*;

#[program]
pub mod vault {
    use super::*;
    pub fn initialize(ctx: Context<Initialize>) -> Result<()> { Ok(()) }
    pub fn withdraw(ctx: Context<Withdraw>, amount: u64) -> Result<()> { Ok(()) }
    pub fn sweep(ctx: Context<Sweep>) -> Result<()> { Ok(()) }
}

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(init, payer = user, space = 8 + 32)]
    pub vault: Account<'info, VaultState>,
    #[account(mut)]
    pub user: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct Withdraw<'info> {
    #[account(mut, has_one = authority)]
    pub vault: Account<'info, VaultState>,
    pub authority: Signer<'info>,
}

#[derive(Accounts)]
pub struct Sweep<'info> {
    #[account(mut)]
    pub vault: Account<'info, VaultState>,
    /// CHECK: unchecked destination
    pub dest: UncheckedAccount<'info>,
    pub caller: Signer<'info>,
}
