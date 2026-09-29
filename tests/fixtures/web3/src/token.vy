owner: public(address)
balances: HashMap[address, uint256]

@external
@payable
def deposit():
    self.balances[msg.sender] += msg.value

@external
@nonreentrant("lock")
def withdraw(amount: uint256):
    self.balances[msg.sender] -= amount
    send(msg.sender, amount)

@external
def set_owner(new_owner: address):
    assert msg.sender == self.owner
    self.owner = new_owner

@view
@external
def get_balance() -> uint256:
    return self.balances[msg.sender]
