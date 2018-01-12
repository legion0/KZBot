* Trailing stop loss, raise stop loss when price rises, do not lower stop loss when price drops, e.g. trail at 10% below price.
* Rewrite the worker to place a limit (maker?) instead of a market bid and cancel / place bids based on the closest target for the pair.
* Rewrite the worker to use streams instead of polling.
* Order history (canceled / filled)
* Add pretty graphs with matplotlib of bar chart of orders and current price.

