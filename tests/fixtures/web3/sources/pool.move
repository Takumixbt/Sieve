module 0x1::pool {
    struct AdminCap has key { id: UID }
    public entry fun deposit(account: &signer, amount: u64) { }
    public fun set_fee(cap: &AdminCap, fee: u64) { }
    fun helper() { }
}
