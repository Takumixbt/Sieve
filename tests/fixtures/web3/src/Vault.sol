// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IERC20} from "./IERC20.sol";

/// @notice traps: braces and keywords inside comments and strings must not confuse the parser
/// require(msg.sender == owner); function fake() external { totalSupply = 0; }
interface IOracle {
    function getPrice(address asset) external view returns (uint256);
}

abstract contract Ownable {
    address public owner;
    modifier onlyOwner() {
        require(msg.sender == owner, "not owner { brace in string }");
        _;
    }
    function transferOwnership(address next) external onlyOwner {
        owner = next;
    }
}

contract Vault is Ownable {
    uint256 public constant MAX_FEE = 1000;
    IERC20 public immutable asset;
    IOracle public oracle;
    mapping(address => uint256) public balances;
    mapping(address => mapping(address => uint256)) internal allowances;
    uint256 public totalSupply;
    uint256 public fee;
    bool private initialized;
    /* block comment with { unbalanced brace */
    address public keeper;

    event Deposit(address indexed who, uint256 amount);

    constructor(IERC20 _asset, IOracle _oracle) {
        asset = _asset;
        oracle = _oracle;
        owner = msg.sender;
    }

    function initialize(address _keeper) external {
        require(!initialized, "init");
        initialized = true;
        keeper = _keeper;
    }

    function deposit(uint256 amount) external nonReentrant returns (uint256 shares) {
        shares = amount * totalSupply / asset.balanceOf(address(this));
        asset.transferFrom(msg.sender, address(this), amount);
        balances[msg.sender] += shares;
        totalSupply += shares;
        emit Deposit(msg.sender, amount);
    }

    function withdraw(
        uint256 shares,
        address to
    )
        external
        returns (uint256 out)
    {
        out = shares * asset.balanceOf(address(this)) / totalSupply;
        _burn(msg.sender, shares);
        asset.transfer(to, out);
    }

    function _burn(address who, uint256 shares) internal {
        unchecked {
            balances[who] -= shares;
        }
        totalSupply -= shares;
    }

    function setFee(uint256 newFee) external onlyOwner {
        require(newFee <= MAX_FEE, "fee cap");
        fee = newFee;
    }

    function setOracle(IOracle o) external onlyOwner {
        oracle = o;
    }

    function rebalance(uint256 minOut) external onlyRole(KEEPER_ROLE) {
        uint256 p = oracle.getPrice(address(asset));
        (bool ok, ) = keeper.call{value: 0}("");
        require(ok && p > minOut);
    }

    function emergencyWithdraw(address to) external {
        require(msg.sender == owner, "auth");
        (bool ok, ) = to.call{value: address(this).balance}("");
        require(ok);
    }

    function price() external view returns (uint256) {
        return oracle.getPrice(address(asset));
    }

    receive() external payable {}
}

library MathLib {
    function mulDiv(uint256 a, uint256 b, uint256 c) internal pure returns (uint256) {
        return a * b / c;
    }
}
