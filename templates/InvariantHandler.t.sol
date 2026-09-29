// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Fill-in Foundry invariant/handler harness — works as a starting point for both Foundry's own
// `forge test --match-contract InvariantHandler` invariant runner and, with the matching
// echidna.yaml/medusa.json pointing at this contract, Echidna or Medusa. See
// `references/property-fuzzing.md`.
//
// Fill in: the target contract's real type, the bounded actions a real caller could take, and one
// `invariant_*` function per property from `xray/invariants.md` or `invariant-agent.md`'s output.

import {Test} from "forge-std/Test.sol";

interface ITarget {
    function deposit(uint256 amount) external;
    function withdraw(uint256 amount) external;
    function balanceOf(address who) external view returns (uint256);
    function totalSupply() external view returns (uint256);
}

contract InvariantHandler is Test {
    ITarget internal target;
    address[] internal actors;

    uint256 public ghost_deposited;
    uint256 public ghost_withdrawn;

    constructor(address _target) {
        target = ITarget(_target);
        for (uint256 i = 0; i < 5; i++) {
            actors.push(address(uint160(0x1000 + i)));
        }
    }

    function _actor(uint256 seed) internal view returns (address) {
        return actors[seed % actors.length];
    }

    /// Bound every action's parameters to something the real system could actually see —
    /// an unbounded fuzz input burns runs reaching states no real caller could reach.
    function deposit(uint256 actorSeed, uint256 amount) external {
        address who = _actor(actorSeed);
        amount = bound(amount, 1, 1_000_000e18);
        vm.prank(who);
        // target.deposit(amount);   // uncomment and adapt once wired to the real target
        ghost_deposited += amount;
    }

    function withdraw(uint256 actorSeed, uint256 amount) external {
        address who = _actor(actorSeed);
        uint256 bal = target.balanceOf(who);
        if (bal == 0) return;
        amount = bound(amount, 1, bal);
        vm.prank(who);
        // target.withdraw(amount);  // uncomment and adapt once wired to the real target
        ghost_withdrawn += amount;
    }

    /// A donation action models the first-depositor/share-inflation vector (W3-INF-01) —
    /// include it whenever the target has a share-price formula, even if no normal user path
    /// donates directly; the fuzzer needs the action modeled to find the break.
    function donate(uint256 amount) external {
        amount = bound(amount, 1, 1_000_000e18);
        // (bool ok,) = address(target).call{value: amount}("");  // adapt to the real asset
    }

    function skipTime(uint256 seconds_) external {
        vm.warp(block.timestamp + bound(seconds_, 1, 30 days));
    }
}

contract InvariantHandlerTest is Test {
    InvariantHandler internal handler;

    function setUp() public {
        address target = address(0); // deploy or point at the real target here
        handler = new InvariantHandler(target);
        targetContract(address(handler));
    }

    /// Conservation: nothing is created or destroyed outside deposit/withdraw.
    function invariant_conservation() public view {
        // assertEq(handler.ghost_deposited() - handler.ghost_withdrawn(), target.totalSupply());
    }

    /// Solvency: the system can always honor its stated liabilities.
    function invariant_solvency() public view {
        // assertGe(token.balanceOf(address(target)), target.totalSupply());
    }
}
