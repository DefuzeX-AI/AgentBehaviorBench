"""City and weather endpoints ported from the Java controllers."""

import random

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.responses import json_success
from app.db.models import City, CityWeather
from app.db.session import get_db

router = APIRouter()


@router.get("/city/getByProvince")
def get_by_province(pCode: str = Query(...), db: Session = Depends(get_db)):
    """Return cities whose `father` column matches the province code."""

    rows = db.execute(select(City).where(City.father == pCode)).scalars().all()
    return json_success(rows)


@router.get("/city/weather/getByDateAndCity")
def get_weather_by_date_and_city(
    date: str = Query(...),
    cityCode: str = Query(...),
    db: Session = Depends(get_db),
):
    """Return one generated weather row by MMDDHH date and city code."""

    row = db.execute(
        select(CityWeather).where(CityWeather.date == date, CityWeather.city_code == cityCode)
    ).scalars().first()
    return json_success(row)


@router.post("/city/weather/generateWeather")
def generate_weather(cityCode: str = Query(...), db: Session = Depends(get_db)):
    """Regenerate 12 months x 31 days x 24 hours of random weather."""

    db.execute(delete(CityWeather).where(CityWeather.city_code == cityCode))
    # Java uses a simple random integer in [0, 5] for each hourly slot.
    for month in range(1, 13):
        for day in range(1, 32):
            for hour in range(1, 25):
                db.add(
                    CityWeather(
                        city_code=cityCode,
                        date=f"{month:02d}{day:02d}{hour:02d}",
                        weather=random.randint(0, 5),
                    )
                )
    return json_success(True)
