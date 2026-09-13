\# OpenMagpie connector contract



\## durable commit interface



The connector must implement:



```python

CommitCallback = Callable\[\[NormalizedPostRecord], Awaitable\[bool]]

