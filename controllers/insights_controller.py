from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db, get_db_vector, get_optional_db_oip
from services import InsightsService

router = APIRouter()


@router.get("/sales-force")
async def get_salesforce_insights(
    vector_db: Session = Depends(get_db_vector),
    sf_exec_db: Session = Depends(get_db),
):
    insights_service = InsightsService()
    return await insights_service.get_salesforce_insights(vector_db, sf_exec_db)


@router.get("/oip")
async def get_oip_insights(
    vector_db: Session = Depends(get_db_vector),
    oip_exec_db: Session | None = Depends(get_optional_db_oip),
):
    insights_service = InsightsService()
    return await insights_service.get_oip_insights(vector_db, oip_exec_db)


@router.get("/sales-force/charts")
async def get_salesforce_charts(
    vector_db: Session = Depends(get_db_vector),
    sf_exec_db: Session = Depends(get_db),
):
    insights_service = InsightsService()
    return await insights_service.get_salesforce_charts(vector_db, sf_exec_db)


@router.get("/oip/charts")
async def get_oip_charts(
    vector_db: Session = Depends(get_db_vector),
    oip_exec_db: Session | None = Depends(get_optional_db_oip),
):
    insights_service = InsightsService()
    return await insights_service.get_oip_charts(vector_db, oip_exec_db)
