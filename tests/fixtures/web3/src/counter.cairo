#[starknet::contract]
mod Counter {
    #[abi(embed_v0)]
    impl CounterImpl of super::ICounter<ContractState> {
        fn increase(ref self: ContractState, amount: u256) {
            self.count.write(self.count.read() + amount);
        }
        fn get(self: @ContractState) -> u256 { self.count.read() }
        fn reset(ref self: ContractState) {
            self.ownable.assert_only_owner();
            self.count.write(0);
        }
    }
}
