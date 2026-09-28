"""临时冒烟测试：启动应用并跑通 article 基础 CRUD。"""
import os

os.environ["FASTAPI_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/smoke_hub.db"
os.environ["CACHE_ENABLED"] = "false"

from fastapi.testclient import TestClient
from app.factory import create_app

app = create_app()

with TestClient(app) as client:
    r = client.get("/api/v1/article")
    print("list", r.status_code, r.json()["meta"]["total"])

    r = client.post("/api/v1/article", json={"title": "t", "content_md": "c"})
    print("create", r.status_code)
    aid = r.json()["data"]["id"]

    r = client.get(f"/api/v1/article/{aid}")
    print("detail", r.status_code)

    r = client.put(f"/api/v1/article/{aid}", json={"title": "t2"})
    print("update", r.status_code)

    r = client.patch(f"/api/v1/article/{aid}/status", json={"status": "published"})
    print("status", r.status_code, r.json()["data"]["status"])

    r = client.delete(f"/api/v1/article/{aid}")
    print("delete", r.status_code)

    r = client.get(f"/api/v1/article/{aid}")
    print("detail-after-delete", r.status_code)
print("SMOKE OK")
