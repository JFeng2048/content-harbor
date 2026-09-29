"""
平台账号API路由

此文件由 SQL-to-FastAPI-Scaffold 自动生成。

约定：
- HTTP 层统一只依赖 Service，不直接依赖 Repository。
- 默认要求登录（get_current_active_user）；公开接口请显式去掉该 Depends。
- 字段校验由 Schema 在进入端点前完成。
- 状态/标识位字段通过 PATCH /{id}/status 专用修改。
"""

from fastapi import APIRouter, Depends, Path, Query, status

from core.permissions import get_current_active_user
from service import get_account_service
from service.account_service import AccountService
from schemas.account import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    
    AccountStatusUpdate,
    
)
from schemas.response import (
    SuccessResponse,
    PaginationResponse,
    success_response,
    paginated_response,
)
from utils.custom_exceptions import handle_service_exceptions


router = APIRouter(prefix="/account", tags=["平台账号管理"])


@router.get(
    "",
    response_model=PaginationResponse[AccountResponse],
    status_code=status.HTTP_200_OK,
    summary="获取平台账号列表",
)
@handle_service_exceptions
async def get_account_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    _user=Depends(get_current_active_user),
    service: AccountService = Depends(get_account_service),
):
    """获取平台账号分页列表"""
    result = await service.get_list(page=page, size=page_size)
    return paginated_response(
        items=result["items"],
        total=result["total"],
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{id}",
    response_model=SuccessResponse[AccountResponse],
    status_code=status.HTTP_200_OK,
    summary="获取平台账号详情",
)
@handle_service_exceptions
async def get_account_detail(
    id: int = Path(..., description="主键ID"),
    _user=Depends(get_current_active_user),
    service: AccountService = Depends(get_account_service),
):
    """获取平台账号详情"""
    result = await service.get_detail(id)
    return success_response(result)


@router.post(
    "",
    response_model=SuccessResponse[AccountResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建平台账号",
)
@handle_service_exceptions
async def create_account(
    data: AccountCreate,
    _user=Depends(get_current_active_user),
    service: AccountService = Depends(get_account_service),
):
    """创建平台账号"""
    result = await service.create(data)
    return success_response(result, message="平台账号创建成功")


@router.put(
    "/{id}",
    response_model=SuccessResponse[AccountResponse],
    summary="更新平台账号",
)
@handle_service_exceptions
async def update_account(
    id: int = Path(..., description="主键ID"),
    data: AccountUpdate = ...,
    _user=Depends(get_current_active_user),
    service: AccountService = Depends(get_account_service),
):
    """更新平台账号（不含状态/标识位字段）"""
    result = await service.update(id, data)
    return success_response(result, message="平台账号更新成功")



@router.patch(
    "/{id}/status",
    response_model=SuccessResponse[AccountResponse],
    summary="修改平台账号状态/标识位",
)
@handle_service_exceptions
async def update_account_status(
    id: int = Path(..., description="主键ID"),
    data: AccountStatusUpdate = ...,
    _user=Depends(get_current_active_user),
    service: AccountService = Depends(get_account_service),
):
    """
    专用修改状态/标识位：status
    """
    result = await service.update_status(id, data)
    return success_response(result, message="平台账号状态更新成功")



@router.delete(
    "/{id}",
    response_model=SuccessResponse[None],
    summary="删除平台账号",
)
@handle_service_exceptions
async def delete_account(
    id: int = Path(..., description="主键ID"),
    _user=Depends(get_current_active_user),
    service: AccountService = Depends(get_account_service),
):
    """删除平台账号"""
    await service.delete(id)
    return success_response(None, message="平台账号删除成功")
