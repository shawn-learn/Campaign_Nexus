from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.campaign.deps import CampaignContext, require_campaign_role
from app.modules.campaign.models import Campaign
from app.modules.equipment import service as equipment_service
from app.modules.merchant import service
from app.modules.merchant.schemas import (
    MerchantCreate,
    MerchantOut,
    MerchantUpdate,
    PurchaseIn,
    PurchaseResult,
    SellbackIn,
    SellbackResult,
    StockLineCreate,
    StockLineOut,
    StockLineUpdate,
)

Viewer = Depends(require_campaign_role("viewer"))
Editor = Depends(require_campaign_role("editor"))

router = APIRouter(prefix="/api/v1/campaigns/{campaign_id}/merchants", tags=["merchants"])


def _campaign(session: Session, campaign_id: str) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return campaign


def _404(exc: Exception, what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc) or f"{what} not found")


def _422(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("", response_model=list[MerchantOut])
def list_merchants(
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer,
) -> list[MerchantOut]:
    return service.list_merchants(session, ctx.campaign_id)


@router.post("", response_model=MerchantOut, status_code=status.HTTP_201_CREATED)
def create_merchant(
    body: MerchantCreate,
    session: Session = Depends(get_session), ctx: CampaignContext = Editor,
) -> MerchantOut:
    try:
        return service.create_merchant(
            session, _campaign(session, ctx.campaign_id), body, created_by=ctx.user_id
        )
    except service.MerchantError as exc:
        raise _422(exc) from exc


@router.get("/{merchant_id}", response_model=MerchantOut)
def get_merchant(
    merchant_id: str,
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer,
) -> MerchantOut:
    try:
        return service.get_merchant(session, ctx.campaign_id, merchant_id)
    except service.MerchantNotFound as exc:
        raise _404(exc, "merchant") from exc


@router.patch("/{merchant_id}", response_model=MerchantOut)
def update_merchant(
    merchant_id: str, body: MerchantUpdate,
    session: Session = Depends(get_session), ctx: CampaignContext = Editor,
) -> MerchantOut:
    try:
        return service.update_merchant(session, ctx.campaign_id, merchant_id, body)
    except service.MerchantNotFound as exc:
        raise _404(exc, "merchant") from exc
    except service.MerchantError as exc:
        raise _422(exc) from exc


@router.delete("/{merchant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_merchant(
    merchant_id: str,
    session: Session = Depends(get_session), ctx: CampaignContext = Editor,
) -> None:
    try:
        service.delete_merchant(session, ctx.campaign_id, merchant_id, deleted_by=ctx.user_id)
    except service.MerchantNotFound as exc:
        raise _404(exc, "merchant") from exc


# -- stock --------------------------------------------------------------------

@router.get("/{merchant_id}/stock", response_model=list[StockLineOut])
def list_stock(
    merchant_id: str,
    session: Session = Depends(get_session), ctx: CampaignContext = Viewer,
) -> list[StockLineOut]:
    try:
        return service.list_stock(session, ctx.campaign_id, merchant_id)
    except service.MerchantNotFound as exc:
        raise _404(exc, "merchant") from exc


@router.post("/{merchant_id}/stock", response_model=StockLineOut, status_code=status.HTTP_201_CREATED)
def add_stock(
    merchant_id: str, body: StockLineCreate,
    session: Session = Depends(get_session), ctx: CampaignContext = Editor,
) -> StockLineOut:
    try:
        return service.add_stock(
            session, _campaign(session, ctx.campaign_id), merchant_id, body
        )
    except service.MerchantNotFound as exc:
        raise _404(exc, "merchant") from exc
    except service.MerchantError as exc:
        raise _422(exc) from exc


@router.patch("/{merchant_id}/stock/{line_id}", response_model=StockLineOut)
def update_stock(
    merchant_id: str, line_id: str, body: StockLineUpdate,
    session: Session = Depends(get_session), ctx: CampaignContext = Editor,
) -> StockLineOut:
    try:
        return service.update_stock(session, ctx.campaign_id, line_id, body)
    except service.StockNotFound as exc:
        raise _404(exc, "stock line") from exc
    except service.MerchantError as exc:
        raise _422(exc) from exc


@router.delete("/{merchant_id}/stock/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_stock(
    merchant_id: str, line_id: str,
    session: Session = Depends(get_session), ctx: CampaignContext = Editor,
) -> None:
    try:
        service.remove_stock(session, ctx.campaign_id, line_id)
    except service.StockNotFound as exc:
        raise _404(exc, "stock line") from exc


# -- transactions -------------------------------------------------------------

@router.post("/{merchant_id}/stock/{line_id}/buy", response_model=PurchaseResult)
def buy(
    merchant_id: str, line_id: str, body: PurchaseIn,
    session: Session = Depends(get_session), ctx: CampaignContext = Editor,
) -> PurchaseResult:
    try:
        return service.purchase(
            session, _campaign(session, ctx.campaign_id), merchant_id, line_id, body,
            created_by=ctx.user_id,
        )
    except (service.MerchantNotFound, service.StockNotFound) as exc:
        raise _404(exc, "merchant") from exc
    except service.MerchantError as exc:
        raise _422(exc) from exc


@router.post("/{merchant_id}/sell", response_model=SellbackResult)
def sell(
    merchant_id: str, body: SellbackIn,
    session: Session = Depends(get_session), ctx: CampaignContext = Editor,
) -> SellbackResult:
    try:
        return service.sellback(
            session, _campaign(session, ctx.campaign_id), merchant_id, body
        )
    except service.MerchantNotFound as exc:
        raise _404(exc, "merchant") from exc
    except equipment_service.ItemNotFound as exc:
        raise _404(exc, "item") from exc
    except service.MerchantError as exc:
        raise _422(exc) from exc
