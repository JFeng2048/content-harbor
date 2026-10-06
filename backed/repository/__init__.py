"""
Repository 包（数据访问层）

Skill 生成的单表仓储放在本目录；可被覆盖生成。
仅提供单条记录的 create / delete / update / get（增删改查顺序）。
列表分页、过滤、状态变更等业务逻辑请写在 service/ 下对应的 *_service.py。
API/Resource 不要直接依赖本目录。
"""
