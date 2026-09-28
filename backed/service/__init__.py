"""
Service包（业务逻辑层）

分层约定：
- api/Resource ：只依赖 Service
- service/    ：单条委托 Repository；列表/状态等业务写在本层（已存在则 skill 跳过）
- repository/ ：仅单条 create / delete / update / get（增删改查顺序，可覆盖）
"""
