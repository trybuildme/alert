"""ALERT real-time hazard intelligence package.

The earthquake module is the first citizen; floods, typhoons,
landslides, volcanic activity etc. should reuse:
  - base.HazardEvent      normalized event model
  - base.HazardProvider   provider abstraction
  - base.EventBus         in-process asyncio pub/sub for SSE delivery
  - store.py              SQLite persistence pattern
  - alerts.py             rule engine + dispatcher abstraction
"""
