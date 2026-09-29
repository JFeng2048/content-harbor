"""
统一任务API路由

此文件由 SQL-to-FastAPI-Scaffold 自动生成。

约定：
- HTTP 层统一只依赖 Service，不直接依赖 Repository。
- 默认要求登录（get_current_active_user）；公开接口请显式去掉该 Depends。
- 字段校验由 Schema 在进入端点前完成。
- 状态/标识位字段通过 PATCH /{id}/status 专用修改。
"""

from fastapi import APIRouter, Depends, Path, Query, status

from core.permissions import get_current_active_user
from service import get_task_service
from service.task_service import TaskService
from schemas.task import (
    TaskCreate,
    TaskUpdate,
    TaskResponse,
    
    TaskStatusUpdate,
    
)
from schemas.response import (
    SuccessResponse,
    PaginationResponse,
    success_response,
    paginated_response,
)
from utils.custom_exceptions import handle_service_exceptions


router = APIRouter(prefix="/task", tags=["统一任务管理"])


@router.get(
    "",
    response_model=PaginationResponse[TaskResponse],
    status_code=status.HTTP_200_OK,
    summary="获取统一任务列表",
)
@handle_service_exceptions
async def get_task_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    _user=Depends(get_current_active_user),
    service: TaskService = Depends(get_task_service),
):
    """获取统一任务分页列表"""
    result = await service.get_list(page=page, size=page_size)
    return paginated_response(
        items=result["items"],
        total=result["total"],
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{id}",
    response_model=SuccessResponse[TaskResponse],
    status_code=status.HTTP_200_OK,
    summary="获取统一任务详情",
)
@handle_service_exceptions
async def get_task_detail(
    id: int = Path(..., description="主键ID"),
    _user=Depends(get_current_active_user),
    service: TaskService = Depends(get_task_service),
):
    """获取统一任务详情"""
    result = await service.get_detail(id)
    return success_response(result)


@router.post(
    "",
    response_model=SuccessResponse[TaskResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建统一任务",
)
@handle_service_exceptions
async def create_task(
    data: TaskCreate,
    _user=Depends(get_current_active_user),
    service: TaskService = Depends(get_task_service),
):
    """创建统一任务"""
    result = await service.create(data)
    return success_response(result, message="统一任务创建成功")


@router.put(
    "/{id}",
    response_model=SuccessResponse[TaskResponse],
    summary="更新统一任务",
)
@handle_service_exceptions
async def update_task(
    id: int = Path(..., description="主键ID"),
    data: TaskUpdate = ...,
    _user=Depends(get_current_active_user),
    service: TaskService = Depends(get_task_service),
):
    """更新统一任务（不含状态/标识位字段）"""
    result = await service.update(id, data)
    return success_response(result, message="统一任务更新成功")



@router.patch(
    "/{id}/status",
    response_model=SuccessResponse[TaskResponse],
    summary="修改统一任务状态/标识位",
)
@handle_service_exceptions
async def update_task_status(
    id: int = Path(..., description="主键ID"),
    data: TaskStatusUpdate = ...,
    _user=Depends(get_current_active_user),
    service: TaskService = Depends(get_task_service),
):
    """
    专用修改状态/标识位：status
    """
    result = await service.update_status(id, data)
    return success_response(result, message="统一任务状态更新成功")



@router.delete(
    "/{id}",
    response_model=SuccessResponse[None],
    summary="删除统一任务",
)
@handle_service_exceptions
async def delete_task(
    id: int = Path(..., description="主键ID"),
    _user=Depends(get_current_active_user),
    service: TaskService = Depends(get_task_service),
):
    """删除统一任务"""
    await service.delete(id)
    return success_response(None, message="统一任务删除成功")
