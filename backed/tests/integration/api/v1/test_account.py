"""
平台账号接口集成测试（直连真实 MySQL）

路径：/api/v1/account
说明：
- 主键字段：id（类型 int）
- 本表无软删字段，DELETE 为硬删除；删除后详情应 404，库中记录应不存在。
- 状态字段走 PATCH /{pk}/status；通用 PUT 不得携带状态字段（期望 422）。

【覆盖策略】文件已存在则 skill 跳过（人手维护）。
"""

import uuid

import httpx
import pytest
from sqlalchemy import select

from core import database
from models.account import Account



def _new_name() -> str:
    """生成测试用唯一 name，避免多次运行冲突"""
    
    value = f"skill_name_" + uuid.uuid4().hex[:8]
    
    return value[:50]
    
    



async def _db_row(pk: int) -> Account | None:
    async with database.AsyncSessionLocal() as s:
        return (
            await s.execute(
                select(Account).where(Account.id == pk)
            )
        ).scalar_one_or_none()


@pytest.mark.asyncio
async def test_account_crud_flow(app):
    """基础 CRUD 集成测试（真实 MySQL）"""
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": "Bearer test-token"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # --- 生成 Create 请求体：按表字段填写；唯一字段请用 _new_*() ---
        payload = {
            
            "platform": 'juejin',
            
            "name": _new_name(),
            
            "profile_dir": 'data/profiles/juejin_default',
            
        }

        # 1) 创建
        resp = await client.post("/api/v1/account", json=payload, headers=headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        pk = data["id"]

        row = await _db_row(pk)
        assert row is not None, "创建后未在真实 account 表中找到记录"
        

        # 2) 列表
        resp = await client.get(
            "/api/v1/account",
            params={"page": 1, "page_size": 10},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["meta"]["total"] >= 1

        # 3) 详情
        resp = await client.get(f"/api/v1/account/{pk}", headers=headers)
        assert resp.status_code == 200, resp.text

        # 4) 更新（不含状态/标识位字段）
        update_payload = {
            
            "platform": 'juejin',
            
            "name": _new_name(),
            
            "profile_dir": 'data/profiles/juejin_default',
            
        }
        resp = await client.put(
            f"/api/v1/account/{pk}",
            json=update_payload,
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

        
        # 4b) PUT 携带状态字段应被 Schema 拒绝
        resp = await client.put(
            f"/api/v1/account/{pk}",
            json={
                
                "status": 'failed',
                
            },
            headers=headers,
        )
        assert resp.status_code == 422, resp.text

        # 5) 专用改状态
        resp = await client.patch(
            f"/api/v1/account/{pk}/status",
            json={
                
                "status": 'failed',
                
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        
        assert resp.json()["data"]["status"] == 'failed'
        

        resp = await client.patch(
            f"/api/v1/account/{pk}/status",
            json={
                
                "status": 'ok',
                
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        

        # 删除
        resp = await client.delete(f"/api/v1/account/{pk}", headers=headers)
        assert resp.status_code == 200, resp.text

        resp = await client.get(f"/api/v1/account/{pk}", headers=headers)
        assert resp.status_code == 404, resp.text

        row = await _db_row(pk)
        
        assert row is None, "硬删除后记录应不在 account 表中"
        


# ===========================================================================
# 商业逻辑接口测试占位（后续业务 API 在此补充；默认 skip）
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.skip(reason="占位：补齐商业逻辑接口测试后移除 skip")
async def test_account_business_api_placeholder(app):
    """
    占位：商业逻辑接口集成测试

    在 Service/Resource 增加非基础 CRUD 业务接口后，在此补充真实请求断言。
    """
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": "Bearer test-token"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # resp = await client.post("/api/v1/account/...", json={...}, headers=headers)
        # assert resp.status_code == 200, resp.text
        assert False, "请实现商业逻辑接口集成测试"
