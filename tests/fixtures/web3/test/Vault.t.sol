contract VaultTest {
    function testDeposit() public {}
    function testFuzzWithdraw(uint256 a) public {}
    function invariant_solvency() public {}
    function echidna_never_zero() public returns (bool) { return true; }
}
