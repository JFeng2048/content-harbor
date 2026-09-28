"""应用入口文件"""

import uvicorn

from config import settings
from app import create_app

# 创建应用实例
app = create_app()



if __name__ == "__main__":
    uvicorn.run(
        "start:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
